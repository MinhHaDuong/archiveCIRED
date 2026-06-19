"""Remplacer des collections Zotero par des tags, puis supprimer les collections.

Pour chaque collection cible, on ajoute un tag manuel à chacun de ses items
(union avec les tags existants), on vérifie, puis on supprime la collection. Les
items restent dans leurs autres collections (ici « Documents à consulter »).

Dry-run par défaut ; `--apply` (exige `--backup`) exécute.
"""

import argparse
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("zotero_tag_collections")

API = "https://api.zotero.org"
DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_PLAN = Path("outputs/tag_collections_plan.json")
# collection -> tag
DEFAULT_MAP = {"RZUZGILL": "CIRED", "MX3QN57W": "LEESU"}


def merge_tags(existing: list[dict], tag: str) -> list[dict] | None:
    """Ajoute un tag manuel s'il manque. None si déjà présent (rien à faire)."""
    if any(t.get("tag") == tag for t in existing):
        return None
    return existing + [{"tag": tag}]


def _write(method: str, url: str, api_key: str, version: int,
           body: dict | None = None) -> int:
    headers = {"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
               "If-Unmodified-Since-Version": str(version)}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with rz.urlopen_retry(req) as resp:
        return resp.status


def collection_items(uid: str, coll: str, api_key: str) -> list[dict]:
    items, start = [], 0
    while True:
        page, total = rz._get(
            f"{API}/users/{uid}/collections/{coll}/items/top?limit=100&start={start}",
            api_key)
        items.extend(page)
        start += 100
        if start >= total or not page:
            break
    return items


def collection_version(uid: str, coll: str, api_key: str) -> int:
    data, _ = rz._get(f"{API}/users/{uid}/collections/{coll}", api_key)
    return data["version"]


def apply_map(uid: str, mapping: dict[str, str], api_key: str) -> dict:
    done = {"tags_posés": 0, "déjà_taggés": 0, "collections_supprimées": 0,
            "errors": []}
    for coll, tag in mapping.items():
        items = collection_items(uid, coll, api_key)
        for it in items:
            try:
                new = merge_tags(it["data"].get("tags", []), tag)
                if new is None:
                    done["déjà_taggés"] += 1
                    continue
                _write("PATCH", f"{API}/users/{uid}/items/{it['key']}",
                       api_key, it["version"], {"tags": new})
                done["tags_posés"] += 1
            except urllib.error.HTTPError as e:  # noqa: PERF203
                done["errors"].append(f"{it['key']}: HTTP {e.code}")
        # vérifier que tous portent le tag avant de supprimer la collection
        remaining = [i for i in collection_items(uid, coll, api_key)
                     if not any(t.get("tag") == tag for t in i["data"].get("tags", []))]
        if remaining:
            done["errors"].append(f"{coll}: {len(remaining)} sans tag, collection conservée")
            continue
        _write("DELETE", f"{API}/users/{uid}/collections/{coll}",
               api_key, collection_version(uid, coll, api_key))
        done["collections_supprimées"] += 1
    return done


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--backup", type=Path, default=None)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
    uid = rz.fetch_user_id(api_key)

    plan = {tag: len(collection_items(uid, coll, api_key))
            for coll, tag in DEFAULT_MAP.items()}
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    logger.info("À taguer : %s", plan)

    if not args.apply:
        logger.info("DRY-RUN — aucune écriture. Relancer avec --apply.")
        return
    if not args.backup:
        raise SystemExit("--apply exige --backup.")
    backup = rz.fetch_top_items(f"users/{uid}", api_key)
    args.backup.write_text(json.dumps(backup, ensure_ascii=False))
    logger.info("Sauvegarde : %d notices → %s", len(backup), args.backup)
    done = apply_map(uid, DEFAULT_MAP, api_key)
    logger.info("Tags posés %d, déjà taggés %d, collections supprimées %d, erreurs %d",
                done["tags_posés"], done["déjà_taggés"],
                done["collections_supprimées"], len(done["errors"]))
    for e in done["errors"][:10]:
        logger.warning("  %s", e)


if __name__ == "__main__":
    main()
