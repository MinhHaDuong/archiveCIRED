"""Réconcilier doc_index.json avec le catalogue Zotero distant existant.

Le catalogue Zotero (bibliothèque perso + groupe Recueil_CIRED) référence les
PDF numérisés par leur URL sur inari.centre-cired.fr, dont le *basename* est le
nom de fichier d'archive (ex: CIR_SAC_0317.pdf, ENPC00_AR_LEESU_0012.pdf). Ce
nom est la clé de jointure avec nos `fichiers[].fichier` dans doc_index.json.

Le script produit un rapport de réconciliation :
  - documents de notre index déjà catalogués dans Zotero (match par clé)
  - documents absents du catalogue (à ajouter)
  - notices Zotero non rattachées à un de nos documents
  - ventilation par fonds et qualité de métadonnées

Sans réseau (fonctions pures) il reste testable ; la collecte Zotero utilise la
seule lib standard (urllib) — pas de dépendance externe.
"""

import argparse
import json
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("reconcile_zotero")

API = "https://api.zotero.org"
DEFAULT_GROUP_ID = "2511149"  # groupe privé "Recueil_CIRED"
DEFAULT_ENV = Path.home() / ".config/keys/zotero-archive-cired.env"
DEFAULT_DOC_INDEX = Path("outputs/doc_index.json")
DEFAULT_REPORT = Path("outputs/reconcile_report.json")

# Clé d'archive : CIR_SAC_0317, CIR_GOD_0052, ENPC00_AR_LEESU_0012, …
KEY_RE = re.compile(r"(CIR_[A-Z]+_\d+|ENPC\d*_[A-Z]+_LEESU_\d+)")


def extract_archive_key(text: str | None) -> str | None:
    """Extrait la clé d'archive normalisée d'un chemin, d'une URL ou d'un nom.

    >>> extract_archive_key("TDM/1970_CIR_SAC_0317.pdf")
    'CIR_SAC_0317'
    >>> extract_archive_key("https://x/docs/ENPC00_AR_LEESU_0012.PDF")
    'ENPC00_AR_LEESU_0012'
    >>> extract_archive_key("Godard-OCDE-libre.pdf") is None
    True
    """
    if not text:
        return None
    m = KEY_RE.search(text)
    return m.group(1) if m else None


def doc_keys(doc: dict) -> set[str]:
    """Toutes les clés d'archive trouvées dans les fichiers d'un document."""
    keys = set()
    for f in doc.get("fichiers", []):
        k = extract_archive_key(f.get("fichier"))
        if k:
            keys.add(k)
    return keys


def fonds_of(key: str) -> str:
    """Le fonds d'une clé : CIR_SAC, CIR_GOD, ENPC_LEESU, …"""
    if key.startswith("ENPC"):
        return "ENPC_LEESU"
    parts = key.split("_")
    return f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else key


def classify(docs: list[dict], zotero_keys: set[str]) -> dict:
    """Réconcilie les documents de l'index avec les clés présentes dans Zotero.

    Retourne un rapport sérialisable : compteurs, ventilation par fonds, et
    listes d'ids pour les documents non catalogués et les clés Zotero orphelines.
    """
    matched_docs, gap_docs, no_key_docs = [], [], []
    matched_keys: set[str] = set()
    by_fonds: dict[str, dict[str, int]] = {}

    for doc in docs:
        keys = doc_keys(doc)
        if not keys:
            no_key_docs.append(doc["id"])
            continue
        hit = keys & zotero_keys
        for k in keys:
            f = fonds_of(k)
            by_fonds.setdefault(f, {"index": 0, "catalogue": 0})
            by_fonds[f]["index"] += 1
            if k in zotero_keys:
                by_fonds[f]["catalogue"] += 1
        if hit:
            matched_docs.append(doc["id"])
            matched_keys |= hit
        else:
            gap_docs.append({"id": doc["id"], "cles": sorted(keys),
                             "annee": doc.get("annee"), "titre": doc.get("titre")})

    orphan_keys = sorted(zotero_keys - matched_keys)
    return {
        "total_docs": len(docs),
        "docs_catalogues": len(matched_docs),
        "docs_a_ajouter": len(gap_docs),
        "docs_sans_cle_archive": len(no_key_docs),
        "cles_zotero_totales": len(zotero_keys),
        "cles_zotero_orphelines": len(orphan_keys),
        "par_fonds": dict(sorted(by_fonds.items())),
        "liste_docs_a_ajouter": gap_docs,
        "liste_docs_sans_cle": no_key_docs,
        "liste_cles_orphelines": orphan_keys,
    }


# --- collecte Zotero (réseau, non testé en unitaire) ---------------------------

def load_env(path: Path) -> dict[str, str]:
    """Lit un fichier KEY=VALUE en nettoyant guillemets et espaces parasites."""
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"").strip()
    return env


def urlopen_retry(req: urllib.request.Request, tries: int = 5):
    """urlopen avec respect du rate-limiting Zotero (429/503 + Retry-After)."""
    delay = 2
    for attempt in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                wait = int(e.headers.get("Retry-After") or delay)
                logger.warning("rate-limit %s, pause %ss…", e.code, wait)
                time.sleep(wait)
                delay *= 2
                continue
            raise


def _get(url: str, api_key: str) -> tuple[list, int]:
    """GET Zotero -> (objets json, Total-Results). Lève sur erreur HTTP."""
    req = urllib.request.Request(url, headers={"Zotero-API-Key": api_key,
                                               "Zotero-API-Version": "3"})
    with urlopen_retry(req) as resp:
        total = int(resp.headers.get("Total-Results", 0))
        return json.loads(resp.read().decode()), total


def fetch_user_id(api_key: str) -> str:
    """ID numérique de l'utilisateur (le fichier env ne contient que le login)."""
    data, _ = _get(f"{API}/keys/current", api_key)
    return str(data["userID"])


def fetch_top_items(library: str, api_key: str) -> list[dict]:
    """Toutes les notices top-level d'une bibliothèque (paginé, 100/page)."""
    items, start = [], 0
    while True:
        page, total = _get(
            f"{API}/{library}/items/top?limit=100&start={start}", api_key)
        items.extend(page)
        start += 100
        if start >= total or not page:
            break
    return items


def zotero_keys_from_items(items: list[dict]) -> set[str]:
    """Clés d'archive extraites des URLs des notices."""
    keys = set()
    for it in items:
        k = extract_archive_key(it.get("data", {}).get("url"))
        if k:
            keys.add(k)
    return keys


def collect_zotero(env_path: Path, group_id: str) -> tuple[set[str], dict]:
    """Collecte les clés (perso + groupe) et une méta de provenance."""
    env = load_env(env_path)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {env_path}")
    user_id = fetch_user_id(api_key)
    perso = fetch_top_items(f"users/{user_id}", api_key)
    groupe = fetch_top_items(f"groups/{group_id}", api_key)
    meta = {"notices_perso": len(perso), "notices_groupe": len(groupe)}
    keys = zotero_keys_from_items(perso) | zotero_keys_from_items(groupe)
    meta["cles_distinctes"] = len(keys)
    return keys, meta


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--doc-index", type=Path, default=DEFAULT_DOC_INDEX)
    p.add_argument("--env", type=Path, default=DEFAULT_ENV)
    p.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    p.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--zotero-keys", type=Path, default=None,
                   help="JSON de clés déjà collectées (hors-ligne, sans réseau)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    docs = json.loads(args.doc_index.read_text())
    if args.zotero_keys:
        zkeys = set(json.loads(args.zotero_keys.read_text()))
        meta = {"source": str(args.zotero_keys)}
    else:
        zkeys, meta = collect_zotero(args.env, args.group_id)

    report = {"zotero": meta, **classify(docs, zkeys)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    logger.info("Documents index : %d", report["total_docs"])
    logger.info("  déjà catalogués Zotero : %d", report["docs_catalogues"])
    logger.info("  à ajouter (clé absente) : %d", report["docs_a_ajouter"])
    logger.info("  sans clé d'archive      : %d", report["docs_sans_cle_archive"])
    logger.info("Clés Zotero orphelines    : %d", report["cles_zotero_orphelines"])
    logger.info("Rapport écrit : %s", args.output)


if __name__ == "__main__":
    main()
