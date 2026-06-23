"""Réinjecter dans My Library les notes d'annotation d'Antonin Pottier portées
par le groupe Zotero `Recueil_CIRED` (ticket 0029, remédiation de l'audit 0025).

Pour chaque note du groupe dont le texte est introuvable dans My Library, crée
une note-fille sur la notice My Library équivalente, préfixée d'un en-tête
« Note de Antonin Pottier ». La notice cible est déterminée par le même
appariement que l'audit (`verify_recueil_mirror.assess_item`) ; deux notices sans
match net ont une cible validée manuellement (`RELAXED_TARGETS`).

Sécurité : dry-run par défaut (aucune écriture). `--apply` exige `--backup FILE`
(sauvegarde JSON des notes de groupe avant écriture). Idempotent : une note déjà
présente sur la cible (même en-tête + même début de texte) est sautée.
"""

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

import reconcile_zotero as rz
import verify_recueil_mirror as vm

logger = logging.getLogger("inject_recueil_notes")

DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_GROUP_ID = "2511149"
NOTE_HEADER = "Note de Antonin Pottier"

# Notices de groupe sans appariement net dans l'audit, mais dont la notice
# My Library équivalente a été identifiée manuellement (même année, auteur
# commun, PDF du même document). Clé = item de groupe, valeur = notice cible.
RELAXED_TARGETS = {
    "ERX2ECHX": "5GPCR5FK",  # Ecodevelopment… (1974, Sachs)
    "VZZLHYNW": "WCI9YSD4",  # Integration of technology in development planning (1979, Sachs)
}


def build_note_html(original_html: str, header: str = NOTE_HEADER) -> str:
    """Contenu de la note injectée : en-tête en gras puis le texte d'origine."""
    body = original_html or ""
    return f"<p><strong>{header}</strong></p>\n{body}"


def already_injected(target_children: list[dict], header: str,
                     text_probe: str) -> bool:
    """Vrai si une note-fille de la cible porte déjà cet en-tête + ce texte."""
    probe = vm.norm_text(text_probe)[:40]
    for c in target_children:
        if c.get("itemType") != "note":
            continue
        txt = vm.norm_text(vm.note_text(c.get("note")))
        if vm.norm_text(header) in txt and (not probe or probe in txt):
            return True
    return False


def plan_injections(group_notes: list[dict], group_top: list[dict],
                    enriched_lib: list[tuple[dict, set[str]]],
                    lib_children: dict[str, list[dict]],
                    relaxed: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Détermine, pour chaque note non vide, la notice My Library cible.

    Retourne (injections planifiées, notes sans cible). Fonction pure.
    """
    by_key = {d["key"]: d for d in group_top}
    planned, orphans = [], []
    for note in group_notes:
        text = vm.note_text(note.get("note"))
        if not text:
            continue
        parent = note.get("parentItem")
        g = by_key.get(parent)
        target = None
        if g is not None:
            r = vm.assess_item(g, enriched_lib)
            target = r.get("matched") if r["tier"] != "loss" else None
        if target is None:
            target = relaxed.get(parent)
        if target is None:
            orphans.append({"parent": parent,
                            "titre": (g or {}).get("title"),
                            "extrait": text[:90]})
            continue
        skip = already_injected(lib_children.get(target, []), NOTE_HEADER, text)
        planned.append({
            "group_parent": parent,
            "group_titre": (g or {}).get("title"),
            "target": target,
            "note_html": build_note_html(note.get("note")),
            "extrait": text[:90],
            "already_present": skip,
        })
    return planned, orphans


# --- écriture Zotero (réseau) ------------------------------------------------

def post_note(user_id: str, target_key: str, note_html: str,
              api_key: str) -> str:
    """Crée une note-fille sur `target_key`. Retourne la clé créée."""
    payload = json.dumps([{"itemType": "note", "parentItem": target_key,
                           "note": note_html}]).encode()
    req = urllib.request.Request(
        f"{rz.API}/users/{user_id}/items", data=payload, method="POST",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json"})
    with rz.urlopen_retry(req) as resp:
        result = json.loads(resp.read().decode())
    success = result.get("successful", {})
    if not success:
        raise RuntimeError(f"échec création note: {result.get('failed')}")
    return success["0"]["key"]


def collect_targets(env_path: Path, group_id: str):
    """Collecte live : notes de groupe, items de groupe, lib enrichie, enfants lib."""
    env = rz.load_env(env_path)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {env_path}")
    user_id = rz.fetch_user_id(api_key)

    def is_doc(d):
        return not d.get("parentItem") and d.get("itemType") not in ("attachment", "note")

    all_group = vm._fetch_all_items(f"groups/{group_id}", api_key)
    all_perso = vm._fetch_all_items(f"users/{user_id}", api_key)
    group_top = [it["data"] for it in all_group if is_doc(it["data"])]
    group_notes = [it["data"] for it in all_group if it["data"].get("itemType") == "note"]
    lib_top = [it["data"] for it in all_perso if is_doc(it["data"])]
    lib_children = vm._children_by_parent(all_perso)
    enriched = vm._enrich_library(lib_top, lib_children)
    return user_id, api_key, group_notes, group_top, enriched, lib_children


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    p.add_argument("--apply", action="store_true",
                   help="écrit réellement les notes (sinon dry-run)")
    p.add_argument("--backup", type=Path, default=None,
                   help="fichier de sauvegarde JSON des notes de groupe (requis avec --apply)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup FILE")

    (user_id, api_key, group_notes, group_top,
     enriched, lib_children) = collect_targets(args.env, args.group_id)
    planned, orphans = plan_injections(group_notes, group_top, enriched,
                                       lib_children, RELAXED_TARGETS)

    to_write = [pl for pl in planned if not pl["already_present"]]
    logger.info("Notes de groupe à injecter : %d (déjà présentes : %d, sans cible : %d)",
                len(to_write), len(planned) - len(to_write), len(orphans))
    for pl in planned:
        flag = "SKIP(déjà)" if pl["already_present"] else "→"
        logger.info("  %s %-9s %-40s :: %s", flag, pl["target"],
                    (pl["group_titre"] or "")[:40], pl["extrait"])
    for o in orphans:
        logger.warning("  SANS CIBLE %-40s :: %s", (o["titre"] or "")[:40], o["extrait"])

    if not args.apply:
        logger.info("\nDRY-RUN : aucune écriture. Relancer avec --apply --backup FILE.")
        return 0

    args.backup.write_text(json.dumps(group_notes, ensure_ascii=False, indent=2))
    logger.info("Sauvegarde des %d notes de groupe : %s", len(group_notes), args.backup)
    created = 0
    for pl in to_write:
        key = post_note(user_id, pl["target"], pl["note_html"], api_key)
        created += 1
        logger.info("  créé note %s sur %s (%s)", key, pl["target"],
                    (pl["group_titre"] or "")[:40])
    logger.info("Notes créées : %d", created)
    return 0


if __name__ == "__main__":
    sys.exit(main())
