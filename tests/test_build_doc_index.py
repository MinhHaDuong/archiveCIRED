import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from build_doc_index import canonical_key, group_by_canonical_key


def test_canonical_key():
    assert canonical_key("docs/1994_CIR_SAC_0042.pdf") == "cir_sac_0042"
    assert canonical_key("1994-042-Sachs-Titre.pdf") == "1994-042"
    assert canonical_key("2006-129.pdf") == "2006-129"
    assert canonical_key("1994-42-Author.pdf") == "1994-042"  # zero-padding


def test_group_by_canonical_key_no_cross_decade():
    """1994-042 and 2004-042 must NOT group together."""
    records = [
        {
            "fichier": "docs/1994-042-Foo.pdf",
            "hash": "aaa",
            "ext": ".pdf",
            "taille": 100,
        },
        {
            "fichier": "docs/2004-042-Bar.pdf",
            "hash": "bbb",
            "ext": ".pdf",
            "taille": 200,
        },
    ]
    groups = group_by_canonical_key(records)
    assert len(groups) == 2


def test_group_by_canonical_key_pdf_txt():
    """CIR_SAC PDF and OCR TXT share canonical key."""
    records = [
        {
            "fichier": "docs/CIR_SAC_0042.pdf",
            "hash": "aaa",
            "ext": ".pdf",
            "taille": 100,
        },
        {
            "fichier": "docs/1994_CIR_SAC_0042.txt",
            "hash": "bbb",
            "ext": ".txt",
            "taille": 50,
        },
    ]
    groups = group_by_canonical_key(records)
    assert len(groups) == 1


@pytest.mark.adherence
@pytest.mark.integration
def test_ruff():
    import subprocess

    result = subprocess.run(["uv", "run", "ruff", "check", "."], capture_output=True)
    assert result.returncode == 0, result.stdout.decode()
