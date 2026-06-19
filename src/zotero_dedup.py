"""Dédoublonner My Library Zotero : fusionner les générations 2015 et 2020.

Chaque document d'archive existe en double : une notice 2020 (métadonnées
rafraîchies + URL inari, sans PDF) et une notice 2015 (PDF attaché, métadonnées
anciennes). Ce script garde la notice la plus récente comme maître, y re-parente
le PDF de sa jumelle, puis supprime les jumelles.

Invariant de sûreté : on ne supprime une jumelle qu'après avoir vérifié que le
PDF est rattaché au maître — le fichier stocké survit tant que sa pièce jointe
survit. Re-parenter AVANT de supprimer.

Dry-run par défaut : écrit le plan, n'écrit rien dans Zotero. `--apply` exécute.
"""

import argparse
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("zotero_dedup")

API = "https://api.zotero.org"
DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_PLAN = Path("outputs/dedup_plan.json")


# --- logique pure (testable, sans réseau) -------------------------------------

# Champs de contrôle/système jamais fusionnés depuis la jumelle.
SKIP_FIELDS = {
    "key", "version", "itemType", "dateAdded", "dateModified", "relations",
    "collections", "tags", "parentItem", "note", "md5", "mtime", "linkMode",
    "contentType", "filename", "charset", "accessDate", "url", "title",
    "pages", "date",  # gérés par des règles dédiées
}


def item_year(item: dict) -> str:
    return (item.get("data", {}).get("dateAdded") or "")[:4]


def has_pdf(item: dict) -> bool:
    return (item.get("meta", {}).get("numChildren") or 0) > 0


def _empty(v) -> bool:
    return v in (None, "", [], {})


def richer_date(master_date, twin_date) -> bool:
    """La date 2015 est-elle plus riche : plage, incertitude, ou maître vide ?"""
    if _empty(twin_date):
        return False
    if _empty(master_date):
        return True
    t = str(twin_date)
    return any(mark in t for mark in (" - ", " – ", "–", "?", "["))


def merge_fields(master: dict, twins: list[dict]) -> dict:
    """Patch à appliquer au maître 2020 selon la politique de fusion.

    Politique : base 2020 ; `pages`←2015 ; `date`←2015 si plus riche ; tout champ
    vide du maître ← première valeur non vide d'une jumelle (2015 d'abord).
    Ne touche jamais aux champs de contrôle ni à un champ déjà rempli (hors
    pages/date). Retourne seulement les champs modifiés.
    """
    md = master["data"]
    older_first = sorted(twins, key=item_year)  # 2015 avant 2020
    patch: dict = {}

    for t in older_first:  # backfill des champs vides
        for f, v in t["data"].items():
            if f in SKIP_FIELDS or f in patch or _empty(v):
                continue
            if _empty(md.get(f)):
                patch[f] = v

    for t in older_first:  # pages ← 2015
        pv = t["data"].get("pages")
        if not _empty(pv) and pv != md.get("pages"):
            patch["pages"] = pv
            break

    for t in older_first:  # date ← 2015 si plus riche
        if richer_date(md.get("date"), t["data"].get("date")):
            patch["date"] = t["data"]["date"]
            break

    return patch


def choose_master(items: list[dict]) -> dict:
    """La notice la plus récente est maître (2020 > 2015) ; clé en tie-break."""
    return sorted(items, key=lambda it: (item_year(it), it["key"]))[-1]


def plan_for_key(key: str, items: list[dict]) -> dict:
    """Plan de fusion pour une clé d'archive : maître, re-parentage, suppressions."""
    master = choose_master(items)
    others = [it for it in items if it["key"] != master["key"]]
    reparent_from = None
    if not has_pdf(master):
        src = next((it for it in others if has_pdf(it)), None)
        reparent_from = src["key"] if src else None
    return {
        "key": key,
        "master": master["key"],
        "master_year": item_year(master),
        "master_version": master["version"],
        "master_has_pdf": has_pdf(master),
        "reparent_pdf_from": reparent_from,
        "merge_patch": merge_fields(master, others),
        "delete": [{"key": it["key"], "version": it["version"],
                    "year": item_year(it), "had_pdf": has_pdf(it)}
                   for it in others],
    }


def build_plan(items: list[dict]) -> dict:
    """Groupe par clé d'archive et plan les clés en doublon."""
    by_key: dict[str, list[dict]] = {}
    for it in items:
        k = rz.extract_archive_key(it.get("data", {}).get("url"))
        if k:
            by_key.setdefault(k, []).append(it)
    dup = {k: v for k, v in by_key.items() if len(v) > 1}
    plans = [plan_for_key(k, v) for k, v in sorted(dup.items())]
    n_delete = sum(len(p["delete"]) for p in plans)
    n_reparent = sum(1 for p in plans if p["reparent_pdf_from"])
    n_merge = sum(1 for p in plans if p["merge_patch"])
    champs = {}
    for p in plans:
        for f in p["merge_patch"]:
            champs[f] = champs.get(f, 0) + 1
    return {
        "cles_total": len(by_key),
        "cles_dupliquees": len(dup),
        "maitres": len(plans),
        "suppressions": n_delete,
        "reparentages_pdf": n_reparent,
        "maitres_enrichis": n_merge,
        "champs_fusionnes": dict(sorted(champs.items(), key=lambda kv: -kv[1])),
        "plans": plans,
    }


# --- réseau (non testé en unitaire) -------------------------------------------

def _write(method: str, url: str, api_key: str, version: int,
           body: dict | None = None) -> int:
    headers = {"Zotero-API-Key": api_key, "Zotero-API-Version": "3",
               "If-Unmodified-Since-Version": str(version)}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status


def find_pdf_child(uid: str, parent_key: str, api_key: str) -> dict | None:
    children, _ = rz._get(f"{API}/users/{uid}/items/{parent_key}/children", api_key)
    for c in children:
        d = c.get("data", {})
        if d.get("itemType") == "attachment" and d.get("contentType") == "application/pdf":
            return c
    return None


def master_has_attachment(uid: str, master_key: str, api_key: str) -> bool:
    return find_pdf_child(uid, master_key, api_key) is not None


def apply_plan(uid: str, plan: dict, api_key: str, limit: int | None) -> dict:
    """Exécute le plan. Re-parente le PDF puis supprime, en vérifiant l'invariant."""
    done = {"merged": 0, "reparented": 0, "deleted": 0, "skipped": 0, "errors": []}
    plans = plan["plans"][:limit] if limit else plan["plans"]
    for p in plans:
        try:
            if p["merge_patch"]:  # fusion des champs sur le maître AVANT suppression
                _write("PATCH", f"{API}/users/{uid}/items/{p['master']}",
                       api_key, p["master_version"], p["merge_patch"])
                done["merged"] += 1
            if p["reparent_pdf_from"]:
                att = find_pdf_child(uid, p["reparent_pdf_from"], api_key)
                if not att:
                    done["skipped"] += 1
                    done["errors"].append(f"{p['key']}: pas de PDF chez {p['reparent_pdf_from']}")
                    continue
                _write("PATCH", f"{API}/users/{uid}/items/{att['key']}",
                       api_key, att["version"], {"parentItem": p["master"]})
                done["reparented"] += 1
            # INVARIANT : le maître doit avoir un PDF avant toute suppression
            if not master_has_attachment(uid, p["master"], api_key):
                done["skipped"] += 1
                done["errors"].append(f"{p['key']}: maître sans PDF, suppressions annulées")
                continue
            for d in p["delete"]:
                _write("DELETE", f"{API}/users/{uid}/items/{d['key']}",
                       api_key, d["version"])
                done["deleted"] += 1
        except urllib.error.HTTPError as e:  # noqa: PERF203
            done["errors"].append(f"{p['key']}: HTTP {e.code}")
    return done


def dump_backup(uid: str, api_key: str, path: Path) -> int:
    items = rz.fetch_top_items(f"users/{uid}", api_key)
    path.write_text(json.dumps(items, ensure_ascii=False))
    return len(items)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    p.add_argument("--apply", action="store_true",
                   help="exécute la fusion (sinon dry-run)")
    p.add_argument("--limit", type=int, default=None,
                   help="ne traiter que les N premières clés (apply)")
    p.add_argument("--backup", type=Path, default=None,
                   help="dump JSON des notices avant apply")
    p.add_argument("--items-json", type=Path, default=None,
                   help="notices déjà collectées (hors-ligne)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key and not args.items_json:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")

    if args.items_json:
        items = json.loads(args.items_json.read_text())
        uid = None
    else:
        uid = rz.fetch_user_id(api_key)
        items = rz.fetch_top_items(f"users/{uid}", api_key)

    plan = build_plan(items)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    logger.info("Clés dupliquées : %d  → maîtres %d, suppressions %d, "
                "re-parentages PDF %d", plan["cles_dupliquees"], plan["maitres"],
                plan["suppressions"], plan["reparentages_pdf"])
    logger.info("Plan écrit : %s", args.output)

    if not args.apply:
        logger.info("DRY-RUN — aucune écriture. Relancer avec --apply pour exécuter.")
        return

    if not args.backup:
        raise SystemExit("--apply exige --backup (export de sauvegarde).")
    n = dump_backup(uid, api_key, args.backup)
    logger.info("Sauvegarde : %d notices → %s", n, args.backup)
    stamp = datetime.now(timezone.utc).isoformat()
    logger.info("APPLY %s (limit=%s)…", stamp, args.limit)
    done = apply_plan(uid, plan, api_key, args.limit)
    logger.info("Fusionnés %d, re-parentés %d, supprimés %d, ignorés %d, erreurs %d",
                done["merged"], done["reparented"], done["deleted"],
                done["skipped"], len(done["errors"]))
    for e in done["errors"][:20]:
        logger.warning("  %s", e)


if __name__ == "__main__":
    main()
