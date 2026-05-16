import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from build_file_index import build_file_index

KNOWN_SHA1_OF_HELLO = "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"


def test_build_file_index(tmp_path):
    """One record per file, recursive, correct fields and SHA1, no id field."""
    (tmp_path / "alpha.pdf").write_bytes(b"hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "beta.txt").write_bytes(b"world")

    records = build_file_index(tmp_path)

    assert len(records) == 2

    by_fichier = {r["fichier"]: r for r in records}

    assert "alpha.pdf" in by_fichier
    assert "sub/beta.txt" in by_fichier

    for rec in records:
        assert set(rec.keys()) == {"fichier", "taille", "hash", "ext"}, (
            f"Wrong fields: {set(rec.keys())}"
        )

    assert by_fichier["alpha.pdf"]["hash"] == KNOWN_SHA1_OF_HELLO, (
        "SHA1 of content b'hello' expected — wrong hash algorithm or hashing path instead of content"
    )

    assert by_fichier["alpha.pdf"]["taille"] == 5
    assert by_fichier["sub/beta.txt"]["taille"] == 5

    assert by_fichier["alpha.pdf"]["ext"] == ".pdf"
    assert by_fichier["sub/beta.txt"]["ext"] == ".txt"

    fichiers = [r["fichier"] for r in records]
    assert fichiers == sorted(fichiers)


@pytest.mark.adherence
@pytest.mark.integration
def test_ruff():
    result = subprocess.run(["uv", "run", "ruff", "check", "."], capture_output=True)
    assert result.returncode == 0, result.stdout.decode()
