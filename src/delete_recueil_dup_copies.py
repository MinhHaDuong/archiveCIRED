"""Supprimer définitivement les 5 copies de notices créées à tort par #27.

L'audit 0025 avait signalé 6 notices `no_match` ; #27 en a POSTé des copies dans
My Library. Pour 5 d'entre elles, l'œuvre existait déjà (faux négatif du matcher),
d'où des doublons. M. Ha-Duong a fusionné/retiré les copies de la collection ;
l'originale porte désormais les **deux URL** (`url` numérisation + URL recueil
dans `Extra`). Les 5 copies #27 ne servent plus et restent vivantes dans la
bibliothèque — ce script les supprime.

Garde-fou : une copie n'est supprimée **que si** son originale existe et porte
bien les 2 URL (recueil + numérisation). Sinon on s'abstient (rien ne doit
perdre l'URL recueil).

Sécurité : dry-run par défaut. `--apply` exige `--backup FILE`.
"""

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("delete_recueil_dup_copies")

DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"

# (copie #27 à supprimer, originale à garder, libellé)
PAIRS = [
    ("5M7TJ5DZ", "Z83SYUK5", "Eléments gestion eau"),
    ("X8HZN2J3", "NYFD6CNL", "La Méditerranée"),
    ("ZDV4BIS9", "UI8XFEWK", "Entre nature et société"),
    ("KETCQX77", "5GPCR5FK", "Ecodevelopment 1974"),
    ("4PMKVKH6", "WCI9YSD4", "Integration of technology"),
]


def url_sources(data: dict) -> set[str]:
    """Buckets inari présents dans url+extra ('recueil' et/ou 'numerisation')."""
    s = (data.get("url", "") or "") + " " + (data.get("extra", "") or "")
    out = set()
    if "Wehurei6" in s:
        out.add("recueil")
    if "kCj0pHP0" in s:
        out.add("numerisation")
    return out


def _get(uid: str, k: str, api_key: str) -> dict | None:
    try:
        return rz._get(f"{rz.API}/users/{uid}/items/{k}", api_key)[0]["data"]
    except Exception:  # noqa: BLE001
        return None


def plan_deletions(uid: str, api_key: str, pairs=PAIRS) -> tuple[list, list]:
    """Retourne (à_supprimer, abstentions). Pur sur l'état live collecté."""
    to_delete, skipped = [], []
    for copy_key, orig_key, lbl in pairs:
        cd, od = _get(uid, copy_key, api_key), _get(uid, orig_key, api_key)
        if cd is None:
            skipped.append((copy_key, lbl, "copie déjà absente"))
            continue
        if od is None or url_sources(od) != {"recueil", "numerisation"}:
            skipped.append((copy_key, lbl, "originale sans les 2 URL — abstention"))
            continue
        to_delete.append({"key": copy_key, "version": cd["version"],
                          "orig": orig_key, "label": lbl, "data": cd})
    return to_delete, skipped


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
                   help="supprime réellement (sinon dry-run)")
    p.add_argument("--backup", type=Path, default=None,
                   help="sauvegarde JSON des copies supprimées (requis avec --apply)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup FILE")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
    uid = rz.fetch_user_id(api_key)
    to_delete, skipped = plan_deletions(uid, api_key)

    logger.info("Copies #27 à supprimer : %d (abstentions : %d)",
                len(to_delete), len(skipped))
    for d in to_delete:
        logger.info("  SUPPR %-9s %-26s (garde l'originale %s, 2 URL)",
                    d["key"], d["label"], d["orig"])
    for k, lbl, why in skipped:
        logger.info("  skip  %-9s %-26s : %s", k, lbl, why)

    if not args.apply:
        logger.info("\nDRY-RUN : aucune suppression. Relancer avec --apply --backup FILE.")
        return 0

    args.backup.write_text(
        json.dumps([d["data"] for d in to_delete], ensure_ascii=False, indent=2),
        encoding="utf-8")
    logger.info("Sauvegarde des %d copies : %s", len(to_delete), args.backup)
    for d in to_delete:
        _delete(uid, d["key"], d["version"], api_key)
        logger.info("  supprimé %s (%s)", d["key"], d["label"])
    logger.info("Copies supprimées : %d", len(to_delete))
    return 0


if __name__ == "__main__":
    sys.exit(main())
