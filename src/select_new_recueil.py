"""Sélectionner les documents *nouveaux* du recueil 50 ans CIRED (ticket 0018).

Le recueil d'Antonin est l'archive locale `attente/à dédoublonner avec ce qui
est déjà traité/` (110 fichiers, noms descriptifs `YYYY-NN-Auteur-titre.pdf`).
Un document y est *nouveau* — à ajouter au catalogue — si :

  1. son contenu n'est pas déjà dans le corpus (hash SHA-1 absent du reste de
     l'index : sinon c'est un simple renommage) ; ET
  2. son id `YYYY-NNN` (préfixe `YYYY-NN` zéro-paddé) est absent de `docs/`
     (sinon c'est un *autre scan* d'un document déjà connu).

Cette décision ne dépend PAS de la table `YYYY-NN`↔document d'Antonin qui
bloquait le ticket parent 0015 : « absent » se lit sur le fichier lui-même.

Sortie : buckets `deja_corpus`, `meilleur_scan`, `nouveau`, `id_non_standard`,
plus `ids_en_collision` (un même id porté par deux fichiers de contenu différent
— ex. `1975-019` ×2, deux articles au même numéro — à arbitrer à la main).

Fonctions pures, testables sans réseau ni accès disque.
"""

import argparse
import json
import logging
import os
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger("select_new_recueil")

DEFAULT_FILE_INDEX = Path("outputs/file_index.json")
DEFAULT_OUTPUT = Path("outputs/recueil_new_docs.json")
RECUEIL_DIR_MARK = "dédoublonner"

# Préfixe d'id du recueil : « 1973-9 », « 1975 15 », « 2004 127 » -> YYYY-NNN.
_PREFIX = re.compile(r"^(\d{4})[-\s]+(\d{1,3})\b")
# Id canonique YYYY-NNN dans un nom de fichier docs/.
_DOCID = re.compile(r"(\d{4}-\d{3})")


def parse_recueil_id(filename: str) -> str | None:
    """Id `YYYY-NNN` zéro-paddé depuis un nom de fichier du recueil, ou None.

    >>> parse_recueil_id("1975 15-Hourcade.pdf")
    '1975-015'
    >>> parse_recueil_id("PAS-DANS-LA-LISTE-1975 elements.pdf") is None
    True
    """
    m = _PREFIX.match(os.path.basename(filename))
    return f"{m.group(1)}-{int(m.group(2)):03d}" if m else None


def corpus_hashes(file_index: list[dict], recueil_paths: set[str]) -> set[str]:
    """Hashes présents dans le corpus *hors* recueil (pour détecter les renommages)."""
    return {e["hash"] for e in file_index if e["fichier"] not in recueil_paths}


def docs_ids(file_index: list[dict]) -> set[str]:
    """Ids `YYYY-NNN` déjà présents sous `docs/`."""
    ids = set()
    for e in file_index:
        if e["fichier"].startswith("docs/"):
            m = _DOCID.search(os.path.basename(e["fichier"]))
            if m:
                ids.add(m.group(1))
    return ids


def recueil_entries(file_index: list[dict]) -> list[dict]:
    """Entrées de l'index appartenant au recueil (dossier `à dédoublonner`)."""
    return [e for e in file_index if RECUEIL_DIR_MARK in e["fichier"]]


def classify_recueil(att: list[dict], corpus_hashes: set[str],
                     docids: set[str]) -> dict:
    """Range chaque fichier du recueil dans son bucket.

    `nouveau` = contenu inédit ET id absent de docs/. `meilleur_scan` = contenu
    inédit mais id déjà connu. `deja_corpus` = hash déjà présent ailleurs.
    `id_non_standard` = contenu inédit sans préfixe `YYYY-NN` exploitable.
    """
    out = {"deja_corpus": [], "meilleur_scan": [], "nouveau": [],
           "id_non_standard": [], "ids_en_collision": []}
    for e in att:
        path = e["fichier"]
        if e["hash"] in corpus_hashes:
            out["deja_corpus"].append(path)
            continue
        cid = parse_recueil_id(path)
        if cid is None:
            out["id_non_standard"].append(path)
        elif cid in docids:
            out["meilleur_scan"].append({"id": cid, "fichier": path, "hash": e["hash"]})
        else:
            out["nouveau"].append({"id": cid, "fichier": path, "hash": e["hash"]})
    new_ids = Counter(d["id"] for d in out["nouveau"])
    out["ids_en_collision"] = sorted(i for i, n in new_ids.items() if n > 1)
    return out


def build_report(file_index: list[dict]) -> dict:
    """Rapport complet de sélection depuis l'index de fichiers."""
    att = recueil_entries(file_index)
    paths = {e["fichier"] for e in att}
    r = classify_recueil(att, corpus_hashes(file_index, paths), docs_ids(file_index))
    return {
        "recueil_total": len(att),
        "n_deja_corpus": len(r["deja_corpus"]),
        "n_meilleur_scan": len(r["meilleur_scan"]),
        "n_nouveau": len(r["nouveau"]),
        "n_id_non_standard": len(r["id_non_standard"]),
        **r,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file-index", type=Path, default=DEFAULT_FILE_INDEX)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    file_index = json.loads(args.file_index.read_text())
    report = build_report(file_index)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    logger.info("Recueil : %d fichiers", report["recueil_total"])
    logger.info("  déjà dans le corpus (renommage) : %d", report["n_deja_corpus"])
    logger.info("  meilleur scan (id connu)        : %d", report["n_meilleur_scan"])
    logger.info("  NOUVEAU (à ajouter)             : %d", report["n_nouveau"])
    logger.info("  id non standard (à arbitrer)    : %d", report["n_id_non_standard"])
    if report["ids_en_collision"]:
        logger.info("  ids en collision (même n° archive): %s",
                    ", ".join(report["ids_en_collision"]))
    logger.info("Rapport écrit : %s", args.output)


if __name__ == "__main__":
    main()
