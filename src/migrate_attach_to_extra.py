"""Migrer les URL recueil des attachements `linked_url` vers le champ `Extra`.

La réconciliation initiale (`reconcile_recueil_urls.py`) stockait la 2ᵉ URL
(fichier recueil distinct) comme attachement-fille `linked_url`. Décision
ultérieure (M. Ha-Duong) : la 2ᵉ URL va dans le champ **`Extra`** de la notice,
car un attachement n'apparaît pas dans une biblio exportée. Ce script migre les
notices concernées : il écrit l'URL recueil dans `Extra`, puis retire
l'attachement devenu inutile.

Cible : les attachements `linked_url` dont le titre commence par
`MARKER` (ceux créés par reconcile_recueil_urls.py).

Sécurité : dry-run par défaut. `--apply` exige `--backup FILE` (sauvegarde des
notices parentes et des attachements avant écriture). Idempotent : une notice
dont l'`Extra` contient déjà l'URL est seulement nettoyée de son attachement.
"""

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

import reconcile_zotero as rz
import verify_recueil_mirror as vm

logger = logging.getLogger("migrate_attach_to_extra")

DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
MARKER = "Recueil 50 ans CIRED — PDF distinct"


def find_migrations(all_items: list[dict]) -> list[dict]:
    """Attachements linked_url à migrer + état de la notice parente (pur)."""
    by_key = {it["key"]: it["data"] for it in all_items}
    out = []
    for it in all_items:
        d = it["data"]
        if d.get("itemType") != "attachment" or d.get("linkMode") != "linked_url":
            continue
        if not (d.get("title") or "").startswith(MARKER):
            continue
        parent = by_key.get(d.get("parentItem"), {})
        out.append({
            "attach_key": d["key"],
            "attach_version": d["version"],
            "url": d.get("url", ""),
            "parent_key": d.get("parentItem"),
            "parent_version": parent.get("version"),
            "parent_extra": parent.get("extra", ""),
            "parent_title": parent.get("title", ""),
        })
    return out


def new_extra(current: str, url: str) -> str | None:
    """Extra mis à jour, ou None si l'URL y est déjà (rien à patcher)."""
    if url in (current or ""):
        return None
    return f"{current}\n{url}".strip() if current else url


def _patch(uid: str, key: str, version: int, fields: dict, api_key: str) -> None:
    data = json.dumps(fields).encode()
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items/{key}", data=data, method="PATCH",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json",
                 "If-Unmodified-Since-Version": str(version)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"PATCH {key}: HTTP {resp.status}")


def _delete(uid: str, key: str, version: int, api_key: str) -> None:
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items/{key}", method="DELETE",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "If-Unmodified-Since-Version": str(version)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"DELETE {key}: HTTP {resp.status}")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--apply", action="store_true",
                   help="migre réellement (sinon dry-run)")
    p.add_argument("--backup", type=Path, default=None,
                   help="sauvegarde JSON parents+attachements (requis avec --apply)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup FILE")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
    uid = rz.fetch_user_id(api_key)
    all_items = vm._fetch_all_items(f"users/{uid}", api_key)
    migrations = find_migrations(all_items)

    logger.info("Attachements à migrer vers Extra : %d", len(migrations))
    for m in migrations:
        flag = "Extra déjà OK" if new_extra(m["parent_extra"], m["url"]) is None else "→ Extra"
        logger.info("  %s  %-9s %s", flag, m["parent_key"],
                    (m["parent_title"] or "")[:48])

    if not args.apply:
        logger.info("\nDRY-RUN : aucune écriture. Relancer avec --apply --backup FILE.")
        return 0

    backup = {m["attach_key"]: m for m in migrations}
    args.backup.write_text(json.dumps(backup, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    logger.info("Sauvegarde : %s", args.backup)

    patched = deleted = 0
    for m in migrations:
        ne = new_extra(m["parent_extra"], m["url"])
        if ne is not None:
            _patch(uid, m["parent_key"], m["parent_version"], {"extra": ne}, api_key)
            patched += 1
        _delete(uid, m["attach_key"], m["attach_version"], api_key)
        deleted += 1
        logger.info("  migré %s (Extra+%s, attachement retiré)", m["parent_key"],
                    "0" if ne is None else "1")
    logger.info("Extra patchés : %d · attachements retirés : %d", patched, deleted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
