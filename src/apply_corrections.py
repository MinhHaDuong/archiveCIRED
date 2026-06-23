"""Appliquer les corrections manuelles vérifiées aux notices My Library (Zotero).

Lit `outputs/manual_corrections.json` (champ `set` par notice), **sauvegarde
d'abord** les notices concernées (backup complet), puis écrit :
  - PATCH partiel quand l'itemType ne change pas ;
  - PUT d'un objet reconstruit quand l'itemType change (report→journalArticle,
    journalArticle→bookSection), en ne conservant qu'un sous-ensemble de champs
    transférables pour éviter les champs invalides du type d'origine.

Dry-run par défaut ; `--apply` exige `--backup`. Sens unique : on n'écrit que les
champs `set`, jamais d'effacement implicite. Le contrôle de version (header
`If-Unmodified-Since-Version`) empêche d'écraser une modif concurrente.
"""

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("apply_corrections")

DEFAULT_LEDGER = Path("outputs/manual_corrections.json")
DEFAULT_ENV = rz.DEFAULT_ENV

# Champs transférables lors d'un changement d'itemType (on repart de zéro pour
# le nouveau type afin de ne pas traîner les champs invalides de l'ancien).
CARRY = ("title", "creators", "abstractNote", "date", "language", "url",
         "accessDate", "rights", "extra", "shortTitle", "pages", "volume",
         "ISSN", "ISBN", "DOI", "tags", "collections", "relations")


def build_write(current: dict, set_fields: dict) -> tuple[str, dict]:
    """Construit (méthode, corps) pour écrire les corrections sur une notice.

    `current` est l'objet `data` actuel (avec `key`, `version`, `itemType`).
    Retourne ("PATCH", champs) si l'itemType ne change pas, sinon ("PUT", objet
    reconstruit pour le nouveau type).
    """
    new_type = set_fields.get("itemType")
    if not new_type or new_type == current.get("itemType"):
        body = {k: v for k, v in set_fields.items() if k != "itemType"}
        return "PATCH", body
    # Un PUT complet exige ces conteneurs structurels, même vides.
    body = {"key": current["key"], "version": current["version"],
            "itemType": new_type,
            "relations": current.get("relations") or {},
            "collections": current.get("collections") or [],
            "tags": current.get("tags") or []}
    for f in CARRY:
        if current.get(f):
            body[f] = current[f]
    for k, v in set_fields.items():
        body[k] = v
    return "PUT", body


def _write(uid: str, key: str, version: int, method: str, body: dict,
           api_key: str) -> None:
    """Envoie le PATCH/PUT à Zotero avec contrôle de version (lève sur échec)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items/{key}", data=data, method=method,
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json",
                 "If-Unmodified-Since-Version": str(version)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"{key}: HTTP {resp.status}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--backup", type=Path, default=None,
                   help="Fichier de sauvegarde des notices avant écriture")
    p.add_argument("--apply", action="store_true",
                   help="Écrire réellement (sinon dry-run)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup")

    entries = json.loads(args.ledger.read_text())
    pending = [e for e in entries if not e.get("applied")]
    if not pending:
        raise SystemExit("Rien à appliquer : toutes les entrées sont applied.")
    env = rz.load_env(args.env)
    api_key = env["ZOTERO_API_KEY"]
    uid = rz.fetch_user_id(api_key)

    backup, plan = [], []
    for e in pending:
        key = e["key"]
        item, _ = rz._get(f"{rz.API}/users/{uid}/items/{key}", api_key)
        backup.append(item)
        method, body = build_write(item["data"], e["set"])
        plan.append((e, item["data"], method, body))
        logger.info("%s [%s] %s", key, method, e["ref"])
        for k, v in e["set"].items():
            logger.info("    %-16s %r -> %r", k, item["data"].get(k), v)

    if args.backup:
        args.backup.write_text(json.dumps(backup, ensure_ascii=False, indent=2))
        logger.info("Backup écrit : %s (%d notices)", args.backup, len(backup))

    if not args.apply:
        logger.info("DRY-RUN — rien écrit. Ajouter --apply --backup pour écrire.")
        return

    for e, data, method, body in plan:
        try:
            _write(uid, e["key"], data["version"], method, body, api_key)
            logger.info("OK   %s", e["key"])
        except urllib.error.HTTPError as ex:
            logger.error("ÉCHEC %s : HTTP %s %s", e["key"], ex.code,
                         ex.read().decode()[:200])


if __name__ == "__main__":
    main()
