"""Tests des fonctions pures d'audit du miroir Recueil_CIRED → My Library.

Vérification indépendante (ticket 0025) : aucune écriture Zotero, tout le verdict
repose sur une fonction pure `assess_item` testable sur fixtures.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import verify_recueil_mirror as vm  # noqa: E402


# --- normalisation -----------------------------------------------------------

def test_norm_text_folds_accents_and_punct():
    assert vm.norm_text("Décentralisation: un levier!") == "decentralisation un levier"
    assert vm.norm_text("  A   B  ") == "a b"
    assert vm.norm_text(None) == ""


def test_norm_year_extracts_four_digits():
    assert vm.norm_year("1993-05") == "1993"
    assert vm.norm_year("1993") == "1993"
    assert vm.norm_year("") == ""
    assert vm.norm_year(None) == ""


def test_author_lastnames_normalised_set():
    creators = [{"creatorType": "author", "lastName": "Godard", "firstName": "O."},
                {"name": "CIRED"}]
    assert vm.author_lastnames(creators) == {"godard", "cired"}
    assert vm.author_lastnames(None) == set()


def test_url_basename():
    assert vm.url_basename("https://x.fr/a/B%20C.PDF") == "b c.pdf"
    assert vm.url_basename("") == ""
    assert vm.url_basename(None) == ""


# --- couverture des champs énumérés ------------------------------------------

def test_metadata_missing_reports_absent_enriched_field():
    g = {"DOI": "10.1/x", "volume": "22", "pages": "29-35"}
    lib = {"DOI": "10.1/x", "volume": "22"}  # pages manquant
    assert vm.metadata_missing(g, lib) == ["pages"]


def test_metadata_missing_empty_when_lib_superset():
    g = {"volume": "22"}
    lib = {"volume": "22", "pages": "1-9", "DOI": "10.1/x"}
    assert vm.metadata_missing(g, lib) == []


def test_metadata_missing_no_numeric_substring_false_cover():
    # volume « 2 » ne doit PAS être couvert par une année « 2024 » (sous-chaîne).
    assert vm.metadata_missing({"volume": "2"}, {"volume": "2024"}) == ["volume"]
    # mais « 29-35 » reste couvert par « pp. 29-35 » (inclusion par tokens).
    assert vm.metadata_missing({"pages": "29-35"}, {"pages": "pp. 29-35"}) == []


def test_metadata_missing_ignores_typographic_labels():
    # Les étiquettes d'énumération (« vol. », « n° », « p. ») ne sont pas de
    # l'information : la version propre côté lib couvre la version préfixée du recueil.
    g = {"volume": "vol. 34", "issue": "n°1", "pages": "p. 137-151"}
    lib = {"volume": "34", "issue": "1", "pages": "137-151"}
    assert vm.metadata_missing(g, lib) == []
    # symétrique : « 31 p. » couvert par « 31 »
    assert vm.metadata_missing({"pages": "31 p."}, {"pages": "31"}) == []


# --- assess_item : les trois niveaux de préservation -------------------------

def _enrich(items):
    """(data, url_basenames) — pas d'enfants dans les fixtures simples."""
    return [(d, {vm.url_basename(d.get("url"))} - {""}) for d in items]


def test_assess_url_preserved_when_recueil_url_present():
    g = {"key": "G1", "title": "T", "date": "1993", "url": "https://inari/recueil/x.pdf",
         "creators": [{"lastName": "Godard"}]}
    lib = _enrich([{"key": "L1", "title": "T", "date": "1993",
                    "url": "https://inari/recueil/x.pdf"}])
    r = vm.assess_item(g, lib)
    assert r["tier"] == "url_preserved"
    assert r["matched"] == "L1"


def test_assess_url_preserved_when_recueil_url_in_extra():
    # 2e URL recueil stockée dans Extra (url = numérisation) → toujours préservée.
    g = {"key": "G1b", "title": "T", "date": "1993",
         "url": "https://inari/recueil/x.pdf", "creators": [{"lastName": "Godard"}]}
    lib = vm._enrich_library([{"key": "L1b", "title": "Tout autre titre",
                               "date": "1993",
                               "url": "https://inari/numerisation/CIR_GOD_9.pdf",
                               "extra": "https://inari/recueil/x.pdf"}], {})
    r = vm.assess_item(g, lib)
    assert r["tier"] == "url_preserved"
    assert r["matched"] == "L1b"


def test_assess_doc_equivalent_when_metadata_full_and_pdf_present():
    # Pas de copie URL, mais une notice pré-existante couvre tout + a un PDF inari.
    g = {"key": "G2", "title": "Les villes", "date": "1996", "volume": "209",
         "url": "https://inari/recueil/villes.pdf",
         "creators": [{"lastName": "Godard"}]}
    lib = _enrich([{"key": "L2", "title": "Les villes", "date": "1996", "volume": "209",
                    "url": "https://inari/archive/anciennes-villes.pdf",
                    "creators": [{"lastName": "Godard"}]}])
    r = vm.assess_item(g, lib)
    assert r["tier"] == "doc_equivalent"
    assert r["matched"] == "L2"


def test_assess_loss_when_enriched_field_dropped():
    # Notice trouvée (titre+année+auteur) mais il lui manque un champ du groupe.
    g = {"key": "G3", "title": "Civilisation", "date": "1972", "pages": "11-20",
         "url": "https://inari/recueil/civ.pdf", "creators": [{"lastName": "Sachs"}]}
    lib = _enrich([{"key": "L3", "title": "Civilisation", "date": "1972",
                    "url": "https://inari/archive/civ-old.pdf",
                    "creators": [{"lastName": "Sachs"}]}])  # pages absent
    r = vm.assess_item(g, lib)
    assert r["tier"] == "loss"
    assert r["reason"] == "metadata_incomplete"
    assert "pages" in r["missing"]


def test_assess_loss_when_no_match():
    g = {"key": "G4", "title": "Decentralisation France", "date": "1986",
         "url": "https://inari/recueil/dec.pdf", "creators": [{"lastName": "Ceron"}]}
    lib = _enrich([{"key": "L4", "title": "Tout autre sujet", "date": "1979",
                    "url": "https://inari/archive/autre.pdf",
                    "creators": [{"lastName": "Godard"}]}])
    r = vm.assess_item(g, lib)
    assert r["tier"] == "loss"
    assert r["reason"] == "no_match"


def test_assess_author_corroboration_blocks_title_only_match():
    # Même titre + année mais auteur différent : ne couvre pas (jamais par titre seul).
    g = {"key": "G5", "title": "Rapport", "date": "1980", "url": "https://inari/recueil/r.pdf",
         "creators": [{"lastName": "Sachs"}]}
    lib = _enrich([{"key": "L5", "title": "Rapport", "date": "1980",
                    "url": "https://inari/archive/r2.pdf",
                    "creators": [{"lastName": "Hourcade"}]}])
    r = vm.assess_item(g, lib)
    assert r["tier"] == "loss"
    assert r["reason"] == "no_match"


def test_assess_no_title_only_match_when_group_lacks_creators():
    # Groupe sans auteur : titre+année identiques ne suffisent pas (jamais par
    # titre seul) -> signalé pour revue, pas apparié.
    g = {"key": "G8", "title": "Croissance", "date": "1972",
         "url": "https://inari/recueil/c.pdf", "creators": []}
    lib = _enrich([{"key": "L8", "title": "Croissance", "date": "1972",
                    "url": "https://inari/archive/c2.pdf", "creators": []}])
    r = vm.assess_item(g, lib)
    assert r["tier"] == "loss"
    assert r["reason"] == "no_match"


def test_assess_doc_equivalent_requires_pdf_on_matched_notice():
    # Le groupe porte un PDF, la notice candidate n'en a aucun : PDF perdu.
    g = {"key": "G6", "title": "Sans PDF", "date": "1981", "url": "https://inari/recueil/s.pdf",
         "creators": [{"lastName": "Thery"}]}
    lib = _enrich([{"key": "L6", "title": "Sans PDF", "date": "1981", "url": "",
                    "creators": [{"lastName": "Thery"}]}])
    r = vm.assess_item(g, lib)
    assert r["tier"] == "loss"
    assert r["reason"] == "no_pdf_on_match"


def test_assess_no_pdf_required_when_group_has_no_url():
    # Notice de groupe sans URL : rien à préserver côté PDF, métadonnées couvertes.
    g = {"key": "G7", "title": "Rapport sans lien", "date": "1993", "url": "",
         "creators": [{"lastName": "Godard"}]}
    lib = _enrich([{"key": "L7", "title": "Rapport sans lien", "date": "1993", "url": "",
                    "creators": [{"lastName": "Godard"}]}])
    r = vm.assess_item(g, lib)
    assert r["tier"] == "doc_equivalent"


# --- notes d'annotation ------------------------------------------------------

def test_note_text_strips_html():
    assert vm.note_text("<p>Bon <b>texte</b></p>") == "Bon texte"
    assert vm.note_text(None) == ""


def test_unpreserved_notes_flags_absent_text():
    gnotes = [{"parentItem": "P1", "note": "<p>commentaire unique d'Antonin sur la crise</p>"},
              {"parentItem": "P2", "note": "<p>texte présent ailleurs</p>"},
              {"parentItem": "P3", "note": ""}]  # vide : jamais une perte
    lib_notes = ["un autre texte présent ailleurs dans la bibliothèque"]
    lost = vm.unpreserved_notes(gnotes, lib_notes)
    parents = {n["parent"] for n in lost}
    assert parents == {"P1"}


def test_unpreserved_notes_matches_across_paragraph_boundaries():
    # Note multi-paragraphe : la recherche ne doit pas être cassée par les noms
    # de balises (un probe traversant </p><p> ou <br/> doit matcher).
    gnotes = [{"parentItem": "P1",
               "note": "<p>très bon texte</p>\n<p>culture et technologie</p>"},
              {"parentItem": "P2",
               "note": "<p>peut-être pas à lire<br />rapport à l'OCDE</p>"}]
    # Côté lib : mêmes notes ré-injectées avec en-tête (balises incluses).
    lib_notes = [
        "<p><strong>Note de Antonin Pottier</strong></p>\n<p>très bon texte</p>\n<p>culture et technologie</p>",
        "<p><strong>Note de Antonin Pottier</strong></p>\n<p>peut-être pas à lire<br />rapport à l'OCDE</p>",
    ]
    assert vm.unpreserved_notes(gnotes, lib_notes) == []


def test_assess_all_note_loss_forces_no_go():
    group = [{"key": "A", "title": "T", "date": "1990", "url": "https://inari/recueil/a.pdf",
              "creators": [{"lastName": "X"}]}]
    lib = [{"key": "LA", "title": "T", "date": "1990", "url": "https://inari/recueil/a.pdf"}]
    gnotes = [{"parentItem": "A", "note": "annotation introuvable cote perso"}]
    rep = vm.assess_all(group, lib, {}, group_notes=gnotes, lib_note_texts=[])
    assert rep["losses"] == []           # métadonnées/PDF OK
    assert len(rep["note_losses"]) == 1  # mais une note perdue
    assert rep["verdict"] == "no-go"


# --- agrégation --------------------------------------------------------------

def test_assess_all_partitions_and_verdict():
    group = [
        {"key": "A", "title": "T", "date": "1990", "url": "https://inari/recueil/a.pdf",
         "creators": [{"lastName": "X"}]},
        {"key": "B", "title": "Other", "date": "1991", "url": "https://inari/recueil/b.pdf",
         "creators": [{"lastName": "Y"}]},
    ]
    lib = [
        {"key": "LA", "title": "T", "date": "1990", "url": "https://inari/recueil/a.pdf"},
        {"key": "LZ", "title": "Nope", "date": "2000", "url": "https://inari/z.pdf"},
    ]
    rep = vm.assess_all(group, lib, children_by_parent={})
    assert rep["total"] == 2
    assert rep["url_preserved"] == 1
    assert len(rep["losses"]) == 1
    assert rep["losses"][0]["key"] == "B"
    assert rep["verdict"] == "no-go"


def test_duplicate_clusters_groups_same_title_year():
    lib = [
        {"key": "A", "title": "Le modèle", "date": "2010"},
        {"key": "B", "title": "Le Modèle", "date": "2010-05"},  # même (titre, année)
        {"key": "C", "title": "Autre", "date": "1999"},
        {"key": "D", "title": "", "date": "2000"},  # titre vide : ignoré
    ]
    clusters = vm.duplicate_clusters(lib)
    assert len(clusters) == 1
    assert set(clusters[0]["keys"]) == {"A", "B"}


def test_assess_all_go_when_no_loss():
    group = [{"key": "A", "title": "T", "date": "1990", "url": "https://inari/recueil/a.pdf",
              "creators": [{"lastName": "X"}]}]
    lib = [{"key": "LA", "title": "T", "date": "1990", "url": "https://inari/recueil/a.pdf"}]
    rep = vm.assess_all(group, lib, children_by_parent={})
    assert rep["verdict"] == "go"
    assert rep["losses"] == []
