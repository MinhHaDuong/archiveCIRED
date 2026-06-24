"""Relier deux notices Zotero par une relation « Connexe » (`dc:relation`).

Zotero matérialise le lien « Connexe » par le champ `relations` → clé
`dc:relation`, une liste d'URI d'items. La relation n'est PAS symétrique côté
stockage : il faut l'écrire sur **les deux** notices pour qu'elle apparaisse des
deux côtés dans l'interface. Ce script ajoute l'URI de chaque notice à l'autre.

Cas d'usage : deux publications distinctes d'un même fond qu'il faut **lier**
sans dédoublonner (ex. un article de revue et le chapitre d'ouvrage dérivé).

Sécurité : dry-run par défaut. `--apply` exige `--backup FILE` (sauvegarde du
champ `relations` des deux notices avant écriture). Idempotent : un lien déjà
présent n'est pas réécrit.
"""

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("relate_zotero_items")

DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"


def item_uri(uid: str, key: str) -> str:
    """URI Zotero d'une notice de bibliothèque utilisateur."""
    return f"http://zotero.org/users/{uid}/items/{key}"


def _as_list(rel: dict, pred: str = "dc:relation") -> list[str]:
    """Valeur d'un prédicat de `relations` normalisée en liste (Zotero la stocke
    en chaîne quand il n'y a qu'un lien, en liste au-delà)."""
    v = (rel or {}).get(pred)
    if not v:
        return []
    return [v] if isinstance(v, str) else list(v)


def add_relation(current: dict, uri: str) -> dict | None:
    """`relations` mis à jour avec `uri` ajouté à `dc:relation`, ou None si
    l'URI y figure déjà (rien à patcher)."""
    existing = _as_list(current)
    if uri in existing:
        return None
    updated = dict(current or {})
    updated["dc:relation"] = existing + [uri]
    return updated


def plan_relation(a: dict, b: dict, uid: str) -> list[dict]:
    """PATCH à appliquer pour relier les notices `a` et `b` (data brutes).

    Retourne 0 à 2 entrées {key, version, relations, ref} — une par notice dont
    le lien vers l'autre manque encore.
    """
    out = []
    for src, dst in ((a, b), (b, a)):
        new_rel = add_relation(src.get("relations", {}), item_uri(uid, dst["key"]))
        if new_rel is not None:
            out.append({"key": src["key"], "version": src["version"],
                        "relations": new_rel, "ref": (src.get("title") or "")[:60]})
    return out


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


def _link_side(uid: str, key: str, other_key: str, api_key: str) -> bool:
    """Ajoute le lien `key → other_key` à partir de l'état frais de la notice.

    Re-fetch juste avant l'écriture : Zotero crée la relation réciproque côté
    serveur quand on lie l'autre notice d'abord, ce qui périmerait une version
    capturée plus tôt (412). Retourne True si un PATCH a été émis, False si le
    lien était déjà présent.
    """
    item, _ = rz._get(f"{rz.API}/users/{uid}/items/{key}", api_key)
    data = item["data"]
    new_rel = add_relation(data.get("relations", {}), item_uri(uid, other_key))
    if new_rel is None:
        return False
    _patch(uid, key, data["version"], {"relations": new_rel}, api_key)
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("keys", nargs=2, metavar="KEY",
                   help="les deux clés de notices My Library à relier")
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--apply", action="store_true",
                   help="écrit réellement (sinon dry-run)")
    p.add_argument("--backup", type=Path, default=None,
                   help="sauvegarde JSON des `relations` avant écriture (requis avec --apply)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup FILE")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
    uid = rz.fetch_user_id(api_key)

    ka, kb = args.keys
    a, _ = rz._get(f"{rz.API}/users/{uid}/items/{ka}", api_key)
    b, _ = rz._get(f"{rz.API}/users/{uid}/items/{kb}", api_key)
    a, b = a["data"], b["data"]

    patches = plan_relation(a, b, uid)
    logger.info("Notices : %s « %s » ↔ %s « %s »",
                ka, (a.get("title") or "")[:48], kb, (b.get("title") or "")[:48])
    logger.info("PATCH(es) à appliquer : %d", len(patches))
    for pt in patches:
        logger.info("  + lien sur %s → %s", pt["key"], pt["relations"]["dc:relation"][-1])

    if not patches:
        logger.info("Déjà reliées — rien à faire.")
        return 0

    if not args.apply:
        logger.info("\nDRY-RUN : aucune écriture. Relancer avec --apply --backup FILE.")
        return 0

    backup = {ka: a.get("relations", {}), kb: b.get("relations", {})}
    args.backup.write_text(json.dumps(backup, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    logger.info("Sauvegarde : %s", args.backup)

    patched = 0
    for key, other in ((ka, kb), (kb, ka)):
        if _link_side(uid, key, other, api_key):
            patched += 1
            logger.info("  relié %s → %s", key, other)
        else:
            logger.info("  %s déjà relié à %s (réciproque automatique)", key, other)
    logger.info("Notices reliées : %d", patched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
