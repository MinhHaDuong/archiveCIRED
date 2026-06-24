"""Tests des fonctions pures de enrich_openalex (parsing, scoring, diff — sans réseau)."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import enrich_openalex as oa  # noqa: E402


@pytest.mark.adherence
def test_ruff():
    result = subprocess.run(["uv", "run", "ruff", "check", "."], capture_output=True)
    assert result.returncode == 0, result.stdout.decode()


# ── extraction d'identifiants ─────────────────────────────────────────────────

def test_openalex_id_from_url_standard():
    assert oa.openalex_id_from_url("https://openalex.org/W2741809807") == "W2741809807"


def test_openalex_id_from_url_none():
    assert oa.openalex_id_from_url(None) is None


def test_openalex_id_from_url_plain_string_no_match():
    assert oa.openalex_id_from_url("W2741809807") is None  # pas d'URL


def test_doi_normalize_strips_prefix():
    assert oa.doi_normalize("https://doi.org/10.1038/abc") == "10.1038/abc"


def test_doi_normalize_dx_prefix():
    assert oa.doi_normalize("http://dx.doi.org/10.1038/abc") == "10.1038/abc"


def test_doi_normalize_plain():
    assert oa.doi_normalize("10.1038/abc") == "10.1038/abc"


def test_doi_normalize_none():
    assert oa.doi_normalize(None) is None


def test_doi_normalize_blank():
    assert oa.doi_normalize("   ") is None


# ── champ extra ───────────────────────────────────────────────────────────────

def test_existing_openalex_id_found():
    assert oa.existing_openalex_id("OpenAlex: W2741809807\nPMID: 123") == "W2741809807"


def test_existing_openalex_id_not_found():
    assert oa.existing_openalex_id("PMID: 123") is None


def test_existing_openalex_id_none():
    assert oa.existing_openalex_id(None) is None


def test_extra_with_openalex_empty():
    assert oa.extra_with_openalex(None, "W123") == "OpenAlex: W123"


def test_extra_with_openalex_appends():
    result = oa.extra_with_openalex("PMID: 456", "W123")
    assert result == "PMID: 456\nOpenAlex: W123"


def test_extra_with_openalex_updates_existing():
    result = oa.extra_with_openalex("OpenAlex: W000\nPMID: 456", "W123")
    assert "W123" in result
    assert "W000" not in result
    assert "PMID: 456" in result


# ── parsing d'un work OpenAlex ────────────────────────────────────────────────

SAMPLE_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1038/s41586-018-0377-y",
    "title": "Estimating economic damage from climate change",
    "publication_year": 2018,
    "authorships": [
        {"author": {"display_name": "Solomon Hsiang"}},
        {"author": {"display_name": "Robert Kopp"}},
    ],
    "primary_location": {
        "source": {"display_name": "Nature"}
    },
    "biblio": {
        "volume": "560",
        "issue": "7719",
        "first_page": "549",
        "last_page": "553",
    },
}


def test_parse_work_extracts_id_and_doi():
    p = oa.parse_work(SAMPLE_WORK)
    assert p["id"] == "W2741809807"
    assert p["doi"] == "10.1038/s41586-018-0377-y"


def test_parse_work_extracts_biblio():
    p = oa.parse_work(SAMPLE_WORK)
    assert p["volume"] == "560"
    assert p["issue"] == "7719"
    assert p["pages"] == "549–553"


def test_parse_work_extracts_journal():
    p = oa.parse_work(SAMPLE_WORK)
    assert p["journal"] == "Nature"


def test_parse_work_handles_missing_biblio():
    p = oa.parse_work({"id": "https://openalex.org/W1", "title": "X"})
    assert p["volume"] is None
    assert p["pages"] is None


# ── scoring notice ↔ work ─────────────────────────────────────────────────────

NOTICE_HSIANG = {
    "title": "Estimating economic damage from climate change in the United States",
    "creators": [{"lastName": "Hsiang", "creatorType": "author"},
                 {"lastName": "Kopp", "creatorType": "author"}],
    "date": "2018",
    "DOI": "",
    "extra": "",
}

NOTICE_GODARD = {
    "title": "Gestion de l'environnement en France",
    "creators": [{"lastName": "Godard", "creatorType": "author"}],
    "date": "1985",
    "DOI": "",
    "extra": "",
}


def test_score_high_for_matching_notice():
    s = oa.score_notice_work(NOTICE_HSIANG, SAMPLE_WORK)
    assert s >= 0.75


def test_score_low_for_unrelated():
    s = oa.score_notice_work(NOTICE_GODARD, SAMPLE_WORK)
    assert s < 0.3


def test_score_author_bonus_increases_score():
    no_author = {**NOTICE_HSIANG, "creators": []}
    s_with = oa.score_notice_work(NOTICE_HSIANG, SAMPLE_WORK)
    s_without = oa.score_notice_work(no_author, SAMPLE_WORK)
    assert s_with >= s_without


# ── match_work ────────────────────────────────────────────────────────────────

def test_match_work_returns_best_above_threshold():
    other_work = {**SAMPLE_WORK, "title": "Fiscalité carbone et croissance",
                  "publication_year": 2009}
    best, score = oa.match_work(NOTICE_HSIANG, [other_work, SAMPLE_WORK])
    assert best is SAMPLE_WORK
    assert score >= 0.75


def test_match_work_returns_none_below_threshold():
    low_work = {"id": "https://openalex.org/W1",
                "title": "A completely unrelated paper about botany",
                "publication_year": 1990, "authorships": [], "biblio": {}}
    best, score = oa.match_work(NOTICE_HSIANG, [low_work])
    assert best is None
    assert score < 0.75


# ── diff_notice_work ──────────────────────────────────────────────────────────

def test_diff_adds_openalex_id_to_empty_extra():
    notice = {**NOTICE_HSIANG, "extra": ""}
    fields = oa.diff_notice_work(notice, SAMPLE_WORK)
    assert "extra" in fields
    assert "W2741809807" in fields["extra"]


def test_diff_adds_doi_when_missing():
    notice = {**NOTICE_HSIANG, "DOI": ""}
    fields = oa.diff_notice_work(notice, SAMPLE_WORK)
    assert fields.get("DOI") == "10.1038/s41586-018-0377-y"


def test_diff_skips_doi_when_present():
    notice = {**NOTICE_HSIANG, "DOI": "10.1126/science.aag2669"}
    fields = oa.diff_notice_work(notice, SAMPLE_WORK)
    assert "DOI" not in fields


def test_diff_adds_journal_when_missing():
    notice = {**NOTICE_HSIANG, "publicationTitle": ""}
    fields = oa.diff_notice_work(notice, SAMPLE_WORK)
    assert fields.get("publicationTitle") == "Nature"


def test_diff_skips_journal_when_present():
    notice = {**NOTICE_HSIANG, "publicationTitle": "Science"}
    fields = oa.diff_notice_work(notice, SAMPLE_WORK)
    assert "publicationTitle" not in fields


def test_diff_skips_all_when_already_enriched():
    notice = {**NOTICE_HSIANG,
              "extra": "OpenAlex: W2741809807",
              "DOI": "10.1038/s41586-018-0377-y",
              "publicationTitle": "Nature",
              "volume": "560", "issue": "7719", "pages": "549–553"}
    fields = oa.diff_notice_work(notice, SAMPLE_WORK)
    assert not fields


def test_diff_adds_biblio_when_missing():
    notice = {**NOTICE_HSIANG, "volume": "", "issue": "", "pages": ""}
    fields = oa.diff_notice_work(notice, SAMPLE_WORK)
    assert fields.get("volume") == "560"
    assert fields.get("issue") == "7719"
    assert fields.get("pages") == "549–553"


# ── render_markdown ───────────────────────────────────────────────────────────

def test_render_markdown_includes_key_stats():
    report = {
        "total": 10, "already_enriched": 2, "searched": 8,
        "matched": 6, "not_matched": 2,
        "results": [{"key": "ABC123", "ref": "Some title", "score": 0.87,
                     "openalex_id": "W999", "doi_found": "10.1/x",
                     "searched_by": "title",
                     "set": {"extra": "OpenAlex: W999"}}],
        "not_matched_list": [{"key": "XYZ", "title": "unknown",
                              "reason": "low_score", "best_score": 0.4,
                              "best_candidate": "something else"}],
    }
    md = oa.render_markdown(report)
    assert "ABC123" in md
    assert "W999" in md
    assert "XYZ" in md
    assert "low_score" in md
