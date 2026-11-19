"""Lane e77: theme engine items left open after Release 76.

1. Exxon (owner, 18 Nov: "Exxon Mobil Corporation"): the R76 US Oil and gas deck still printed "ExxonMobil Holdings Corp" 10 times: XOM's stored
   page predates the registrant record. The reporting registrant's name is found from the SEC's filings (a holding-company succession, 8-K12B),
   kept, and used by every place a name shows: theme rows (dive, deck), the public theme page, the stock page and the directory.
2. OSI Systems (LIVE13A-001 / LIVE14A-002): kept in "Fabless chip design" by "its official industry or way of earning": the way of earning an
   answer read off its official industry ("fabless", medium confidence), which its words (security and inspection systems) never say.
3. Counts: "584 companies: 588 from the official industry list, 2 added" (Software), "195 companies ... 199" (REITs): one company under two
   symbols counted once, said so.
4. Change-log churn: a company's same-day moves (Kanoria, Adamas Trust) shown as the day's net move with its reason.
"""
import json
import pathlib
import sys

import httpx
import pytest

from app import deck, public_themes, stock_pages
from app.intel import sec
from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_data as D
from tests import world
from tests.test_sec_live_samples import load

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import release_gate as G  # noqa: E402

R69 = pathlib.Path(__file__).resolve().parent / "fixtures" / "themes_live" / "r69"


@pytest.fixture
def wd(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._reporting.clear()
    stock_pages._dir.clear()
    yield built
    stock_pages._reporting.clear()
    built["close"]()


# ---------- 1. Exxon Mobil Corporation ----------
def _hit(name, sym, cik, form="8-K12B"):
    return {"_id": f"0000034088-26-000001:x.htm", "_source": {"file_type": form, "display_names": [f"{name}  ({sym})  (CIK {cik:010d})"],
                                                                "file_date": "2026-07-01"}}


def _transport(calls, extra_hits=()):
    new, old = load("xom_holdings"), load("exxon_mobil_corp")
    by_cik = {2115436: new, 34088: old}
    hits = [_hit("ExxonMobil Holdings Corp", "XOM", 2115436)] + list(extra_hits)

    def handler(r: httpx.Request):
        calls.append(r.url.path)
        if r.url.host == "efts.sec.gov":
            return httpx.Response(200, json={"hits": {"total": {"value": len(hits)}, "hits": hits}})
        if r.url.path == "/files/company_tickers.json":
            rows = {"0": {"cik_str": 2115436, "ticker": "XOM", "title": "ExxonMobil Holdings Corp"}}
            for i, h in enumerate(extra_hits, 1):
                m = sec._DISPLAY.match(h["_source"]["display_names"][0])
                rows[str(i)] = {"cik_str": int(m.group(3)), "ticker": m.group(2), "title": m.group(1)}
            return httpx.Response(200, json=rows)
        for cik, d in by_cik.items():
            if r.url.path == f"/submissions/CIK{cik:010d}.json":
                return httpx.Response(200, json=d["subs"])
            if r.url.path == f"/api/xbrl/companyfacts/CIK{cik:010d}.json":
                return httpx.Response(200, json=d["facts"])
        if r.url.path.startswith("/submissions/CIK"):
            cik = int(r.url.path.split("CIK")[1].split(".")[0])
            return httpx.Response(200, json={"cik": cik, "name": f"Co {cik}", "sic": "1311", "filings": {"recent": {"form": ["10-K"],
                                             "filingDate": ["2026-02-01"], "accessionNumber": [f"{cik:010d}-26-000001"], "primaryDocument": ["a.htm"]}}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_e77_the_succession_filings_name_exxon_as_its_reporting_registrant_bounded_and_cached():
    """Fails before: nothing read a listed company's reporting registrant apart from a full page build, so XOM's page stored before r69e
    kept "ExxonMobil Holdings Corp" in the theme, the deck and the directory until it was rebuilt."""
    calls = []
    s = sec.SEC(transport=_transport(calls))
    got = s.successor_names(listed={"XOM": "ExxonMobil Holdings Corp"})
    assert got == {"XOM": {"name": "Exxon Mobil Corporation", "listed": "ExxonMobil Holdings Corp"}}
    # cached: asked again, the reporting name is not read again (one filing search only)
    n = len(calls)
    assert s.successor_names(listed={"XOM": "ExxonMobil Holdings Corp"})["XOM"]["name"] == "Exxon Mobil Corporation"
    assert [c for c in calls[n:] if "companyfacts" in c or "submissions" in c] == []
    # a page build and this read share the answer: a fresh client whose company() found it asks nothing more
    calls2 = []
    s2 = sec.SEC(transport=_transport(calls2))
    assert s2.company("XOM")["name"] == "Exxon Mobil Corporation"
    m = len(calls2)
    assert s2.reporting_name("XOM") == "Exxon Mobil Corporation" and len(calls2) == m
    # a company skipped (checked lately) is not asked; one not on the list is left out
    assert s.successor_names(listed={"XOM": "x"}, skip={"XOM"}) == {}
    assert s.successor_names(listed={}) == {}


def test_e77_a_days_read_of_successions_is_bounded(monkeypatch):
    extra = [_hit(f"Holdco {i} Inc", f"HC{i}", 3000000 + i) for i in range(30)]
    calls = []
    s = sec.SEC(transport=_transport(calls, extra))
    monkeypatch.setattr(s, "SUCCESSION_MOST", 5)
    listed = {"XOM": "ExxonMobil Holdings Corp", **{f"HC{i}": f"Holdco {i} Inc" for i in range(30)}}
    got = s.successor_names(listed=listed)
    assert len(got) == 5                                   # at most SUCCESSION_MOST worked out in one call
    assert all(v["name"] == "" for k, v in got.items() if k != "XOM")      # no predecessor of the same name: no reporting name
    got2 = s.successor_names(listed=listed, skip=set(got))
    assert len(got2) == 5 and not set(got2) & set(got)


def test_e77_every_place_a_name_shows_takes_the_reporting_registrant(wd):
    """Fails before: with the reporting name known, a stored page without the registrant record still named XOM "ExxonMobil Holdings Corp"
    on its stock page, in the directory and in the theme's rows."""
    stock_pages.keep_reporting_names("US", {"XOM": {"name": "Exxon Mobil Corporation", "listed": "ExxonMobil Holdings Corp"},
                                            "AAPL": {"name": "", "listed": "Apple Inc."}})
    assert stock_pages.reporting_name("US", "XOM") == "Exxon Mobil Corporation"
    assert stock_pages.reporting_name("US", "AAPL") == "" and stock_pages.reporting_name("IN", "XOM") == ""
    assert {"XOM", "AAPL"} <= stock_pages.reporting_skip("US")
    old = {"v": stock_pages.FACTS_VERSION, "name": "ExxonMobil Holdings Corp", "region": "US", "symbol": "XOM"}
    f = stock_pages.with_reporting_name("US", "XOM", old)
    assert f["name"] == "Exxon Mobil Corporation" and f["registrant"] == "ExxonMobil Holdings Corp"
    # the theme's row name (dive, app rows, deck) from such a page
    assert D.member_name("US", "XOM", "ExxonMobil Holdings Corp", f["name"], f) == "Exxon Mobil Corporation"
    # the directory
    assert stock_pages.label_of("US", "XOM", {"name": "ExxonMobil Holdings Corp"}) == "Exxon Mobil Corporation"
    assert stock_pages.label_of("US", "AAPL", {"name": "APPLE INC"}) == "Apple Inc"
    # the stock page, stored before it kept the registrant: served and rendered under the reporting name
    stock_pages._put("stocks:page:US:XOM", {"ts": 9e12, "facts": old})
    pages = stock_pages.Pages(lambda region, co: None)
    assert pages.peek("US", "XOM")["name"] == "Exxon Mobil Corporation"
    assert pages.get("US", "XOM", {"name": "ExxonMobil Holdings Corp"})["name"] == "Exxon Mobil Corporation"
    html = stock_pages.render(pages.get("US", "XOM", {"name": "ExxonMobil Holdings Corp"}), "US", "XOM", "ExxonMobil Holdings Corp")
    assert "Exxon Mobil Corporation" in html and "ExxonMobil Holdings" not in html.split("<h1")[1].split("</h1>")[0]
    # a page that keeps its registrant, and any other company, unchanged
    kept = {"name": "Exxon Mobil Corporation", "registrant": "ExxonMobil Holdings Corp"}
    assert stock_pages.with_reporting_name("US", "XOM", kept) is kept
    assert stock_pages.with_reporting_name("US", "AAPL", {"name": "Apple Inc."}) == {"name": "Apple Inc."}


def test_e77_a_page_build_that_finds_the_registrant_keeps_the_name_for_the_directory(wd):
    built = {"v": stock_pages.FACTS_VERSION, "name": "Exxon Mobil Corporation", "registrant": "ExxonMobil Holdings Corp"}
    pages = stock_pages.Pages(lambda region, co: dict(built))
    pages.get("US", "XOM", {"name": "ExxonMobil Holdings Corp"})
    assert stock_pages.reporting_name("US", "XOM") == "Exxon Mobil Corporation"


def test_e77_the_public_theme_page_names_companies_as_the_dive_and_the_reporting_registrant(wd, monkeypatch):
    """Fails before: the public Semiconductors page listed "Osi Systems Inc" (the map's listed name) beside the deck's "OSI Systems Inc", and
    the Oil and gas page "ExxonMobil Holdings Corp"."""
    dive = {"layers": [{"companies": [{"symbol": "OSIS", "name": "OSI Systems Inc"}, {"symbol": "X", "name": ""}]}],
            "subs": [{"companies": [{"symbol": "OSIS", "name": "Other"}]}]}
    assert public_themes.dive_names(dive) == {"OSIS": "OSI Systems Inc"}
    stock_pages.keep_reporting_names("US", {"XOM": {"name": "Exxon Mobil Corporation", "listed": "ExxonMobil Holdings Corp"}})
    dive = {"layers": [{"companies": [{"symbol": "OSIS", "name": "OSI Systems Inc"}, {"symbol": "XOM", "name": "ExxonMobil Holdings Corp"}]}]}
    monkeypatch.setattr(public_themes, "_dive", lambda region, name, p: dive)
    p = {"sector": "Mixed", "value_chain": [{"layer": "Makers", "companies": [
        {"ticker": "OSIS", "name": "Osi Systems Inc", "verified": True, "what": "OSI makes inspection systems"},
        {"ticker": "XOM", "name": "ExxonMobil Holdings Corp", "verified": True, "what": "Exxon explores for oil"},
        {"ticker": "ZZZ", "name": "ZETA WORKS INC", "verified": True, "what": "Zeta makes widgets"}]}]}
    got = public_themes.view({"region": "US", "name": "Mixed", "label": "Mixed", "slug": "mixed"}, p)
    names = {c["symbol"]: c["name"] for v in got["layers"] for c in v["companies"]}
    assert names == {"OSIS": "OSI Systems Inc", "XOM": "Exxon Mobil Corporation", "ZZZ": "Zeta Works Inc"}, names


def test_e77_the_daily_list_job_reads_the_reporting_names(wd, monkeypatch):
    from app import main
    seen = {}
    monkeypatch.setattr(main.sec_feed, "successor_names", lambda skip=(): seen.setdefault("skip", set(skip)) and {} or
                        {"XOM": {"name": "Exxon Mobil Corporation", "listed": "ExxonMobil Holdings Corp"}})
    main.us_reporting_names()
    assert stock_pages.reporting_name("US", "XOM") == "Exxon Mobil Corporation"


# ---------- 2. OSI Systems out of "Fabless chip design" ----------
def _live_semis(d):
    """The live R76 input as the R67 re-check left it: OSI in "Fabless chip design", published there, its last move Other -> Fabless."""
    for v in d["value_chain"]:
        for c in list(v["companies"]):
            if c["ticker"] == "OSIS":
                v["companies"].remove(c)
                osi = c
    osi = {**osi, "sold_by": "its own words say it sells what “Fabless chip design” is"}
    next(v for v in d["value_chain"] if v["layer"] == "Fabless chip design")["companies"].append(osi)
    d["moved_before"]["OSIS"] = ["Other semiconductor companies", "Fabless chip design"]
    d["published"]["OSIS"] = d["previous"]["OSIS"] = "Fabless chip design"
    d["kept"]["assign"]["OSIS"] = {"layer": "Fabless chip design", "by": "ai"}


def _where(out, sym):
    for v in out["value_chain"]:
        for c in v["companies"]:
            if c["ticker"] == sym:
                return v["layer"], c
    return None, None


def test_e77_osi_leaves_fabless_chip_design_on_the_live_input():
    """Fails before: the replay of the live input as R76 stored it kept OSI Systems in "Fabless chip design" with "its official industry or
    way of earning says it sells what “Fabless chip design” is": the way of earning ("fabless", read off its official industry, medium
    confidence) took it in though its words name security and inspection systems, X-ray machines and medical monitoring."""
    d = G.load(R69 / "semis.json")
    _live_semis(d)
    fabless = {x["ticker"] for v in d["value_chain"] if v["layer"] == "Fabless chip design" for x in v["companies"]}
    with G.offline():
        out, _ = G.engine(d)
    lay, c = _where(out, "OSIS")
    assert lay != "Fabless chip design", (lay, c)
    why = (c.get("refit") or {}).get("why") or ""
    assert "Fabless chip design" in why and "own words don't say" in why, why
    # (guard) the layer's chip designers stay
    for s in ("NVDA", "AVGO", "QCOM", "AMD", "MRVL"):
        if s in fabless:
            assert _where(out, s)[0] == "Fabless chip design", s


def test_e77_a_way_of_earning_takes_a_company_into_a_layer_only_where_its_words_bear_it_out():
    named = [v for v in json.loads((R69 / "semis.json").read_text())["value_chain"] if not v.get("official")]
    fab = next(v for v in named if v["layer"] == "Fabless chip design")
    tw = B.kind_stems("Semiconductors")
    osi = B.sold_text("OSI Systems, Inc. develops and markets security and inspection systems such as airport security X-ray machines and "
                      "metal detectors, medical monitoring and anesthesia systems, and optoelectronic devices.", "Osi Systems Inc")
    assert B.sells_layer(fab, named, osi, "Semiconductors & Related Devices", tw, "fabless") is False
    assert not B.model_said(osi, "fabless", tw)
    # (guard) words that name the theme's product, or state the way of earning, or no words at all: the way of earning still says it
    chips = B.sold_text("Ambiq designs ultra-low-power chips for wearables.", "Ambiq Micro")
    assert B.model_said(chips, "fabless", tw) and B.sells_layer(fab, named, chips, None, tw, "fabless") is True
    assert B.model_said("We are a fabless company; our products are made by foundries.", "fabless", tw)
    assert B.model_said("", "fabless", tw) and B.sells_layer(fab, named, "", None, tw, "fabless") is True
    assert B.model_said("makes graphics processors", "fabless", tw)          # what a fabless company is of: its chips (theme_check.MODEL_OF)


# ---------- 3. counts that add up ----------
def test_e77_the_notes_companies_line_says_those_listed_twice():
    """Fails before: the REITs deck's notes said "195 companies in all, each in one layer: 199 from the exchange's official industries."."""
    assert deck.who_companies(195, 199, 0, 0, 4, 0) == ("195 companies in all, each in one layer: 199 from the exchange's official industries, "
                                                         "less 4 listed twice under another symbol, counted once.")
    assert deck.who_companies(584, 588, 0, 2, 6, 0) == ("584 companies in all, each in one layer: 588 from the exchange's official industries, "
                                                         "2 added by the AI from other industries, less 6 listed twice under another symbol, counted once.")
    # (guard) as before where nothing is listed twice; the rest by where it came from
    assert deck.who_companies(10, 8, 0, 1, 0, 1) == ("10 companies in all, each in one layer: 8 from the exchange's official industries, "
                                                      "1 added by the AI from other industries, 1 kept on their own words from other industries.")


# ---------- 4. change-log churn ----------
def _mv(sym, a, b, why=""):
    return {"symbol": sym, "name": sym.title(), "from": a, "to": b, **({"why": why} if why else {})}


def _e(d, moved, at="00", cause="rules", **extra):
    return {"at": f"{d}T{at}:00:00+00:00", "d": d, "cause": cause, "counts": {"removed": 0, "added": 0, "moved": len(moved), "layers": 0,
                                                                                 "restated": 0}, "removed": [], "added": [], "moved": moved,
            "layers": [], "restated": [], **extra}


def test_e77_same_day_moves_show_the_days_net_move_with_its_reason():
    """Fails before: the Cement log moved Kanoria 3 times on 17 Nov (to the layer, to Other, to the smaller layer) and REITs moved Adamas
    Trust Other -> Mortgage REITs -> Other -> Mortgage REITs on 18 Nov, each re-check an entry of its own."""
    L, S, O = "Cement integrated producers", "Cement integrated producers (smaller)", "Other cement companies"
    log = [_e("2026-11-16", [_mv("KEIL", L, O, "words a")]),
           _e("2026-11-17", [_mv("KEIL", O, L, "industry")], "01"),
           _e("2026-11-17", [_mv("KEIL", L, O, "words b"), _mv("ACC", L, S, "split")], "05"),
           _e("2026-11-17", [_mv("KEIL", O, S, "theme product")], "09"),
           _e("2026-11-18", [_mv("ADAMAS", "Other REITs", "Mortgage REITs", "m1")], "01"),
           _e("2026-11-18", [_mv("ADAMAS", "Mortgage REITs", "Other REITs", "m2")], "03"),
           _e("2026-11-18", [_mv("ADAMAS", "Other REITs", "Mortgage REITs", "m3")], "05"),
           _e("2026-11-19", [_mv("X", "A", "B", "x1")], "01"),
           _e("2026-11-19", [_mv("X", "B", "A", "x2")], "02")]
    out = C.net_by_day(log)
    moves = [(e["d"], r["symbol"], r["from"], r["to"], r.get("why"), r.get("times")) for e in out for r in e["moved"]]
    assert moves == [("2026-11-16", "KEIL", L, O, "words a", None),
                     ("2026-11-17", "ACC", L, S, "split", None),
                     ("2026-11-17", "KEIL", O, S, "theme product", 3),
                     ("2026-11-18", "ADAMAS", "Other REITs", "Mortgage REITs", "m3", 3)]
    # entries the collapse empties are not shown; counts follow the rows
    assert [e["counts"]["moved"] for e in out] == [len(e["moved"]) for e in out]
    assert all(e["moved"] for e in out)
    # (guard) an entry with other changes stays, its moves dropped only where they net out
    log2 = [_e("2026-11-20", [_mv("Y", "A", "B")], "01"), {**_e("2026-11-20", [_mv("Y", "B", "A")], "02"), "added": [{"symbol": "Z"}]}]
    log2[1]["counts"]["added"] = 1
    out2 = C.net_by_day(log2)
    assert len(out2) == 1 and out2[0]["added"] == [{"symbol": "Z"}] and out2[0]["moved"] == [] and out2[0]["counts"]["moved"] == 0


def test_e77_the_served_log_is_the_net_one(wd):
    from app import db
    log = [_e("2026-11-18", [_mv("ADAMAS", "Other REITs", "Mortgage REITs", "m1")], "01"),
           _e("2026-11-18", [_mv("ADAMAS", "Mortgage REITs", "Other REITs", "m2")], "03"),
           _e("2026-11-18", [_mv("ADAMAS", "Other REITs", "Mortgage REITs", "m3")], "05")]
    db.set_setting(C.key_of("US", "REITs"), json.dumps({"snap": {}, "log": log, "since": "2026-11-01"}))
    got = C.view("US", "REITs", True)
    assert len(got["entries"]) == 1 and got["entries"][0]["moved"][0]["why"] == "m3"
