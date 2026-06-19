"""Lier les versions multiples d'une même œuvre en Zotero Related items.

Après dédoublonnage, des notices distinctes décrivent la même œuvre sous
plusieurs formes (preprint/article, traductions, revue + chapitre). On ne les
fusionne pas (fichiers distincts) ; on pose des relations `dc:relation`
bidirectionnelles pour les rattacher. Opération non destructive et réversible.

Dry-run par défaut : écrit le plan, n'écrit rien. `--apply` exécute.
"""

import argparse
import json
import logging
import re
import urllib.error
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("zotero_relate")

API = "https://api.zotero.org"
DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_PLAN = Path("outputs/relate_plan.json")
_PUNCT = re.compile(r"[\s\W_]+")


def normalize_title(title: str | None) -> str:
    """Titre comparable : minuscules, ponctuation/espaces réduits."""
    return _PUNCT.sub(" ", (title or "").lower()).strip()


def first_author(item: dict) -> str:
    for c in item.get("data", {}).get("creators", []):
        name = (c.get("lastName") or c.get("name") or "").strip().lower()
        if name:
            return name
    return ""


def group_versions(items: list[dict]) -> list[list[str]]:
    """Groupes (≥2) de notices partageant titre normalisé + 1er auteur.

    Garde-fou : on écarte un groupe dont deux membres partagent la même clé
    d'archive — c'est un doublon résiduel (à fusionner), pas des versions
    distinctes à relier.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for it in items:
        t = normalize_title(it.get("data", {}).get("title"))
        if not t:
            continue
        groups.setdefault((t, first_author(it)), []).append(it)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        keys = [rz.extract_archive_key(m.get("data", {}).get("url")) for m in members]
        nz = [k for k in keys if k]
        if len(nz) != len(set(nz)):  # collision de clé d'archive -> doublon résiduel
            continue
        out.append(sorted(m["key"] for m in members))
    return out


def item_uri(uid: str, key: str) -> str:
    return f"http://zotero.org/users/{uid}/items/{key}"


def relation_targets(uid: str, group: list[str]) -> dict[str, list[str]]:
    """Pour chaque clé du groupe, les URI des autres membres (lien bidirectionnel)."""
    return {k: [item_uri(uid, o) for o in group if o != k] for k in group}


def build_plan(items: list[dict], uid: str | None) -> dict:
    groups = group_versions(items)
    return {
        "groupes": len(groups),
        "notices_concernees": sum(len(g) for g in groups),
        "plans": [{"cles": g,
                   "relations": relation_targets(uid or "UID", g)} for g in groups],
    }


def _current_relations(uid: str, key: str, api_key: str) -> tuple[dict, int]:
    data, _ = rz._get(f"{API}/users/{uid}/items/{key}", api_key)
    return data["data"].get("relations", {}) or {}, data["version"]


def apply_plan(uid: str, plan: dict, api_key: str) -> dict:
    done = {"relations_posees": 0, "errors": []}
    for p in plan["plans"]:
        for key, uris in p["relations"].items():
            try:
                rel, ver = _current_relations(uid, key, api_key)
                existing = set(rel.get("dc:relation", []) if isinstance(
                    rel.get("dc:relation"), list) else
                    ([rel["dc:relation"]] if rel.get("dc:relation") else []))
                merged = sorted(existing | set(uris))
                if merged == sorted(existing):
                    continue
                rel["dc:relation"] = merged
                _write_item(uid, key, ver, {"relations": rel}, api_key)
                done["relations_posees"] += 1
            except urllib.error.HTTPError as e:  # noqa: PERF203
                done["errors"].append(f"{key}: HTTP {e.code}")
    return done


def _write_item(uid: str, key: str, version: int, body: dict, api_key: str) -> int:
    import urllib.request
    headers = {"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
               "Content-Type": "application/json",
               "If-Unmodified-Since-Version": str(version)}
    req = urllib.request.Request(f"{API}/users/{uid}/items/{key}",
                                 data=json.dumps(body).encode(),
                                 method="PATCH", headers=headers)
    with rz.urlopen_retry(req) as resp:
        return resp.status


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--backup", type=Path, default=None)
    p.add_argument("--items-json", type=Path, default=None)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if args.items_json:
        items = json.loads(args.items_json.read_text())
        uid = None
    else:
        if not api_key:
            raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
        uid = rz.fetch_user_id(api_key)
        items = rz.fetch_top_items(f"users/{uid}", api_key)

    plan = build_plan(items, uid)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    logger.info("Groupes à relier : %d (%d notices)", plan["groupes"],
                plan["notices_concernees"])
    logger.info("Plan écrit : %s", args.output)

    if not args.apply:
        logger.info("DRY-RUN — aucune écriture. Relancer avec --apply.")
        return
    if not args.backup:
        raise SystemExit("--apply exige --backup.")
    backup_items = rz.fetch_top_items(f"users/{uid}", api_key)
    args.backup.write_text(json.dumps(backup_items, ensure_ascii=False))
    logger.info("Sauvegarde : %d notices → %s", len(backup_items), args.backup)
    done = apply_plan(uid, plan, api_key)
    logger.info("Relations posées : %d, erreurs %d",
                done["relations_posees"], len(done["errors"]))


if __name__ == "__main__":
    main()
