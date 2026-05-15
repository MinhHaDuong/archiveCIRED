"""Build a global JSON index of the digitized CIRED archive."""

import argparse
import csv
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type prefix table
# ---------------------------------------------------------------------------
PREFIX_TYPE: list[tuple[str, str]] = [
    ("CIR-HOU-TH", "these"),
    ("CIR_SAC_", "gris-sachs"),
    ("ENPC00_AR_LEESU_", "article"),
    ("ENPC00_OUV_LEESU_", "ouvrage"),
    ("ENPC00_RA_LEESU_", "rapport"),
    ("ENPC00_TH_LEESU_", "these"),
    ("Charte_droits-", "rapport"),
]


def _type_from_stem(stem: str) -> str | None:
    for prefix, typ in PREFIX_TYPE:
        if stem.startswith(prefix):
            return typ
    return None


def _year_from_stem(stem: str) -> int | None:
    """Extract year from YYYY-NNN or YYYY_NNN style prefix."""
    m = re.match(r"^(\d{4})[-_]", stem)
    if m:
        yr = int(m.group(1))
        if 1960 <= yr <= 2030:
            return yr
    return None


# ---------------------------------------------------------------------------
# check_dependencies
# ---------------------------------------------------------------------------
def check_dependencies() -> None:
    """Raise RuntimeError if pdftotext or libreoffice not on PATH."""
    for tool in ("pdftotext", "libreoffice"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"Required tool not found on PATH: {tool}")
    logger.info("Dependencies OK: pdftotext, libreoffice")


# ---------------------------------------------------------------------------
# enumerate_docs
# ---------------------------------------------------------------------------
def enumerate_docs(docs_dir: Path) -> list[dict]:
    """Scan docs_dir (non-recursive). Include .pdf, .doc, .docx files.

    Excludes:
    - .txt files (OCR siblings)
    - Inventaire_Doc_CIRED.xls
    - robots.txt
    - anything under TDMSachs/ subdirectory
    """
    excluded_names = {"Inventaire_Doc_CIRED.xls", "robots.txt"}
    included_extensions = {".pdf", ".doc", ".docx"}

    # Build mapping: CIR_SAC_NNNN -> (texte_ocr_path, year) from YYYY_CIR_SAC_NNNN.txt
    txt_map: dict[str, tuple[str, int]] = {}
    for p in docs_dir.iterdir():
        if p.is_file() and p.suffix == ".txt":
            # Pattern: YYYY_CIR_SAC_NNNN.txt — year is in the filename prefix
            m = re.match(r"^(\d{4})_(CIR_SAC_\d+)\.txt$", p.name)
            if m:
                yr = int(m.group(1))
                sac_id = m.group(2)
                txt_map[sac_id] = ("docs/" + p.name, yr)

    entries: list[dict] = []
    for p in docs_dir.iterdir():
        # Skip directories (including TDMSachs)
        if p.is_dir():
            continue
        if p.name in excluded_names:
            continue
        if p.suffix.lower() not in included_extensions:
            continue

        stem = p.stem
        fichier = "docs/" + p.name

        # Year from stem
        annee = _year_from_stem(stem)

        # Type from prefix
        doc_type = _type_from_stem(stem)

        # texte_ocr and year for CIR_SAC (year is in the txt filename prefix)
        texte_ocr: str | None = None
        if stem.startswith("CIR_SAC_"):
            txt_info = txt_map.get(stem)
            if txt_info is not None:
                texte_ocr, txt_year = txt_info
                if annee is None:
                    annee = txt_year

        entry: dict = {
            "id": stem,
            "annee": annee,
            "auteurs": None,
            "titre": None,
            "type": doc_type,
            "revue_editeur": None,
            "fichier": fichier,
            "texte_ocr": texte_ocr,
            "statut_droits": "inconnu",
            "hal_id": None,
            "notes": "",
        }
        entries.append(entry)

    entries.sort(key=lambda e: e["id"])
    logger.info("Enumerated %d documents from %s", len(entries), docs_dir)
    return entries


# ---------------------------------------------------------------------------
# enrich_from_dedoublonner
# ---------------------------------------------------------------------------
def _normalize_id(raw: str) -> str | None:
    """Normalize messy year-number prefix to YYYY-NNN form.

    Handles: YYYY-N, YYYY-NN, YYYY-NNN, YYYY_NNN, YYYY NNN (em-dash too).
    """
    m = re.match(r"^(\d{4})[-_ –](\d+)", raw)
    if not m:
        return None
    year = m.group(1)
    num = m.group(2).lstrip("0") or "0"
    return f"{year}-{int(num):03d}"


def enrich_from_dedoublonner(entries: list[dict], attente_dir: Path) -> None:
    """Parse filenames in attente_dir. Match to entries by YYYY-NNN id.
    Try to extract author/title from filename if fields still None.
    """
    by_id: dict[str, dict] = {e["id"]: e for e in entries}
    unmatched: list[str] = []

    for p in attente_dir.iterdir():
        if p.is_dir():
            continue
        name = p.stem

        # Extract normalized id
        norm_id = _normalize_id(name)
        if norm_id is None:
            logger.debug("Dedoublonner: could not extract id from %s", name)
            unmatched.append(name)
            continue

        # Try exact match, then _1 and _2 variants
        entry: dict | None = by_id.get(norm_id)
        if entry is None:
            entry = by_id.get(norm_id + "_1")
        if entry is None:
            entry = by_id.get(norm_id + "_2")
        if entry is None:
            logger.debug("Dedoublonner: no entry matched for %s (id=%s)", name, norm_id)
            unmatched.append(name)
            continue

        # Don't overwrite already-set fields
        if entry["auteurs"] is not None and entry["titre"] is not None:
            continue

        # Attempt to extract author + title from the suffix after YYYY-NNN-...
        # Remove the year-number prefix (with optional underscore-number suffix)
        suffix = re.sub(r"^\d{4}[-_ –]\d+[-_ –]?", "", name).strip()
        if not suffix:
            continue

        # Split on common separators to get tokens
        tokens = re.split(r"[-_]", suffix, maxsplit=1)

        if entry["auteurs"] is None and tokens:
            candidate = tokens[0].strip()
            # Must look like a name: mostly alphabetic, reasonable length
            if 2 <= len(candidate) <= 50 and re.match(r"^[A-Za-zÀ-ÿ ]+$", candidate):
                entry["auteurs"] = [candidate]

        if entry["titre"] is None and len(tokens) > 1:
            titre_candidate = tokens[1].replace("_", " ").strip()
            if len(titre_candidate) >= 5:
                entry["titre"] = titre_candidate

    if unmatched:
        logger.info(
            "Dedoublonner: %d filenames unmatched (first 10: %s)",
            len(unmatched),
            unmatched[:10],
        )


# ---------------------------------------------------------------------------
# convert_xls_to_csv
# ---------------------------------------------------------------------------
def convert_xls_to_csv(xls_path: Path, tmp_dir: Path) -> Path:
    """Convert XLS to CSV using libreoffice. Return CSV path."""
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "csv",
        "--outdir",
        str(tmp_dir),
        str(xls_path),
    ]
    logger.info("Converting %s to CSV", xls_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"libreoffice conversion failed: {result.stderr}")

    csv_path = tmp_dir / (xls_path.stem + ".csv")
    if not csv_path.exists():
        raise RuntimeError(f"Expected CSV not found at {csv_path}")

    # Log first 5 rows for debugging
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        rows = [next(reader, None) for _ in range(5)]
    for i, row in enumerate(rows):
        if row is not None:
            logger.debug("CSV row %d: %s", i, row)

    return csv_path


# ---------------------------------------------------------------------------
# enrich_from_inventaire_xls
# ---------------------------------------------------------------------------
def enrich_from_inventaire_xls(entries: list[dict], xls_path: Path) -> None:
    """Convert XLS to CSV, parse, match rows to entries, set metadata."""
    by_id: dict[str, dict] = {e["id"]: e for e in entries}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        try:
            csv_path = convert_xls_to_csv(xls_path, tmp_dir)
        except RuntimeError as exc:
            logger.warning("Skipping XLS enrichment: %s", exc)
            return

        with open(csv_path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            # Inspect column names
            fieldnames = reader.fieldnames or []
            logger.info("XLS columns: %s", fieldnames)

            matched = 0
            for row in reader:
                # Try to find id column — look for something that looks like a doc id
                row_id: str | None = None
                for col in fieldnames:
                    val = (row.get(col) or "").strip()
                    if (
                        re.match(r"^\d{4}-\d+", val)
                        or re.match(r"^CIR_", val)
                        or re.match(r"^ENPC", val)
                    ):
                        row_id = val
                        break

                if row_id is None:
                    continue

                # Normalize id
                if re.match(r"^\d{4}-\d+", row_id):
                    norm = _normalize_id(row_id)
                    if norm:
                        row_id = norm

                entry = by_id.get(row_id)
                if entry is None:
                    continue
                matched += 1

                # Map common column names
                col_map = {k.lower().strip(): k for k in fieldnames}

                # Year
                if entry["annee"] is None:
                    for key in ("annee", "année", "year", "date"):
                        col = col_map.get(key)
                        if col:
                            val = (row.get(col) or "").strip()
                            m = re.search(r"\b(\d{4})\b", val)
                            if m:
                                entry["annee"] = int(m.group(1))
                            break

                # Auteurs
                if entry["auteurs"] is None:
                    for key in ("auteur", "auteurs", "author", "authors"):
                        col = col_map.get(key)
                        if col:
                            val = (row.get(col) or "").strip()
                            if val:
                                entry["auteurs"] = [
                                    v.strip()
                                    for v in re.split(r"[;,]", val)
                                    if v.strip()
                                ]
                            break

                # Titre
                if entry["titre"] is None:
                    for key in ("titre", "title", "titré"):
                        col = col_map.get(key)
                        if col:
                            val = (row.get(col) or "").strip()
                            if val:
                                entry["titre"] = val
                            break

                # Type
                if entry["type"] is None:
                    for key in ("type", "nature", "document type"):
                        col = col_map.get(key)
                        if col:
                            val = (row.get(col) or "").strip()
                            if val:
                                entry["type"] = val
                            break

                # revue_editeur
                if entry["revue_editeur"] is None:
                    for key in ("revue", "editeur", "éditeur", "journal", "publisher"):
                        col = col_map.get(key)
                        if col:
                            val = (row.get(col) or "").strip()
                            if val:
                                entry["revue_editeur"] = val
                            break

            logger.info("XLS enrichment: matched %d entries", matched)


# ---------------------------------------------------------------------------
# extract_text_page1
# ---------------------------------------------------------------------------
def extract_text_page1(pdf_path: Path) -> str | None:
    """Extract first page text with pdftotext. Return text if >= 200 chars, else None."""
    try:
        result = subprocess.run(
            ["pdftotext", "-l", "1", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        text = result.stdout
        if len(text.strip()) >= 200:
            return text
        return None
    except subprocess.TimeoutExpired:
        logger.warning("pdftotext timed out on %s", pdf_path)
        return None
    except OSError as exc:
        logger.warning("pdftotext error on %s: %s", pdf_path, exc)
        return None


# ---------------------------------------------------------------------------
# year_from_text
# ---------------------------------------------------------------------------
def year_from_text(text: str) -> int | None:
    """Find a 4-digit year 1970–2013 in first 500 chars."""
    snippet = text[:500]
    for m in re.finditer(r"\b(1[9][7-9]\d|200\d|201[0-3])\b", snippet):
        yr = int(m.group(1))
        if 1970 <= yr <= 2013:
            return yr
    return None


# ---------------------------------------------------------------------------
# title_author_from_text
# ---------------------------------------------------------------------------
def title_author_from_text(text: str) -> tuple[str | None, list[str] | None]:
    """Heuristic title/author extraction from first 3 non-empty lines."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
        if len(lines) >= 3:
            break

    titre: str | None = None
    auteurs: list[str] | None = None

    # Title = first non-empty line >= 10 chars
    for line in lines:
        if len(line) >= 10:
            titre = line
            break

    if titre is None:
        return None, None

    # Author = second non-empty line that looks like a name
    remaining = [ln for ln in lines if ln != titre]
    for line in remaining:
        if _looks_like_name(line):
            auteurs = [line]
            break

    return titre, auteurs


def _looks_like_name(text: str) -> bool:
    """Heuristic: short line (<=60 chars), mostly alpha + spaces/dashes, no numbers."""
    if len(text) > 60:
        return False
    if re.search(r"\d", text):
        return False
    alpha_ratio = sum(c.isalpha() or c in " -.'," for c in text) / max(len(text), 1)
    return alpha_ratio >= 0.85


# ---------------------------------------------------------------------------
# enrich_from_pdftotext
# ---------------------------------------------------------------------------
def enrich_from_pdftotext(entries: list[dict], docs_dir: Path) -> None:
    """Enrich entries missing annee/titre/auteurs using pdftotext on first page."""
    image_only_count = 0
    processed = 0

    for entry in entries:
        # Skip CIR_SAC (handled separately)
        if entry["id"].startswith("CIR_SAC_"):
            continue

        # Skip fully complete entries
        complete = (
            entry["annee"] is not None
            and entry["auteurs"] is not None
            and entry["titre"] is not None
        )
        if complete:
            continue

        # Only process PDF files
        fichier_path = docs_dir.parent / entry["fichier"]
        if fichier_path.suffix.lower() != ".pdf":
            continue

        processed += 1
        text = extract_text_page1(fichier_path)
        if text is None:
            image_only_count += 1
            continue

        if entry["annee"] is None:
            yr = year_from_text(text)
            if yr is not None:
                entry["annee"] = yr

        if entry["auteurs"] is None or entry["titre"] is None:
            titre, auteurs = title_author_from_text(text)
            if entry["titre"] is None and titre is not None:
                entry["titre"] = titre
            if entry["auteurs"] is None and auteurs is not None:
                entry["auteurs"] = auteurs

    logger.info(
        "pdftotext enrichment: processed %d PDFs, %d image-only",
        processed,
        image_only_count,
    )


# ---------------------------------------------------------------------------
# enrich_from_cir_sac_txt
# ---------------------------------------------------------------------------
def enrich_from_cir_sac_txt(entries: list[dict]) -> None:
    """Enrich CIR_SAC entries from their OCR .txt files (best-effort)."""
    enriched = 0
    for entry in entries:
        if not entry["id"].startswith("CIR_SAC_"):
            continue
        if entry["texte_ocr"] is None:
            continue
        if entry["auteurs"] is not None and entry["titre"] is not None:
            continue

        # texte_ocr is "docs/YYYY_CIR_SAC_NNNN.txt" — resolve via the global archive root
        pdf_path = _archive_root / entry["fichier"]
        txt_full_path = pdf_path.parent / Path(entry["texte_ocr"]).name

        if not txt_full_path.exists():
            logger.debug("OCR txt not found: %s", txt_full_path)
            continue

        try:
            with open(txt_full_path, encoding="utf-8", errors="replace") as f:
                lines = [f.readline().strip() for _ in range(30)]
        except OSError as exc:
            logger.warning("Error reading %s: %s", txt_full_path, exc)
            continue

        text = "\n".join(lines)
        titre, auteurs = title_author_from_text(text)

        if entry["titre"] is None and titre is not None and len(titre) >= 10:
            entry["titre"] = titre
            enriched += 1
        if entry["auteurs"] is None and auteurs is not None:
            entry["auteurs"] = auteurs

    logger.info("CIR_SAC txt enrichment: enriched %d entries", enriched)


# ---------------------------------------------------------------------------
# write_unresolved
# ---------------------------------------------------------------------------
def write_unresolved(entries: list[dict], output_path: Path) -> None:
    """Write CSV of entries missing annee OR (auteurs AND titre)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "fichier", "annee_missing", "metadata_missing"],
        )
        writer.writeheader()
        for entry in entries:
            annee_missing = entry["annee"] is None
            metadata_missing = entry["auteurs"] is None and entry["titre"] is None
            if annee_missing or metadata_missing:
                writer.writerow(
                    {
                        "id": entry["id"],
                        "fichier": entry["fichier"],
                        "annee_missing": annee_missing,
                        "metadata_missing": metadata_missing,
                    }
                )
    logger.info("Wrote unresolved CSV to %s", output_path)


# ---------------------------------------------------------------------------
# write_index
# ---------------------------------------------------------------------------
def write_index(entries: list[dict], output_path: Path) -> None:
    """Write JSON array sorted by id."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_entries = sorted(entries, key=lambda e: e["id"])
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted_entries, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %d entries to %s", len(sorted_entries), output_path)


# ---------------------------------------------------------------------------
# Global archive root (needed by enrich_from_cir_sac_txt)
# ---------------------------------------------------------------------------
_archive_root: Path = Path("/home/haduong/data/datasets/ours/Archives CIRED numerisées")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Build JSON index of CIRED archive.")
    parser.add_argument(
        "--archive-dir",
        default="/home/haduong/data/datasets/ours/Archives CIRED numerisées",
        help="Root of the digitized archive",
    )
    parser.add_argument(
        "--output",
        default="src/index.json",
        help="Output JSON index path",
    )
    parser.add_argument(
        "--unresolved",
        default="src/unresolved.csv",
        help="Output CSV of unresolved entries",
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

    archive_dir = Path(args.archive_dir)
    docs_dir = archive_dir / "docs"
    dedoublonner_dir = (
        archive_dir / "attente" / "à dédoublonner avec ce qui est déjà traité"
    )
    xls_path = docs_dir / "Inventaire_Doc_CIRED.xls"
    output_path = Path(args.output)
    unresolved_path = Path(args.unresolved)

    # Set global for enrich_from_cir_sac_txt
    global _archive_root
    _archive_root = archive_dir

    # Step 1: Check dependencies
    logger.info("Step 1: Checking dependencies")
    check_dependencies()

    # Step 2: Enumerate documents
    logger.info("Step 2: Enumerating documents")
    entries = enumerate_docs(docs_dir)
    logger.info("Found %d documents", len(entries))

    # Step 3: Enrich from dedoublonner filenames
    logger.info("Step 3: Enriching from dedoublonner filenames")
    if dedoublonner_dir.exists():
        enrich_from_dedoublonner(entries, dedoublonner_dir)
    else:
        logger.warning("Dedoublonner dir not found: %s", dedoublonner_dir)

    # Step 4: Enrich from XLS inventaire
    logger.info("Step 4: Enriching from XLS inventaire")
    if xls_path.exists():
        enrich_from_inventaire_xls(entries, xls_path)
    else:
        logger.warning("XLS not found: %s", xls_path)

    # Step 5: Enrich from pdftotext
    logger.info("Step 5: Enriching from pdftotext")
    enrich_from_pdftotext(entries, docs_dir)

    # Step 6: Enrich CIR_SAC from txt files
    logger.info("Step 6: Enriching CIR_SAC from OCR txt files")
    enrich_from_cir_sac_txt(entries)

    # Step 7: Write outputs
    logger.info("Step 7: Writing outputs")
    write_index(entries, output_path)
    write_unresolved(entries, unresolved_path)

    # Step 8: Coverage report
    total = len(entries)
    n_annee = sum(1 for e in entries if e["annee"] is not None)
    n_auteurs = sum(1 for e in entries if e["auteurs"] is not None)
    n_titre = sum(1 for e in entries if e["titre"] is not None)
    n_type = sum(1 for e in entries if e["type"] is not None)
    logger.info(
        "Coverage: total=%d annee=%.1f%% auteurs=%.1f%% titre=%.1f%% type=%.1f%%",
        total,
        100 * n_annee / total,
        100 * n_auteurs / total,
        100 * n_titre / total,
        100 * n_type / total,
    )


if __name__ == "__main__":
    main()
