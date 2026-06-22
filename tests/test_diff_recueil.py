"""Tests du diff de corrections recueil → perso (purs, sans réseau).

L'appariement flou (main) dépend de match_untyped (ticket 0008, pas encore sur
main) ; ces tests ne couvrent que la logique de diff, indépendante du matcher.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import diff_recueil as dr  # noqa: E402


def test_diff_fields_detects_addition_when_perso_empty():
    group = {"pages": "145-174", "issue": "39/40"}
    perso = {"pages": "", "issue": "39/40"}
    d = dr.diff_fields(group, perso)
    assert d["pages"]["type"] == "ajout"
    assert "issue" not in d  # identiques


def test_diff_fields_detects_modification():
    d = dr.diff_fields({"title": "Titre corrigé"}, {"title": "Titre ancien"})
    assert d["title"]["type"] == "modification"
    assert d["title"]["groupe"] == "Titre corrigé"


def test_diff_fields_never_erases_when_group_empty():
    # perso renseigné, groupe vide -> jamais d'effacement, absent du diff
    assert dr.diff_fields({"abstractNote": ""}, {"abstractNote": "résumé"}) == {}


def test_diff_fields_ignores_whitespace_and_case():
    assert dr.diff_fields({"title": "  Le  Titre "}, {"title": "le titre"}) == {}


def test_diff_creators_flags_difference():
    group = {"creators": [{"lastName": "Godard", "firstName": "Olivier"}]}
    perso = {"creators": [{"lastName": "Godard", "firstName": "O."}]}
    d = dr.diff_fields(group, perso)
    assert d["creators"]["type"] == "modification"


def test_diff_creators_identical_no_diff():
    cr = [{"lastName": "Hourcade", "firstName": "Jean-Charles"}]
    assert dr.diff_fields({"creators": cr}, {"creators": list(cr)}) == {}


def test_corrections_report_counts():
    pairs = [
        {"groupe": {"pages": "1-10", "title": "T2"}, "perso": {"pages": "", "title": "T1"},
         "perso_key": "K1", "score": 0.9},
        {"groupe": {"title": "Same"}, "perso": {"title": "Same"},
         "perso_key": "K2", "score": 0.8},  # aucune correction
    ]
    r = dr.corrections_report(pairs)
    assert r["paires_avec_corrections"] == 1
    assert r["total_ajouts"] == 1          # pages
    assert r["total_modifications"] == 1   # title
    assert r["corrections"][0]["perso_key"] == "K1"
