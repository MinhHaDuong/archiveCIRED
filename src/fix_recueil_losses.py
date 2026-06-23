"""Corriger les 8 pertes métadonnées/PDF (ticket 0029, axe non-notes).

Deux catégories :
  metadata_incomplete — PATCH la notice My Library avec les champs manquants du groupe.
  no_match           — POST la notice de groupe vers My Library
                       (devient url_preserved à l'audit suivant, URL inari identique).

Dry-run par défaut ; --apply exige --backup FILE.
"""

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz
import verify_recueil_mirror as vm

logger = logging.getLogger("fix_recueil_losses")

COLLECTION = "VPDB49CK"   # Recueil 50 ans CIRED (My Library)
TAG = "recueil-50ans"


# --- planification (pur) --------------------------------------------------------

def plan_patches(losses: list[dict], group_by_key: dict,
                 lib_by_key: dict) -> list[dict]:
    """PATCH à appliquer pour les pertes metadata_incomplete.

    Retourne une liste de {lib_key, group_key, fields, ref}.
    """
    patches = []
    for loss in losses:
        if loss.get("reason") != "metadata_incomplete":
            continue
        matched_key = loss.get("matched")
        group_key = loss["key"]
        group = group_by_key.get(group_key, {})
        if not matched_key or not group:
            logger.warning("Notice lib %s ou groupe %s introuvable", matched_key, group_key)
            continue
        missing = loss.get("missing", [])
        fields = {f: group[f] for f in missing if group.get(f)}
        if fields:
            patches.append({"lib_key": matched_key, "group_key": group_key,
                            "fields": fields, "ref": group.get("title", "")[:80]})
    return patches


def plan_copies(losses: list[dict], group_by_key: dict) -> list[dict]:
    """Copies à créer dans My Library pour les pertes no_match.

    Chaque copie reprend toutes les métadonnées du groupe (sauf key/version/dates).
    La même URL inari garantit url_preserved à l'audit suivant.
    Retourne une liste de {group_key, item, ref}.
    """
    copies = []
    skip = {"key", "version", "dateAdded", "dateModified"}
    for loss in losses:
        if loss.get("reason") != "no_match":
            continue
        group_key = loss["key"]
        group = group_by_key.get(group_key, {})
        if not group:
            continue
        item = {k: v for k, v in group.items() if k not in skip}
        item["collections"] = [COLLECTION]
        item.setdefault("tags", [])
        if not any(t.get("tag") == TAG for t in item["tags"]):
            item["tags"].append({"tag": TAG})
        copies.append({"group_key": group_key, "item": item,
                       "ref": group.get("title", "")[:80]})
    return copies


# --- écriture Zotero (réseau) ---------------------------------------------------

def _patch(uid: str, key: str, version: int, fields: dict, api_key: str) -> None:
    """PATCH partiel avec contrôle de version."""
    data = json.dumps(fields).encode()
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items/{key}", data=data, method="PATCH",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json",
                 "If-Unmodified-Since-Version": str(version)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"PATCH {key}: HTTP {resp.status}")


def _post_items(uid: str, items: list[dict], api_key: str) -> dict:
    """POST de création (jusqu'à 50 notices) ; retourne la réponse Zotero."""
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items", data=json.dumps(items).encode(),
        method="POST",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


# --- point d'entrée --------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", type=Path, default=vm.DEFAULT_ENV)
    p.add_argument("--group-id", default=vm.DEFAULT_GROUP_ID)
    p.add_argument("--backup", type=Path, default=None,
                   help="Fichier de sauvegarde des notices My Library avant écriture")
    p.add_argument("--apply", action="store_true",
                   help="Écrire réellement (sinon dry-run)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup")

    logger.info("Collecte des données Zotero...")
    group_data, lib_top, children, group_notes, lib_note_texts, meta = \
        vm.collect(args.env, args.group_id)
    uid = meta["user_id"]
    logger.info("Groupe : %d notices | My Library top : %d", len(group_data), len(lib_top))

    report = vm.assess_all(group_data, lib_top, children, group_notes, lib_note_texts)
    losses = report["losses"]
    logger.info("Pertes identifiées : %d (verdict : %s)", len(losses), report["verdict"])

    group_by_key = {g["key"]: g for g in group_data}
    lib_by_key = {lib["key"]: lib for lib in lib_top}

    patches = plan_patches(losses, group_by_key, lib_by_key)
    copies = plan_copies(losses, group_by_key)

    logger.info("Plan : %d PATCH(es) (metadata_incomplete) + %d copie(s) (no_match)",
                len(patches), len(copies))
    for pt in patches:
        logger.info("  PATCH lib/%s ← groupe/%s : champs %s",
                    pt["lib_key"], pt["group_key"], list(pt["fields"].keys()))
        logger.info("        %s", pt["ref"])
    for cp in copies:
        logger.info("  POST  groupe/%s → My Library : %s", cp["group_key"], cp["ref"])

    if not args.apply:
        logger.info("DRY-RUN — rien écrit. Ajouter --apply --backup FILE pour appliquer.")
        return

    env = rz.load_env(args.env)
    api_key = env["ZOTERO_API_KEY"]

    # Sauvegarde préalable des notices My Library qui seront patchées
    backup_data = []
    for pt in patches:
        item, _ = rz._get(f"{rz.API}/users/{uid}/items/{pt['lib_key']}", api_key)
        backup_data.append(item)
    args.backup.write_text(json.dumps(backup_data, ensure_ascii=False, indent=2))
    logger.info("Backup écrit : %s (%d notices)", args.backup, len(backup_data))

    # PATCH des champs manquants
    for pt in patches:
        item, _ = rz._get(f"{rz.API}/users/{uid}/items/{pt['lib_key']}", api_key)
        version = item["data"]["version"]
        try:
            _patch(uid, pt["lib_key"], version, pt["fields"], api_key)
            logger.info("OK PATCH %s : %s", pt["lib_key"], list(pt["fields"].keys()))
        except urllib.error.HTTPError as ex:
            logger.error("ÉCHEC PATCH %s : HTTP %s %s", pt["lib_key"], ex.code,
                         ex.read().decode()[:200])

    # POST des copies no_match
    if copies:
        items_to_post = [cp["item"] for cp in copies]
        res = _post_items(uid, items_to_post, api_key)
        ok = res.get("successful", {})
        failed = res.get("failed", {})
        logger.info("POST : %d créées, %d échouées", len(ok), len(failed))
        if failed:
            logger.error("ÉCHECS POST : %s", json.dumps(failed, ensure_ascii=False)[:400])
        for i, cp in enumerate(copies):
            key_created = (ok.get(str(i)) or {}).get("key")
            logger.info("  groupe/%s → My Library/%s", cp["group_key"],
                        key_created or "ÉCHEC")


if __name__ == "__main__":
    main()
