"""Tests de extract_meta et des fonctions pures de enrich_web (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import enrich_web as ew  # noqa: E402


HIGHWIRE_HTML = """\
<html><head>
<meta name="citation_title" content="Économie et environnement">
<meta name="citation_author" content="Godard, Olivier">
<meta name="citation_author" content="Sachs, Ignacy">
<meta name="citation_year" content="1984">
<meta name="citation_doi" content="10.1234/foo">
<meta name="citation_journal_title" content="Futuribles">
<meta name="citation_volume" content="82">
<meta name="citation_firstpage" content="45">
</head><body></body></html>
"""

DC_HTML = """\
<html><head>
<meta name="DC.title" content="Développement endogène">
<meta name="DC.creator" content="Sachs, Ignacy">
<meta name="DC.date" content="1980-03">
<meta name="DC.identifier" content="https://doi.org/10.5678/bar">
</head><body></body></html>
"""

OG_HTML = """\
<html><head>
<meta property="og:title" content="Les limites de la croissance">
</head><body></body></html>
"""

LD_HTML = """\
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"ScholarlyArticle",
 "name":"Écodéveloppement et stratégies de rupture",
 "datePublished":"1977",
 "author":[{"@type":"Person","name":"Sachs, Ignacy"}],
 "identifier":"10.9999/zzz"}
</script>
</head><body></body></html>
"""

MIXED_HTML = """\
<html><head>
<meta name="citation_title" content="Titre Highwire">
<meta property="og:title" content="Titre OG">
</head><body></body></html>
"""


def test_extract_meta_highwire():
    m = ew.extract_meta(HIGHWIRE_HTML)
    assert m["title"] == "Économie et environnement"
    assert "Godard, Olivier" in m["authors"]
    assert "Sachs, Ignacy" in m["authors"]
    assert m["year"] == "1984"
    assert m["doi"] == "10.1234/foo"
    assert m["journalTitle"] == "Futuribles"
    assert m["volume"] == "82"
    assert m["pages"] == "45"


def test_extract_meta_dublin_core():
    m = ew.extract_meta(DC_HTML)
    assert m["title"] == "Développement endogène"
    assert m["authors"] == ["Sachs, Ignacy"]
    assert m["year"] == "1980"
    assert m["doi"] == "10.5678/bar"


def test_extract_meta_og_fallback():
    m = ew.extract_meta(OG_HTML)
    assert m["title"] == "Les limites de la croissance"


def test_extract_meta_ld_json():
    m = ew.extract_meta(LD_HTML)
    assert m["title"] == "Écodéveloppement et stratégies de rupture"
    assert m["year"] == "1977"
    assert m["doi"] == "10.9999/zzz"
    assert "Sachs, Ignacy" in m.get("authors", [])


def test_highwire_wins_over_og():
    """Highwire (citation_*) a priorité sur og:title."""
    m = ew.extract_meta(MIXED_HTML)
    assert m["title"] == "Titre Highwire"


def test_extract_meta_empty():
    m = ew.extract_meta("<html><body>rien</body></html>")
    assert m == {}


def test_ddg_result_parser_skips_ddg_urls():
    p = ew.DDGResultParser()
    p.feed('<a href="https://example.com/article">Titre</a>'
           '<a href="https://duckduckgo.com/internal">skip</a>'
           '<a href="/lite?q=foo">skip relative</a>')
    assert p.urls == ["https://example.com/article"]


def test_proposed_web_diff_adds_url():
    notice = {"title": "T", "date": "1984", "publicationTitle": ""}
    candidate = {"title": "T", "year": "1984", "journalTitle": "Futuribles",
                 "doi": "10.1/x", "url": "https://revues.fr/f/123"}
    diff = ew.proposed_web_diff(notice, candidate)
    assert diff["url"] == "https://revues.fr/f/123"
    assert diff["add"]["publicationTitle"] == "Futuribles"
    assert diff["add"]["DOI"] == "10.1/x"
