"""Tests purs pour normalize_biblio_fields (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import normalize_biblio_fields as nb  # noqa: E402


def _item(key="K1", version=1, **fields):
    return {"data": {"key": key, "version": version, **fields}}


def test_dirty_fields_volume_prefix():
    d = nb.dirty_fields({"volume": "vol. 8", "issue": "n°316", "pages": "417-438"})
    assert d["volume"] == ("vol. 8", "8")
    assert d["issue"] == ("n°316", "316")
    assert d["pages"] == ("417-438", "417–438")


def test_dirty_fields_clean_values():
    assert nb.dirty_fields({"volume": "8", "issue": "2", "pages": "417–438"}) == {}


def test_dirty_fields_skips_empty():
    assert nb.dirty_fields({"volume": "", "pages": ""}) == {}


def test_dirty_fields_ignores_page_counts():
    # "31 p." ne se corrige pas automatiquement
    assert nb.dirty_fields({"pages": "31 p."}) == {}


def test_page_counts_flags_count():
    assert nb.page_counts({"pages": "31 p."}) == ["31 p."]
    assert nb.page_counts({"pages": "22 p"}) == ["22 p"]
    assert nb.page_counts({"pages": "417-438"}) == []
    assert nb.page_counts({"pages": "417–438"}) == []
    assert nb.page_counts({"pages": ""}) == []


def test_plan_separates_patches_and_flags():
    items = [
        _item("A", volume="vol. 8"),           # à patcher
        _item("B", pages="31 p."),             # à signaler
        _item("C", issue="n°2", pages="1-10"), # à patcher (deux champs)
        _item("D", volume="8", pages="1–10"),  # propre → rien
    ]
    patches, flags = nb.plan(items)
    patch_keys = {pt["key"] for pt in patches}
    assert patch_keys == {"A", "C"}
    assert len(flags) == 1 and flags[0]["key"] == "B"


def test_plan_patch_fields_content():
    items = [_item("X", version=3, issue="no 176", pages="417-438")]
    patches, _ = nb.plan(items)
    assert len(patches) == 1
    pt = patches[0]
    assert pt["key"] == "X"
    assert pt["version"] == 3
    assert pt["fields"]["issue"] == ("no 176", "176")
    assert pt["fields"]["pages"] == ("417-438", "417–438")
