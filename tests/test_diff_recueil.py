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


def test_pair_fuzzy_matches_by_title_year_and_finds_corrections():
    # match_untyped est sur main depuis le merge de 0008 : appariement réel.
    group = [{"title": "Oppositions locales aux projets d'équipement",
              "date": "1981", "pages": "417-438",
              "creators": [{"lastName": "Nicolon", "firstName": "Alexandre"}]}]
    perso = [
        {"key": "HIT", "title": "Oppositions locales aux projets d'équipement",
         "date": "1981", "pages": "", "creators": [{"lastName": "Nicolon", "firstName": "A."}]},
        {"key": "MISS", "title": "Tout autre sujet sans rapport",
         "date": "2010", "pages": "1-2", "creators": [{"lastName": "Autre"}]},
    ]
    pairs = dr._pair_fuzzy(group, perso, threshold=0.75)
    assert len(pairs) == 1 and pairs[0]["perso_key"] == "HIT"
    d = dr.diff_fields(pairs[0]["groupe"], pairs[0]["perso"])
    assert d["pages"]["type"] == "ajout"      # perso vide -> groupe renseigne


def test_render_markdown_one_row_per_field_change():
    report = {
        "paires_avec_corrections": 1, "paires_appariement_douteux": 0,
        "total_ajouts": 1, "total_modifications": 1,
        "corrections": [{
            "perso_key": "K1", "score": 0.9, "titre_sim": 1.0, "titre": "Un titre",
            "champs": {"pages": {"type": "ajout", "perso": "", "groupe": "1-10"},
                       "title": {"type": "modification", "perso": "A | B", "groupe": "A-B"}},
        }],
    }
    md = dr.render_markdown(report)
    assert "Valeur actuelle (My Library)" in md     # en-tête explicite, sans ambiguïté
    assert "Valeur d'Antonin (Recueil_CIRED)" in md
    assert "| 1 | Un titre | `pages` | ➕ ajout | — | 1-10 |  |" in md  # colonne Note vide
    assert "\\|" in md                              # pipe échappé dans une valeur
    assert md.count("\n| 2 |") == 1                 # numérotation continue


def test_render_markdown_partitions_doubtful_matches():
    report = {
        "paires_avec_corrections": 2, "paires_appariement_douteux": 1,
        "total_ajouts": 0, "total_modifications": 2,
        "corrections": [
            {"perso_key": "OK", "score": 0.9, "titre_sim": 1.0, "titre": "Bon",
             "champs": {"pages": {"type": "modification", "perso": "1", "groupe": "2"}}},
            {"perso_key": "BAD", "score": 0.8, "titre_sim": 0.5, "titre": "Douteux",
             "champs": {"title": {"type": "modification", "perso": "X", "groupe": "Y"}}},
        ],
    }
    md = dr.render_markdown(report)
    sure, doubt = md.split("Appariement douteux")
    assert "Bon" in sure and "Bon" not in doubt        # match sûr au-dessus
    assert "Douteux" in doubt                           # match faible isolé en bas


def test_diff_fields_drops_publicationtitle_that_copies_the_title():
    group = {"title": "Mon article", "publicationTitle": "Mon article"}
    perso = {"title": "Mon article", "publicationTitle": "Futuribles"}
    assert "publicationTitle" not in dr.diff_fields(group, perso)


def test_diff_fields_normalizes_date_to_iso():
    d = dr.diff_fields({"date": "07/1994"}, {"date": "1991"})
    assert d["date"]["groupe"] == "1994-07"


def test_field_note_flags_allcaps_and_publisher_in_booktitle():
    d = dr.diff_fields({"bookTitle": "DÉVELOPPEMENT local. Genève: Editions Régionales"},
                       {"bookTitle": ""})
    assert "ALLCAPS" in d["bookTitle"]["note"]
    assert "éditeur" in d["bookTitle"]["note"]


def test_norm_number_strips_prefix():
    assert dr._norm_number("vol. 8") == "8"
    assert dr._norm_number("n°316") == "316"
    assert dr._norm_number("v.3") == "3"
    assert dr._norm_number("42") == "42"
    assert dr._norm_number("numéro 7") == "7"
    assert dr._norm_number("n. 12") == "12"
    assert dr._norm_number("vol.") == "vol."     # pas un entier : inchangé


def test_norm_pages_normalizes_range():
    assert dr._norm_pages("417-438") == "417–438"
    assert dr._norm_pages("29–35") == "29–35"    # déjà tiret long
    assert dr._norm_pages("80") == "80"
    assert dr._norm_pages("22 p.") == "22 p."   # décompte, inchangé


def test_diff_fields_normalizes_volume_issue():
    # groupe="8", perso="vol. 8" → patch généré : Zotero doit passer à "8"
    d = dr.diff_fields({"volume": "8"}, {"volume": "vol. 8"})
    assert d["volume"]["type"] == "modification"
    assert d["volume"]["groupe"] == "8"
    assert d["volume"]["perso"] == "vol. 8"
    # idem issue : n°2 → 2
    d2 = dr.diff_fields({"issue": "2"}, {"issue": "n°2"})
    assert d2["issue"]["groupe"] == "2"
    # groupe normalisé aussi quand il porte un préfixe
    d3 = dr.diff_fields({"volume": "316"}, {"volume": "vol. 28"})
    assert d3["volume"]["groupe"] == "316"


def test_diff_fields_normalizes_pages_range():
    assert dr.diff_fields({"pages": "417–438"}, {"pages": "417-438"}) == {}
    d = dr.diff_fields({"pages": "417-438"}, {"pages": "22 p."})
    assert d["pages"]["groupe"] == "417–438"


def test_field_note_flags_publisher_equal_to_journal():
    d = dr.diff_fields({"publisher": "Futuribles", "publicationTitle": "Futuribles"},
                       {"publisher": "", "publicationTitle": "Futuribles"})
    assert "organisme" in d["publisher"]["note"]


def test_pair_fuzzy_one_to_one_keeps_best_title_match():
    # deux notices de groupe convoitent la même perso ; la perso va au titre le
    # plus proche, la perdante est écartée (source des faux appariements).
    perso = [{"key": "P", "title": "Plaidoyer pour les technologies appropriées",
              "date": "1980", "creators": [{"lastName": "Hourcade"}]}]
    group = [
        {"title": "Plaidoyer pour les technologies appropriées",
         "date": "1980", "creators": [{"lastName": "Hourcade"}]},          # vrai (sim 1.0)
        {"title": "Mimétisme ou pluralisme de technologies appropriées",
         "date": "1980", "creators": [{"lastName": "Hourcade"}]},          # faux prétendant
    ]
    pairs = dr._pair_fuzzy(group, perso, threshold=0.6)
    assert len(pairs) == 1
    assert pairs[0]["titre_sim"] == 1.0


def test_report_to_ledger_filters_noted_creators_and_excludes():
    report = {"corrections": [
        {"perso_key": "A", "titre_sim": 1.0, "titre": "Bon",
         "champs": {"pages": {"type": "modification", "perso": "1", "groupe": "417-438"},
                    "volume": {"type": "modification", "perso": "x", "groupe": "31", "note": "à vérifier"},
                    "creators": {"type": "modification", "groupe": ["g"], "perso": ["p"]}}},
        {"perso_key": "B", "titre_sim": 0.5, "titre": "Douteux",
         "champs": {"pages": {"type": "ajout", "perso": "", "groupe": "1-2"}}},
        {"perso_key": "EXCL", "titre_sim": 1.0, "titre": "Exclu",
         "champs": {"date": {"type": "ajout", "perso": "", "groupe": "1996-05"}}},
    ]}
    led = dr.report_to_ledger(report, exclude_keys={"EXCL"})
    assert len(led) == 1                      # B douteux écarté, EXCL exclu
    e = led[0]
    assert e["key"] == "A" and e["set"] == {"pages": "417-438"}  # volume noté + creators exclus
    assert e["applied"] is False
