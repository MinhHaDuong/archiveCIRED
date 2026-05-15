import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dedup import classify_attente, hash_corpus


def test_classify_exact_duplicate(tmp_path):
    corpus_dir = tmp_path / "docs"
    corpus_dir.mkdir()
    attente_dir = tmp_path / "attente"
    attente_dir.mkdir()

    content_a = b"PDF content A"
    content_b = b"PDF content B"

    (corpus_dir / "doc1.pdf").write_bytes(content_a)
    (attente_dir / "copy_of_doc1.pdf").write_bytes(content_a)
    (attente_dir / "new_doc.pdf").write_bytes(content_b)

    corpus_hashes = hash_corpus(corpus_dir)
    results = classify_attente(attente_dir, corpus_hashes)

    by_name = {Path(r["fichier"]).name: r for r in results}
    assert by_name["copy_of_doc1.pdf"]["statut"] == "exact_duplicate"
    assert by_name["copy_of_doc1.pdf"]["doublon_de"] is not None
    assert by_name["new_doc.pdf"]["statut"] == "inédit"
    assert by_name["new_doc.pdf"]["doublon_de"] is None


@pytest.mark.adherence
@pytest.mark.integration
def test_ruff():

    result = subprocess.run(["uv", "run", "ruff", "check", "."], capture_output=True)
    assert result.returncode == 0, result.stdout.decode()
