"""Tests des fonctions pures de fix_recueil_losses.py (ticket 0029)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fix_recueil_losses as frl


# --- plan_patches ---------------------------------------------------------------

def _loss_meta(key, matched, missing):
    return {"key": key, "reason": "metadata_incomplete",
            "matched": matched, "missing": missing}


def _loss_no_match(key):
    return {"key": key, "reason": "no_match", "matched": None, "missing": []}


def test_plan_patches_fills_missing_fields():
    losses = [_loss_meta("G1", "L1", ["pages", "publisher"])]
    group_by_key = {"G1": {"key": "G1", "title": "T", "pages": "29-35",
                           "publisher": "Mouton"}}
    lib_by_key = {"L1": {"key": "L1", "title": "T"}}
    patches = frl.plan_patches(losses, group_by_key, lib_by_key)
    assert len(patches) == 1
    assert patches[0]["lib_key"] == "L1"
    assert patches[0]["group_key"] == "G1"
    assert patches[0]["fields"] == {"pages": "29-35", "publisher": "Mouton"}


def test_plan_patches_skips_empty_fields_in_group():
    # pages est dans missing mais le groupe ne l'a pas non plus
    losses = [_loss_meta("G2", "L2", ["pages"])]
    group_by_key = {"G2": {"key": "G2", "title": "T"}}  # pages absent
    lib_by_key = {"L2": {"key": "L2"}}
    patches = frl.plan_patches(losses, group_by_key, lib_by_key)
    assert patches == []


def test_plan_patches_ignores_no_match_losses():
    losses = [_loss_no_match("G3")]
    group_by_key = {"G3": {"key": "G3", "title": "T"}}
    lib_by_key = {}
    patches = frl.plan_patches(losses, group_by_key, lib_by_key)
    assert patches == []


def test_plan_patches_multiple_losses():
    losses = [
        _loss_meta("G1", "L1", ["pages"]),
        _loss_meta("G2", "L2", ["volume", "publicationTitle"]),
        _loss_no_match("G3"),
    ]
    group_by_key = {
        "G1": {"key": "G1", "pages": "10-20"},
        "G2": {"key": "G2", "volume": "22", "publicationTitle": "Revue X"},
    }
    lib_by_key = {"L1": {}, "L2": {}}
    patches = frl.plan_patches(losses, group_by_key, lib_by_key)
    assert len(patches) == 2
    keys = {p["lib_key"] for p in patches}
    assert keys == {"L1", "L2"}


# --- plan_copies ----------------------------------------------------------------

def test_plan_copies_creates_item_from_group():
    losses = [_loss_no_match("G4")]
    group_by_key = {
        "G4": {"key": "G4", "version": 5, "dateAdded": "2020-01-01",
               "dateModified": "2020-01-02",
               "title": "Ecodevelopment", "date": "1974",
               "url": "https://inari/recueil/eco.pdf",
               "creators": [{"lastName": "Sachs"}],
               "tags": []}
    }
    copies = frl.plan_copies(losses, group_by_key)
    assert len(copies) == 1
    item = copies[0]["item"]
    assert item["title"] == "Ecodevelopment"
    assert item["url"] == "https://inari/recueil/eco.pdf"
    assert frl.COLLECTION in item["collections"]
    assert any(t["tag"] == frl.TAG for t in item["tags"])
    # clés exclues de la copie
    assert "key" not in item
    assert "version" not in item
    assert "dateAdded" not in item


def test_plan_copies_adds_tag_if_absent():
    losses = [_loss_no_match("G5")]
    group_by_key = {"G5": {"key": "G5", "title": "T", "tags": []}}
    copies = frl.plan_copies(losses, group_by_key)
    assert any(t["tag"] == frl.TAG for t in copies[0]["item"]["tags"])


def test_plan_copies_does_not_duplicate_tag():
    losses = [_loss_no_match("G6")]
    group_by_key = {"G6": {"key": "G6", "title": "T",
                           "tags": [{"tag": frl.TAG}]}}
    copies = frl.plan_copies(losses, group_by_key)
    assert sum(1 for t in copies[0]["item"]["tags"] if t["tag"] == frl.TAG) == 1


def test_plan_copies_ignores_metadata_incomplete():
    losses = [_loss_meta("G7", "L7", ["pages"])]
    group_by_key = {"G7": {"key": "G7", "title": "T", "pages": "1-5", "tags": []}}
    copies = frl.plan_copies(losses, group_by_key)
    assert copies == []


def test_plan_copies_handles_multiple_no_match():
    losses = [_loss_no_match("G8"), _loss_no_match("G9")]
    group_by_key = {
        "G8": {"key": "G8", "title": "A", "tags": []},
        "G9": {"key": "G9", "title": "B", "tags": []},
    }
    copies = frl.plan_copies(losses, group_by_key)
    assert len(copies) == 2
    group_keys = {c["group_key"] for c in copies}
    assert group_keys == {"G8", "G9"}
