"""Normaliser volume, numéro (issue) et pages dans toutes les notices My Library.

Pour chaque notice dont un de ces champs contient une valeur sale, génère un
PATCH vers la valeur normalisée :

  volume / issue  :  "vol. 8" → "8",  "n°316" → "316"
  pages           :  "417-438" → "417–438"  (tiret simple → tiret long)

Les décomptes ("22 p.", "31 p.") ne sont pas auto-corrigés car la valeur
correcte (intervalle réel) est inconnue — ils sont signalés séparément.

Dry-run par défaut. `--apply` exige `--backup FILE`.
"""

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diff_recueil as dr  # noqa: E402  (_norm_number, _norm_pages)
import reconcile_zotero as rz  # noqa: E402

logger = logging.getLogger("normalize_biblio_fields")

DEFAULT_ENV = rz.DEFAULT_ENV
FIELDS = ("volume", "issue", "pages")


def dirty_fields(data: dict) -> dict[str, tuple[str, str]]:
    """Champs dont la valeur normalisée diffère de la valeur brute.

    Retourne {champ: (valeur_brute, valeur_normalisée)}.
    Exclut les décomptes de pages ("31 p.") : auto-correction impossible.
    """
    out = {}
    for f in FIELDS:
        raw = (data.get(f) or "").strip()
        if not raw:
            continue
        if f in ("volume", "issue"):
            norm = dr._norm_number(raw)
        else:
            norm = dr._norm_pages(raw)
        if norm != raw:
            out[f] = (raw, norm)
    return out


def page_counts(data: dict) -> list[str]:
    """Valeurs de pages qui ressemblent à un décompte ('31 p.') — à traiter manuellement."""
    import re
    raw = (data.get("pages") or "").strip()
    if raw and re.search(r"\d+\s*p\.?$", raw, re.IGNORECASE) and not re.search(r"\d+\s*[-–]", raw):
        return [raw]
    return []


def plan(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(patches, signalements_decompte) à partir des notices My Library.

    patches : [{key, version, title, fields: {f: (raw, norm)}}]
    signalements : [{key, title, pages}]
    """
    patches, flags = [], []
    for it in items:
        d = it["data"]
        dirty = dirty_fields(d)
        if dirty:
            patches.append({"key": d["key"], "version": d["version"],
                            "title": (d.get("title") or "")[:70],
                            "fields": dirty})
        counts = page_counts(d)
        if counts:
            flags.append({"key": d["key"],
                          "title": (d.get("title") or "")[:70],
                          "pages": counts[0]})
    return patches, flags


def _patch(uid: str, key: str, version: int, fields: dict, api_key: str) -> None:
    body = json.dumps(fields).encode()
    req = urllib.request.Request(
        f"{rz.API}/users/{uid}/items/{key}", data=body, method="PATCH",
        headers={"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
                 "Content-Type": "application/json",
                 "If-Unmodified-Since-Version": str(version)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"PATCH {key}: HTTP {resp.status}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--apply", action="store_true",
                   help="écrire réellement (sinon dry-run)")
    p.add_argument("--backup", type=Path, default=None,
                   help="sauvegarde JSON des notices avant écriture (requis avec --apply)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.apply and not args.backup:
        raise SystemExit("--apply exige --backup FILE")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")

    uid = rz.fetch_user_id(api_key)
    logger.info("Collecte des notices My Library…")
    items = rz.fetch_top_items(f"users/{uid}", api_key)
    logger.info("%d notices récupérées.", len(items))

    patches, flags = plan(items)

    logger.info("\nNotices à normaliser : %d", len(patches))
    for pt in patches:
        logger.info("  %-9s %s", pt["key"], pt["title"])
        for f, (raw, norm) in pt["fields"].items():
            logger.info("    %-6s  %r → %r", f, raw, norm)

    if flags:
        logger.info("\nDécomptes de pages à corriger manuellement : %d", len(flags))
        for fl in flags:
            logger.info("  %-9s %-50s  pages=%r", fl["key"], fl["title"], fl["pages"])

    if not args.apply:
        logger.info("\nDRY-RUN — rien écrit. Relancer avec --apply --backup FILE.")
        return 0

    args.backup.write_text(
        json.dumps([it for it in items
                    if it["data"]["key"] in {pt["key"] for pt in patches}],
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    logger.info("\nSauvegarde : %s (%d notices)", args.backup, len(patches))

    ok = ko = 0
    for pt in patches:
        norm_fields = {f: norm for f, (_, norm) in pt["fields"].items()}
        try:
            _patch(uid, pt["key"], pt["version"], norm_fields, api_key)
            logger.info("OK   %s", pt["key"])
            ok += 1
        except Exception as exc:
            logger.error("ÉCHEC %s : %s", pt["key"], exc)
            ko += 1

    logger.info("\nNormalisées : %d  Échecs : %d", ok, ko)
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
