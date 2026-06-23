"""Tests des fonctions pures de réconciliation des URL recueil (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import reconcile_recueil_urls as rru  # noqa: E402


def test_distinct_rows_garde_taille_differente():
    comp = [
        {"verdict": "taille_differente", "url_recueil": "u1", "mylib_key": "K1"},
        {"verdict": "taille_identique", "url_recueil": "u2", "mylib_key": "K2",
         "fichiers_identiques": True},
        {"verdict": "url_manquante", "url_recueil": "", "mylib_key": "K3"},
    ]
    out = rru.distinct_rows(comp)
    assert [r["mylib_key"] for r in out] == ["K1"]


def test_distinct_rows_garde_hash_different():
    comp = [{"verdict": "taille_identique", "url_recueil": "u", "mylib_key": "K",
             "fichiers_identiques": False}]
    assert len(rru.distinct_rows(comp)) == 1


def test_distinct_rows_ignore_sans_cible():
    comp = [{"verdict": "taille_differente", "url_recueil": "u", "mylib_key": ""}]
    assert rru.distinct_rows(comp) == []


def test_already_linked():
    children = [{"linkMode": "linked_url", "url": "http://x/a.pdf"},
                {"linkMode": "imported_file", "url": "http://x/a.pdf"}]
    assert rru.already_linked(children, "http://x/a.pdf") is True
    assert rru.already_linked(children, "http://x/b.pdf") is False


def test_plan_links_marque_deja_present():
    rows = [
        {"mylib_key": "K1", "url_recueil": "http://x/a.pdf", "annee": "1981",
         "titre": "A"},
        {"mylib_key": "K2", "url_recueil": "http://x/b.pdf", "annee": "1982",
         "titre": "B"},
    ]
    lib_children = {"K1": [{"linkMode": "linked_url", "url": "http://x/a.pdf"}]}
    planned = rru.plan_links(rows, lib_children)
    by_target = {p["target"]: p for p in planned}
    assert by_target["K1"]["already_present"] is True
    assert by_target["K2"]["already_present"] is False
    assert by_target["K2"]["title"].endswith("(b.pdf)")
