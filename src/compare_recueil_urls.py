"""Comparer les fichiers PDF des paires « URL recueil non dupliquée ».

L'audit du miroir (`verify_recueil_mirror.py`) classe 54 notices en
`doc_equivalent` : le groupe Recueil_CIRED pointe une URL inari, et My Library
porte un document équivalent **sous une autre URL inari**. Ces deux URL vivent
dans deux buckets inari distincts :

  - recueil    : inari.centre-cired.fr/Wehurei6-recueil_50ans_CIRED/<nom>.pdf
  - numérisation: inari.centre-cired.fr/kCj0pHP0-CIRED_numerisation/.../docs/<clé>.pdf

Ce sont donc potentiellement **deux scans physiques différents** du même
contenu intellectuel (souvent : extrait ciblé de l'article côté recueil, scan du
volume entier côté numérisation). Avant toute décision, on documente :

  - les **deux URL** (préservées en versionné, indépendamment du sort du groupe),
  - la **comparaison des fichiers** : taille, date, et hash SHA-256 pour les
    paires de taille identique (preuve d'identité ou de différence).

Aucune écriture Zotero, aucune suppression. Lecture seule.
"""

import argparse
import hashlib
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

import reconcile_zotero as rz

logger = logging.getLogger("compare_recueil_urls")

DEFAULT_ENV = rz.DEFAULT_ENV
DEFAULT_GROUP_ID = rz.DEFAULT_GROUP_ID
DEFAULT_REPORT_IN = Path("outputs/verify_recueil_mirror_report.json")
DEFAULT_OUTPUT = Path("outputs/recueil_url_comparison.json")


def fetch_all_items(library: str, api_key: str) -> dict:
    """Map key -> data pour toutes les notices d'une bibliothèque (paginé)."""
    out: dict[str, dict] = {}
    start = 0
    while True:
        page, total = rz._get(
            f"{rz.API}/{library}/items?limit=100&start={start}", api_key)
        for it in page:
            out[it["key"]] = it["data"]
        start += 100
        if start >= total or not page:
            break
    return out


def head(url: str) -> dict:
    """HEAD inari : statut, taille, date. Ne lève pas (capture l'erreur)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            cl = r.headers.get("Content-Length")
            return {"status": r.status,
                    "size": int(cl) if cl else None,
                    "last_modified": r.headers.get("Last-Modified")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "size": None, "last_modified": None}
    except Exception as e:  # noqa: BLE001 — réseau best-effort
        return {"status": "ERR", "error": str(e)[:80],
                "size": None, "last_modified": None}


def sha256(url: str) -> str | None:
    """SHA-256 du contenu téléchargé en flux (None si erreur)."""
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            h = hashlib.sha256()
            for chunk in iter(lambda: r.read(1 << 20), b""):
                h.update(chunk)
            return h.hexdigest()
    except Exception as e:  # noqa: BLE001
        logger.warning("hash échoué %s : %s", url, e)
        return None


def classify(recueil: dict, mylib: dict) -> str:
    """Verdict de comparaison à partir des deux relevés HEAD."""
    if not recueil.get("url") or not mylib.get("url"):
        return "url_manquante"
    rs, ms = recueil["head"].get("size"), mylib["head"].get("size")
    if rs is None or ms is None:
        return "inatteignable"
    if rs == ms:
        return "taille_identique"
    return "taille_differente"


def compare_pairs(pairs: list[dict], group: dict, mylib: dict,
                  hash_identical: bool = True) -> list[dict]:
    """Construit la comparaison pour chaque paire doc_equivalent."""
    rows = []
    for d in pairs:
        ru = group.get(d["key"], {}).get("url", "")
        mu = mylib.get(d["matched"], {}).get("url", "")
        rec = {"url": ru, "head": head(ru) if ru else {}}
        myl = {"url": mu, "head": head(mu) if mu else {}}
        verdict = classify(rec, myl)
        row = {
            "annee": d.get("annee"),
            "titre": d.get("title"),
            "recueil_key": d["key"],
            "mylib_key": d["matched"],
            "url_recueil": ru,
            "url_mylib": mu,
            "taille_recueil": rec["head"].get("size"),
            "taille_mylib": myl["head"].get("size"),
            "date_recueil": rec["head"].get("last_modified"),
            "date_mylib": myl["head"].get("last_modified"),
            "verdict": verdict,
        }
        if verdict == "taille_identique" and hash_identical:
            hr, hm = sha256(ru), sha256(mu)
            row["sha256_recueil"] = hr
            row["sha256_mylib"] = hm
            row["fichiers_identiques"] = (hr is not None and hr == hm)
        rows.append(row)
        logger.info("%s | %s | %s", verdict, d.get("annee"),
                    (d.get("title") or "")[:50])
    return rows


def write_markdown(rows: list[dict], path: Path) -> None:
    """Résumé lisible : compte par verdict + table des deux URL."""
    import collections
    counts = collections.Counter(r["verdict"] for r in rows)
    ident = sum(1 for r in rows if r.get("fichiers_identiques") is True)
    diff_hash = sum(1 for r in rows if r.get("fichiers_identiques") is False)
    lines = [
        "# Comparaison des URL « recueil non dupliquée » (54 paires)",
        "",
        "Généré par `src/compare_recueil_urls.py`. Données : "
        "`recueil_url_comparison.json`. **Lecture seule, aucune décision.**",
        "",
        "Chaque notice du groupe Recueil_CIRED pointe une URL inari ; My Library "
        "porte un document équivalent sous **une autre URL inari** (deux buckets "
        "distincts). On compare les deux fichiers, sans en supprimer aucun.",
        "",
        "## Synthèse",
        "",
        f"- **Fichiers distincts** (taille différente, ou SHA-256 différent) : "
        f"**{counts.get('taille_differente', 0) + diff_hash}**",
        f"- Vrais doublons (SHA-256 identiques) : **{ident}** "
        f"sur {counts.get('taille_identique', 0)} de taille égale",
        f"- Sans PDF des deux côtés (métadonnée seule) : "
        f"{counts.get('url_manquante', 0)} · inatteignable : "
        f"{counts.get('inatteignable', 0)}",
        "",
        "**Conséquence pour 0025** : les fichiers distincts ne sont PAS de simples "
        "doublons — souvent un extrait d'article côté recueil contre le scan du "
        "volume entier côté My Library, parfois un meilleur scan côté recueil. "
        "Supprimer le groupe sans les **réconcilier au préalable** (rattacher "
        "l'URL/fichier recueil à la notice My Library) **détruirait ces fichiers** "
        "→ **perte d'information, cause de NO-GO** s'ajoutant aux pertes "
        "métadonnées de l'audit. Les vrais doublons (hash identique), eux, ne "
        "posent pas de perte de fichier. Aucune copie n'est supprimée ici.",
        "",
        "## Détail",
        "",
        "| Année | Titre | Recueil (o) | My Library (o) | Verdict |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (x["annee"] or "")):
        sr = f"{r['taille_recueil']:,}" if r["taille_recueil"] else "—"
        sm = f"{r['taille_mylib']:,}" if r["taille_mylib"] else "—"
        v = r["verdict"]
        if r.get("fichiers_identiques") is True:
            v = "identique (hash)"
        elif r.get("fichiers_identiques") is False:
            v = "différent (hash)"
        lines.append(
            f"| {r['annee']} | {(r['titre'] or '')[:46]} | {sr} | {sm} | {v} |")
    lines += [
        "",
        "## URL préservées",
        "",
        "Les deux URL de chaque paire sont enregistrées dans le JSON "
        "(`url_recueil`, `url_mylib`) — donc conservées en versionné même si le "
        "groupe Recueil_CIRED venait un jour à être supprimé.",
        "",
        "## Reproduire",
        "",
        "```bash",
        "uv run python src/compare_recueil_urls.py  # réseau + creds Zotero",
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_IN,
                        help="rapport d'audit (source des paires doc_equivalent)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-hash", action="store_true",
                        help="ne pas hasher les paires de taille identique")
    args = parser.parse_args()

    env = rz.load_env(args.env)
    api_key = env.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit(f"ZOTERO_API_KEY absent de {args.env}")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    pairs = report["doc_equivalent_list"]
    user_id = rz.fetch_user_id(api_key)
    logger.info("Collecte groupe %s et My Library…", args.group_id)
    group = fetch_all_items(f"groups/{args.group_id}", api_key)
    mylib = fetch_all_items(f"users/{user_id}", api_key)

    rows = compare_pairs(pairs, group, mylib, hash_identical=not args.no_hash)
    args.output.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(rows, args.output.with_suffix(".md"))
    logger.info("Écrit %s (+ .md) — %d paires", args.output, len(rows))


if __name__ == "__main__":
    main()
