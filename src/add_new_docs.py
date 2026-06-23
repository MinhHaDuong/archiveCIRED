"""Créer dans My Library les 18 documents nouveaux du recueil (ticket 0018).

Pour chaque doc « nouveau » (cf. `select_new_recueil.py`) :
  - s'il a une notice dans le groupe Recueil_CIRED (apparié par préfixe YYYY-NN),
    on **recopie ses métadonnées riches** (titre, auteurs, revue, pages, url…) ;
  - sinon, on crée une **notice honnête « à vérifier »** : titre = nom descriptif
    du fichier (info préservée, pas de découpage hasardeux auteur/titre), année,
    chemin local en `extra`, à enrichir par les swarms HAL/OpenAlex (0022/0023).

Chaque notice est d'emblée rangée dans la collection « Recueil 50 ans CIRED » et
taguée `recueil-50ans`. Dry-run par défaut ; `--apply` crée réellement (POST) et
enregistre les clés créées (réversible par suppression).
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

import build_recueil_ris as brr  # noqa: E402
import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("add_new_docs")

DEFAULT_NEW_DOCS = Path("outputs/recueil_new_docs.json")
DEFAULT_CREATED = Path("outputs/recueil_new_docs_created.json")
DEFAULT_ENV = rz.DEFAULT_ENV
DEFAULT_GROUP_ID = rz.DEFAULT_GROUP_ID
COLLECTION = "VPDB49CK"   # « Recueil 50 ans CIRED » (My Library)
TAG = "recueil-50ans"
_STRIP_PREFIX = re.compile(r"^\d{4}[-\s]+\d{1,3}-?")


def descriptive_title(filename: str) -> str:
    """Titre lisible depuis le nom de fichier descriptif (préfixe/ext retirés).

    >>> descriptive_title("attente/x/2010-150-Monjon_Quirion-Border_adjustment.pdf")
    'Monjon Quirion Border adjustment'
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    body = _STRIP_PREFIX.sub("", stem)
    return " ".join(body.replace("_", " ").replace("-", " ").split())


def build_item(new_doc: dict, group_data: dict | None,
               collection: str = COLLECTION, tag: str = TAG) -> dict:
    """Objet notice Zotero à créer pour un doc nouveau (sans key/version)."""
    if group_data:
        skip = {"key", "version", "dateAdded", "dateModified"}
        item = {k: v for k, v in group_data.items() if k not in skip}
        item["collections"] = [collection]
        item["tags"] = (item.get("tags") or []) + [{"tag": tag}]
        return item
    year = (new_doc.get("id") or "")[:4]
    return {
        "itemType": "document",
        "title": descriptive_title(new_doc["fichier"]),
        "date": year,
        "extra": f"À vérifier — fichier recueil : {os.path.basename(new_doc['fichier'])}. "
                 f"Enrichir via HAL/OpenAlex (tickets 0022/0023).",
        "collections": [collection],
        "tags": [{"tag": tag}, {"tag": "à-vérifier"}],
    }


def build_items(new_docs: list[dict], group_index: dict[str, dict]) -> list[dict]:
    """Notices à créer pour tous les docs nouveaux (riches si appariées)."""
    items = []
    for d in new_docs:
        k = brr.prefix_key(d["fichier"])
        items.append(build_item(d, group_index.get(k) if k else None))
    return items


def _post_items(uid: str, items: list[dict], api_key: str) -> dict:
    """POST de création (jusqu'à 50 notices) ; retourne la réponse Zotero."""
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items", data=json.dumps(items).encode(),
        method="POST",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-docs", type=Path, default=DEFAULT_NEW_DOCS)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    p.add_argument("--created", type=Path, default=DEFAULT_CREATED)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    new_docs = json.loads(args.new_docs.read_text())["nouveau"]
    env = rz.load_env(args.env)
    api_key = env["ZOTERO_API_KEY"]
    uid = rz.fetch_user_id(api_key)
    notices = rz.fetch_top_items(f"groups/{args.group_id}", api_key)
    index = brr.index_group_by_prefix(notices)

    items = build_items(new_docs, index)
    rich = sum(1 for d in new_docs if brr.prefix_key(d["fichier"]) in index)
    logger.info("%d notices à créer : %d riches (groupe), %d à vérifier (stub)",
                len(items), rich, len(items) - rich)
    for it in items:
        logger.info("   [%s] %s", it["itemType"], it["title"][:70])

    if not args.apply:
        logger.info("DRY-RUN — rien créé. Ajouter --apply pour créer.")
        return

    res = _post_items(uid, items, api_key)
    created = {i: o["key"] for i, o in res.get("successful", {}).items()}
    failed = res.get("failed", {})
    args.created.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    logger.info("Créées : %d | échecs : %d | clés dans %s",
                len(created), len(failed), args.created)
    if failed:
        logger.error("ÉCHECS : %s", json.dumps(failed, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
