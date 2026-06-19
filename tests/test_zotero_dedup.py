"""Tests de la logique de fusion (pure, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import zotero_dedup as zd  # noqa: E402


def item(key, year, url, n_pdf=0, version=1):
    return {"key": key, "version": version,
            "data": {"dateAdded": f"{year}-01-01T00:00:00Z", "url": url},
            "meta": {"numChildren": n_pdf}}


URL = "https://inari/docs/CIR_SAC_0317.pdf"


def test_choose_master_prefers_recent():
    older = item("OLD", "2015", URL, n_pdf=1)
    newer = item("NEW", "2020", URL, n_pdf=0)
    assert zd.choose_master([older, newer])["key"] == "NEW"


def test_plan_reparents_pdf_to_master():
    # maître 2020 sans PDF, jumelle 2015 avec PDF
    plan = zd.plan_for_key("CIR_SAC_0317", [
        item("NEW", "2020", URL, n_pdf=0, version=4752),
        item("OLD", "2015", URL, n_pdf=1, version=4821),
    ])
    assert plan["master"] == "NEW"
    assert plan["master_has_pdf"] is False
    assert plan["reparent_pdf_from"] == "OLD"
    assert [d["key"] for d in plan["delete"]] == ["OLD"]


def test_plan_no_reparent_when_master_has_pdf():
    plan = zd.plan_for_key("CIR_SAC_0001", [
        item("NEW", "2020", URL, n_pdf=1),
        item("OLD", "2015", URL, n_pdf=1),
    ])
    assert plan["reparent_pdf_from"] is None
    assert [d["key"] for d in plan["delete"]] == ["OLD"]


def test_plan_quadruple():
    items = [
        item("N1", "2020", URL, n_pdf=0), item("N2", "2020", URL, n_pdf=0),
        item("O1", "2015", URL, n_pdf=1), item("O2", "2015", URL, n_pdf=1),
    ]
    plan = zd.plan_for_key("CIR_SAC_0097", items)
    assert plan["master_year"] == "2020"
    assert len(plan["delete"]) == 3
    assert plan["reparent_pdf_from"] in ("O1", "O2")


def test_build_plan_counts_only_duplicates():
    items = [
        item("A1", "2020", "https://x/docs/CIR_SAC_0001.pdf", n_pdf=0),
        item("A2", "2015", "https://x/docs/CIR_SAC_0001.pdf", n_pdf=1),
        item("B1", "2020", "https://x/docs/CIR_SAC_0002.pdf", n_pdf=1),  # unique
        item("C1", "2020", "https://x/no-key.pdf", n_pdf=0),            # sans clé
    ]
    plan = zd.build_plan(items)
    assert plan["cles_dupliquees"] == 1
    assert plan["maitres"] == 1
    assert plan["suppressions"] == 1
    assert plan["reparentages_pdf"] == 1
