"""Tests de la logique d'ajout de tag (pure, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import zotero_tag_collections as ztc  # noqa: E402


def test_merge_tags_adds_when_absent():
    assert ztc.merge_tags([], "CIRED") == [{"tag": "CIRED"}]
    assert ztc.merge_tags([{"tag": "x"}], "CIRED") == [{"tag": "x"}, {"tag": "CIRED"}]


def test_merge_tags_none_when_present():
    assert ztc.merge_tags([{"tag": "CIRED"}], "CIRED") is None


def test_merge_tags_preserves_existing():
    out = ztc.merge_tags([{"tag": "a"}, {"tag": "b"}], "LEESU")
    assert {"tag": "a"} in out and {"tag": "b"} in out and {"tag": "LEESU"} in out
