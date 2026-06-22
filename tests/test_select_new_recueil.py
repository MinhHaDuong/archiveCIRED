"""Tests de la sélection des documents nouveaux du recueil (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import select_new_recueil as snr  # noqa: E402


def test_parse_recueil_id_zero_pads():
    assert snr.parse_recueil_id("1973-9-reaction.pdf") == "1973-009"
    assert snr.parse_recueil_id("1975 15-Hourcade.pdf") == "1975-015"
    assert snr.parse_recueil_id("2004 127-Caparros.pdf") == "2004-127"


def test_parse_recueil_id_rejects_non_standard():
    assert snr.parse_recueil_id("PAS-DANS-LA-LISTE-1975 elements.pdf") is None
    assert snr.parse_recueil_id("1997-Godard-111-Social.pdf") is None
    assert snr.parse_recueil_id("2000-hourcade-le-climat.pdf") is None


def test_classify_buckets():
    att = [
        {"fichier": "attente/x/1973-9-deja.pdf", "hash": "h_dup"},      # hash déjà ailleurs
        {"fichier": "attente/x/2007-136-new.pdf", "hash": "h_new"},     # unique, id absent
        {"fichier": "attente/x/1975 15-scan.pdf", "hash": "h_scan"},    # unique, id présent
        {"fichier": "attente/x/PAS-DANS-LA-LISTE-z.pdf", "hash": "h_w"},  # unique, id non std
    ]
    corpus_hashes = {"h_dup"}            # h_dup existe hors recueil
    docids = {"1975-015"}                # seul 1975-015 est dans docs/
    r = snr.classify_recueil(att, corpus_hashes, docids)
    assert r["deja_corpus"] == ["attente/x/1973-9-deja.pdf"]
    assert [d["id"] for d in r["nouveau"]] == ["2007-136"]
    assert [d["id"] for d in r["meilleur_scan"]] == ["1975-015"]
    assert r["id_non_standard"] == ["attente/x/PAS-DANS-LA-LISTE-z.pdf"]


def test_classify_flags_colliding_new_ids():
    # deux articles distincts au même numéro d'archive (cf. 1975-019 ×2)
    att = [
        {"fichier": "attente/x/1975-19-artuso.pdf", "hash": "h1"},
        {"fichier": "attente/x/1975-19-chabrol.pdf", "hash": "h2"},
    ]
    r = snr.classify_recueil(att, corpus_hashes=set(), docids=set())
    assert "1975-019" in r["ids_en_collision"]
