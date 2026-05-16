#!/usr/bin/env python3
import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path


def hash_pdf(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def hash_corpus(docs_dir: Path) -> dict[str, str]:
    # sha1 -> relative path like "docs/foo.pdf"
    # Skip TDMSachs/, skip non-.pdf
    result = {}
    for f in docs_dir.rglob("*.pdf"):
        if "TDMSachs" in f.parts:
            continue
        rel = str(f.relative_to(docs_dir.parent))
        result[hash_pdf(f)] = rel
    return result


def classify_attente(attente_dir: Path, corpus_hashes: dict[str, str]) -> list[dict]:
    results = []
    for f in sorted(attente_dir.glob("*.pdf")):
        sha = hash_pdf(f)
        rel = str(f.relative_to(attente_dir.parent))
        doublon_de = corpus_hashes.get(sha)
        results.append(
            {
                "fichier": rel,
                "sha1": sha,
                "statut": "exact_duplicate" if doublon_de else "inédit",
                "doublon_de": doublon_de,
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser(description="Dédoublonner le corpus par SHA1")
    parser.add_argument("--docs", required=True, type=Path)
    parser.add_argument("--attente", required=True, type=Path)
    parser.add_argument(
        "--output", default=Path("outputs/dedup_report.json"), type=Path
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger(__name__)

    log.info("Hashing corpus %s", args.docs)
    corpus = hash_corpus(args.docs)
    log.info("%d PDFs hashed in corpus", len(corpus))

    log.info("Classifying attente %s", args.attente)
    results = classify_attente(args.attente, corpus)

    inédits = [r["fichier"] for r in results if r["statut"] == "inédit"]
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "corpus_count": len(corpus),
        "attente_count": len(results),
        "results": results,
        "inédits": inédits,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    log.info(
        "Doublons exacts: %d, Inédits: %d", len(results) - len(inédits), len(inédits)
    )
    log.info("Rapport écrit : %s", args.output)


if __name__ == "__main__":
    main()
