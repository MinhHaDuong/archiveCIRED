"""Importer dans My Library les 13 stubs du recueil avec leurs DOI (ticket 0018).

Les 13 documents « nouveaux » du recueil absents du groupe d'Antonin ont été
résolus via Crossref/OpenAlex/HAL (`resolve_stubs.py`). Onze ont un DOI, deux
sont de la littérature grise sans DOI. Ce script crée une notice Zotero par
document :

  - DOI connu  → métadonnées **propres récupérées sur Crossref par DOI**
                 (titre, auteurs, revue, volume/numéro/pages, année), type
                 journalArticle / bookSection selon Crossref.
  - sans DOI   → notice `report` honnête, titre lisible, marquée `à-vérifier`.

Chaque notice porte l'**URL inari existante** du PDF (bucket numérisation) — pas
de téléversement. Tag `recueil-50ans-ajout-0018` pour retrouver le lot. Les
notices ne sont **pas** rangées dans la collection `VPDB49CK` (miroir audité des
131 ; on ne la touche pas).

Dry-run par défaut ; `--apply` crée réellement (POST) et écrit les clés créées
(réversible par suppression). Idempotent : un DOI déjà présent dans My Library
est sauté.
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz  # noqa: E402
import verify_recueil_mirror as vm  # noqa: E402

logger = logging.getLogger("import_stubs")

DEFAULT_NEW_DOCS = Path("outputs/recueil_new_docs.json")
DEFAULT_CREATED = Path("outputs/recueil_stubs_created.json")
INARI_ROOT = "https://inari.centre-cired.fr/kCj0pHP0-CIRED_numerisation/zotero/www/"
TAG = "recueil-50ans-ajout-0018"

# Résolution curatée depuis outputs/resolve_stubs_report.md (revue humaine 0018).
# 11 DOI confirmés (Crossref, 8 corroborés HAL) ; 2 grise sans DOI.
RESOLVED: dict[str, dict] = {
    "2001-197": {"doi": "10.3763/cpol.2001.0125"},
    "2007-136": {"doi": "10.1007/s10584-006-9161-z"},
    "2007-172": {"doi": "10.1016/j.ecolecon.2006.05.011"},
    "2008-143": {"doi": "10.1016/j.jebo.2007.05.001"},
    "2008-207": {"doi": "10.7551/mitpress/9780262073028.003.0005"},
    "2010-150": {"doi": "10.1016/j.enpol.2010.05.005"},
    "2010-151": {"doi": "10.1504/ijgenvi.2010.030566"},
    "2010-152": {"doi": "10.1007/s10584-010-9868-8"},
    "2011-175": {"doi": "10.1080/14693062.2011.605702"},
    "2011-210": {"doi": "10.1007/s10784-012-9169-y"},
    "2012-212": {"doi": "10.1016/j.enpol.2012.06.005"},
    "2007-138": {"doi": None, "itemType": "report",
                 "title": "Differentiation and dynamics of EU ETS industrial "
                          "competitiveness impacts",
                 "date": "2007", "extra": "Climate Strategies Report"},
    "2013-162": {"doi": None, "itemType": "report",
                 "title": "Effet net sur l'emploi de la transition énergétique "
                          "en France : une analyse input-output du scénario négaWatt",
                 "institution": "CIRED", "date": "2013",
                 "extra": "Working Paper CIRED"},
}

_CR_TYPE = {"journal-article": "journalArticle", "book-chapter": "bookSection",
            "book-section": "bookSection", "proceedings-article": "conferencePaper",
            "report": "report", "monograph": "book", "book": "book"}


# --- pur ---------------------------------------------------------------------

def file_id(filename: str) -> str | None:
    """Id `YYYY-NNN` zéro-paddé depuis un nom de fichier, ou None."""
    m = re.match(r"(\d{4})[ _-](\d+)", os.path.basename(filename))
    return f"{m.group(1)}-{int(m.group(2)):03d}" if m else None


def inari_url(relpath: str) -> str:
    """URL inari du PDF depuis le chemin relatif d'archive (bucket numérisation)."""
    return INARI_ROOT + urllib.parse.quote(relpath)


def crossref_to_item(msg: dict, url: str, tags: list[str]) -> dict:
    """Notice Zotero (sans key/version) depuis un `message` Crossref + URL inari."""
    itype = _CR_TYPE.get(msg.get("type", ""), "journalArticle")
    creators = []
    for a in msg.get("author", []):
        if a.get("family"):
            creators.append({"creatorType": "author", "lastName": a["family"],
                             "firstName": a.get("given", "")})
        elif a.get("name"):
            creators.append({"creatorType": "author", "name": a["name"]})
    year = str((msg.get("issued", {}).get("date-parts", [[None]]) or [[None]])[0][0] or "")
    container = (msg.get("container-title") or [""])[0]
    item = {
        "itemType": itype,
        "title": (msg.get("title") or [""])[0],
        "creators": creators,
        "date": year,
        "DOI": msg.get("DOI", ""),
        "url": url,
        "volume": msg.get("volume", ""),
        "issue": msg.get("issue", ""),
        "pages": msg.get("page", ""),
        "language": msg.get("language", ""),
        "tags": [{"tag": t} for t in tags],
    }
    if itype == "bookSection":
        item["bookTitle"] = container
        item["publisher"] = (msg.get("publisher") or "")
    else:
        item["publicationTitle"] = container
    return {k: v for k, v in item.items() if v not in ("", [], None)}


def grey_item(spec: dict, url: str, tags: list[str]) -> dict:
    """Notice `report` honnête pour un document sans DOI, marquée à-vérifier."""
    item = {
        "itemType": spec.get("itemType", "report"),
        "title": spec["title"],
        "date": spec.get("date", ""),
        "url": url,
        "extra": spec.get("extra", ""),
        "tags": [{"tag": t} for t in tags] + [{"tag": "à-vérifier"}],
    }
    if spec.get("institution"):
        item["institution"] = spec["institution"]
    return {k: v for k, v in item.items() if v not in ("", [], None)}


def existing_dois(lib_items: list[dict]) -> set[str]:
    """DOI (minuscule) déjà présents dans My Library."""
    out = set()
    for it in lib_items:
        d = (it.get("data", it).get("DOI") or "").strip().lower()
        if d:
            out.add(d)
    return out


def existing_urls(lib_items: list[dict]) -> set[str]:
    """URL déjà présentes dans My Library (dédup des notices sans DOI)."""
    out = set()
    for it in lib_items:
        u = (it.get("data", it).get("url") or "").strip()
        if u:
            out.add(u)
    return out


# --- réseau ------------------------------------------------------------------

def fetch_crossref_work(doi: str) -> dict:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={
        "User-Agent": "archiveCIRED/1.0 (mailto:minh.haduong@gmail.com)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["message"]


def _post_items(uid: str, items: list[dict], api_key: str) -> dict:
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items", data=json.dumps(items).encode(),
        method="POST",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


# --- planification ------------------------------------------------------------

def plan_items(new_docs: list[dict], skip_dois: set[str],
               skip_urls: set[str] | None = None) -> list[dict]:
    """Notices à créer pour les 13 stubs (DOI → Crossref, sinon report).

    Retourne une liste de {id, doi, item, url} ; saute un DOI ou une URL déjà
    présents dans My Library (idempotent).
    """
    skip_urls = skip_urls or set()
    by_id = {file_id(d["fichier"]): d for d in new_docs}
    plan = []
    for sid, spec in RESOLVED.items():
        doc = by_id.get(sid)
        if not doc:
            logger.warning("  stub %s introuvable dans new_docs", sid)
            continue
        url = inari_url(doc["fichier"])
        doi = spec.get("doi")
        if doi and doi.lower() in skip_dois:
            logger.info("  %s déjà présent (DOI %s) — sauté", sid, doi)
            continue
        if url in skip_urls:
            logger.info("  %s déjà présent (URL inari) — sauté", sid)
            continue
        if doi:
            msg = fetch_crossref_work(doi)
            item = crossref_to_item(msg, url, [TAG])
        else:
            item = grey_item(spec, url, [TAG])
        plan.append({"id": sid, "doi": doi, "url": url, "item": item})
    return plan


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--new-docs", type=Path, default=DEFAULT_NEW_DOCS)
    p.add_argument("--env", type=Path, default=rz.DEFAULT_ENV)
    p.add_argument("--created", type=Path, default=DEFAULT_CREATED,
                   help="fichier des clés créées (artefact d'annulation)")
    p.add_argument("--apply", action="store_true", help="crée réellement (POST)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    new_docs = json.loads(args.new_docs.read_text())["nouveau"]
    env = rz.load_env(args.env)
    api_key = env["ZOTERO_API_KEY"]
    uid = rz.fetch_user_id(api_key)

    lib = vm._fetch_all_items(f"users/{uid}", api_key)
    plan = plan_items(new_docs, existing_dois(lib))

    logger.info("Notices à créer : %d", len(plan))
    for e in plan:
        it = e["item"]
        logger.info("  [%s] %s — %s", it["itemType"], (it["title"] or "")[:60],
                    e["doi"] or "sans DOI")

    if not args.apply:
        logger.info("\nDRY-RUN — rien créé. Ajouter --apply pour créer.")
        return 0

    res = _post_items(uid, [e["item"] for e in plan], api_key)
    created = {i: o["key"] for i, o in res.get("successful", {}).items()}
    failed = res.get("failed", {})
    args.created.write_text(json.dumps(res, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    logger.info("Créées : %d | échecs : %d | clés dans %s",
                len(created), len(failed), args.created)
    if failed:
        logger.error("ÉCHECS : %s", json.dumps(failed, ensure_ascii=False)[:300])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
