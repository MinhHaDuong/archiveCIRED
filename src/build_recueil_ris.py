"""Préparer l'ingestion Zotero des docs nouveaux du recueil (ticket 0018).

Les 18 documents *nouveaux* sélectionnés par `select_new_recueil.py` existent
déjà comme notices dans le groupe privé `Recueil_CIRED`, avec les métadonnées
soignées par Antonin (type, titre, auteurs, revue, volume, pages, URL inari).
Plutôt que de reconstruire des métadonnées pauvres depuis les noms de fichiers,
on **apparie chaque nouveau fichier à sa notice de groupe** par le préfixe de
numérotation du recueil (`YYYY-NN`, présent à la fois dans le nom de fichier
local et dans le basename de l'URL inari de la notice), puis on émet un **RIS**
que l'utilisateur revoit et importe (aucune écriture Zotero ici).

La jointure est interne au recueil (sa propre numérotation des deux côtés) :
elle ne dépend pas de la table `YYYY-NN`↔archive qui bloquait 0015.

Fonctions pures testables ; la collecte des notices de groupe utilise la lib
standard via `reconcile_zotero`.
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("build_recueil_ris")

DEFAULT_NEW_DOCS = Path("outputs/recueil_new_docs.json")
DEFAULT_OUTPUT = Path("outputs/recueil_new_docs.ris")
DEFAULT_GROUP_ID = rz.DEFAULT_GROUP_ID
DEFAULT_ENV = rz.DEFAULT_ENV

_PREFIX = re.compile(r"^(\d{4})[-\s]+(\d{1,3})\b")

# Zotero itemType -> RIS reference type.
_RIS_TYPE = {
    "journalArticle": "JOUR", "report": "RPRT", "bookSection": "CHAP",
    "book": "BOOK", "conferencePaper": "CPAPER", "thesis": "THES",
    "magazineArticle": "MGZN", "manuscript": "UNPB", "document": "GEN",
}


def prefix_key(name: str) -> str | None:
    """Clé de numérotation recueil `YYYY-N` (sans zéro-padding), ou None.

    Normalise le séparateur et l'éventuel zéro initial pour que le nom de
    fichier local et le basename d'URL s'apparient.

    >>> prefix_key("1975 15-Hourcade.pdf")
    '1975-15'
    >>> prefix_key("2007-136-Hallegate.pdf")
    '2007-136'
    """
    m = _PREFIX.match(os.path.basename(name))
    return f"{m.group(1)}-{int(m.group(2))}" if m else None


def index_group_by_prefix(notices: list[dict]) -> dict[str, dict]:
    """Indexe les notices de groupe par clé de préfixe, depuis leur URL inari."""
    idx: dict[str, dict] = {}
    for it in notices:
        url = it.get("data", {}).get("url") or ""
        if not url:
            continue
        base = os.path.basename(urllib.parse.urlparse(url).path)
        k = prefix_key(base)
        if k:
            idx.setdefault(k, it["data"])
    return idx


def _ris_authors(creators: list[dict]) -> list[str]:
    """Lignes AU `Nom, Prénom` pour les creators de type auteur."""
    out = []
    for c in creators or []:
        if c.get("creatorType") not in (None, "author"):
            continue
        last, first = c.get("lastName") or "", c.get("firstName") or ""
        name = ", ".join(p for p in (last, first) if p) or c.get("name") or ""
        if name:
            out.append(name)
    return out


def notice_to_ris(data: dict) -> str:
    """Convertit une notice Zotero (dict `data`) en enregistrement RIS."""
    lines = [f"TY  - {_RIS_TYPE.get(data.get('itemType'), 'GEN')}"]
    if data.get("title"):
        lines.append(f"TI  - {data['title']}")
    lines += [f"AU  - {a}" for a in _ris_authors(data.get("creators", []))]
    m = re.search(r"\b(\d{4})\b", data.get("date") or "")
    if m:
        lines.append(f"PY  - {m.group(1)}")
    container = data.get("publicationTitle") or data.get("bookTitle") or data.get("series")
    if container:
        lines.append(f"T2  - {container}")
    if data.get("volume"):
        lines.append(f"VL  - {data['volume']}")
    if data.get("issue"):
        lines.append(f"IS  - {data['issue']}")
    pages = data.get("pages") or ""
    if pages:
        parts = re.split(r"[-–]", pages, maxsplit=1)
        lines.append(f"SP  - {parts[0].strip()}")
        if len(parts) == 2 and parts[1].strip():
            lines.append(f"EP  - {parts[1].strip()}")
    if data.get("publisher"):
        lines.append(f"PB  - {data['publisher']}")
    if data.get("url"):
        lines.append(f"UR  - {data['url']}")
    if data.get("abstractNote"):
        lines.append(f"AB  - {data['abstractNote']}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def pair_new_docs(new_docs: list[dict], group_index: dict[str, dict]) -> dict:
    """Apparie chaque doc nouveau à sa notice de groupe par clé de préfixe."""
    paired, unpaired = [], []
    for d in new_docs:
        k = prefix_key(d["fichier"])
        data = group_index.get(k) if k else None
        if data:
            paired.append({"id": d["id"], "fichier": d["fichier"], "data": data})
        else:
            unpaired.append({"id": d["id"], "fichier": d["fichier"], "cle": k})
    return {"paired": paired, "unpaired": unpaired}


def filename_to_ris(doc: dict) -> str:
    """RIS *stub* dérivé du nom de fichier descriptif, pour un doc non apparié.

    Les noms du recueil suivent `YYYY-NN-Auteurs-Titre…-Revue.ext`. On en tire
    une notice GEN minimale, **explicitement marquée à vérifier** (N1) : le
    parsing est heuristique (les tirets internes aux titres brouillent le
    découpage), il sert d'amorce d'import, pas de métadonnée définitive.
    """
    base = os.path.basename(doc["fichier"])
    stem = os.path.splitext(base)[0]
    body = re.sub(r"^\d{4}[-\s]+\d{1,3}-?", "", stem)
    first, _, rest = body.partition("-")
    authors = [a.strip() for a in re.split(r"[_,]", first) if a.strip()]
    title = (rest.replace("-", " ").replace("_", " ").strip() or first.strip())
    year = (prefix_key(base) or "-").split("-")[0]
    lines = ["TY  - GEN", f"TI  - {title}"]
    lines += [f"AU  - {a}" for a in authors]
    if year:
        lines.append(f"PY  - {year}")
    lines.append("N1  - Métadonnées dérivées du nom de fichier — à vérifier")
    lines.append(f"L1  - {doc['fichier']}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def build_ris(result: dict) -> str:
    """RIS complet : notices riches pour les appariés, stubs pour les autres."""
    rich = "".join(notice_to_ris(p["data"]) for p in result["paired"])
    stubs = "".join(filename_to_ris(u) for u in result["unpaired"])
    return rich + stubs


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-docs", type=Path, default=DEFAULT_NEW_DOCS)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    p.add_argument("--group-notices", type=Path, default=None,
                   help="JSON de notices de groupe déjà collectées (hors-ligne)")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    new_docs = json.loads(args.new_docs.read_text())["nouveau"]
    if args.group_notices and args.group_notices.exists():
        notices = json.loads(args.group_notices.read_text())
    else:
        env = rz.load_env(args.env)
        notices = rz.fetch_top_items(f"groups/{args.group_id}", env["ZOTERO_API_KEY"])

    result = pair_new_docs(new_docs, index_group_by_prefix(notices))
    args.output.write_text(build_ris(result))

    logger.info("Docs nouveaux                 : %d", len(new_docs))
    logger.info("  notice de groupe (RIS riche): %d", len(result["paired"]))
    logger.info("  stub depuis nom de fichier  : %d (à vérifier)", len(result["unpaired"]))
    for u in result["unpaired"]:
        logger.info("    - %s (%s)", os.path.basename(u["fichier"]), u["cle"])
    logger.info("RIS écrit (18 notices) : %s", args.output)


if __name__ == "__main__":
    main()
