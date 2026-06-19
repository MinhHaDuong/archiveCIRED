"""Tests des fonctions pures de réconciliation (sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import reconcile_zotero as rz  # noqa: E402


def test_extract_archive_key_variants():
    assert rz.extract_archive_key("TDM/1970_CIR_SAC_0317.pdf") == "CIR_SAC_0317"
    assert rz.extract_archive_key("docs/CIR_SAC_0317.pdf") == "CIR_SAC_0317"
    assert (rz.extract_archive_key("https://x/docs/ENPC00_AR_LEESU_0012.PDF")
            == "ENPC00_AR_LEESU_0012")
    assert rz.extract_archive_key("CIR_GOD_0052") == "CIR_GOD_0052"


def test_extract_archive_key_none():
    assert rz.extract_archive_key("Godard-OCDE-libre.pdf") is None
    assert rz.extract_archive_key("") is None
    assert rz.extract_archive_key(None) is None


def test_doc_keys_dedups_across_files():
    # même numéro d'archive dans deux dossiers -> une seule clé
    doc = {"fichiers": [
        {"fichier": "TDM/1970_CIR_SAC_0317.pdf", "role": "doublon"},
        {"fichier": "docs/CIR_SAC_0317.pdf", "role": "principal"},
    ]}
    assert rz.doc_keys(doc) == {"CIR_SAC_0317"}


def test_doc_keys_empty_when_no_archive_name():
    assert rz.doc_keys({"fichiers": [{"fichier": "docs/Godard-libre.pdf"}]}) == set()


def test_fonds_of():
    assert rz.fonds_of("CIR_SAC_0317") == "CIR_SAC"
    assert rz.fonds_of("CIR_GOD_0052") == "CIR_GOD"
    assert rz.fonds_of("ENPC00_AR_LEESU_0012") == "ENPC_LEESU"


def test_classify_partitions_docs():
    docs = [
        {"id": "a", "fichiers": [{"fichier": "docs/CIR_SAC_0001.pdf"}]},  # catalogué
        {"id": "b", "fichiers": [{"fichier": "docs/CIR_SAC_0002.pdf"}],
         "annee": 1980, "titre": "T"},                                    # à ajouter
        {"id": "c", "fichiers": [{"fichier": "docs/Godard-libre.pdf"}]},  # sans clé
    ]
    zkeys = {"CIR_SAC_0001", "CIR_GOD_9999"}  # 9999 = orpheline
    r = rz.classify(docs, zkeys)
    assert r["total_docs"] == 3
    assert r["docs_catalogues"] == 1
    assert r["docs_a_ajouter"] == 1
    assert r["docs_sans_cle_archive"] == 1
    assert r["liste_docs_a_ajouter"][0]["id"] == "b"
    assert r["liste_cles_orphelines"] == ["CIR_GOD_9999"]
    assert r["par_fonds"]["CIR_SAC"] == {"index": 2, "catalogue": 1}


def test_load_env_strips_quotes(tmp_path):
    f = tmp_path / "e.env"
    f.write_text('ZOTERO_API_KEY="abc123"\n# c\nZOTERO_USER_ID = Base R2DS \n')
    env = rz.load_env(f)
    assert env["ZOTERO_API_KEY"] == "abc123"
    assert env["ZOTERO_USER_ID"] == "Base R2DS"
