"""Build outputs/file_index.json and outputs/file_index.csv — one record per physical file."""

import argparse
import csv
import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def build_file_index(archive_root: Path) -> list[dict]:
    """Walk all files under archive_root. Return records sorted by fichier."""
    records = []
    for p in archive_root.rglob("*"):
        if not p.is_file():
            continue
        if p.is_symlink():
            logger.warning("Skipping symlink: %s", p)
            continue
        rel = p.relative_to(archive_root).as_posix()
        try:
            content = p.read_bytes()
        except OSError as exc:
            logger.warning("Cannot read %s: %s", p, exc)
            continue
        records.append(
            {
                "fichier": rel,
                "taille": len(content),
                "hash": hashlib.sha1(content).hexdigest(),
                "ext": p.suffix.lower(),
            }
        )
    records.sort(key=lambda r: r["fichier"])
    logger.info("Indexed %d files from %s", len(records), archive_root)
    return records


def write_json(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %d records to %s", len(records), output_path)


def write_csv(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["fichier", "taille", "hash", "ext"])
        writer.writeheader()
        writer.writerows(records)
    logger.info("Wrote CSV to %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build archivistic file index (one record per physical file)."
    )
    parser.add_argument(
        "--archive-dir",
        default="/home/haduong/data/datasets/ours/Archives CIRED numerisées",
        help="Root of the digitized archive",
    )
    parser.add_argument(
        "--output-json",
        default="outputs/file_index.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--output-csv",
        default="outputs/file_index.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    archive_root = Path(args.archive_dir)
    records = build_file_index(archive_root)
    write_json(records, Path(args.output_json))
    write_csv(records, Path(args.output_csv))


if __name__ == "__main__":
    main()
