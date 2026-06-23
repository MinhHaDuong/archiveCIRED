"""Tests de la construction des écritures Zotero (purs, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import apply_corrections as ac  # noqa: E402


def test_patch_when_itemtype_unchanged():
    current = {"key": "K", "version": 5, "itemType": "journalArticle",
               "date": "1996"}
    method, body = ac.build_write(current, {"date": "1996-05", "extra": "x"})
    assert method == "PATCH"
    assert body == {"date": "1996-05", "extra": "x"}  # pas d'itemType, pas de version


def test_put_when_itemtype_changes_keeps_transferable_fields():
    current = {"key": "K", "version": 7, "itemType": "report",
               "title": "T", "creators": [{"lastName": "Godard"}],
               "institution": "CIRED", "reportNumber": "12", "date": "1984"}
    method, body = ac.build_write(
        current, {"itemType": "journalArticle",
                  "publicationTitle": "Les Nouvelles de l'Écodéveloppement",
                  "issue": "30", "date": "1984-09"})
    assert method == "PUT"
    assert body["itemType"] == "journalArticle"
    assert body["title"] == "T" and body["creators"] == [{"lastName": "Godard"}]
    assert body["publicationTitle"] == "Les Nouvelles de l'Écodéveloppement"
    assert body["date"] == "1984-09"          # set écrase la valeur portée
    assert body["version"] == 7 and body["key"] == "K"
    # conteneurs structurels présents même vides (exigés par un PUT complet)
    assert body["relations"] == {} and body["collections"] == [] and body["tags"] == []
    # champs propres à l'ancien type (report) non transférés
    assert "institution" not in body and "reportNumber" not in body
