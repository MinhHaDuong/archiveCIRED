"""Enrichir les notices du catalogue via HAL (ticket 0022) — phase rapport.

Pour chaque notice : interroger HAL (titre + auteur), apparier le résultat avec
**corroboration** (Jaccard du titre + recoupement d'auteur + année à ±1 — jamais
le seul containment du titre, cf. leçon 0019), puis proposer le `halId` et les
champs que HAL renseigne et que la notice n'a pas (revue, volume, numéro, pages,
DOI, date).

Lecture seule : produit un rapport JSON + Markdown. L'écriture se fait ensuite,
après revue humaine, via `apply_corrections.py`. Ce script ne touche pas Zotero.
"""

import argparse
import json
import logging
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("enrich_hal")

DEFAULT_OUTPUT = Path("outputs/enrich_hal_report.json")
HAL_API = "https://api.archives-ouvertes.fr/search/"
HAL_FIELDS = ("title_s", "authLastName_s", "journalTitle_s", "volume_s",
              "issue_s", "page_s", "producedDateY_i", "doiId_s", "halId_s",
              "docType_s")
# champ notice (Zotero) ← champ HAL
FIELD_MAP = {"publicationTitle": "journalTitle", "volume": "volume",
             "issue": "issue", "pages": "page", "DOI": "doi", "date": "year"}
_STOP = {"the", "a", "an", "of", "for", "and", "in", "on", "to", "de", "la",
         "le", "les", "des", "du", "un", "une", "et", "pour", "dans", "sur"}


# --- normalisation / appariement (pur) ---------------------------------------

def norm_tokens(s: str | None) -> set[str]:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return {t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
            if len(t) > 1 and t not in _STOP}


def jaccard(a: str, b: str) -> float:
    A, B = norm_tokens(a), norm_tokens(b)
    return len(A & B) / len(A | B) if (A | B) else 0.0


def lastnames(creators: list[dict] | None) -> set[str]:
    out = set()
    for c in creators or []:
        n = c.get("lastName") or c.get("name") or ""
        # dernier mot pour les `name` corporatifs/composés
        tok = norm_tokens(n)
        if tok:
            out |= tok
    return out


def year_of(date: str | None) -> str:
    m = re.search(r"\d{4}", date or "")
    return m.group(0) if m else ""


def match_hal(notice: dict, candidates: list[dict], threshold: float = 0.5) -> dict | None:
    """Meilleur candidat HAL corroboré, ou None.

    Corroboration exigée : Jaccard(titre) ≥ threshold ET ≥1 auteur commun ET
    (année identique à ±1 ou absente d'un côté).
    """
    n_authors = lastnames(notice.get("creators"))
    n_year = year_of(notice.get("date"))
    best = None
    for c in candidates:
        sim = jaccard(notice.get("title", ""), c.get("title", ""))
        if sim < threshold:
            continue
        if not (n_authors & {t for a in c.get("authors", []) for t in norm_tokens(a)}):
            continue
        cy = str(c.get("year") or "")
        if n_year and cy and abs(int(n_year) - int(cy)) > 1:
            continue
        score = (round(sim, 3), )
        if best is None or score > best[0]:
            best = (score, c, sim)
    if not best:
        return None
    return {**best[1], "title_sim": round(best[2], 3)}


def proposed_diff(notice: dict, hal: dict) -> dict:
    """halId + champs que HAL renseigne et que la notice n'a pas (ou diffère).

    Retourne {halId, add:{champ:val}, differ:{champ:(notice,hal)}}.
    """
    add, differ = {}, {}
    for zf, hf in FIELD_MAP.items():
        hv = str(hal.get(hf) or "").strip()
        if not hv:
            continue
        nv = str(notice.get(zf) or "").strip()
        if not nv:
            add[zf] = hv
        elif norm_tokens(nv) != norm_tokens(hv):
            differ[zf] = (nv, hv)
    return {"halId": hal.get("halId", ""), "add": add, "differ": differ}


# --- réseau ------------------------------------------------------------------

def hal_search(title: str, author: str, rows: int = 5) -> list[dict]:
    q = " ".join(norm_tokens(title)) + (f" {author}" if author else "")
    params = {"q": q, "fl": ",".join(HAL_FIELDS), "rows": rows, "wt": "json"}
    url = HAL_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "archiveCIRED/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        docs = json.loads(resp.read().decode()).get("response", {}).get("docs", [])
    out = []
    for d in docs:
        t = d.get("title_s")
        out.append({
            "halId": d.get("halId_s", ""),
            "title": (t[0] if isinstance(t, list) else t) or "",
            "authors": d.get("authLastName_s", []) or [],
            "journalTitle": _first(d.get("journalTitle_s")),
            "volume": _first(d.get("volume_s")), "issue": _first(d.get("issue_s")),
            "page": _first(d.get("page_s")), "doi": _first(d.get("doiId_s")),
            "year": d.get("producedDateY_i"), "docType": d.get("docType_s", "")})
    return out


def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def enrich_one(notice: dict, pause: float, threshold: float) -> dict:
    """Cherche, apparie et propose le diff pour une notice (réseau)."""
    au = sorted(lastnames(notice.get("creators")))
    first_author = au[0] if au else ""
    try:
        cands = hal_search(notice.get("title", ""), first_author)
    except Exception as e:  # réseau/API : marquer en erreur, continuer
        logger.warning("  HAL KO pour %s : %s", notice.get("key"), e)
        time.sleep(pause)
        return {"key": notice.get("key"), "title": notice.get("title", ""),
                "matched": None, "error": str(e)[:80]}
    time.sleep(pause)
    hal = match_hal(notice, cands, threshold)
    res = {"key": notice.get("key"), "title": notice.get("title", ""),
           "matched": None}
    if hal:
        res["matched"] = {"halId": hal["halId"], "title_sim": hal["title_sim"]}
        res["diff"] = proposed_diff(notice, hal)
    return res


# --- rapport -----------------------------------------------------------------

def summarize(results: list[dict]) -> dict:
    matched = [r for r in results if r.get("matched")]
    with_add = [r for r in matched if r.get("diff", {}).get("add")]
    with_halid = [r for r in matched if r["matched"].get("halId")]
    return {"total": len(results), "matched": len(matched),
            "with_halid": len(with_halid), "with_field_adds": len(with_add),
            "unmatched": len(results) - len(matched)}


def render_markdown(results: list[dict], summary: dict) -> str:
    L = ["# Enrichissement HAL — rapport (ticket 0022, revue avant écriture)\n",
         f"- notices traitées : **{summary['total']}**",
         f"- appariées HAL : **{summary['matched']}** "
         f"({100*summary['matched']//max(1,summary['total'])} %)",
         f"- avec halId : **{summary['with_halid']}**",
         f"- avec champs à ajouter : **{summary['with_field_adds']}**",
         f"- non appariées : **{summary['unmatched']}**\n",
         "## Appariées avec propositions\n",
         "| key | sim | halId | champs à ajouter | divergences |",
         "|---|---|---|---|---|"]
    for r in results:
        if not r.get("matched"):
            continue
        d = r.get("diff", {})
        add = ", ".join(f"{k}={v[:18]}" for k, v in d.get("add", {}).items())
        dif = ", ".join(d.get("differ", {}).keys())
        L.append(f"| {r['key']} | {r['matched']['title_sim']} | "
                 f"{r['matched']['halId']} | {add} | {dif} |")
    return "\n".join(L) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=rz.DEFAULT_ENV)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--limit", type=int, default=40, help="taille du lot (0 = tout)")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--stride", type=int, default=1,
                   help="échantillon représentatif : 1 notice sur N (avant --limit)")
    p.add_argument("--types", default="journalArticle,bookSection,conferencePaper",
                   help="itemTypes à traiter (séparés par des virgules)")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--pause", type=float, default=0.4)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    env = rz.load_env(args.env)
    api_key = env["ZOTERO_API_KEY"]
    uid = rz.fetch_user_id(api_key)
    types = set(args.types.split(","))
    notices = [it["data"] for it in rz.fetch_top_items(f"users/{uid}", api_key)
               if it["data"].get("itemType") in types]
    if args.stride > 1:
        notices = notices[args.offset::args.stride]
        args.offset = 0
    batch = notices[args.offset:] if args.limit == 0 else \
        notices[args.offset:args.offset + args.limit]
    logger.info("Notices éligibles : %d | lot traité : %d", len(notices), len(batch))

    results = []
    for i, n in enumerate(batch, 1):
        results.append(enrich_one(n, args.pause, args.threshold))
        if i % 10 == 0:
            logger.info("  %d/%d…", i, len(batch))

    summary = summarize(results)
    args.output.write_text(json.dumps({"summary": summary, "results": results},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_markdown(results, summary),
                                              encoding="utf-8")
    logger.info("Appariées %d/%d · halId %d · champs à ajouter %d · rapport %s",
                summary["matched"], summary["total"], summary["with_halid"],
                summary["with_field_adds"], args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
