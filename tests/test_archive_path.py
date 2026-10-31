import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import archive_path


def test_env_set(monkeypatch, tmp_path):
    monkeypatch.setenv("DATASETS_DIR", str(tmp_path))
    got = archive_path.archive_dir(conf_path=tmp_path / "absent.conf")
    assert got == tmp_path / "ours" / "Archives CIRED numerisées"


def test_env_unset_conf_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("DATASETS_DIR", raising=False)
    conf = tmp_path / "50-datasets.conf"
    conf.write_text("# comment\nOTHER=x\nDATASETS_DIR=/srv/ds\n")
    got = archive_path.archive_dir(conf_path=conf)
    assert got == Path("/srv/ds/ours/Archives CIRED numerisées")


def test_env_wins_over_conf(monkeypatch, tmp_path):
    monkeypatch.setenv("DATASETS_DIR", "/from/env")
    conf = tmp_path / "c.conf"
    conf.write_text("DATASETS_DIR=/from/conf\n")
    assert archive_path.archive_dir(conf_path=conf).parts[:3] == ("/", "from", "env")


def test_both_absent_exits_with_message(monkeypatch, tmp_path):
    monkeypatch.delenv("DATASETS_DIR", raising=False)
    with pytest.raises(SystemExit) as exc:
        archive_path.archive_dir(conf_path=tmp_path / "absent.conf")
    assert "DATASETS_DIR" in str(exc.value)
    assert "absent.conf" in str(exc.value)


def test_conf_without_key_exits(monkeypatch, tmp_path):
    monkeypatch.delenv("DATASETS_DIR", raising=False)
    conf = tmp_path / "c.conf"
    conf.write_text("# DATASETS_DIR=/commented\nMIRRORS_DIR=/m\n")
    with pytest.raises(SystemExit):
        archive_path.archive_dir(conf_path=conf)
