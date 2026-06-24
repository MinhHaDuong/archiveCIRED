"""Tests des fonctions pures d'appariement flou (sans réseau).

Les 195 docs sans clé d'archive n'ont pas d'identifiant joignable ; on les
rapproche des notices Zotero par titre/auteur/année. L'appariement est *flou*
et produit des candidats à **revue humaine** — jamais une fusion automatique
(règle projet : apparier par id, jamais par titre ; cf. faux doublons Sachs).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import match_untyped as mu  # noqa: E402


def test_normalize_strips_accents_case_punctuation():
    # normalisation pure : accents/casse/ponctuation, PAS les mots vides
    assert mu.normalize("L'Environnement, Obstacle ?") == "l environnement obstacle"
    assert mu.normalize("  Élément  pour   l'eau ") == "element pour l eau"
    assert mu.normalize(None) == ""


def test_tokens_drops_stopwords_and_short_tokens():
    # le filtrage des mots vides et des jetons d'une lettre vit dans _tokens
    assert mu._tokens("L'Environnement, Obstacle ?") == {"environnement", "obstacle"}
    assert mu._tokens("la gestion de l'eau") == {"gestion", "eau"}


def test_last_names_extracts_family_name():
    assert mu.last_names(["Hourcade J.-C."]) == {"hourcade"}
    assert mu.last_names(["Godard, Olivier", "Hourcade J.-C."]) == {"godard", "hourcade"}
    assert mu.last_names(None) == set()
    # un « auteur » qui est en fait un nom de revue reste un token, sans crash
    assert mu.last_names(["options"]) == {"options"}


def test_title_sim_token_jaccard():
    assert mu.title_sim("gestion de l'eau", "gestion de l'eau") == 1.0
    assert mu.title_sim("gestion de l'eau", "la gestion de l eau") > 0.7
    assert mu.title_sim("environnement", "fiscalité carbone") == 0.0
    # titres vides -> 0, pas de division par zéro
    assert mu.title_sim("", "") == 0.0


def test_title_match_containment_handles_truncation():
    # titre du doc = troncature du titre complet de la notice -> containment 1.0
    short = "gestion eau pays mediterraneens approche"
    full = "elements pour une nouvelle approche gestion eau pays mediterraneens"
    assert mu.title_match(short, full) == 1.0
    assert mu.title_match(short, full) > mu.title_sim(short, full)
    # garde-fou : deux titres courts à mots génériques ne s'apparient pas par containment
    assert mu.title_match("chaire developpement durable",
                          "le droit au developpement durable") < 0.6


def test_score_title_dominant_author_year_only_help():
    # auteur bruité (nom de revue) ne doit pas écraser un titre quasi identique
    doc = {"titre": "Eléments pour une nouvelle approche de la gestion de l'eau",
           "auteurs": ["La Méditerranée aujourd'hui"], "annee": 1975}
    notice = {"title": "Elements pour une nouvelle approche de la gestion de l'eau",
              "creators": [{"lastName": "Chabrol"}], "year": 1975}
    assert mu.score(doc, notice) >= 0.75
    # titre exact sans année ni auteur exploitables reste un appariement probable
    bare = {"titre": "Does uncertainty justify intensity emission caps?",
            "auteurs": None, "annee": None}
    exact = {"title": "Does uncertainty justify intensity emission caps?",
             "creators": [{"lastName": "Quirion"}], "year": 2005}
    assert mu.score(bare, exact) >= 0.75


def test_score_combines_title_author_year():
    doc = {"titre": "Gestion de l'eau en Méditerranée",
           "auteurs": ["Hourcade J.-C."], "annee": 1975}
    same = {"title": "La gestion de l'eau en Méditerranée",
            "creators": [{"lastName": "Hourcade"}], "year": 1975}
    other = {"title": "Fiscalité carbone et croissance",
             "creators": [{"lastName": "Godard"}], "year": 2009}
    assert mu.score(doc, same) > mu.score(doc, other)
    assert mu.score(doc, same) >= 0.75


def test_match_one_ranks_and_thresholds():
    doc = {"id": "x", "titre": "Gestion de l'eau", "auteurs": ["Hourcade J.-C."],
           "annee": 1975}
    notices = [
        {"key": "AAA", "title": "Gestion de l'eau", "creators": [{"lastName": "Hourcade"}], "year": 1975},
        {"key": "BBB", "title": "Tout autre sujet", "creators": [{"lastName": "Dupont"}], "year": 2000},
    ]
    cands = mu.match_one(doc, notices, top=2)
    assert cands[0]["key"] == "AAA"
    assert cands[0]["score"] > cands[1]["score"]


def test_score_pure_containment_without_corroboration_is_incertain():
    """Pure containment (jac < 0.4) sans auteur ni année → < 0.75 (incertain).

    Régression ticket 0026 : cov seul poussait un appariement Godard↔Hourcade
    à 0.75+ alors que le Jaccard valait 0.25.  Depuis le fix, une accroche
    purement par containment exige un recoupement auteur OU année pour rester
    « probable ».
    """
    # doc : 4 jetons, sous-ensemble du titre notice (12 jetons) → cov=1, jac≈0.33
    doc_containment = {
        "titre": "eau potable qualite ressources",
        "auteurs": ["Godard, Olivier"],
        "annee": 1984,
    }
    notice_long = {
        "title": ("eau potable qualite ressources naturelles mondiales "
                  "gouvernance institutions marches economique international"),
        "creators": [{"lastName": "Hourcade"}],
        "year": 1997,
    }
    s = mu.score(doc_containment, notice_long)
    assert s < 0.75, f"containment seul sans corroboration doit rester incertain, score={s}"


def test_score_pure_containment_with_author_stays_probable():
    """Containment + même auteur → reste ≥ 0.75 (probable)."""
    doc = {
        "titre": "eau potable qualite ressources",
        "auteurs": ["Godard, Olivier"],
        "annee": 1984,
    }
    notice = {
        "title": ("eau potable qualite ressources naturelles mondiales "
                  "gouvernance institutions marches economique international"),
        "creators": [{"lastName": "Godard"}],
        "year": 1997,
    }
    assert mu.score(doc, notice) >= 0.75


def test_score_pure_containment_with_year_stays_probable():
    """Containment + même année → reste ≥ 0.75 (probable)."""
    doc = {
        "titre": "eau potable qualite ressources",
        "auteurs": ["Godard, Olivier"],
        "annee": 1984,
    }
    notice = {
        "title": ("eau potable qualite ressources naturelles mondiales "
                  "gouvernance institutions marches economique international"),
        "creators": [{"lastName": "Hourcade"}],
        "year": 1984,
    }
    assert mu.score(doc, notice) >= 0.75


def test_match_all_partitions_probable_uncertain_absent():
    docs = [
        {"id": "hit", "titre": "Gestion de l'eau", "auteurs": ["Hourcade J.-C."], "annee": 1975},
        {"id": "gone", "titre": "Sujet introuvable nulle part", "auteurs": ["Inconnu X."], "annee": 1999},
        {"id": "nometa", "titre": None, "auteurs": None, "annee": None},
    ]
    notices = [
        {"key": "AAA", "title": "La gestion de l'eau", "creators": [{"lastName": "Hourcade"}], "year": 1975},
    ]
    r = mu.match_all(docs, notices, probable=0.75, maybe=0.5)
    assert r["total"] == 3
    ids_probable = {m["doc_id"] for m in r["probable"]}
    assert "hit" in ids_probable
    ids_absent = set(r["absent"])
    assert "gone" in ids_absent
    # un doc sans métadonnée exploitable est signalé à part, pas noyé dans "absent"
    assert "nometa" in r["sans_metadonnees"]
