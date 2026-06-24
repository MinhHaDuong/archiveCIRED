"""Tests des fonctions pures d'enrichissement Crossref (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import enrich_crossref as ec  # noqa: E402

ITEM_GODARD = {
    "DOI": "10.1016/j.ecolecon.2003.05.001",
    "title": ["Carbon taxes and CO2 emissions reduction"],
    "author": [{"family": "Godard", "given": "Olivier"}],
    "published": {"date-parts": [[2003]]},
    "container-title": ["Ecological Economics"],
    "volume": "47",
    "issue": "2",
    "page": "123-145",
    "ISSN": ["0921-8009"],
    "type": "journal-article",
}

ITEM_OTHER = {
    "DOI": "10.1000/other",
    "title": ["Tout autre sujet completement different"],
    "author": [{"family": "Dupont", "given": "Jean"}],
    "published": {"date-parts": [[2010]]},
    "container-title": ["Other Journal"],
}


def test_parse_item_extracts_all_fields():
    p = ec.parse_item(ITEM_GODARD)
    assert p["doi"] == "10.1016/j.ecolecon.2003.05.001"
    assert p["title"] == "Carbon taxes and CO2 emissions reduction"
    assert p["authors"] == ["Godard"]
    assert p["year"] == 2003
    assert p["journal"] == "Ecological Economics"
    assert p["volume"] == "47"
    assert p["issue"] == "2"
    assert p["pages"] == "123-145"
    assert p["issn"] == "0921-8009"


def test_parse_item_handles_empty():
    p = ec.parse_item({})
    assert p["doi"] == ""
    assert p["title"] == ""
    assert p["authors"] == []
    assert p["year"] is None
    assert p["journal"] == ""


def test_combined_score_exact_title_gives_probable():
    notice_data = {
        "title": "Carbon taxes and CO2 emissions reduction",
        "creators": [{"lastName": "Godard", "creatorType": "author"}],
        "date": "2003",
    }
    parsed = ec.parse_item(ITEM_GODARD)
    assert ec.combined_score(notice_data, parsed) >= ec.THRESHOLD_PROBABLE


def test_combined_score_unrelated_title_is_low():
    notice_data = {
        "title": "Completement autre chose sans rapport aucun",
        "creators": [{"lastName": "Godard", "creatorType": "author"}],
        "date": "2003",
    }
    parsed = ec.parse_item(ITEM_GODARD)
    assert ec.combined_score(notice_data, parsed) < 0.2


def test_combined_score_author_year_are_additive_bonus():
    # titre partiel : Jaccard < 1.0 → les bonus auteur/année sont visibles
    partial = {
        "title": "Carbon taxes emissions",  # sous-ensemble → Jaccard < 1
        "creators": [],
        "date": "",
    }
    partial_with_corroboration = {
        "title": "Carbon taxes emissions",
        "creators": [{"lastName": "Godard", "creatorType": "author"}],
        "date": "2003",
    }
    parsed = ec.parse_item(ITEM_GODARD)
    s_bare = ec.combined_score(partial, parsed)
    s_full = ec.combined_score(partial_with_corroboration, parsed)
    assert s_full > s_bare  # bonus effectifs
    # et un titre exact seul reste probable (bonus jamais pénalité)
    exact = {"title": "Carbon taxes and CO2 emissions reduction",
             "creators": [], "date": ""}
    assert ec.combined_score(exact, parsed) >= ec.THRESHOLD_PROBABLE


def test_best_match_selects_highest_score():
    notice_data = {
        "title": "Carbon taxes and CO2 emissions reduction",
        "creators": [{"lastName": "Godard", "creatorType": "author"}],
        "date": "2003",
    }
    best, score = ec.best_match(notice_data, [ITEM_GODARD, ITEM_OTHER])
    assert best is not None
    assert best["doi"] == "10.1016/j.ecolecon.2003.05.001"
    assert score >= ec.THRESHOLD_PROBABLE


def test_best_match_empty_items():
    notice_data = {"title": "Quelque chose", "creators": [], "date": ""}
    best, score = ec.best_match(notice_data, [])
    assert best is None
    assert score == 0.0


def test_diff_fields_detects_ajout_and_modification():
    notice_data = {
        "DOI": "",
        "publicationTitle": "",
        "volume": "47",           # identique → pas de diff
        "issue": "",
        "pages": "100-120",       # différent → modification
        "ISSN": "",
    }
    parsed = ec.parse_item(ITEM_GODARD)
    diffs = ec.diff_fields(notice_data, parsed)
    by_field = {d["champ"]: d for d in diffs}

    assert "DOI" in by_field
    assert by_field["DOI"]["type"] == "ajout"
    assert "publicationTitle" in by_field
    assert "pages" in by_field
    assert by_field["pages"]["type"] == "modification"
    assert by_field["pages"]["valeur_actuelle"] == "100-120"
    assert "volume" not in by_field  # identique


def test_diff_fields_existing_doi_becomes_verification():
    notice_data = {
        "DOI": "10.existing/doi",
        "publicationTitle": "",
        "volume": "",
        "issue": "",
        "pages": "",
        "ISSN": "",
    }
    parsed = ec.parse_item(ITEM_GODARD)
    diffs = ec.diff_fields(notice_data, parsed)
    by_field = {d["champ"]: d for d in diffs}
    assert by_field["DOI"]["type"] == "verification"


def test_diff_fields_no_erasure_when_crossref_empty():
    # publicationTitle renseigné côté notice, vide côté Crossref → pas de diff
    notice_data = {
        "DOI": "",
        "publicationTitle": "Ma Revue Locale",
        "volume": "",
        "issue": "",
        "pages": "",
        "ISSN": "",
    }
    sparse = ec.parse_item({"DOI": "10.test/x", "title": ["X"]})
    diffs = ec.diff_fields(notice_data, sparse)
    by_field = {d["champ"]: d for d in diffs}
    assert "publicationTitle" not in by_field  # Crossref vide → pas d'effacement
    assert "DOI" in by_field


def test_to_ledger_excludes_verification_only():
    report = {
        "probable": [{
            "key": "ABCD1234",
            "score": 0.9,
            "match": {"doi": "10.test/x"},
            "diffs": [{"champ": "DOI", "type": "verification",
                       "valeur_actuelle": "10.old/x", "valeur_proposee": "10.test/x"}],
        }],
        "incertain": [], "absent": [], "sans_titre": [],
    }
    assert ec.to_ledger(report) == []


def test_to_ledger_includes_ajout_and_modification():
    report = {
        "probable": [{
            "key": "ABCD1234",
            "score": 0.9,
            "match": {"doi": "10.test/x"},
            "diffs": [
                {"champ": "DOI", "type": "ajout",
                 "valeur_actuelle": "", "valeur_proposee": "10.test/x"},
                {"champ": "publicationTitle", "type": "modification",
                 "valeur_actuelle": "Ancienne Revue", "valeur_proposee": "Nature"},
            ],
        }],
        "incertain": [], "absent": [], "sans_titre": [],
    }
    ledger = ec.to_ledger(report)
    assert len(ledger) == 1
    assert ledger[0]["key"] == "ABCD1234"
    assert ledger[0]["ref"] == "crossref:10.test/x"
    assert ledger[0]["set"]["DOI"] == "10.test/x"
    assert ledger[0]["set"]["publicationTitle"] == "Nature"
    assert ledger[0]["applied"] is False
