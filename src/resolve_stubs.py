"""Résoudre les stubs du recueil (ticket 0018) via Crossref, OpenAlex et HAL.

Les 13 documents « nouveaux » du recueil absents du groupe d'Antonin n'ont pour
métadonnée que leur nom de fichier descriptif
(`YYYY-NNN-Auteurs-Titre-Journal.ext`). Ce script interroge trois sources
bibliographiques avec cette chaîne et propose, par source, le meilleur candidat
(DOI / halId + métadonnées) avec un score de confiance, pour **revue humaine**.

Lecture seule : aucune écriture Zotero. Sortie = rapport JSON + Markdown.

Le score est le *taux de couverture du titre candidat par le nom de fichier* :
fraction des mots du titre proposé présents dans la chaîne de requête. Élevé
quand le vrai titre est contenu dans le nom de fichier (le nom contient en plus
les auteurs et le journal, d'où une couverture, pas une égalité).
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

logger = logging.getLogger("resolve_stubs")

DEFAULT_INPUT = Path("outputs/recueil_new_docs.json")
DEFAULT_OUTPUT = Path("outputs/resolve_stubs_report.json")
_STOP = {"the", "a", "an", "of", "for", "and", "in", "on", "to", "de", "la",
         "le", "les", "des", "du", "un", "une", "et", "a", "pour", "dans"}


# --- parsing & scoring (pur) -------------------------------------------------

def norm_tokens(s: str | None) -> set[str]:
    """Jetons alphanumériques pliés ASCII, mots-outils retirés."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return {t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
            if len(t) > 1 and t not in _STOP}


def parse_stub(filename: str) -> dict:
    """`{id, year, query}` depuis un nom de fichier `YYYY-NNN-…descriptif….ext`."""
    base = Path(filename).name
    m = re.match(r"(\d{4})[ _-](\d+)[ _-](.+?)(?:\.\w+)?$", base)
    if not m:
        return {"id": None, "year": None, "query": re.sub(r"\.\w+$", "", base)}
    year, num, rest = m.group(1), m.group(2), m.group(3)
    query = re.sub(r"[-_]+", " ", rest)
    query = re.sub(r"\s+", " ", query).strip()
    return {"id": f"{year}-{int(num):03d}", "year": int(year), "query": query}


def title_coverage(query: str, candidate_title: str) -> float:
    """Fraction des mots du titre candidat présents dans la requête (0..1)."""
    cand = norm_tokens(candidate_title)
    if not cand:
        return 0.0
    return len(cand & norm_tokens(query)) / len(cand)


def best_candidate(query: str, candidates: list[dict]) -> dict | None:
    """Candidat de meilleure couverture de titre (None si liste vide)."""
    scored = [{**c, "score": round(title_coverage(query, c.get("title", "")), 3)}
              for c in candidates]
    return max(scored, key=lambda c: c["score"], default=None)


# --- requêtes réseau ---------------------------------------------------------

def _get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "archiveCIRED/1.0 (reconciliation; mailto:contact@centre-cired.fr)",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def query_crossref(query: str, rows: int = 3, mailto: str | None = None) -> list[dict]:
    p = {"query.bibliographic": query, "rows": rows,
         "select": "DOI,title,author,container-title,issued"}
    if mailto:
        p["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(p)
    out = []
    for it in _get_json(url).get("message", {}).get("items", []):
        issued = it.get("issued", {}).get("date-parts", [[None]])[0][0]
        out.append({
            "source": "crossref", "id": it.get("DOI"),
            "title": (it.get("title") or [""])[0],
            "authors": [f"{a.get('family','')} {a.get('given','')}".strip()
                        for a in it.get("author", [])][:8],
            "journal": (it.get("container-title") or [""])[0], "year": issued})
    return out


def query_openalex(query: str, rows: int = 3, mailto: str | None = None) -> list[dict]:
    p = {"search": query, "per_page": rows}
    if mailto:
        p["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(p)
    out = []
    for w in _get_json(url).get("results", []):
        out.append({
            "source": "openalex", "id": w.get("doi") or w.get("id"),
            "title": w.get("title") or "",
            "authors": [a.get("author", {}).get("display_name", "")
                        for a in w.get("authorships", [])][:8],
            "journal": (w.get("primary_location") or {}).get("source", {}).get("display_name")
            if (w.get("primary_location") or {}).get("source") else "",
            "year": w.get("publication_year")})
    return out


def query_hal(query: str, rows: int = 3) -> list[dict]:
    p = {"q": query, "rows": rows, "wt": "json",
         "fl": "title_s,authFullName_s,doiId_s,halId_s,producedDateY_i,journalTitle_s"}
    url = "https://api.archives-ouvertes.fr/search/?" + urllib.parse.urlencode(p)
    out = []
    for d in _get_json(url).get("response", {}).get("docs", []):
        out.append({
            "source": "hal", "id": d.get("doiId_s") or d.get("halId_s"),
            "hal_id": d.get("halId_s"),
            "title": (d.get("title_s") or [""])[0] if isinstance(d.get("title_s"), list)
            else d.get("title_s", ""),
            "authors": (d.get("authFullName_s") or [])[:8],
            "journal": d.get("journalTitle_s", ""), "year": d.get("producedDateY_i")})
    return out


def resolve_one(stub: dict, mailto: str | None, pause: float) -> dict:
    """Interroge les 3 sources pour un stub et garde le meilleur de chacune."""
    q = stub["query"]
    result = {"id": stub["id"], "year": stub["year"], "query": q, "sources": {}}
    for name, fn in (("crossref", lambda: query_crossref(q, mailto=mailto)),
                     ("openalex", lambda: query_openalex(q, mailto=mailto)),
                     ("hal", lambda: query_hal(q))):
        try:
            result["sources"][name] = best_candidate(q, fn())
        except Exception as e:  # réseau/API : on continue les autres sources
            logger.warning("  %s KO pour %s : %s", name, stub["id"], e)
            result["sources"][name] = None
        time.sleep(pause)
    return result


# --- rapport -----------------------------------------------------------------

def render_markdown(results: list[dict]) -> str:
    lines = ["# Résolution des stubs recueil (Crossref / OpenAlex / HAL)\n",
             f"{len(results)} documents — meilleur candidat par source, score = "
             "couverture du titre candidat par le nom de fichier.\n"]
    for r in results:
        lines.append(f"\n## {r['id']} — `{r['query']}`\n")
        lines.append("| source | score | id/DOI | titre | année |")
        lines.append("|---|---|---|---|---|")
        for src in ("crossref", "openalex", "hal"):
            c = r["sources"].get(src)
            if not c:
                lines.append(f"| {src} | — | — | (rien) | — |")
                continue
            lines.append(f"| {src} | {c.get('score')} | {c.get('id') or ''} | "
                         f"{(c.get('title') or '')[:70]} | {c.get('year') or ''} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                   help="recueil_new_docs.json (clé `nouveau`)")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--paired-group", action="store_true",
                   help="résoudre TOUS les nouveaux, pas seulement les non-appariés")
    p.add_argument("--mailto", default=None,
                   help="email pour le pool poli Crossref/OpenAlex")
    p.add_argument("--pause", type=float, default=1.0,
                   help="pause (s) entre appels API")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    new = json.loads(args.input.read_text())["nouveau"]
    stubs = [parse_stub(d["fichier"]) for d in new]
    logger.info("Stubs à résoudre : %d", len(stubs))

    results = []
    for s in stubs:
        logger.info("  %s …", s["id"])
        results.append(resolve_one(s, args.mailto, args.pause))

    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_markdown(results), encoding="utf-8")
    hits = sum(1 for r in results
               if any((c and c.get("score", 0) >= 0.8) for c in r["sources"].values()))
    logger.info("Rapport : %s", args.output)
    logger.info("Au moins une source ≥0.8 : %d/%d", hits, len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
