"""Tests des fonctions pures de l'audit d'autonomie PDF (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import audit_pdf_stubs as aps  # noqa: E402


def test_fonds_of():
    assert aps.fonds_of("CIR_SAC_0317.pdf") == "CIR_SAC"
    assert aps.fonds_of("ENPC00_OUV_LEESU_0016.pdf") == "LEESU"
    assert aps.fonds_of("Hourcade - 1984 - prospective.pdf") == "AUTRE"


def test_source_group_extracts_id():
    att = {"relations": {"owl:sameAs": "http://zotero.org/groups/329932/items/X"}}
    assert aps.source_group(att) == "329932"


def test_source_group_absent():
    assert aps.source_group({"relations": {}}) is None
    assert aps.source_group({}) is None


def test_match_stubs_partitions_by_archive_presence():
    file_index = [
        {"fichier": "docs/CIR_SAC_0317.pdf"},
        {"fichier": "docs/1973-009.txt"},  # même radical, ext différente
    ]
    stubs = [
        {"key": "A", "filename": "CIR_SAC_0317.pdf"},   # exact
        {"key": "B", "filename": "1973-009.pdf"},        # radical
        {"key": "C", "filename": "introuvable_0001.pdf"},
    ]
    out = aps.match_stubs(stubs, file_index)
    assert [r["key"] for r in out["exact"]] == ["A"]
    assert [r["key"] for r in out["radical"]] == ["B"]
    assert [r["key"] for r in out["introuvable"]] == ["C"]
    assert out["exact"][0]["archive"] == "docs/CIR_SAC_0317.pdf"


def test_build_worklist_counts_real_pdf_vs_stub():
    items = [
        {"data": {"key": "P1", "itemType": "document"}},
        {"data": {"key": "att_real", "itemType": "attachment",
                  "linkMode": "imported_file", "md5": "abc",
                  "filename": "CIR_SAC_0317.pdf"}},
        {"data": {"key": "att_stub", "itemType": "attachment",
                  "linkMode": "imported_file", "md5": None,
                  "filename": "CIR_SAC_0317.pdf",
                  "relations": {"owl:sameAs":
                                "http://zotero.org/groups/329932/items/Z"}}},
    ]
    file_index = [{"fichier": "docs/CIR_SAC_0317.pdf"}]
    w = aps.build_worklist(items, file_index)
    t = w["totaux"]
    assert t["notices_top_level"] == 1
    assert t["pdf_reels_televerse"] == 1
    assert t["stubs_sans_fichier"] == 1
    assert t["stubs_du_groupe_mort_329932"] == 1
    assert t["apparies_exact"] == 1
    assert w["par_fonds"] == {"CIR_SAC": 1}
