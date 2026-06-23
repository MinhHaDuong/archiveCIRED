"""Tests des fonctions pures de comparaison d'URL recueil (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import compare_recueil_urls as cru  # noqa: E402


def _side(url, size):
    return {"url": url, "head": {"size": size}}


def test_classify_taille_differente():
    assert cru.classify(_side("a", 100), _side("b", 200)) == "taille_differente"


def test_classify_taille_identique():
    assert cru.classify(_side("a", 100), _side("b", 100)) == "taille_identique"


def test_classify_url_manquante_si_un_cote_vide():
    assert cru.classify(_side("", None), _side("b", 100)) == "url_manquante"
    assert cru.classify(_side("a", 100), _side("", None)) == "url_manquante"


def test_classify_inatteignable_si_taille_absente():
    # URL présente des deux côtés mais HEAD n'a pas rendu de taille
    assert cru.classify(_side("a", None), _side("b", 100)) == "inatteignable"
