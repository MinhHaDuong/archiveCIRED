"""Enrichir les notices My Library (Zotero) via OpenAlex.

Pour chaque notice sans openalexId dans `extra` :
  - Si DOI présent dans la notice : lookup direct par DOI (précis).
  - Sinon : recherche par titre + année (API de recherche OpenAlex).
  - Appariement par score (titre Jaccard + auteur + année), seuil configurable.
  - Diff : openalexId (toujours), DOI (si absent), revue/volume/numéro/pages
    (si absents). Règle sens unique : on n'écrase jamais un champ renseigné.
  - Rapport JSON + Markdown pour revue humaine.
  - Ledger `openalex_corrections.json` compatible `apply_corrections.py`.

Dry-run : ce script ne modifie jamais Zotero. Pour appliquer les corrections :
  uv run python src/apply_corrections.py \\
      --ledger outputs/openalex_corrections.json \\
      --backup outputs/openalex_backup.json --apply
"""

import argparse
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match_untyped as mu  # noqa: E402  normalize, title_match, _notice_lastnames
import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("enrich_openalex")

OA_API = "https://api.openalex.org"
DEFAULT_MAILTO = "minh.haduong@gmail.com"
DEFAULT_THRESHOLD = 0.75
DEFAULT_PAUSE = 0.5   # secondes entre appels (polite pool ≤ 10 req/s)

DEFAULT_ENV = rz.DEFAULT_ENV
DEFAULT_OUTPUT = Path("outputs/openalex_report.json")
DEFAULT_CORRECTIONS = Path("outputs/openalex_corrections.json")

EXTRA_OA_RE = re.compile(r"^OpenAlex:\s*(W\d+).*$", re.MULTILINE)


# ── fonctions pures (testables sans réseau) ───────────────────────────────────

def openalex_id_from_url(url: str | None) -> str | None:
    """Extrait l'id `W…` d'une URL OpenAlex.

    >>> openalex_id_from_url("https://openalex.org/W2741809807")
    'W2741809807'
    >>> openalex_id_from_url(None) is None
    True
    """
    if not url:
        return None
    m = re.search(r"/(W\d+)(?:[?#]|$)", url)
    return m.group(1) if m else None


def doi_normalize(doi: str | None) -> str | None:
    """Normalise un DOI : retire le préfixe URL si présent, retourne None si vide.

    >>> doi_normalize("https://doi.org/10.1038/s41586-018-0377-y")
    '10.1038/s41586-018-0377-y'
    >>> doi_normalize("10.1038/abc")
    '10.1038/abc'
    >>> doi_normalize(None) is None
    True
    >>> doi_normalize("  ") is None
    True
    """
    if not doi:
        return None
    doi = doi.strip()
    if not doi:
        return None
    m = re.match(r"https?://(?:dx\.)?doi\.org/(.+)", doi)
    return m.group(1) if m else doi


def existing_openalex_id(extra: str | None) -> str | None:
    """Extrait l'id OpenAlex déjà présent dans le champ extra Zotero.

    >>> existing_openalex_id("OpenAlex: W2741809807\\nPMID: 123")
    'W2741809807'
    >>> existing_openalex_id("PMID: 123") is None
    True
    >>> existing_openalex_id(None) is None
    True
    """
    if not extra:
        return None
    m = EXTRA_OA_RE.search(extra)
    return m.group(1) if m else None


def extra_with_openalex(extra: str | None, wid: str) -> str:
    """Retourne le champ extra avec l'id OpenAlex ajouté ou mis à jour.

    >>> extra_with_openalex(None, "W123")
    'OpenAlex: W123'
    >>> extra_with_openalex("PMID: 456", "W123")
    'PMID: 456\\nOpenAlex: W123'
    >>> extra_with_openalex("OpenAlex: W000\\nPMID: 456", "W123")
    'OpenAlex: W123\\nPMID: 456'
    """
    new_line = f"OpenAlex: {wid}"
    if not extra:
        return new_line
    if EXTRA_OA_RE.search(extra):
        return EXTRA_OA_RE.sub(new_line, extra)
    return f"{extra.rstrip()}\n{new_line}"


def _year_of(date_str: str | None) -> int | None:
    """Extrait l'année d'une chaîne de date Zotero (YYYY, YYYY-MM, etc.)."""
    if not date_str:
        return None
    m = re.match(r"(\d{4})", str(date_str))
    return int(m.group(1)) if m else None


def _work_lastnames(work: dict) -> set[str]:
    """Noms de famille normalisés des auteurs d'un work OpenAlex brut."""
    names = set()
    for a in work.get("authorships") or []:
        display = (a.get("author") or {}).get("display_name") or ""
        parts = display.split()
        if parts:
            n = mu.normalize(parts[-1])
            tok = n.split()
            if tok:
                names.add(tok[0])
    return names


def parse_work(work: dict) -> dict:
    """Extrait les champs utiles d'un work OpenAlex brut en dict plat."""
    biblio = work.get("biblio") or {}
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    fp, lp = biblio.get("first_page"), biblio.get("last_page")
    pages = f"{fp}–{lp}" if fp and lp else (fp or lp)
    return {
        "id": openalex_id_from_url(work.get("id")),
        "doi": doi_normalize(work.get("doi")),
        "title": work.get("title"),
        "year": work.get("publication_year"),
        "journal": source.get("display_name"),
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "pages": pages,
    }


def score_notice_work(notice_data: dict, raw_work: dict) -> float:
    """Score d'appariement notice Zotero ↔ work OpenAlex, dans [0, 1].

    Même logique que match_untyped.score : titre dominant, auteur + année bonus.
    """
    t = mu.title_match(notice_data.get("title"), raw_work.get("title"))
    if t < 0.2:
        return round(t, 4)
    na = mu._notice_lastnames(notice_data)
    wa = _work_lastnames(raw_work)
    author = 1.0 if (na & wa) else 0.0
    ny = _year_of(notice_data.get("date"))
    wy = raw_work.get("publication_year")
    year = 1.0 if (ny and wy and ny == int(wy)) else 0.0
    return round(min(1.0, t + 0.12 * year + 0.10 * author), 4)


def match_work(notice_data: dict, raw_works: list[dict],
               threshold: float = DEFAULT_THRESHOLD) -> tuple[dict | None, float]:
    """Trouve le meilleur work OpenAlex pour une notice Zotero.

    Retourne (work_brut, score) si score ≥ threshold, sinon (None, meilleur_score).
    """
    best: dict | None = None
    best_score = 0.0
    for w in raw_works:
        s = score_notice_work(notice_data, w)
        if s > best_score:
            best_score, best = s, w
    if best_score >= threshold:
        return best, best_score
    return None, best_score


def diff_notice_work(notice_data: dict, raw_work: dict) -> dict:
    """Champs à corriger dans la notice Zotero d'après le work OpenAlex.

    Règle sens unique : on n'ajoute que ce qui est absent. Exception : `extra`
    est mis à jour pour y insérer l'id OpenAlex sans écraser le contenu existant.
    """
    p = parse_work(raw_work)
    fields: dict = {}

    if p["id"] and not existing_openalex_id(notice_data.get("extra")):
        fields["extra"] = extra_with_openalex(notice_data.get("extra"), p["id"])

    if p["doi"] and not doi_normalize(notice_data.get("DOI")):
        fields["DOI"] = p["doi"]

    if p["journal"] and not (notice_data.get("publicationTitle") or "").strip():
        fields["publicationTitle"] = p["journal"]

    if p["volume"] and not (notice_data.get("volume") or "").strip():
        fields["volume"] = str(p["volume"])

    if p["issue"] and not (notice_data.get("issue") or "").strip():
        fields["issue"] = str(p["issue"])

    if p["pages"] and not (notice_data.get("pages") or "").strip():
        fields["pages"] = str(p["pages"])

    return fields


# ── réseau ────────────────────────────────────────────────────────────────────

class BudgetExhausted(Exception):
    """OpenAlex a épuisé le budget quotidien gratuit (reset à minuit UTC)."""


def _oa_get(url: str, mailto: str) -> dict:
    """GET OpenAlex avec pool poli, retourne JSON.

    Relance sur 429 transitoire (≤ 120 s d'attente, 3 tentatives).
    Lève BudgetExhausted si le budget quotidien est épuisé (Retry-After > 600 s).
    """
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}mailto={urllib.parse.quote(mailto)}"
    req = urllib.request.Request(
        full, headers={"User-Agent": f"archiveCIRED/1.0 (mailto:{mailto})"})
    delay = 10
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                raw_body = e.read().decode(errors="replace")
                try:
                    retry_after = int(e.headers.get("Retry-After") or delay)
                except ValueError:
                    retry_after = delay
                if retry_after > 600:
                    raise BudgetExhausted(
                        f"Budget OpenAlex épuisé — reset dans {retry_after}s "
                        f"(~{retry_after // 3600}h). Relancer après minuit UTC."
                    ) from None
                logger.warning("rate-limit 429, pause %ds… (tentative %d/3; %s)",
                               retry_after, attempt + 1, raw_body[:80])
                time.sleep(retry_after)
                delay = min(delay * 2, 120)
                continue
            raise


def search_by_doi(doi: str, mailto: str) -> dict | None:
    """Lookup direct par DOI. Retourne le work OpenAlex brut ou None si introuvable.

    Propage BudgetExhausted (budget quotidien épuisé).
    """
    enc = urllib.parse.quote(doi, safe="/")
    try:
        return _oa_get(f"{OA_API}/works/https://doi.org/{enc}", mailto)
    except BudgetExhausted:
        raise
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        logger.warning("DOI lookup KO (HTTP %s) : %s", e.code, doi[:40])
        return None


def search_by_title(title: str, year: int | None, mailto: str,
                    per_page: int = 5) -> list[dict]:
    """Recherche OpenAlex par titre, optionnellement filtrée par année.

    Propage BudgetExhausted (budget quotidien épuisé).
    """
    params: dict[str, str] = {"search": title, "per_page": str(per_page)}
    if year:
        params["filter"] = f"publication_year:{year}"
    qs = urllib.parse.urlencode(params)
    try:
        data = _oa_get(f"{OA_API}/works?{qs}", mailto)
        return data.get("results") or []
    except BudgetExhausted:
        raise
    except urllib.error.HTTPError:
        logger.warning("OpenAlex search KO : %s (%s)", title[:50], year)
        return []


# ── orchestration ─────────────────────────────────────────────────────────────

def enrich_notices(notices: list[dict], mailto: str = DEFAULT_MAILTO,
                   threshold: float = DEFAULT_THRESHOLD,
                   pause: float = DEFAULT_PAUSE,
                   skip_keys: set[str] | None = None,
                   checkpoint_path: Path | None = None,
                   checkpoint_every: int = 50) -> dict:
    """Recherche et apparie chaque notice contre OpenAlex.

    `notices` : liste d'items Zotero complets (avec champ `data`) ou de dicts
    notice_of()-compatibles (avec `key`, `title`, `creators`, `date`, `DOI`,
    `extra`, etc. au niveau racine).

    `skip_keys` : clés déjà traitées lors d'une exécution précédente (--resume).
    `checkpoint_path` : si fourni, sauvegarde le rapport partiel tous les
    `checkpoint_every` notices pour permettre une reprise en cas d'interruption.

    Retourne un rapport sérialisable avec résultats, corrections, non-trouvées.
    """
    results: list[dict] = []
    not_matched: list[dict] = []
    skipped: list[str] = []
    errors: list[dict] = []
    done = skip_keys or set()
    n_processed = 0

    for item in notices:
        data = item.get("data") or item
        key = data.get("key") or item.get("key", "")
        title = (data.get("title") or "").strip()

        if key in done:
            continue

        if existing_openalex_id(data.get("extra")):
            skipped.append(key)
            done.add(key)
            continue

        try:
            year = _year_of(data.get("date"))
            doi = doi_normalize(data.get("DOI"))
            raw_works: list[dict] = []
            searched_by = "title"

            if doi:
                logger.info("DOI   %s … (%s)", doi[:30], key)
                w = search_by_doi(doi, mailto)
                time.sleep(pause)
                if w:
                    raw_works = [w]
                    searched_by = "doi"

            if not raw_works and title:
                logger.info("titre %s… (%s)", title[:40], year or "?")
                raw_works = search_by_title(title, year, mailto)
                time.sleep(pause)

            if not raw_works:
                not_matched.append({"key": key, "title": title[:80],
                                    "reason": "no_results"})
            else:
                if searched_by == "doi":
                    best, score = raw_works[0], 1.0
                else:
                    best, score = match_work(data, raw_works, threshold)
                if best is None:
                    not_matched.append({
                        "key": key,
                        "title": title[:80],
                        "reason": "low_score",
                        "best_score": round(score, 4),
                        "best_candidate": (raw_works[0].get("title") or "")[:80],
                    })
                else:
                    set_fields = diff_notice_work(data, best)
                    p = parse_work(best)
                    results.append({
                        "key": key,
                        "ref": title[:80],
                        "searched_by": searched_by,
                        "openalex_id": p["id"],
                        "doi_found": p["doi"],
                        "score": score,
                        "set": set_fields,
                    })
                    logger.info("  → %s (%.2f) corrections: %s",
                                p["id"], score, list(set_fields.keys()) or "aucune")

        except BudgetExhausted as exc:
            logger.error("BUDGET ÉPUISÉ : %s", exc)
            if checkpoint_path:
                _write_checkpoint(checkpoint_path, results, not_matched,
                                  skipped, errors, len(notices))
                logger.info("Checkpoint sauvegardé : %s", checkpoint_path)
            logger.info("Reprendre demain avec : --resume %s", checkpoint_path)
            break

        except Exception as exc:
            logger.error("erreur notice %s : %s", key, exc)
            errors.append({"key": key, "title": title[:80], "error": str(exc)})

        done.add(key)
        n_processed += 1

        if checkpoint_path and n_processed % checkpoint_every == 0:
            _write_checkpoint(checkpoint_path, results, not_matched, skipped,
                              errors, len(notices))
            logger.info("[checkpoint %d/%d]", n_processed, len(notices))

    return {
        "total": len(notices),
        "already_enriched": len(skipped),
        "searched": len(notices) - len(skipped),
        "matched": len(results),
        "not_matched": len(not_matched),
        "errors": len(errors),
        "results": results,
        "not_matched_list": not_matched,
        "error_list": errors,
    }


def _write_checkpoint(path: Path, results: list, not_matched: list,
                      skipped: list, errors: list, total: int) -> None:
    """Écrit un rapport partiel pour permettre la reprise."""
    partial = {
        "total": total,
        "already_enriched": len(skipped),
        "searched": len(results) + len(not_matched) + len(errors),
        "matched": len(results),
        "not_matched": len(not_matched),
        "errors": len(errors),
        "results": results,
        "not_matched_list": not_matched,
        "error_list": errors,
        "_partial": True,
    }
    path.write_text(json.dumps(partial, ensure_ascii=False, indent=2),
                    encoding="utf-8")


# ── rapport Markdown ──────────────────────────────────────────────────────────

def render_markdown(report: dict, threshold: float = DEFAULT_THRESHOLD) -> str:
    lines = [
        "# Enrichissement OpenAlex — rapport\n",
        f"Notices totales : {report['total']} | "
        f"Déjà enrichies : {report['already_enriched']} | "
        f"Recherchées : {report['searched']}\n",
        f"Appariées (≥{threshold}) : {report['matched']} | "
        f"Non appariées : {report['not_matched']}\n",
    ]

    if report["results"]:
        lines += [
            "\n## Correspondances et corrections proposées\n",
            "| Clé | Score | OA id | DOI | Corrections |",
            "|---|---|---|---|---|",
        ]
        for r in report["results"]:
            corr = ", ".join(r["set"].keys()) if r["set"] else "—"
            doi = (r["doi_found"] or "")[:30]
            lines.append(
                f"| {r['key']} | {r['score']:.2f} | "
                f"{r['openalex_id'] or ''} | {doi} | {corr} |"
            )

    if report["not_matched_list"]:
        lines += [
            "\n## Non appariées\n",
            "| Clé | Raison | Score | Meilleur candidat |",
            "|---|---|---|---|",
        ]
        for n in report["not_matched_list"]:
            cand = (n.get("best_candidate") or "")[:60]
            sc = n.get("best_score", "—")
            lines.append(f"| {n['key']} | {n['reason']} | {sc} | {cand} |")

    return "\n".join(lines) + "\n"


# ── collecte Zotero ───────────────────────────────────────────────────────────

def fetch_notices(env_path: Path) -> list[dict]:
    """Collecte toutes les notices top-level de My Library (réseau)."""
    env = rz.load_env(env_path)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {env_path}")
    uid = rz.fetch_user_id(api_key)
    logger.info("My Library uid=%s", uid)
    return rz.fetch_top_items(f"users/{uid}", api_key)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--notices", type=Path, default=None,
                   help="JSON de notices Zotero pré-collectées (hors-ligne)")
    p.add_argument("--resume", type=Path, default=None,
                   help="Rapport partiel d'une exécution précédente à compléter")
    p.add_argument("--mailto", default=DEFAULT_MAILTO,
                   help="email pour le pool poli OpenAlex")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help="seuil de score pour accepter un appariement (défaut 0.75)")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    p.add_argument("--pause", type=float, default=DEFAULT_PAUSE,
                   help="pause (s) entre appels OpenAlex")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.notices:
        notices = json.loads(args.notices.read_text())
        logger.info("Notices chargées : %d (hors-ligne)", len(notices))
    else:
        logger.info("Collecte des notices My Library…")
        notices = fetch_notices(args.env)
        logger.info("Notices collectées : %d", len(notices))

    prev_results: list[dict] = []
    prev_not_matched: list[dict] = []
    prev_already_enriched = 0
    prev_errors = 0
    skip_keys: set[str] = set()
    if args.resume and args.resume.exists():
        prev = json.loads(args.resume.read_text())
        prev_results = prev.get("results", [])
        prev_not_matched = prev.get("not_matched_list", [])
        prev_already_enriched = prev.get("already_enriched", 0)
        prev_errors = prev.get("errors", 0)
        skip_keys = (
            {r["key"] for r in prev_results}
            | {n["key"] for n in prev_not_matched}
            | set(prev.get("error_list") and [e["key"] for e in prev["error_list"]] or [])
        )
        logger.info("Reprise : %d déjà appariés, %d non appariés, %d clés ignorées",
                    len(prev_results), len(prev_not_matched), len(skip_keys))

    report = enrich_notices(notices, args.mailto, args.threshold, args.pause,
                            skip_keys=skip_keys,
                            checkpoint_path=args.output)

    # Fusionner avec les résultats précédents si --resume
    report["results"] = prev_results + report["results"]
    report["not_matched_list"] = prev_not_matched + report["not_matched_list"]
    report["matched"] = len(report["results"])
    report["not_matched"] = len(report["not_matched_list"])
    report["already_enriched"] = prev_already_enriched + report["already_enriched"]
    report["errors"] = prev_errors + report["errors"]
    report["searched"] = report["matched"] + report["not_matched"] + report["errors"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    md_path = args.output.with_suffix(".md")
    md_path.write_text(render_markdown(report, args.threshold), encoding="utf-8")

    ledger = [
        {"key": r["key"], "ref": r["ref"], "set": r["set"], "applied": False}
        for r in report["results"]
        if r["set"]
    ]
    args.corrections.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Rapport : %s (%d appariés, %d corrections)",
                args.output, report["matched"], len(ledger))
    logger.info("Non appariées : %d/%d", report["not_matched"], report["searched"])


if __name__ == "__main__":
    main()
