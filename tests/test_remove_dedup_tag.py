"""Tests des fonctions pures du retrait de tag (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import remove_dedup_tag as rt  # noqa: E402


def _it(key, title, tags=()):
    return {"key": key, "title": title,
            "tags": [{"tag": t} for t in tags]}


def test_find_remaining_dups_aucun():
    tagged = [_it("A", "Œuvre une", [rt.TAG]), _it("B", "Œuvre deux", [rt.TAG])]
    all_top = tagged + [_it("C", "Œuvre trois")]
    assert rt.find_remaining_dups(tagged, all_top) == []


def test_find_remaining_dups_detecte_jumeau():
    tagged = [_it("A", "Même œuvre", [rt.TAG])]
    all_top = tagged + [_it("B", "Même œuvre")]  # jumeau non tagué
    out = rt.find_remaining_dups(tagged, all_top)
    assert len(out) == 1
    assert out[0][0] == "A" and out[0][2] == ["B"]


def test_find_remaining_dups_ignore_meme_cle():
    # un item ne doit pas se compter lui-même comme jumeau
    tagged = [_it("A", "Solo", [rt.TAG])]
    assert rt.find_remaining_dups(tagged, tagged) == []
