"""Tests des fonctions pures de resolve_stubs (parsing + scoring, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import resolve_stubs as rs


def test_parse_stub_extracts_id_year_query():
    out = rs.parse_stub(
        "2010-150-Monjon_Quirion-How to design a border adjustment-Energy-policy.pdf")
    assert out["id"] == "2010-150"
    assert out["year"] == 2010
    assert "border adjustment" in out["query"]
    assert ".pdf" not in out["query"]


def test_parse_stub_pads_number():
    assert rs.parse_stub("2001-7-foo.pdf")["id"] == "2001-007"


def test_parse_stub_handles_doc_and_odt_extensions():
    assert rs.parse_stub("2011-175-Finon-Efficiency-Climate policy.odt")["id"] == "2011-175"
    assert rs.parse_stub("2010-151-Sassi-Imaclim.doc")["year"] == 2010


def test_norm_tokens_drops_stopwords_and_accents():
    t = rs.norm_tokens("Étude de la transition énergétique")
    assert "etude" in t and "transition" in t and "energetique" in t
    assert "de" not in t and "la" not in t


def test_title_coverage_full_when_title_in_query():
    q = "Hourcade Quirion How to design a border adjustment Energy Policy"
    assert rs.title_coverage(q, "How to design a border adjustment") == 1.0


def test_title_coverage_partial():
    q = "border adjustment carbon"
    # titre candidat a 4 mots signifiants ; 2 présents
    assert 0.0 < rs.title_coverage(q, "border tax adjustment scheme") < 1.0


def test_title_coverage_zero_for_empty_title():
    assert rs.title_coverage("anything", "") == 0.0


def test_best_candidate_picks_highest_coverage():
    q = "border adjustment European emissions trading"
    cands = [
        {"title": "Something unrelated entirely", "id": "A"},
        {"title": "border adjustment for the European emissions trading", "id": "B"},
    ]
    best = rs.best_candidate(q, cands)
    assert best["id"] == "B"
    assert best["score"] > 0.5


def test_best_candidate_none_when_empty():
    assert rs.best_candidate("q", []) is None
