"""Tests de la génération RIS pour l'ingestion du recueil (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import build_recueil_ris as br  # noqa: E402


def test_prefix_key_normalizes_separator_and_padding():
    assert br.prefix_key("1975 15-Hourcade.pdf") == "1975-15"
    assert br.prefix_key("1975-15-Hourcade.pdf") == "1975-15"
    assert br.prefix_key("2007-136-Hallegate.pdf") == "2007-136"
    assert br.prefix_key("PAS-DANS-LA-LISTE-x.pdf") is None


def test_index_group_by_prefix_uses_url_basename():
    notices = [
        {"data": {"title": "T", "url": "https://inari/x/1993-97-Godard-foo.pdf"}},
        {"data": {"title": "U", "url": ""}},  # sans url -> ignorée
    ]
    idx = br.index_group_by_prefix(notices)
    assert set(idx) == {"1993-97"}
    assert idx["1993-97"]["title"] == "T"


def test_pair_new_docs_matches_and_flags_unpaired():
    new = [
        {"id": "1993-097", "fichier": "attente/x/1993 97-Godard-foo.pdf"},
        {"id": "2099-001", "fichier": "attente/x/2099-1-introuvable.pdf"},
    ]
    idx = {"1993-97": {"title": "Stratégies", "itemType": "journalArticle"}}
    r = br.pair_new_docs(new, idx)
    assert [p["id"] for p in r["paired"]] == ["1993-097"]
    assert [u["id"] for u in r["unpaired"]] == ["2099-001"]
    assert r["unpaired"][0]["cle"] == "2099-1"


def test_notice_to_ris_maps_core_fields():
    data = {
        "itemType": "journalArticle",
        "title": "Stratégies industrielles",
        "creators": [{"creatorType": "author", "lastName": "Godard", "firstName": "Olivier"}],
        "date": "1993", "publicationTitle": "INSEE Méthodes",
        "volume": "39/40", "issue": "", "pages": "145-174",
        "url": "https://inari/x/1993-97.pdf", "abstractNote": "",
    }
    ris = br.notice_to_ris(data)
    assert "TY  - JOUR" in ris
    assert "TI  - Stratégies industrielles" in ris
    assert "AU  - Godard, Olivier" in ris
    assert "PY  - 1993" in ris
    assert "T2  - INSEE Méthodes" in ris
    assert "SP  - 145" in ris and "EP  - 174" in ris
    assert ris.rstrip().endswith("ER  -")


def test_notice_to_ris_falls_back_to_gen_type():
    assert "TY  - GEN" in br.notice_to_ris({"itemType": "weirdType", "title": "X"})


def test_filename_to_ris_stub_is_flagged():
    doc = {"id": "2010-150",
           "fichier": "attente/x/2010-150-Monjon_Quirion-How to design a border adjustment-Energy-policy.pdf"}
    ris = br.filename_to_ris(doc)
    assert "TY  - GEN" in ris
    assert "AU  - Monjon" in ris and "AU  - Quirion" in ris
    assert "PY  - 2010" in ris
    assert "N1  - Métadonnées dérivées du nom de fichier — à vérifier" in ris


def test_build_ris_emits_rich_plus_stubs():
    result = {
        "paired": [{"id": "1993-097", "fichier": "x/1993-97-g.pdf",
                    "data": {"itemType": "journalArticle", "title": "T"}}],
        "unpaired": [{"id": "2010-150", "fichier": "x/2010-150-Monjon-Foo.pdf", "cle": "2010-150"}],
    }
    ris = br.build_ris(result)
    assert ris.count("ER  -") == 2          # une notice riche + un stub
    assert "TY  - JOUR" in ris and "TY  - GEN" in ris
