"""Tests des fonctions pures de enrich_hal (appariement + diff, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import enrich_hal as eh


def test_jaccard_token_overlap():
    assert eh.jaccard("climate policy design", "climate policy design") == 1.0
    assert 0 < eh.jaccard("border carbon adjustment", "carbon adjustment scheme") < 1


def test_lastnames_extracts_tokens():
    cr = [{"lastName": "Hourcade", "firstName": "J."}, {"name": "Godard"}]
    assert "hourcade" in eh.lastnames(cr) and "godard" in eh.lastnames(cr)


def test_match_hal_requires_author_corroboration():
    notice = {"title": "Border adjustment for the EU ETS", "date": "2010",
              "creators": [{"lastName": "Monjon"}, {"lastName": "Quirion"}]}
    # bon titre mais auteur absent → pas d'appariement (anti-leçon 0019)
    cands = [{"title": "Border adjustment for the EU ETS", "authors": ["Smith"],
              "year": 2010, "halId": "hal-1"}]
    assert eh.match_hal(notice, cands) is None
    # auteur recoupé → apparié
    cands2 = [{"title": "Border adjustment for the EU ETS", "authors": ["Quirion"],
               "year": 2010, "halId": "hal-2"}]
    m = eh.match_hal(notice, cands2)
    assert m and m["halId"] == "hal-2"


def test_match_hal_rejects_wrong_year():
    notice = {"title": "Peak oil profiles equilibrium", "date": "2012",
              "creators": [{"lastName": "Waisman"}]}
    cands = [{"title": "Peak oil profiles equilibrium", "authors": ["Waisman"],
              "year": 1999, "halId": "hal-x"}]
    assert eh.match_hal(notice, cands) is None


def test_match_hal_allows_missing_year():
    notice = {"title": "Some unique study title here", "date": "",
              "creators": [{"lastName": "Godard"}]}
    cands = [{"title": "Some unique study title here", "authors": ["Godard"],
              "year": 1996, "halId": "hal-y"}]
    assert eh.match_hal(notice, cands)["halId"] == "hal-y"


def test_proposed_diff_adds_missing_and_flags_differ():
    notice = {"publicationTitle": "Energy Policy", "volume": "", "pages": "1-9",
              "DOI": ""}
    hal = {"journalTitle": "Energy Policy", "volume": "38", "page": "1-9",
           "doi": "10.1/x", "halId": "hal-z"}
    d = eh.proposed_diff(notice, hal)
    assert d["halId"] == "hal-z"
    assert d["add"]["volume"] == "38"
    assert d["add"]["DOI"] == "10.1/x"
    assert "pages" not in d["add"]  # déjà présent, équivalent
    assert "publicationTitle" not in d["add"]


def test_proposed_diff_flags_real_divergence():
    notice = {"volume": "12"}
    hal = {"volume": "34", "halId": "h"}
    d = eh.proposed_diff(notice, hal)
    assert d["differ"]["volume"] == ("12", "34")


def test_summarize_counts():
    results = [
        {"matched": {"halId": "h1"}, "diff": {"add": {"volume": "3"}}},
        {"matched": {"halId": ""}, "diff": {"add": {}}},
        {"matched": None},
    ]
    s = eh.summarize(results)
    assert s["total"] == 3 and s["matched"] == 2 and s["unmatched"] == 1
    assert s["with_halid"] == 1 and s["with_field_adds"] == 1
