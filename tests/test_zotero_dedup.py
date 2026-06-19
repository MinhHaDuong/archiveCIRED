"""Tests de la logique de fusion (pure, sans réseau)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import zotero_dedup as zd  # noqa: E402


def item(key, year, url, n_pdf=0, version=1, **fields):
    data = {"dateAdded": f"{year}-01-01T00:00:00Z", "url": url}
    data.update(fields)
    return {"key": key, "version": version, "data": data,
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


def test_richer_date():
    assert rz_richer("1983", "[1983 ?]") is True          # incertitude
    assert rz_richer("mai 12, 2004", "12 - 15 May 2004") is True  # plage
    assert rz_richer("janvier 2001", "January, 2001") is False    # juste format
    assert rz_richer("", "2001") is True                  # maître vide
    assert rz_richer("2001", "") is False                 # jumelle vide


def rz_richer(a, b):
    return zd.richer_date(a, b)


def test_merge_pages_from_2015():
    master = item("NEW", "2020", URL, pages="p.-307-319")
    twin = item("OLD", "2015", URL, n_pdf=1, pages="p. 307-319")
    patch = zd.merge_fields(master, [twin])
    assert patch["pages"] == "p. 307-319"


def test_merge_backfills_empty_only():
    master = item("NEW", "2020", URL, publisher="", publicationTitle="Revue X")
    twin = item("OLD", "2015", URL, publisher="Quae", publicationTitle="Autre")
    patch = zd.merge_fields(master, [twin])
    assert patch["publisher"] == "Quae"          # vide chez maître -> backfill
    assert "publicationTitle" not in patch        # déjà rempli -> on garde 2020


def test_merge_date_richer():
    master = item("NEW", "2020", URL, date="1983")
    twin = item("OLD", "2015", URL, date="[1983 ?]")
    assert zd.merge_fields(master, [twin])["date"] == "[1983 ?]"


def test_merge_keeps_divergent_creators():
    master = item("NEW", "2020", URL, creators=[{"lastName": "Dupont"}])
    twin = item("OLD", "2015", URL, creators=[{"lastName": "Durand"}])
    # maître non vide -> pas d'écrasement (creators divergents gardent 2020)
    assert "creators" not in zd.merge_fields(master, [twin])


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
