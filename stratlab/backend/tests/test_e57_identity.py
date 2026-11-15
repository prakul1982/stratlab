"""Release 57, lane e57: who a theme's companies are, and which companies a theme considers (the audit of the 24 live R56 decks, RC6, RC7).

RC7: the live R56 Telecom deck held HFCL and Sterlite twice (the map's "HFCL-BE"/"STLTECH-BE" lines beside the index's HFCL/STLTECH);
Biotech, Retail and Software each held a company under two index lines (an old and a new ticker, an over-the-counter line, a bankruptcy
"Q" line); the four Indian REITs listed as "... - REIT"/"-RR" had no description. RC6: Consumer retail lacked Best Buy, AutoZone, Tractor
Supply, Gap and Dick's: a map pick from an industry the theme does not hold never brought that industry's other listed companies.
Each test fails before the change. The rows below are the live R56 inputs' own (names, tickers, industries, market values)."""
import json
import types

import pytest

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app.intel import theme_base as TB, theme_identity as I, theme_routes as TR


# ---------- RC7 (a): one member per company ----------
def test_a_map_line_with_the_exchanges_series_is_the_index_company_never_a_second_member():
    rows = [{"symbol": "HFCL", "name": "HFCL Ltd", "industry": "Telecom - Equipment & Accessories", "market_cap": 31521.1},
            {"symbol": "STLTECH", "name": "Sterlite Technologies Ltd", "industry": "Telecom - Equipment & Accessories", "market_cap": 36535.1}]
    m = {"value_chain": [{"layer": "Fibre, cable and passive gear makers", "companies": [
        {"ticker": "STLTECH-BE", "name": "Sterlite Technologies Limited", "verified": True, "what": "We make optical fibre and cables."},
        {"ticker": "HFCL-BE", "name": "HFCL Limited", "verified": False},
        {"ticker": "HFCL", "name": "HFCL Ltd", "verified": False},
        {"ticker": "STLTECH", "name": "Sterlite Technologies Ltd", "verified": False}]}]}
    got = I.resolve_identity(m, rows)["value_chain"][0]["companies"]
    assert [c["ticker"] for c in got] == ["STLTECH", "HFCL"]
    assert got[0]["verified"] is True and got[0]["listed_as"] == "STLTECH-BE" and got[0]["what"].startswith("We make optical fibre")


def test_a_name_with_another_legal_form_is_the_one_listed_company_of_that_name_and_an_ambiguous_one_is_left():
    rows = [{"symbol": "ACME", "name": "Acme & Sons Limited"}, {"symbol": "TWIN1", "name": "Twin Co Ltd"}, {"symbol": "TWIN2", "name": "Twin Company"}]
    assert I.norm_name("Acme and Sons Ltd.") == I.norm_name("ACME & SONS LIMITED") == "acme and sons"
    m = {"value_chain": [{"layer": "L", "companies": [{"ticker": "ACMESONS", "name": "Acme and Sons Ltd."}, {"ticker": "TWIN", "name": "Twin Corp"}]}]}
    got = I.resolve_identity(m, rows)["value_chain"][0]["companies"]
    assert [c["ticker"] for c in got] == ["ACME", "TWIN"]


def test_a_company_the_index_lists_under_two_lines_is_one_member_the_larger_one():
    out = {"placements": {"placed": 6, "total": 6}, "value_chain": [
        {"layer": "Services-Prepackaged Software", "official": True, "basis": "industry", "companies": [
            {"ticker": "PERF", "name": "Perfect Corp.", "industry": "Services-Prepackaged Software", "cap": 202.7},
            {"ticker": "PERFF", "name": "Perfect Corp.", "industry": "Services-Prepackaged Software", "cap": None},
            {"ticker": "HKIT", "name": "Biddance AI Systems, Inc.", "industry": "Services-Prepackaged Software", "cap": 36.42},
            {"ticker": "BDAI", "name": "Biddance AI Systems, Inc.", "industry": "Services-Prepackaged Software", "cap": 27.36}]},
        {"layer": "Retail-Retail Stores, Nec", "official": True, "basis": "industry", "companies": [
            {"ticker": "LESL", "name": "Leslie's, Inc.", "industry": "Retail-Retail Stores, Nec", "cap": 1.0},
            {"ticker": "LESLQ", "name": "Leslie's, Inc.", "industry": "Retail-Retail Stores, Nec", "cap": 0.49}]}]}
    got = I.one_listing(out)
    assert [c["ticker"] for v in got["value_chain"] for c in v["companies"]] == ["PERF", "HKIT", "LESL"]
    assert got["placements"]["same_company"] == [{"ticker": "BDAI", "name": "Biddance AI Systems, Inc.", "kept": "HKIT"},
                                                 {"ticker": "LESLQ", "name": "Leslie's, Inc.", "kept": "LESL"},
                                                 {"ticker": "PERFF", "name": "Perfect Corp.", "kept": "PERF"}]
    assert got["placements"]["total"] == 3
    # two companies of one name in different industries are two companies
    two = {"value_chain": [{"layer": "L", "companies": [{"ticker": "A", "name": "Delta Corp", "industry": "Airlines", "cap": 5},
                                                        {"ticker": "B", "name": "Delta Ltd", "industry": "Casinos", "cap": 3}]}]}
    assert I.one_listing(two) == two


# ---------- RC7 (c): unit trusts ----------
def test_a_reit_or_invit_listing_line_is_looked_up_under_the_trusts_name():
    assert TB.issuer_name("Brookfield India Real Estate Trust - REIT") == "Brookfield India Real Estate Trust"
    assert TB.issuer_name("Nexus Select Trust - REIT") == "Nexus Select Trust"
    assert TB.issuer_name("Property Share Investment Trust- Propshare Titania") == "Property Share Investment Trust"
    assert TB.issuer_name("Embassy Office Parks REIT") == "Embassy Office Parks"
    assert TB.issuer_name("Altius Telecom Infrastructure Trust") == "Altius Telecom Infrastructure Trust"     # nothing after the name
    assert TR.plain_name("Nexus Select Trust - REIT") == "Nexus Select Trust"
    assert TB.issuer_name("Adyen Nv-Unspon ADR") == "Adyen"                                                  # (as before)


# ---------- RC7 (b): members above the median with no description or figures ----------
def test_members_above_the_median_with_no_description_or_figures_are_data_gaps_and_an_admin_check_never_mailed(monkeypatch):
    members = [{"ticker": t, "name": n, "cap": c} for t, n, c in
               (("BIG", "Big Co", 900), ("NOWORDS", "No Words Ltd", 500), ("NOFIG", "No Figures Ltd", 450), ("MID", "Mid Co", 300), ("SMALL", "Small Co", 10), ("TINY", "Tiny", 5))]
    gaps = I.data_gaps(members, lambda s: s != "NOWORDS" and s != "TINY", lambda s: s != "NOFIG" and s != "TINY")
    assert gaps == [{"ticker": "NOWORDS", "name": "No Words Ltd", "cap": 500, "lacks": ["description"]},
                    {"ticker": "NOFIG", "name": "No Figures Ltd", "cap": 450, "lacks": ["figures"]}]
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "update_setting", lambda k, fn: kept.__setitem__(k, fn(kept.get(k))) if fn(kept.get(k)) is not None else None)
    TR.flag_gaps("IN", "Telecom", gaps)
    checks = TR.data_gap_checks()
    assert len(checks) == 1 and checks[0].mail is False
    assert checks[0].problem == ("2 members above the theme's median market value lack data: No Words Ltd (description), "
                                 "No Figures Ltd (figures).")
    TR.flag_gaps("IN", "Telecom", [])
    assert TR.data_gap_checks()[0].problem is None                         # cleared once it has none
    from app import autofix
    assert TR.data_gap_checks in autofix._sources


# ---------- RC6: a checked pick's industry peers are considered ----------
ROWS = [{"symbol": "AMZN", "name": "Amazon.com, Inc.", "industry": "Retail-Catalog & Mail-Order Houses", "market_cap": 2400000},
        {"symbol": "EBAY", "name": "eBay Inc.", "industry": "Retail-Catalog & Mail-Order Houses", "market_cap": 45000},
        {"symbol": "QVCA", "name": "QVC Group", "industry": "Retail-Catalog & Mail-Order Houses", "market_cap": 300},
        {"symbol": "CVNA", "name": "Carvana Co.", "industry": "Retail-Catalog & Mail-Order Houses", "market_cap": 60000},
        {"symbol": "CHWY", "name": "Chewy, Inc.", "industry": "Retail-Catalog & Mail-Order Houses", "market_cap": 15000},
        {"symbol": "WMT", "name": "Walmart Inc.", "industry": "Retail-Variety Stores", "market_cap": 800000},
        {"symbol": "TGT", "name": "Target Corp", "industry": "Retail-Variety Stores", "market_cap": 9000}]
ABOUT = {"EBAY": "eBay Inc. operates online marketplaces where buyers and sellers trade goods, earning fees on each sale.",
         "CVNA": "Carvana Co. is an e-commerce platform for buying and selling used cars, sold online and delivered to customers.",
         "CHWY": "Chewy, Inc. holds patents and licenses its intellectual property to animal health researchers."}


def _retail():
    return {"sector": "Consumer retail", "placements": {"industries": ["Retail-Variety Stores"], "placed": 3, "total": 3},
            "value_chain": [
                {"layer": "Online retailers", "description": "online stores and marketplaces selling goods to consumers", "companies": [
                    {"ticker": "AMZN", "name": "Amazon.com, Inc.", "verified": True, "base": False, "basis": "added", "cap": 2400000,
                     "what": "Amazon sells goods to consumers through its online stores."}]},
                {"layer": "Big-box stores", "description": "stores selling general merchandise", "companies": [
                    {"ticker": "WMT", "name": "Walmart Inc.", "verified": False, "base": True, "basis": "industry", "cap": 800000},
                    {"ticker": "TGT", "name": "Target Corp", "verified": False, "base": True, "basis": "industry", "cap": 9000}]},
                {"layer": "Variety stores", "official": True, "basis": "industry", "companies": [
                    {"ticker": f"V{i}", "name": f"Variety {i} Inc.", "verified": False, "base": True, "basis": "industry", "cap": c}
                    for i, c in enumerate((100, 200, 400, 500))]}]}


def test_a_checked_picks_industry_brings_its_listed_companies_above_the_median_as_candidates():
    out = I.with_peers(_retail(), ROWS, lambda s: ABOUT.get(s), "Consumer retail")
    peers = {x["ticker"]: x for x in out["placements"]["peer_candidates"]}
    assert set(peers) == {"CVNA", "EBAY", "CHWY"}                          # QVC (300) is under the theme's median market value (500)
    assert peers["EBAY"]["joined"] and peers["CVNA"]["joined"] and peers["EBAY"]["peer_of"] == "AMZN"
    assert not peers["CHWY"]["joined"] and peers["CHWY"]["why"] == "its own description describes other work"
    online = out["value_chain"][0]["companies"]                            # they join the pick's layer, on its words
    assert [c["ticker"] for c in online] == ["AMZN", "CVNA", "EBAY"]
    assert all(c["verified"] and not c["base"] and c["basis"] == "peer" and c["peer_of"] == "AMZN" for c in online[1:])
    assert len(out["value_chain"]) == 3                                     # no new layer
    assert out["placements"]["total"] == 5 and out["placements"]["confirmed"] == 2


def test_a_candidate_with_no_description_is_said_and_read_in_the_background(monkeypatch):
    out = I.with_peers(_retail(), ROWS, lambda s: None, "Consumer retail")
    assert {x["why"] for x in out["placements"]["peer_candidates"]} == {"no description of its own is read yet"}
    assert [c["ticker"] for c in out["value_chain"][0]["companies"]] == ["AMZN"]
    assert I.peers_unread(out) == ["CVNA", "EBAY", "CHWY"]
    asked = []
    monkeypatch.setattr(TR, "_has_description", lambda region, s: False)
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names, budget=None: (lambda syms: asked.append((list(syms), dict(names))) or ({}, set())))
    TR.describe_missing("US", out)
    syms, names = asked[0]
    assert syms[-3:] == ["CVNA", "EBAY", "CHWY"] and names["CVNA"] == "Carvana Co."


def test_no_pick_from_an_industry_outside_the_theme_or_an_unchecked_one_brings_no_candidates():
    m = _retail()
    m["value_chain"][0]["companies"][0]["verified"] = False
    assert "peer_candidates" not in I.with_peers(m, ROWS, lambda s: ABOUT.get(s), "Consumer retail")["placements"]


# ---------- RC6 (b): the audit's "must be considered" check on placement inputs ----------
def test_the_must_consider_check_finds_members_candidates_and_misses(tmp_path):
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("must_consider", pathlib.Path(__file__).parent.parent / "scripts" / "must_consider.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    out = I.with_peers(_retail(), ROWS, lambda s: ABOUT.get(s), "Consumer retail")
    (tmp_path / "retail.json").write_text(json.dumps(out))
    lines, missing = mc.run(tmp_path, {"retail": ["Carvana", "Chewy", "Walmart", "Best Buy"], "cement": ["UltraTech"]})
    got = {ln.split()[1]: ln for ln in lines if ln.startswith("retail")}
    assert "member (Online retailers)" in got["Carvana"] and "candidate: its own description describes other work" in got["Chewy"]
    assert "member (Big-box stores)" in got["Walmart"] and got["Best"].endswith("MISSING") and missing == 1
    assert "cement: no inputs file" in lines
    names = json.loads(mc.DEFAULT.read_text())
    assert names["retail"][:2] == ["Best Buy", "AutoZone"] and len([k for k in names if k != "note"]) == 10
