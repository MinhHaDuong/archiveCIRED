"""Tests des fonctions pures de import_stubs (mapping Crossref→Zotero, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import import_stubs as imp


def test_file_id_pads():
    assert imp.file_id("attente/x/2010-150-Monjon-border.pdf") == "2010-150"
    assert imp.file_id("2001-7-foo.pdf") == "2001-007"


def test_inari_url_encodes_path():
    u = imp.inari_url("attente/à dédoublonner/2010-150 file.pdf")
    assert u.startswith(imp.INARI_ROOT)
    assert " " not in u and "%20" in u


CR_JOURNAL = {
    "type": "journal-article",
    "title": ["How to design a border adjustment"],
    "author": [{"family": "Monjon", "given": "Stéphanie"},
               {"family": "Quirion", "given": "Philippe"}],
    "issued": {"date-parts": [[2010, 5]]},
    "container-title": ["Energy Policy"],
    "volume": "38", "issue": "9", "page": "5199-5207",
    "DOI": "10.1016/j.enpol.2010.05.005", "language": "en",
}


def test_crossref_to_item_journal():
    it = imp.crossref_to_item(CR_JOURNAL, "https://inari/x.pdf", ["recueil-50ans-ajout-0018"])
    assert it["itemType"] == "journalArticle"
    assert it["title"] == "How to design a border adjustment"
    assert it["publicationTitle"] == "Energy Policy"
    assert it["date"] == "2010"
    assert it["volume"] == "38" and it["issue"] == "9" and it["pages"] == "5199-5207"
    assert it["DOI"] == "10.1016/j.enpol.2010.05.005"
    assert it["url"] == "https://inari/x.pdf"
    assert {"tag": "recueil-50ans-ajout-0018"} in it["tags"]
    assert it["creators"][0] == {"creatorType": "author", "lastName": "Monjon",
                                 "firstName": "Stéphanie"}


def test_crossref_to_item_booksection_uses_booktitle():
    msg = {"type": "book-chapter", "title": ["Untying the Gordian Knot"],
           "container-title": ["The Design of Climate Policy"],
           "publisher": "MIT Press", "issued": {"date-parts": [[2008]]},
           "DOI": "10.7551/x", "author": [{"family": "Hourcade", "given": "J."}]}
    it = imp.crossref_to_item(msg, "u", ["t"])
    assert it["itemType"] == "bookSection"
    assert it["bookTitle"] == "The Design of Climate Policy"
    assert it["publisher"] == "MIT Press"
    assert "publicationTitle" not in it


def test_crossref_to_item_drops_empty_fields():
    msg = {"type": "journal-article", "title": ["T"],
           "issued": {"date-parts": [[2009]]}, "DOI": "10.1/x"}
    it = imp.crossref_to_item(msg, "u", ["t"])
    assert "volume" not in it and "issue" not in it and "pages" not in it


def test_grey_item_marks_a_verifier():
    spec = {"itemType": "report", "title": "WP CIRED", "date": "2013",
            "institution": "CIRED", "extra": "Working Paper CIRED"}
    it = imp.grey_item(spec, "https://inari/wp.pdf", ["recueil-50ans-ajout-0018"])
    assert it["itemType"] == "report"
    assert it["institution"] == "CIRED"
    assert {"tag": "à-vérifier"} in it["tags"]
    assert it["url"] == "https://inari/wp.pdf"


def test_existing_dois_lowercased():
    lib = [{"data": {"DOI": "10.1/AbC"}}, {"data": {"DOI": ""}}, {"data": {}}]
    assert imp.existing_dois(lib) == {"10.1/abc"}


def test_resolved_covers_thirteen_stubs():
    assert len(imp.RESOLVED) == 13
    with_doi = [k for k, v in imp.RESOLVED.items() if v.get("doi")]
    assert len(with_doi) == 11
