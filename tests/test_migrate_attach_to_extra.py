"""Tests des fonctions pures de migration attachement → Extra (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import migrate_attach_to_extra as mig  # noqa: E402


def test_new_extra_ajoute_si_absent():
    assert mig.new_extra("", "http://x/a.pdf") == "http://x/a.pdf"
    assert mig.new_extra("note", "http://x/a.pdf") == "note\nhttp://x/a.pdf"


def test_new_extra_none_si_present():
    assert mig.new_extra("http://x/a.pdf", "http://x/a.pdf") is None
    assert mig.new_extra("voir http://x/a.pdf ici", "http://x/a.pdf") is None


def test_find_migrations_cible_le_marqueur():
    items = [
        {"key": "P1", "data": {"key": "P1", "itemType": "journalArticle",
                               "version": 5, "extra": "", "title": "Œuvre"}},
        {"key": "A1", "data": {"key": "A1", "itemType": "attachment",
                               "linkMode": "linked_url", "version": 7,
                               "url": "http://x/r.pdf", "parentItem": "P1",
                               "title": f"{mig.MARKER} (r.pdf)"}},
        # attachement linked_url hors marqueur → ignoré
        {"key": "A2", "data": {"key": "A2", "itemType": "attachment",
                               "linkMode": "linked_url", "version": 7,
                               "url": "http://x/o.pdf", "parentItem": "P1",
                               "title": "autre lien"}},
    ]
    out = mig.find_migrations(items)
    assert len(out) == 1
    m = out[0]
    assert m["attach_key"] == "A1"
    assert m["parent_key"] == "P1"
    assert m["url"] == "http://x/r.pdf"
    assert m["parent_version"] == 5
