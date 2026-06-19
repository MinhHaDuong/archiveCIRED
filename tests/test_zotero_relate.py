"""Tests de la logique de mise en relation (pure, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import zotero_relate as zr  # noqa: E402


def item(key, title, last, url=None):
    return {"key": key, "data": {"title": title, "url": url,
                                 "creators": [{"lastName": last}]}}


def test_normalize_title():
    assert zr.normalize_title("Agropolis !") == "agropolis"
    assert zr.normalize_title("  L'Imagination : le savoir  ") == "l imagination le savoir"
    assert zr.normalize_title(None) == ""


def test_group_versions_groups_same_title_author():
    items = [item("A", "Agropolis", "Sachs"),
             item("B", "Agropolis", "Sachs"),
             item("C", "Autre titre", "Sachs")]
    groups = zr.group_versions(items)
    assert groups == [["A", "B"]]


def test_group_versions_ignores_different_author():
    items = [item("A", "Même titre", "Sachs"),
             item("B", "Même titre", "Hourcade")]
    assert zr.group_versions(items) == []


def test_group_versions_ignores_singletons():
    assert zr.group_versions([item("A", "Seul", "Sachs")]) == []


def test_group_versions_skips_same_archive_id():
    # deux membres même clé d'archive = doublon résiduel, pas des versions
    items = [item("A", "T", "Sachs", "x/CIR_SAC_0016.pdf"),
             item("B", "T", "Sachs", "y/CIR_SAC_0016.pdf")]
    assert zr.group_versions(items) == []
    # clés différentes = vraies versions -> relié
    items2 = [item("A", "T", "Sachs", "x/CIR_SAC_0016.pdf"),
              item("B", "T", "Sachs", "y/CIR_SAC_0099.pdf")]
    assert zr.group_versions(items2) == [["A", "B"]]


def test_relation_targets_bidirectional():
    rel = zr.relation_targets("42", ["A", "B", "C"])
    assert rel["A"] == ["http://zotero.org/users/42/items/B",
                        "http://zotero.org/users/42/items/C"]
    assert "http://zotero.org/users/42/items/A" in rel["B"]
