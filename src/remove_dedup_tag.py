"""Retirer le tag `à-dédoublonner` une fois le dédoublonnage terminé.

Le miroir du recueil avait posé le tag `à-dédoublonner` sur les notices
injectées, à réviser contre les originaux pré-existants de My Library. Après
réconciliation (bijection groupe↔collection) et suppression des copies en double,
plus aucune notice taguée n'a de jumeau : le tag est obsolète.

Garde-fou : on ne retire le tag **que si** aucune notice taguée n'a encore un
jumeau (même œuvre) ailleurs dans My Library. Sinon on s'abstient et on liste les
doublons restants — il ne faut pas effacer un marqueur de travail non terminé.

Sécurité : dry-run par défaut. `--apply` exige `--backup FILE` (clés + titres des
notices taguées, pour pouvoir re-taguer si besoin).
"""

import argparse
import collections
import json
import logging
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import reconcile_zotero as rz
import verify_recueil_mirror as vm

logger = logging.getLogger("remove_dedup_tag")

DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
TAG = "à-dédoublonner"


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^a-zà-ÿ0-9]+", " ", (t or "").lower()).split())[:32]


def find_remaining_dups(tagged: list[dict], all_top: list[dict]) -> list[tuple]:
    """Notices taguées ayant encore un jumeau (même œuvre) — fonction pure."""
    by_work = collections.defaultdict(list)
    for d in all_top:
        by_work[_norm(d.get("title"))].append(d["key"])
    out = []
    for d in tagged:
        twins = [k for k in by_work[_norm(d.get("title"))] if k != d["key"]]
        if twins:
            out.append((d["key"], d.get("title"), twins))
    return out


def _tagged(all_top: list[dict]) -> list[dict]:
    return [d for d in all_top
            if any(t.get("tag") == TAG for t in d.get("tags", []))]


def library_version(uid: str, api_key: str) -> int:
    """Dernière version de la bibliothèque (en-tête Last-Modified-Version)."""
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items?limit=1",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers.get("Last-Modified-Version", 0))


def delete_tag(uid: str, tag: str, version: int, api_key: str) -> None:
    """Supprime le tag de toute la bibliothèque (un appel)."""
    q = urllib.parse.quote(tag)
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/tags?tag={q}", method="DELETE",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "If-Unmodified-Since-Version": str(version)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"DELETE tag: HTTP {resp.status}")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--tag", default=TAG)
    p.add_argument("--apply", action="store_true",
                   help="retire réellement le tag (sinon dry-run)")
    p.add_argument("--backup", type=Path, default=None,
                   help="sauvegarde JSON des notices taguées (requis avec --apply)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup FILE")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
    uid = rz.fetch_user_id(api_key)
    all_top = [it["data"] for it in vm._fetch_all_items(f"users/{uid}", api_key)
               if it["data"].get("itemType") not in ("attachment", "note")
               and not it["data"].get("parentItem")]
    tagged = [d for d in all_top
              if any(t.get("tag") == args.tag for t in d.get("tags", []))]

    logger.info("Notices taguées « %s » : %d", args.tag, len(tagged))
    remaining = find_remaining_dups(tagged, all_top)
    if remaining:
        logger.warning("ABSTENTION : %d notices taguées ont encore un jumeau :",
                       len(remaining))
        for k, title, tw in remaining:
            logger.warning("  %s «%s» ↔ %s", k, (title or "")[:40], tw)
        logger.warning("Dédoublonner d'abord ; le tag reste.")
        return 1

    logger.info("Garde-fou OK : aucune notice taguée n'a de jumeau restant.")
    if not args.apply:
        logger.info("\nDRY-RUN : tag conservé. Relancer avec --apply --backup FILE.")
        return 0

    args.backup.write_text(
        json.dumps([{"key": d["key"], "title": d.get("title")} for d in tagged],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Sauvegarde de %d notices : %s", len(tagged), args.backup)
    delete_tag(uid, args.tag, library_version(uid, api_key), api_key)
    logger.info("Tag « %s » retiré de %d notices.", args.tag, len(tagged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
