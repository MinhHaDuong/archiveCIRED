"""Tests des fonctions pures de suppression des copies #27 (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import delete_recueil_dup_copies as dd  # noqa: E402


def test_url_sources():
    assert dd.url_sources({"url": "x/Wehurei6/a.pdf"}) == {"recueil"}
    assert dd.url_sources({"url": "x/kCj0pHP0/a.pdf",
                           "extra": "x/Wehurei6/b.pdf"}) == {"recueil", "numerisation"}
    assert dd.url_sources({"url": "https://doi.org/x"}) == set()


def test_plan_deletions_garde_fou(monkeypatch):
    # originale avec 2 URL → la copie est supprimable ; sinon abstention
    store = {
        "C1": {"key": "C1", "version": 3, "url": "x/Wehurei6/c.pdf"},
        "O1": {"key": "O1", "url": "x/kCj0pHP0/o.pdf", "extra": "x/Wehurei6/c.pdf"},
        "C2": {"key": "C2", "version": 4, "url": "x/Wehurei6/c2.pdf"},
        "O2": {"key": "O2", "url": "x/kCj0pHP0/o2.pdf"},  # 1 seule URL
    }
    monkeypatch.setattr(dd, "_get", lambda uid, k, key: store.get(k))
    pairs = [("C1", "O1", "ok"), ("C2", "O2", "orig incomplète"),
             ("CX", "OX", "copie absente")]
    to_delete, skipped = dd.plan_deletions("u", "k", pairs)
    assert [d["key"] for d in to_delete] == ["C1"]
    reasons = {k: why for k, _, why in skipped}
    assert "abstention" in reasons["C2"]
    assert "absente" in reasons["CX"]
