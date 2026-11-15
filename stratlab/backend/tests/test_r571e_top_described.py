"""Release 57.1, lane r571e: a theme's largest companies are never left out as "no description found" on a first build (ten new themes built
on R57: McDonald's "no description found in any source", GE Aerospace and RTX left out as insufficient evidence). Before a theme's evidence
check, its largest companies with no description kept are read synchronously, largest first, within a time budget; and an encyclopedia
article whose title has an apostrophe the index's name lacks ("McDonald's" for "McDonalds") is the company's own. Each test fails before."""
import json
import types
from datetime import datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app.intel import theme_routes as TR
from app.intel.news import fits_company
from app.intel.net import SourceError

REPORT = ("We are a company that designs and builds commercial aircraft engines and systems and provides aftermarket services to airlines "
          "and air forces around the world.")


@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    monkeypatch.setattr(TR, "filing_reads", TR.Window())
    TR.EVIDENCE_CACHE.clear()
    yield kept
    TR.EVIDENCE_CACHE.clear()


def _sources(monkeypatch, reads):
    hub = types.SimpleNamespace(screener=None, wiki=types.SimpleNamespace(company=lambda n: None))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None))
    monkeypatch.setattr(TR, "_business_read", lambda s: reads.append(s) or REPORT)


ROWS = [{"symbol": f"C{i:02d}", "name": f"Company {i}", "industry": "Aircraft Engines", "market_cap": 1000 - i} for i in range(40)] + \
       [{"symbol": "OTHER", "name": "Other Co", "industry": "Banks", "market_cap": 5000}]


def test_the_largest_companies_are_read_before_the_check_largest_first_and_bounded(store, monkeypatch):
    reads = []
    _sources(monkeypatch, reads)
    m = {"value_chain": [{"layer": "Engines", "companies": [{"ticker": "C35", "name": "Company 35"}]}]}
    store["theme:evidence:US:C00"] = json.dumps({"at": datetime.now(timezone.utc).isoformat(), "about": REPORT, "v": TR.ABOUT_V})
    got = TR.describe_top("US", m, ROWS, ["Aircraft Engines"])
    assert got == [f"C{i:02d}" for i in range(1, TR.TOP_DESCRIBE)]                # the 30 largest of the theme, C00 already described
    assert "OTHER" not in got and "C35" not in got                                 # not of the theme; outside the top 30
    assert sorted(reads) == sorted(got) and json.loads(store["theme:evidence:US:C01"])["about"] == REPORT
    assert TR.describe_top("US", m, ROWS, ["Aircraft Engines"]) == []             # all kept now: nothing read again


def test_a_largest_company_kept_as_none_found_is_read_again_after_a_while(store, monkeypatch):
    reads = []
    _sources(monkeypatch, reads)
    old = (datetime.now(timezone.utc) - timedelta(hours=TR.TOP_AGAIN_HOURS + 1)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    store["theme:evidence:US:C00"] = json.dumps({"at": old, "about": "", "v": TR.ABOUT_V})       # "no description found" a day ago
    store["theme:evidence:US:C01"] = json.dumps({"at": new, "about": "", "v": TR.ABOUT_V})       # looked for just now
    got = TR.describe_top("US", {"value_chain": []}, ROWS[:2], ["Aircraft Engines"])
    assert got == ["C00"] and reads == ["C00"] and json.loads(store["theme:evidence:US:C00"])["about"] == REPORT


def test_the_check_reads_the_largest_companies_before_the_evidence_check(monkeypatch):
    order = []
    monkeypatch.setattr(TR, "describe_top", lambda region, m, rows, inds: order.append("describe_top"))

    def stop(*a, **kw):
        order.append("check_placements")
        raise RuntimeError("stop here")
    monkeypatch.setattr(TR.theme_check, "check_placements", stop)
    monkeypatch.setattr(TR.A, "get", lambda *a: None)
    monkeypatch.setattr(TR, "_rows", lambda r: [])
    monkeypatch.setattr(TR, "_industries", lambda r, t, m=None: {"industries": [], "how": "stored"})
    monkeypatch.setattr(TR, "published_layers", lambda *a: {})
    monkeypatch.setattr(TR, "kept_placement", lambda *a: ({}, None))
    with pytest.raises(RuntimeError):
        TR._check("IN", "Aerospace", {"generated_at": 1, "value_chain": []})
    assert order == ["describe_top", "check_placements"]


def test_an_article_whose_title_has_an_apostrophe_the_name_lacks_is_the_companys_own():
    art = {"title": "McDonald's", "extract": "McDonald's Corporation is an American multinational fast food chain."}
    assert fits_company("McDonalds", art) and fits_company("McDonald's Corp", art)
    assert not fits_company("Ichor Holdings", {"title": "Ichor", "extract": "In Greek mythology, ichor is the blood of the gods."})
    assert not fits_company("TOYO Co", {"title": "Toyo Tires", "extract": "Toyo Tire Corporation is a tyre company."})


def test_a_busy_source_leaves_the_rest_for_a_later_check(store, monkeypatch):
    hub = types.SimpleNamespace(screener=types.SimpleNamespace(company=lambda s: (_ for _ in ()).throw(SourceError("Screener.in", "busy", busy=True))),
                                wiki=types.SimpleNamespace(company=lambda n: None))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None))
    rows = [{"symbol": "A", "name": "A Ltd", "industry": "Hotels", "market_cap": 9}]
    assert TR.describe_top("IN", {"value_chain": []}, rows, ["Hotels"]) == ["A"]
    assert "theme:evidence:IN:A" not in store                                       # nothing kept: read at the next check
