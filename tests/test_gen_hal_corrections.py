"""Tests des fonctions pures de gen_hal_corrections (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gen_hal_corrections as g


def test_extra_with_hal_appends_to_existing():
    out = g.extra_with_hal("Copie moins bonne : http://x", "hal-123")
    assert out == "Copie moins bonne : http://x\nHAL: hal-123"


def test_extra_with_hal_from_empty():
    assert g.extra_with_hal("", "hal-9") == "HAL: hal-9"


def test_extra_with_hal_idempotent():
    assert g.extra_with_hal("HAL: hal-9", "hal-9") is None
    assert g.extra_with_hal("note\nHAL: hal-9\nmore", "hal-9") is None


def test_extra_with_hal_empty_id():
    assert g.extra_with_hal("anything", "") is None


def test_build_set_adds_hal_and_safe_fields_excludes_pages():
    notice = {"extra": "ok-note"}
    add = {"DOI": "10.1/x", "volume": "38", "pages": "51-99"}
    s = g.build_set(notice, "hal-1", add)
    assert s["extra"] == "ok-note\nHAL: hal-1"
    assert s["DOI"] == "10.1/x" and s["volume"] == "38"
    assert "pages" not in s  # pages exclu de l'auto-ajout


def test_build_set_empty_when_nothing_to_do():
    notice = {"extra": "HAL: hal-1"}
    assert g.build_set(notice, "hal-1", {}) == {}
