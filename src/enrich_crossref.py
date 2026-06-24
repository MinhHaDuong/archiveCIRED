"""Enrichir les notices Zotero My Library via l'API Crossref (DOI + métadonnées).

Pour chaque notice : recherche par titre + auteur, appariement corroboré
(Jaccard titre + auteur/année), diff des champs, rapport JSON + Markdown pour
revue humaine. Produit un ledger compatible avec apply_corrections.py.

Dry-run par défaut — aucune écriture Zotero dans ce script.
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
import match_untyped as mu  # noqa: E402
import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("enrich_crossref")

CROSSREF_API = "https://api.crossref.org/works"
DEFAULT_ENV = rz.DEFAULT_ENV
DEFAULT_CACHE = Path("outputs/crossref_notices_cache.json")
DEFAULT_REPORT = Path("outputs/crossref_enrichment_report.json")
DEFAULT_LEDGER = Path("outputs/crossref_corrections.json")
DEFAULT_MAILTO = "minh.haduong@gmail.com"

THRESHOLD_PROBABLE = 0.75
THRESHOLD_MAYBE = 0.50
REQUEST_DELAY = 0.1  # 10 req/s — bien en dessous du plafond polite pool (50/s)


# ---------- API Crossref -------------------------------------------------------

def search_crossref(title: str, author: str, mailto: str, rows: int = 5) -> list[dict]:
    """Recherche Crossref par titre + auteur. Retourne les items JSON bruts."""
    params = {
        "query.title": title,
        "query.author": author,
        "rows": str(rows),
        "select": "DOI,title,author,container-title,volume,issue,page,published,ISSN,type",
    }
    url = f"{CROSSREF_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"archiveCIRED/1.0 (mailto:{mailto})"}
    )
    delay = 60
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode()).get("message", {}).get("items", [])
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                logger.warning("Crossref rate-limit (429), pause %ds…", delay)
                time.sleep(delay)
                delay *= 2
                continue
            logger.warning("Crossref HTTP %s pour %r", e.code, title[:60])
            return []
        except Exception as exc:
            logger.warning("Crossref erreur %s pour %r", exc, title[:60])
            return []
    return []


def parse_item(item: dict) -> dict:
    """Réduit un item Crossref brut aux champs canoniques."""
    titles = item.get("title") or []
    title = titles[0] if titles else ""

    authors = [
        a.get("family") or a.get("name") or ""
        for a in (item.get("author") or [])
    ]
    authors = [a for a in authors if a]

    pub = item.get("published") or {}
    parts = (pub.get("date-parts") or [[None]])[0]
    year = parts[0] if parts else None

    ct = item.get("container-title") or []
    journal = ct[0] if ct else ""

    issns = item.get("ISSN") or []

    return {
        "doi": item.get("DOI") or "",
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "volume": item.get("volume") or "",
        "issue": item.get("issue") or "",
        "pages": item.get("page") or "",
        "issn": issns[0] if issns else "",
    }


# ---------- appariement -------------------------------------------------------

def _year(notice_data: dict) -> int | None:
    m = re.search(r"\b(\d{4})\b", notice_data.get("date") or "")
    return int(m.group(1)) if m else None


def _lastnames(notice_data: dict) -> set[str]:
    names = set()
    for c in notice_data.get("creators") or []:
        tok = mu.normalize(c.get("lastName") or "").split()
        if tok:
            names.add(tok[0])
    return names


def combined_score(notice_data: dict, parsed: dict) -> float:
    """Score d'appariement notice Zotero ↔ item Crossref, dans [0, 1].

    Le titre (Jaccard+containment de match_untyped) porte le score. Auteur et
    année n'apportent que des bonus additifs, jamais de pénalité.
    """
    t = mu.title_match(notice_data.get("title"), parsed["title"])
    if t < 0.2:
        return round(t, 4)
    year_n = _year(notice_data)
    year_b = 0.12 if (year_n and parsed["year"] and year_n == parsed["year"]) else 0.0
    ln_n = _lastnames(notice_data)
    ln_cr = {mu.normalize(a).split()[0] for a in parsed["authors"] if a} - {""}
    author_b = 0.10 if (ln_n & ln_cr) else 0.0
    return round(min(1.0, t + year_b + author_b), 4)


def best_match(notice_data: dict, items: list[dict]) -> tuple[dict | None, float]:
    """Meilleur item Crossref pour une notice, avec son score combiné."""
    best, best_s = None, 0.0
    for item in items:
        p = parse_item(item)
        s = combined_score(notice_data, p)
        if s > best_s:
            best_s, best = s, p
    return best, best_s


# ---------- diff --------------------------------------------------------------

def diff_fields(notice_data: dict, crossref: dict) -> list[dict]:
    """Champs Crossref différents de la notice (ajout ou modification).

    Jamais d'effacement : si Crossref est vide, le champ est ignoré.
    Un DOI existant est signalé comme 'verification', pas 'modification'.
    """
    diffs = []
    mappings = [
        ("doi", "DOI"),
        ("journal", "publicationTitle"),
        ("volume", "volume"),
        ("issue", "issue"),
        ("pages", "pages"),
        ("issn", "ISSN"),
    ]
    existing_doi = (notice_data.get("DOI") or "").strip()

    for cr_key, z_key in mappings:
        cr_val = str(crossref.get(cr_key) or "").strip()
        z_val = str(notice_data.get(z_key) or "").strip()

        if not cr_val:
            continue
        if " ".join(cr_val.lower().split()) == " ".join(z_val.lower().split()):
            continue

        if z_key == "DOI" and existing_doi:
            kind = "verification"
        else:
            kind = "ajout" if not z_val else "modification"

        diffs.append({
            "champ": z_key,
            "type": kind,
            "valeur_actuelle": z_val,
            "valeur_proposee": cr_val,
        })
    return diffs


# ---------- enrichissement batch ----------------------------------------------

def enrich_notices(notices: list[dict], mailto: str) -> dict:
    """Enrichit toutes les notices via Crossref. Retourne un rapport structuré."""
    probable, incertain, absent, sans_titre = [], [], [], []

    for i, item in enumerate(notices):
        data = item.get("data", {})
        key = data.get("key", "?")
        title = data.get("title") or ""

        if not title:
            sans_titre.append(key)
            continue

        creators = data.get("creators") or []
        author_q = " ".join(
            c.get("lastName") or "" for c in creators[:3]
            if c.get("creatorType") in ("author", None) and c.get("lastName")
        )

        if i > 0:
            time.sleep(REQUEST_DELAY)

        raw = search_crossref(title, author_q, mailto)
        matched, score = best_match(data, raw)

        row = {
            "key": key,
            "title": title,
            "year": _year(data),
            "score": score,
            "match": matched,
            "diffs": diff_fields(data, matched) if matched else [],
        }

        if score >= THRESHOLD_PROBABLE:
            probable.append(row)
        elif score >= THRESHOLD_MAYBE:
            incertain.append(row)
        else:
            absent.append(key)

        if (i + 1) % 50 == 0:
            logger.info("  %d/%d traités…", i + 1, len(notices))

    return {
        "total": len(notices),
        "probable": probable,
        "incertain": incertain,
        "absent": absent,
        "sans_titre": sans_titre,
    }


def to_ledger(report: dict) -> list[dict]:
    """Ledger apply_corrections.py : probable avec diffs ajout/modification."""
    ledger = []
    for row in report["probable"]:
        set_fields = {
            d["champ"]: d["valeur_proposee"]
            for d in row["diffs"]
            if d["type"] in ("ajout", "modification")
        }
        if not set_fields:
            continue
        ledger.append({
            "key": row["key"],
            "ref": f"crossref:{row['match']['doi']}",
            "score": row["score"],
            "set": set_fields,
            "applied": False,
        })
    return ledger


def render_markdown(report: dict) -> str:
    """Rapport lisible Markdown pour revue humaine."""
    lines = [
        "# Enrichissement Crossref — rapport de revue",
        "",
        f"- Notices traitées : **{report['total']}**",
        f"- Appariement probable (≥ {THRESHOLD_PROBABLE}) : **{len(report['probable'])}**",
        f"- Incertain ({THRESHOLD_MAYBE}–{THRESHOLD_PROBABLE}) : "
        f"**{len(report['incertain'])}**",
        f"- Absent (< {THRESHOLD_MAYBE}) : **{len(report['absent'])}**",
        f"- Sans titre (ignoré) : **{len(report['sans_titre'])}**",
        "",
        "## Probable — à valider puis appliquer via apply_corrections.py",
        "",
    ]
    for row in report["probable"]:
        m = row["match"]
        lines.append(f"### `{row['key']}` — {row['title']!r} ({row['year']})")
        lines.append(f"Crossref : {m['title']!r} ({m['year']}) — DOI `{m['doi']}` "
                     f"— score {row['score']:.2f}")
        for d in row["diffs"]:
            lines.append(f"- **{d['champ']}** [{d['type']}] "
                         f"{d['valeur_actuelle']!r} → {d['valeur_proposee']!r}")
        lines.append("")

    if report["incertain"]:
        lines += ["## Incertain — arbitrage humain requis", ""]
        for row in report["incertain"]:
            m = row["match"]
            lines.append(f"- `{row['key']}` {row['title']!r} ({row['year']}) "
                         f"→ score {row['score']:.2f} | {m['title']!r} DOI:{m['doi']}")
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------- collecte notices --------------------------------------------------

def load_notices(env_path: Path, cache: Path | None) -> list[dict]:
    """Notices My Library depuis le cache ou depuis l'API Zotero."""
    if cache and cache.exists():
        notices = json.loads(cache.read_text())
        logger.info("Notices chargées depuis le cache : %d", len(notices))
        return notices
    env = rz.load_env(env_path)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {env_path}")
    uid = rz.fetch_user_id(api_key)
    notices = rz.fetch_top_items(f"users/{uid}", api_key)
    logger.info("Notices collectées depuis Zotero My Library : %d", len(notices))
    if cache:
        cache.write_text(json.dumps(notices, ensure_ascii=False, indent=2))
        logger.info("Notices mises en cache : %s", cache)
    return notices


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--no-cache", action="store_true",
                   help="Ignorer le cache, re-collecter depuis Zotero")
    p.add_argument("--mailto", default=DEFAULT_MAILTO,
                   help="Adresse mail pour le polite pool Crossref")
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    p.add_argument("--limit", type=int, default=None,
                   help="Limiter à N notices (test/débogage)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cache = None if args.no_cache else args.cache
    notices = load_notices(args.env, cache)

    if args.limit:
        notices = notices[: args.limit]
        logger.info("Limité à %d notices (--limit)", args.limit)

    logger.info("Recherche Crossref pour %d notices…", len(notices))
    report = enrich_notices(notices, args.mailto)

    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    args.report.with_suffix(".md").write_text(render_markdown(report))

    ledger = to_ledger(report)
    args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2))

    logger.info("Probable (≥ %.2f) : %d", THRESHOLD_PROBABLE, len(report["probable"]))
    logger.info("Incertain          : %d", len(report["incertain"]))
    logger.info("Absent             : %d", len(report["absent"]))
    logger.info("Sans titre         : %d", len(report["sans_titre"]))
    logger.info("Ledger corrections : %d", len(ledger))
    logger.info("Rapport : %s", args.report)
    logger.info("Ledger  : %s", args.ledger)


if __name__ == "__main__":
    main()
