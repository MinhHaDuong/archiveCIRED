"""Tests de la construction des notices à créer (purs, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import add_new_docs as an  # noqa: E402


def test_descriptive_title_strips_prefix_and_separators():
    assert an.descriptive_title("attente/x/2010-150-Monjon_Quirion-Border_adj.pdf") \
        == "Monjon Quirion Border adj"
    assert an.descriptive_title("1972-7-Rapport Croissance.pdf") == "Rapport Croissance"


def test_build_item_rich_from_group_data():
    doc = {"id": "1993-097", "fichier": "x/1993-97-Godard.pdf"}
    group = {"key": "GK", "version": 9, "dateAdded": "z", "itemType": "journalArticle",
             "title": "Stratégies", "tags": [{"tag": "old"}]}
    it = an.build_item(doc, group, collection="COLL", tag="recueil-50ans")
    assert it["itemType"] == "journalArticle" and it["title"] == "Stratégies"
    assert "key" not in it and "version" not in it          # repart propre
    assert it["collections"] == ["COLL"]
    assert {"tag": "recueil-50ans"} in it["tags"] and {"tag": "old"} in it["tags"]


def test_build_item_stub_when_no_group_match():
    doc = {"id": "2007-136", "fichier": "x/2007-136-Hallegate-Hourcade-Using.pdf"}
    it = an.build_item(doc, None, collection="COLL", tag="recueil-50ans")
    assert it["itemType"] == "document"
    assert it["title"] == "Hallegate Hourcade Using"      # info préservée, non découpée
    assert it["date"] == "2007"
    assert "à vérifier" in it["extra"].lower()
    assert {"tag": "recueil-50ans"} in it["tags"] and {"tag": "à-vérifier"} in it["tags"]
    assert it["collections"] == ["COLL"]
