"""Tests des fonctions pures de relate_zotero_items (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import relate_zotero_items as rzi


def test_item_uri():
    assert rzi.item_uri("2114597", "ABCD1234") == \
        "http://zotero.org/users/2114597/items/ABCD1234"


def test_add_relation_to_empty():
    uri = "http://zotero.org/users/1/items/K2"
    assert rzi.add_relation({}, uri) == {"dc:relation": [uri]}


def test_add_relation_appends_to_existing_list():
    uri = "http://zotero.org/users/1/items/K2"
    cur = {"dc:relation": ["http://zotero.org/users/1/items/K0"]}
    out = rzi.add_relation(cur, uri)
    assert out["dc:relation"] == ["http://zotero.org/users/1/items/K0", uri]


def test_add_relation_normalises_string_form():
    # Zotero stocke un lien unique en chaîne, plusieurs en liste.
    existing = "http://zotero.org/users/1/items/K0"
    uri = "http://zotero.org/users/1/items/K2"
    out = rzi.add_relation({"dc:relation": existing}, uri)
    assert out["dc:relation"] == [existing, uri]


def test_add_relation_idempotent_returns_none():
    uri = "http://zotero.org/users/1/items/K2"
    assert rzi.add_relation({"dc:relation": [uri]}, uri) is None


def test_plan_relation_two_patches_when_unlinked():
    a = {"key": "AAAA", "version": 5, "title": "Article 1984", "relations": {}}
    b = {"key": "BBBB", "version": 9, "title": "Chapitre 1986", "relations": {}}
    plan = rzi.plan_relation(a, b, "1")
    assert {p["key"] for p in plan} == {"AAAA", "BBBB"}
    a_patch = next(p for p in plan if p["key"] == "AAAA")
    assert rzi.item_uri("1", "BBBB") in a_patch["relations"]["dc:relation"]


def test_plan_relation_skips_side_already_linked():
    uri_b = rzi.item_uri("1", "BBBB")
    a = {"key": "AAAA", "version": 5, "relations": {"dc:relation": [uri_b]}}
    b = {"key": "BBBB", "version": 9, "relations": {}}
    plan = rzi.plan_relation(a, b, "1")
    # A pointe déjà B ; seul B doit être patché.
    assert [p["key"] for p in plan] == ["BBBB"]


def test_plan_relation_empty_when_fully_linked():
    a = {"key": "AAAA", "version": 5,
         "relations": {"dc:relation": [rzi.item_uri("1", "BBBB")]}}
    b = {"key": "BBBB", "version": 9,
         "relations": {"dc:relation": [rzi.item_uri("1", "AAAA")]}}
    assert rzi.plan_relation(a, b, "1") == []
