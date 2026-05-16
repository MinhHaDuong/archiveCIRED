"""Build outputs/doc_index.json — one record per logical document, full archive."""

import argparse
import difflib
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_index  # for enrichment functions — set build_index._archive_root before calling

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File-type filter: which extensions represent actual documents
# ---------------------------------------------------------------------------
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt"}
# .txt is only included as an OCR sibling, never as a standalone document in groups


def _is_document_file(record: dict) -> bool:
    """Return True if the record represents a processable document or OCR text."""
    ext = record.get("ext", "").lower()
    fichier = record.get("fichier", "")
    # Exclude TDMSachs website assets
    if "TDMSachs" in fichier:
        return False
    # Exclude Inventaire XLS, README, gitkeep, etc.
    if ext not in DOCUMENT_EXTENSIONS and ext != ".txt":
        return False
    # For .txt: only include OCR txt siblings (docs/ or TDM/ with CIR_SAC_ pattern)
    if ext == ".txt":
        name = Path(fichier).name
        # Only YYYY_CIR_SAC_NNNN.txt are OCR siblings
        if not re.match(r"^\d{4}_CIR_SAC_\d+\.txt$", name):
            return False
    return True


# ---------------------------------------------------------------------------
# canonical_key
# ---------------------------------------------------------------------------
def canonical_key(filename: str) -> str:
    """Compute a canonical grouping key from a filename.

    Rules:
    - Strip path prefix, keep stem only
    - Strip leading YYYY_ prefix (e.g. 1994_CIR_SAC_0042 → CIR_SAC_0042)
    - Normalize YYYY-NNN pattern: extract YYYY-NNN with zero-padded NNN
    - Otherwise: lowercase stem
    """
    stem = Path(filename).stem
    # Strip leading YYYY_ prefix
    stem = re.sub(r"^\d{4}_", "", stem)
    # Normalize YYYY-NNN... pattern: extract just YYYY-NNN (zero-pad NNN to 3 digits)
    m = re.match(r"^(\d{4})-(\d+)", stem)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):03d}"
    return stem.lower()


# ---------------------------------------------------------------------------
# group_by_hash
# ---------------------------------------------------------------------------
def group_by_hash(records: list[dict]) -> tuple[dict, list[dict]]:
    """Group records by identical content hash.

    Returns:
        (groups, ungrouped) where:
        - groups: {hash: [records]} for hashes with >= 2 files
        - ungrouped: records with unique hashes
    """
    from collections import defaultdict

    by_hash: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        h = rec.get("hash", "")
        if h:
            by_hash[h].append(rec)

    groups: dict[str, list[dict]] = {}
    ungrouped: list[dict] = []
    for h, recs in by_hash.items():
        if len(recs) >= 2:
            groups[h] = recs
        else:
            ungrouped.extend(recs)

    logger.info("Hash grouping: %d groups, %d ungrouped", len(groups), len(ungrouped))
    return groups, ungrouped


# ---------------------------------------------------------------------------
# group_by_canonical_key
# ---------------------------------------------------------------------------
def group_by_canonical_key(records: list[dict]) -> dict:
    """Group records by canonical_key(filename).

    Returns {canonical_key: [records]}.
    Note: keys with only one record are still returned (singleton groups).
    """
    from collections import defaultdict

    by_key: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        key = canonical_key(rec["fichier"])
        by_key[key].append(rec)

    return dict(by_key)


# ---------------------------------------------------------------------------
# assign_roles
# ---------------------------------------------------------------------------
def assign_roles(group: list[dict]) -> list[dict]:
    """Assign role to each file in a group.

    Principal selection priority:
    1. PDF in docs/ (non-TDM)
    2. PDF anywhere else
    3. First sorted path

    Roles:
    - principal: the primary file
    - ocr: .txt OCR sibling matching principal's CIR_SAC_ key
    - doublon: same hash as principal (exact duplicate)
    - variante: same canonical key but different content and not OCR
    """
    if not group:
        return []

    # Determine principal
    def priority(rec: dict) -> tuple:
        f = rec["fichier"]
        ext = rec.get("ext", "").lower()
        is_pdf = ext == ".pdf"
        in_docs = f.startswith("docs/") and "TDMSachs" not in f
        return (not (is_pdf and in_docs), not is_pdf, f)

    sorted_group = sorted(group, key=priority)
    principal = sorted_group[0]
    principal_hash = principal.get("hash", "")
    principal_key = canonical_key(principal["fichier"])

    result = []
    for rec in group:
        if rec is principal:
            result.append({"fichier": rec["fichier"], "role": "principal", **rec})
            continue

        ext = rec.get("ext", "").lower()
        rec_key = canonical_key(rec["fichier"])

        # TXT whose key matches principal → OCR sibling
        if ext == ".txt" and rec_key == principal_key:
            result.append({"fichier": rec["fichier"], "role": "ocr", **rec})
        # Same hash → doublon (exact copy)
        elif rec.get("hash") == principal_hash and principal_hash:
            result.append({"fichier": rec["fichier"], "role": "doublon", **rec})
        # Same canonical key but different hash → variante
        else:
            result.append({"fichier": rec["fichier"], "role": "variante", **rec})

    return result


# ---------------------------------------------------------------------------
# build_doc_entry
# ---------------------------------------------------------------------------
def build_doc_entry(
    group_files: list[dict], archive_root: Path, existing: dict
) -> dict:
    """Build a doc_index entry from a group of assigned-role files.

    group_files: list of dicts with 'fichier', 'role', 'hash', 'ext', etc.
    archive_root: Path to archive root (used for context only here)
    existing: {stem: existing_entry} from outputs/index.json
    """
    principal = next((f for f in group_files if f["role"] == "principal"), None)
    if principal is None:
        principal = group_files[0]

    ocr_file = next((f for f in group_files if f["role"] == "ocr"), None)

    principal_path = principal["fichier"]
    principal_stem = Path(principal_path).stem
    principal_hash = principal.get("hash", "")

    # Pre-populate from existing index.json (keyed by stem)
    existing_entry = existing.get(principal_stem, {})

    # Build the shim entry for enrichment (id = stem so enrichment lookups work)
    entry: dict = {
        "id": principal_stem,
        "annee": existing_entry.get("annee"),
        "auteurs": existing_entry.get("auteurs"),
        "titre": existing_entry.get("titre"),
        "type": existing_entry.get("type"),
        "revue_editeur": existing_entry.get("revue_editeur"),
        "fichier": principal_path,
        "texte_ocr": ocr_file["fichier"]
        if ocr_file
        else existing_entry.get("texte_ocr"),
        "statut_droits": existing_entry.get("statut_droits", "inconnu"),
        "hal_id": existing_entry.get("hal_id"),
        "notes": existing_entry.get("notes", ""),
        # doc_index-specific fields (stored separately, not passed to enrichment)
        "_fichiers": [
            {"fichier": f["fichier"], "role": f["role"]} for f in group_files
        ],
        "_principal_hash": principal_hash,
    }

    return entry


# ---------------------------------------------------------------------------
# _finalize_entry
# ---------------------------------------------------------------------------
def _finalize_entry(entry: dict, doc_id: str) -> dict:
    """Convert shim entry to final doc_index schema."""
    fichiers = entry.pop(
        "_fichiers", [{"fichier": entry["fichier"], "role": "principal"}]
    )
    entry.pop("_principal_hash", None)

    return {
        "id": doc_id,
        "fichiers": fichiers,
        "annee": entry.get("annee"),
        "auteurs": entry.get("auteurs"),
        "titre": entry.get("titre"),
        "type": entry.get("type"),
        "revue_editeur": entry.get("revue_editeur"),
        "statut_droits": entry.get("statut_droits", "inconnu"),
        "hal_id": entry.get("hal_id"),
        "notes": entry.get("notes", ""),
        "groupe_incertain": entry.get("groupe_incertain", False),
    }


# ---------------------------------------------------------------------------
# enrich_entry
# ---------------------------------------------------------------------------
def enrich_entry(entry: dict, archive_root: Path) -> None:
    """Run enrichment pipeline on a single shim entry if metadata is incomplete.

    Mutates entry in-place. entry must have 'id' = stem (not sha1).
    """
    attente_dir = (
        archive_root / "attente" / "à dédoublonner avec ce qui est déjà traité"
    )
    xls_path = archive_root / "docs" / "Inventaire_Doc_CIRED.xls"
    docs_dir = archive_root / "docs"

    # Skip if already fully enriched
    if entry.get("auteurs") is not None and entry.get("titre") is not None:
        return

    # Set the global archive root for enrich_from_cir_sac_txt
    build_index._archive_root = archive_root

    # 1. Dedoublonner filenames
    if attente_dir.exists():
        build_index.enrich_from_dedoublonner([entry], attente_dir)

    # 2. Inventaire XLS
    if xls_path.exists():
        build_index.enrich_from_inventaire_xls([entry], xls_path)

    # 3. CIR_SAC OCR txt
    build_index.enrich_from_cir_sac_txt([entry])

    # 4. pdftotext (last resort — slow, skip if already have titre+auteurs)
    if entry.get("auteurs") is None or entry.get("titre") is None:
        build_index.enrich_from_pdftotext([entry], docs_dir)


# ---------------------------------------------------------------------------
# fallback_metadata_match
# ---------------------------------------------------------------------------
def fallback_metadata_match(doc_index: list[dict]) -> None:
    """Passe 3: merge singletons with same year, first author, similar title.

    Mutates doc_index in-place: removes merged entries, sets groupe_incertain=True
    on merged records.
    """
    # Work only on singletons (groups with exactly 1 file)
    singletons = [
        e
        for e in doc_index
        if len(e.get("fichiers", [])) == 1
        and e.get("annee") is not None
        and e.get("auteurs")
        and e.get("titre")
    ]

    merged_ids: set[str] = set()
    merges_done = 0

    for i, e1 in enumerate(singletons):
        if e1["id"] in merged_ids:
            continue
        for e2 in singletons[i + 1 :]:
            if e2["id"] in merged_ids:
                continue
            if e1["annee"] != e2["annee"]:
                continue
            # Compare first author
            a1 = e1["auteurs"][0] if e1["auteurs"] else ""
            a2 = e2["auteurs"][0] if e2["auteurs"] else ""
            if a1.lower() != a2.lower():
                continue
            # Title similarity
            ratio = difflib.SequenceMatcher(None, e1["titre"], e2["titre"]).ratio()
            if ratio < 0.80:
                continue

            # Merge e2 into e1
            e1["fichiers"].extend(e2["fichiers"])
            e1["groupe_incertain"] = True
            merged_ids.add(e2["id"])
            merges_done += 1
            logger.debug(
                "Fallback merge: %s + %s (ratio=%.2f)", e1["id"], e2["id"], ratio
            )

    # Remove merged-away entries
    before = len(doc_index)
    doc_index[:] = [e for e in doc_index if e["id"] not in merged_ids]
    logger.info(
        "Fallback metadata merge: %d merges, removed %d entries",
        merges_done,
        before - len(doc_index),
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build outputs/doc_index.json from file_index.json."
    )
    parser.add_argument(
        "--archive-dir",
        default="/home/haduong/data/datasets/ours/Archives CIRED numerisées",
        help="Root of the digitized archive",
    )
    parser.add_argument(
        "--file-index",
        default="outputs/file_index.json",
        help="Input: file_index.json (from build_file_index.py)",
    )
    parser.add_argument(
        "--index-json",
        default="outputs/index.json",
        help="Input: existing index.json (for metadata pre-population)",
    )
    parser.add_argument(
        "--output",
        default="outputs/doc_index.json",
        help="Output: doc_index.json",
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

    # Set global ONCE before any enrichment
    build_index._archive_root = archive_root

    # --- Load inputs ---
    logger.info("Loading file_index from %s", args.file_index)
    with open(args.file_index, encoding="utf-8") as f:
        all_records: list[dict] = json.load(f)

    logger.info("Loading existing index from %s", args.index_json)
    with open(args.index_json, encoding="utf-8") as f:
        existing_list: list[dict] = json.load(f)

    # Build lookup by stem (W10 fix)
    existing: dict[str, dict] = {Path(e["fichier"]).stem: e for e in existing_list}
    logger.info("Existing index: %d entries", len(existing))

    # --- Filter to actual documents ---
    records = [r for r in all_records if _is_document_file(r)]
    logger.info("Records after filter: %d / %d total", len(records), len(all_records))

    # --- Passe 1: Group by hash ---
    hash_groups, ungrouped_after_hash = group_by_hash(records)
    n_hash_groups = len(hash_groups)

    # --- Passe 2: Group remaining by canonical key ---
    canonical_groups = group_by_canonical_key(ungrouped_after_hash)
    n_canonical_groups = len(canonical_groups)

    # --- Build doc_index entries ---
    doc_index: list[dict] = []

    # From hash groups
    for h, recs in hash_groups.items():
        group_files = assign_roles(recs)
        entry = build_doc_entry(group_files, archive_root, existing)
        doc_index.append(entry)

    # From canonical groups
    for key, recs in canonical_groups.items():
        group_files = assign_roles(recs)
        entry = build_doc_entry(group_files, archive_root, existing)
        doc_index.append(entry)

    logger.info("Built %d doc entries before enrichment", len(doc_index))

    # --- Enrichment ---
    logger.info("Enriching entries...")
    for i, entry in enumerate(doc_index):
        if i % 100 == 0:
            logger.info("  Enriching entry %d / %d", i, len(doc_index))
        enrich_entry(entry, archive_root)

    # --- Passe 3: Fallback metadata match on singletons ---
    # Need to finalize first to have proper 'fichiers' list, then run fallback
    # Actually: run fallback on the shim list (it uses 'fichiers' from _fichiers)
    # We need to temporarily expose fichiers for the check
    for entry in doc_index:
        if "_fichiers" not in entry:
            entry["_fichiers"] = [{"fichier": entry["fichier"], "role": "principal"}]

    # Build a temporary view for fallback matching
    tmp_docs = []
    for entry in doc_index:
        tmp = dict(entry)
        tmp["fichiers"] = tmp.get("_fichiers", [])
        tmp_docs.append(tmp)

    fallback_metadata_match(tmp_docs)

    # Propagate merges back
    surviving_ids = {e["id"] for e in tmp_docs}
    doc_index = [e for e in doc_index if e["id"] in surviving_ids]

    # Propagate groupe_incertain and merged fichiers
    id_to_shim = {e["id"]: e for e in doc_index}
    for tmp in tmp_docs:
        if tmp.get("groupe_incertain"):
            shim = id_to_shim.get(tmp["id"])
            if shim:
                shim["groupe_incertain"] = True
                shim["_fichiers"] = tmp["fichiers"]

    n_fallback = sum(1 for e in doc_index if e.get("groupe_incertain", False))

    logger.info(
        "After fallback: %d doc entries, %d uncertain groups",
        len(doc_index),
        n_fallback,
    )

    # --- Finalize to doc_index schema ---
    final_docs: list[dict] = []
    for entry in doc_index:
        # Use sha1 hash as id (from _principal_hash)
        doc_id = entry.get("_principal_hash") or entry.get("id", "")
        final_docs.append(_finalize_entry(entry, doc_id))

    # Sort by principal fichier path for stability
    final_docs.sort(key=lambda e: e["fichiers"][0]["fichier"] if e["fichiers"] else "")

    # --- Write output ---
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_docs, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d doc entries to %s", len(final_docs), output_path)

    # --- Statistics ---
    total = len(final_docs)
    n_annee = sum(1 for e in final_docs if e["annee"] is not None)
    n_auteurs = sum(1 for e in final_docs if e["auteurs"] is not None)
    n_titre = sum(1 for e in final_docs if e["titre"] is not None)
    n_uncertain = sum(1 for e in final_docs if e.get("groupe_incertain", False))

    logger.info(
        "Statistics: total=%d hash_groups=%d canonical_groups=%d fallback_uncertain=%d",
        total,
        n_hash_groups,
        n_canonical_groups,
        n_uncertain,
    )
    logger.info(
        "Coverage: annee=%.1f%% auteurs=%.1f%% titre=%.1f%%",
        100 * n_annee / max(total, 1),
        100 * n_auteurs / max(total, 1),
        100 * n_titre / max(total, 1),
    )


if __name__ == "__main__":
    main()
