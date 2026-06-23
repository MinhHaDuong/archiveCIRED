"""Réconcilier les 14 URL recueil pointant un fichier PDF distinct (ticket 0029,
action 4).

L'audit du miroir (`verify_recueil_mirror.py`) classe 54 notices en
`doc_equivalent`. La comparaison fichier par fichier (`compare_recueil_urls.py`,
`outputs/recueil_url_comparison.json`) montre que 14 d'entre elles pointent un
PDF **réellement différent** sur inari (souvent un extrait d'article côté recueil
contre le scan du volume entier côté My Library, parfois un meilleur scan côté
recueil). Supprimer le groupe sans réconcilier détruirait ces fichiers.

Réconcilier = attacher l'URL recueil à la notice My Library équivalente comme
attachement `linked_url` (un lien, **zéro octet de stockage**), titré pour la
distinguer. **Aucune copie n'est supprimée** : les deux PDF restent joignables.

Sécurité : dry-run par défaut. `--apply` exige `--backup FILE` (sauvegarde JSON
des notices cibles et de leurs enfants avant écriture). Idempotent : une notice
qui porte déjà un `linked_url` vers l'URL recueil est sautée.
"""

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

import reconcile_zotero as rz
import verify_recueil_mirror as vm

logger = logging.getLogger("reconcile_recueil_urls")

DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_COMPARISON = Path("outputs/recueil_url_comparison.json")
DEFAULT_BACKUP = Path("outputs/recueil_urls_reconcile_backup.json")
ATTACH_TITLE = "Recueil 50 ans CIRED — PDF distinct"


def distinct_rows(comparison: list[dict]) -> list[dict]:
    """Les paires dont les deux URL désignent un fichier distinct.

    = taille différente, ou taille égale mais SHA-256 différent. Les doublons
    vrais (hash identique) et les paires sans PDF sont exclus.
    """
    out = []
    for r in comparison:
        if not r.get("url_recueil") or not r.get("mylib_key"):
            continue
        if r["verdict"] == "taille_differente" or r.get("fichiers_identiques") is False:
            out.append(r)
    return out


def already_linked(children: list[dict], url: str) -> bool:
    """La notice porte-t-elle déjà un attachement linked_url vers cette URL ?"""
    for c in children:
        if c.get("linkMode") == "linked_url" and c.get("url") == url:
            return True
    return False


def plan_links(rows: list[dict], lib_children: dict[str, list[dict]]) -> list[dict]:
    """Plan d'attachements à créer (fonction pure, sans réseau)."""
    planned = []
    for r in rows:
        target = r["mylib_key"]
        url = r["url_recueil"]
        basename = url.rsplit("/", 1)[-1]
        present = already_linked(lib_children.get(target, []), url)
        planned.append({
            "target": target,
            "url": url,
            "title": f"{ATTACH_TITLE} ({basename})",
            "annee": r.get("annee"),
            "titre": r.get("titre"),
            "already_present": present,
        })
    return planned


# --- écriture Zotero (réseau) ------------------------------------------------

def post_linked_url(user_id: str, target_key: str, url: str, title: str,
                    api_key: str) -> str:
    """Crée un attachement linked_url sur `target_key`. Retourne la clé créée."""
    payload = json.dumps([{
        "itemType": "attachment", "linkMode": "linked_url",
        "parentItem": target_key, "url": url, "title": title,
        "contentType": "application/pdf",
    }]).encode()
    req = urllib.request.Request(
        f"{rz.API}/users/{user_id}/items", data=payload, method="POST",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json"})
    with rz.urlopen_retry(req) as resp:
        result = json.loads(resp.read().decode())
    success = result.get("successful", {})
    if not success:
        raise RuntimeError(f"échec création attachement: {result.get('failed')}")
    return success["0"]["key"]


def collect(env_path: Path):
    """Collecte live : user_id, clé API, enfants des notices My Library."""
    env = rz.load_env(env_path)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {env_path}")
    user_id = rz.fetch_user_id(api_key)
    all_perso = vm._fetch_all_items(f"users/{user_id}", api_key)
    lib_children = vm._children_by_parent(all_perso)
    by_key = {it["key"]: it["data"] for it in all_perso}
    return user_id, api_key, lib_children, by_key


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON,
                   help="rapport de comparaison des URL (source des 14 paires)")
    p.add_argument("--apply", action="store_true",
                   help="crée réellement les attachements (sinon dry-run)")
    p.add_argument("--backup", type=Path, default=None,
                   help="sauvegarde JSON des notices cibles (requis avec --apply)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup FILE")

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    rows = distinct_rows(comparison)
    user_id, api_key, lib_children, by_key = collect(args.env)
    planned = plan_links(rows, lib_children)

    to_write = [pl for pl in planned if not pl["already_present"]]
    logger.info("Fichiers distincts à réconcilier : %d (déjà liés : %d)",
                len(to_write), len(planned) - len(to_write))
    for pl in planned:
        flag = "SKIP(déjà)" if pl["already_present"] else "→"
        logger.info("  %s %-9s %s :: %s", flag, pl["target"],
                    (pl["annee"] or ""), (pl["titre"] or "")[:48])

    if not args.apply:
        logger.info("\nDRY-RUN : aucune écriture. Relancer avec --apply --backup FILE.")
        return 0

    targets = {pl["target"] for pl in to_write}
    backup = {k: {"item": by_key.get(k), "children": lib_children.get(k, [])}
              for k in targets}
    args.backup.write_text(json.dumps(backup, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    logger.info("Sauvegarde de %d notices cibles : %s", len(backup), args.backup)

    created = 0
    for pl in to_write:
        key = post_linked_url(user_id, pl["target"], pl["url"], pl["title"],
                              api_key)
        created += 1
        logger.info("  lié %s sur %s (%s)", key, pl["target"],
                    (pl["titre"] or "")[:48])
    logger.info("Attachements linked_url créés : %d", created)
    return 0


if __name__ == "__main__":
    sys.exit(main())
