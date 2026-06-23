"""Tests des fonctions pures d'injection des notes d'Antonin (ticket 0029)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import inject_recueil_notes as inj  # noqa: E402
import verify_recueil_mirror as vm  # noqa: E402


def test_build_note_html_prepends_header():
    out = inj.build_note_html("<p>texte original</p>")
    assert out.startswith("<p><strong>Note de Antonin Pottier</strong></p>")
    assert "texte original" in out


def test_build_note_html_handles_empty():
    assert inj.build_note_html("") == "<p><strong>Note de Antonin Pottier</strong></p>\n"


def test_already_injected_detects_existing():
    children = [{"itemType": "note",
                 "note": "<p><strong>Note de Antonin Pottier</strong></p><p>très bon texte</p>"}]
    assert inj.already_injected(children, inj.NOTE_HEADER, "très bon texte") is True
    assert inj.already_injected(children, inj.NOTE_HEADER, "autre chose") is False
    assert inj.already_injected([], inj.NOTE_HEADER, "x") is False


def _enrich(items):
    return [(d, {vm.url_basename(d.get("url"))} - {""}) for d in items]


def test_plan_injections_maps_via_assess_item():
    group_top = [{"key": "G1", "title": "Titre", "date": "1990",
                  "url": "https://inari/recueil/a.pdf", "creators": [{"lastName": "Sachs"}]}]
    group_notes = [{"parentItem": "G1", "note": "<p>commentaire</p>"}]
    lib = _enrich([{"key": "L1", "title": "Titre", "date": "1990",
                    "url": "https://inari/recueil/a.pdf"}])
    planned, orphans = inj.plan_injections(group_notes, group_top, lib, {}, {})
    assert orphans == []
    assert planned[0]["target"] == "L1"
    assert planned[0]["already_present"] is False


def test_plan_injections_uses_relaxed_target_when_no_match():
    group_top = [{"key": "GX", "title": "Sans match", "date": "1974",
                  "url": "https://inari/recueil/x.pdf", "creators": [{"lastName": "Sachs"}]}]
    group_notes = [{"parentItem": "GX", "note": "<p>note</p>"}]
    lib = _enrich([{"key": "LY", "title": "Tout autre", "date": "2000",
                    "url": "https://inari/y.pdf"}])
    planned, orphans = inj.plan_injections(group_notes, group_top, lib, {},
                                           {"GX": "LZTARGET"})
    assert orphans == []
    assert planned[0]["target"] == "LZTARGET"


def test_plan_injections_orphan_when_no_target():
    group_top = [{"key": "GO", "title": "Orpheline", "date": "1974",
                  "url": "https://inari/recueil/o.pdf", "creators": [{"lastName": "Sachs"}]}]
    group_notes = [{"parentItem": "GO", "note": "<p>note</p>"},
                   {"parentItem": "GO", "note": ""}]  # vide : ignorée
    lib = _enrich([{"key": "LY", "title": "Tout autre", "date": "2000",
                    "url": "https://inari/y.pdf"}])
    planned, orphans = inj.plan_injections(group_notes, group_top, lib, {}, {})
    assert planned == []
    assert len(orphans) == 1
    assert orphans[0]["parent"] == "GO"


def test_plan_injections_flags_already_present():
    group_top = [{"key": "G1", "title": "Titre", "date": "1990",
                  "url": "https://inari/recueil/a.pdf", "creators": [{"lastName": "Sachs"}]}]
    group_notes = [{"parentItem": "G1", "note": "<p>déjà là</p>"}]
    lib = _enrich([{"key": "L1", "title": "Titre", "date": "1990",
                    "url": "https://inari/recueil/a.pdf"}])
    existing = {"L1": [{"itemType": "note",
                        "note": "<p><strong>Note de Antonin Pottier</strong></p><p>déjà là</p>"}]}
    planned, _ = inj.plan_injections(group_notes, group_top, lib, existing, {})
    assert planned[0]["already_present"] is True
