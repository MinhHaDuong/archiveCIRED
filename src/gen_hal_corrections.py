"""Construire les corrections HAL à partir du rapport d'enrichissement (0022).

Lit `outputs/enrich_hal_report.json` (produit par `enrich_hal.py`) et génère des
entrées au format `manual_corrections.json` (champ `set`), pour revue puis
écriture par `apply_corrections.py`.

Politique d'écriture (validée M. Ha-Duong) :
  - **halId** → ligne `HAL: <id>` ajoutée à l'`Extra` existant (jamais d'écrasement).
  - **champs vides** renseignés par HAL : DOI, revue, volume, numéro, date — ajoutés.
  - **pages** : exclues de l'auto-ajout (HAL parfois tronqué) → laissées en revue.
  - **divergences** : jamais écrites — listées pour revue manuelle.

Ne touche pas Zotero : produit un fichier de propositions à relire.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("gen_hal_corrections")

DEFAULT_REPORT = Path("outputs/enrich_hal_report.json")
DEFAULT_OUTPUT = Path("outputs/hal_corrections_proposals.json")
# Champs « vides → HAL » sûrs à ajouter automatiquement ; `pages` exclu (révision).
SAFE_ADD = {"DOI", "publicationTitle", "volume", "issue", "date"}


def extra_with_hal(current: str | None, hal_id: str) -> str | None:
    """`Extra` augmenté d'une ligne `HAL: <id>`, ou None si déjà présent/vide id."""
    if not hal_id:
        return None
    cur = current or ""
    if re.search(r"\bHAL:\s*" + re.escape(hal_id), cur) or hal_id in cur:
        return None
    return (cur + "\nHAL: " + hal_id).strip() if cur.strip() else "HAL: " + hal_id


def build_set(notice: dict, hal_id: str, add: dict) -> dict:
    """Champs Zotero à écrire : ligne HAL dans extra + ajouts sûrs (hors pages)."""
    s = {}
    ne = extra_with_hal(notice.get("extra", ""), hal_id)
    if ne is not None:
        s["extra"] = ne
    for f, v in (add or {}).items():
        if f in SAFE_ADD:
            s[f] = v
    return s


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--env", type=Path, default=rz.DEFAULT_ENV)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    report = json.loads(args.report.read_text())
    matched = [r for r in report["results"] if r.get("matched")]
    env = rz.load_env(args.env)
    api_key = env["ZOTERO_API_KEY"]
    uid = rz.fetch_user_id(api_key)
    logger.info("Appariées dans le rapport : %d", len(matched))

    proposals, skipped, page_reviews = [], 0, []
    for r in matched:
        key = r["key"]
        hal_id = r["matched"]["halId"]
        diff = r.get("diff", {})
        item, _ = rz._get(f"{rz.API}/users/{uid}/items/{key}", api_key)
        data = item["data"]
        set_fields = build_set(data, hal_id, diff.get("add", {}))
        if "pages" in diff.get("add", {}):
            page_reviews.append((key, diff["add"]["pages"]))
        if not set_fields:
            skipped += 1
            continue
        proposals.append({
            "key": key,
            "ref": f"{r['title'][:70]} — HAL {hal_id}",
            "source": f"enrich_hal.py (sim {r['matched']['title_sim']})",
            "set": set_fields,
            "note": f"halId {hal_id}. Divergences (revue, non écrites) : "
                    f"{list(diff.get('differ', {}).keys())}.",
        })

    args.output.write_text(json.dumps(proposals, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    logger.info("Propositions : %d (déjà à jour : %d) → %s",
                len(proposals), skipped, args.output)
    logger.info("Ajouts `pages` mis en revue (non auto) : %d", len(page_reviews))
    return 0


if __name__ == "__main__":
    sys.exit(main())
