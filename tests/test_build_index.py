import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from build_index import enumerate_docs


def test_enumerate_docs_filename_patterns():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "2006-129.pdf").touch()
        (d / "1975-019_1.pdf").touch()
        (d / "CIR_SAC_0001.pdf").touch()
        (d / "1973_CIR_SAC_0011.txt").touch()  # must NOT appear
        (d / "CIR_GOD_0005.pdf").touch()
        (d / "CIR-HOU-TH.pdf").touch()
        (d / "ENPC00_AR_LEESU_0001.pdf").touch()
        (d / "ENPC00_OUV_LEESU_0001.pdf").touch()
        (d / "ENPC00_TH_LEESU_0001.pdf").touch()
        (d / "Inventaire_Doc_CIRED.xls").touch()  # must NOT appear
        (d / "robots.txt").touch()  # must NOT appear
        tdm = d / "TDMSachs"
        tdm.mkdir()
        (tdm / "something.html").touch()

        entries = enumerate_docs(d)

    by_id = {e["id"]: e for e in entries}
    ids = set(by_id)

    assert "2006-129" in ids
    assert "1975-019_1" in ids
    assert "CIR_SAC_0001" in ids
    assert "CIR_GOD_0005" in ids
    assert "CIR-HOU-TH" in ids
    assert "ENPC00_AR_LEESU_0001" in ids
    assert "ENPC00_OUV_LEESU_0001" in ids
    assert "ENPC00_TH_LEESU_0001" in ids

    # Exclusions
    assert not any("Inventaire" in e.get("fichier", "") for e in entries)
    assert not any("TDMSachs" in e.get("fichier", "") for e in entries)
    assert not any(e["fichier"].endswith(".txt") for e in entries)

    # Year
    assert by_id["2006-129"]["annee"] == 2006
    assert by_id["1975-019_1"]["annee"] == 1975
    assert by_id["CIR_SAC_0001"]["annee"] is None

    # Type mapping — including the OUV→ouvrage fix
    assert by_id["CIR_SAC_0001"]["type"] == "gris-sachs"
    assert by_id["CIR-HOU-TH"]["type"] == "these"
    assert by_id["ENPC00_AR_LEESU_0001"]["type"] == "article"
    assert by_id["ENPC00_OUV_LEESU_0001"]["type"] == "ouvrage"
    assert by_id["ENPC00_TH_LEESU_0001"]["type"] == "these"

    # Sorted by id
    ids_list = [e["id"] for e in entries]
    assert ids_list == sorted(ids_list)

    # Schema completeness
    required = {
        "id",
        "annee",
        "auteurs",
        "titre",
        "type",
        "revue_editeur",
        "fichier",
        "texte_ocr",
        "statut_droits",
        "hal_id",
        "notes",
    }
    for e in entries:
        assert set(e.keys()) == required, f"Schema mismatch for {e['id']}"


@pytest.mark.adherence
def test_ruff():
    result = subprocess.run(["uv", "run", "ruff", "check", "."], capture_output=True)
    assert result.returncode == 0, result.stdout.decode()
