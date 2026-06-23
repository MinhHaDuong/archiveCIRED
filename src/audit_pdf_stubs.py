"""Auditer l'autonomie des PDF de la bibliothèque Zotero My Library.

Constat (juin 2026) : sur 764 notices, presque tous les attachements
`imported_file` sont des *coquilles vides* — la fiche d'attachement existe
(nom de fichier, type MIME) mais le PDF n'a jamais été téléversé dans le
stockage Zotero (`md5` absent). Ils proviennent de copies inter-bibliothèques
(groupe 329932 aujourd'hui inaccessible, groupe Recueil_CIRED 2511149) qui ne
transportent pas les octets du fichier.

Ce script apparie chaque stub à son fichier réel dans l'archive physique via
`file_index.json` (clé = basename), pour produire la worklist de téléversement
qui rendra la bibliothèque autonome — sans dépendre du groupe 329932 disparu ni
d'inari.centre-cired.fr.

Sortie : `outputs/pdf_stub_worklist.json` (+ .md), classée par fonds, avec le
sous-lot des stubs introuvables à normaliser.

La collecte Zotero réutilise les helpers de `reconcile_zotero` (lib standard
uniquement, urllib). L'appariement est une fonction pure, testable hors réseau.
"""

import argparse
import json
import logging
import os
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("audit_pdf_stubs")

DEFAULT_ENV = rz.DEFAULT_ENV
DEFAULT_FILE_INDEX = Path("outputs/file_index.json")
DEFAULT_REPORT = Path("outputs/pdf_stub_worklist.json")
DEAD_GROUP = "329932"  # groupe source du catalogue inari, désormais 404


def fetch_all_items(library: str, api_key: str) -> list[dict]:
    """Toutes les notices d'une bibliothèque, attachements compris (paginé)."""
    items, start = [], 0
    while True:
        page, total = rz._get(
            f"{rz.API}/{library}/items?limit=100&start={start}", api_key)
        items.extend(page)
        start += 100
        if start >= total or not page:
            break
    return items


def fonds_of(filename: str) -> str:
    """Préfixe de fonds déduit du nom de fichier."""
    for p in ("CIR_SAC", "CIR_GOD", "CIR_HOU", "CIR_GEN", "LEESU"):
        if p in filename:
            return p
    return "AUTRE"


def match_stubs(stubs: list[dict], file_index: list[dict]) -> dict:
    """Apparie les stubs aux fichiers d'archive (fonction pure).

    Retourne un dict {exact, radical, introuvable} de listes appariées.
    """
    by_base = {os.path.basename(r["fichier"]): r["fichier"] for r in file_index}
    by_stem = {os.path.splitext(os.path.basename(r["fichier"]))[0]: r["fichier"]
               for r in file_index}
    out: dict[str, list] = {"exact": [], "radical": [], "introuvable": []}
    for s in stubs:
        name = s.get("filename", "")
        stem = os.path.splitext(name)[0]
        rec = {"key": s.get("key"), "parent": s.get("parentItem"),
               "filename": name, "fonds": fonds_of(name)}
        if name in by_base:
            rec["archive"] = by_base[name]
            out["exact"].append(rec)
        elif stem in by_stem:
            rec["archive"] = by_stem[stem]
            out["radical"].append(rec)
        else:
            out["introuvable"].append(rec)
    return out


def source_group(att: dict) -> str | None:
    """Groupe source d'une copie inter-bibliothèque (relation owl:sameAs)."""
    import re
    s = att.get("relations", {}).get("owl:sameAs", "")
    if isinstance(s, list):
        s = " ".join(s)
    m = re.search(r"groups/(\d+)", s or "")
    return m.group(1) if m else None


def build_worklist(items: list[dict], file_index: list[dict]) -> dict:
    """Construit la worklist depuis les notices Zotero et l'index d'archive."""
    atts = [it["data"] for it in items
            if it["data"].get("itemType") == "attachment"]
    tops = [it for it in items
            if it["data"].get("itemType") != "attachment"
            and not it["data"].get("parentItem")]
    imported = [a for a in atts if a.get("linkMode") == "imported_file"]
    stubs = [a for a in imported if not a.get("md5")]
    with_file = [a for a in imported if a.get("md5")]
    matched = match_stubs(stubs, file_index)
    by_fonds: dict[str, int] = {}
    for rec in matched["exact"] + matched["radical"]:
        by_fonds[rec["fonds"]] = by_fonds.get(rec["fonds"], 0) + 1
    return {
        "totaux": {
            "notices_top_level": len(tops),
            "attachements_imported_file": len(imported),
            "pdf_reels_televerse": len(with_file),
            "stubs_sans_fichier": len(stubs),
            "stubs_du_groupe_mort_329932": sum(
                source_group(a) == DEAD_GROUP for a in stubs),
            "apparies_exact": len(matched["exact"]),
            "apparies_radical": len(matched["radical"]),
            "introuvables": len(matched["introuvable"]),
        },
        "par_fonds": dict(sorted(by_fonds.items())),
        "a_televerser": matched["exact"] + matched["radical"],
        "a_normaliser": matched["introuvable"],
    }


def write_markdown(worklist: dict, path: Path) -> None:
    """Résumé lisible de la worklist."""
    t = worklist["totaux"]
    lines = [
        "# Worklist — téléverser les vrais PDF dans Zotero My Library",
        "",
        "Généré par `src/audit_pdf_stubs.py`. Données : `pdf_stub_worklist.json`.",
        "",
        "## Constat",
        "",
        f"- Notices top-level : **{t['notices_top_level']}**",
        f"- Attachements `imported_file` : {t['attachements_imported_file']}",
        f"- PDF réellement téléversés (`md5`) : **{t['pdf_reels_televerse']}**",
        f"- Coquilles vides (stubs sans fichier) : **{t['stubs_sans_fichier']}** "
        f"(dont {t['stubs_du_groupe_mort_329932']} copiés du groupe 329932, 404)",
        "",
        "## Récupérables depuis l'archive physique",
        "",
        f"- Appariés au nom exact : **{t['apparies_exact']}**",
        f"- Appariés par radical (extension différente) : {t['apparies_radical']}",
        f"- Introuvables (à normaliser) : **{t['introuvables']}**",
        "",
        "### Ventilation par fonds (appariés)",
        "",
        "| Fonds | PDF à téléverser |",
        "|---|---|",
    ]
    for fonds, n in worklist["par_fonds"].items():
        lines.append(f"| {fonds} | {n} |")
    lines += [
        "",
        "## Reproduire",
        "",
        "```bash",
        "uv run python src/audit_pdf_stubs.py  # réseau + creds Zotero requis",
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV,
                        help="fichier d'environnement Zotero (clé API)")
    parser.add_argument("--file-index", type=Path, default=DEFAULT_FILE_INDEX,
                        help="index physique de l'archive")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT,
                        help="worklist JSON de sortie")
    args = parser.parse_args()

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
    user_id = rz.fetch_user_id(api_key)
    logger.info("Collecte My Library (users/%s)…", user_id)
    items = fetch_all_items(f"users/{user_id}", api_key)
    file_index = json.loads(args.file_index.read_text(encoding="utf-8"))

    worklist = build_worklist(items, file_index)
    args.output.write_text(
        json.dumps(worklist, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(worklist, args.output.with_suffix(".md"))

    t = worklist["totaux"]
    logger.info("PDF réels : %d / %d notices. Stubs : %d, dont %d récupérables "
                "depuis l'archive, %d à normaliser.",
                t["pdf_reels_televerse"], t["notices_top_level"],
                t["stubs_sans_fichier"],
                t["apparies_exact"] + t["apparies_radical"],
                t["introuvables"])
    logger.info("Écrit %s (+ .md)", args.output)


if __name__ == "__main__":
    main()
