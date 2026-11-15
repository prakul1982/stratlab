"""Release 57, lane e57: theme membership rests on the company's own words more often than on its industry label (the owner's review of the
live R56 decks: Biotech 159 of 820 description-verified, Software 200 of 588, Capital goods 185 of 317, FMCG 128 of 208).

Why members had no stored description (the live R56 placement inputs of all 24 themes, replayed in the lane's report): nearly all were never
read. A theme's descriptions were read only in its full check, at most once a day, largest first, within one 40-second budget: about 19
Indian profile pages (the source's per-minute limit) and 6 US annual reports a check. Yet every Indian company's profile page is read
whenever its stock page is built, and its "About" was thrown away; and a US company's annual report was read only after the encyclopedia
left its words thin, at 6 a minute across every theme.

The fixes, one test per source path:
- India: the profile its page build reads is kept as its description (theme_routes.keep_profile, main.stock_page_facts): no new read;
- US: its own annual report (10-K Item 1 / 20-F Item 4) first, the encyclopedia only beside a thin or missing one; 30 reports a minute;
- a report still owed is read at the next check (never held three days as if looked for);
- a view of a checked theme starts one bounded background read of its next companies still without words (describe_more), at most
  hourly a theme, one at a time;
- a company counts as description-verified only when its own description was read (and shows the theme's work).
Each test fails before the change."""
import gzip
import json
import pathlib
import types
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app.intel import theme_base as TB, theme_check as C, theme_data as TD, theme_routes as TR
from app.intel.net import SourceError

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r56_e57.json.gz"
# a profile as the page shows it (synthetic, the usual form of the source's "About")
PROFILE = ("Incorporated in 1986, Acme Machines Ltd manufactures mining and road construction machinery, crushers and screening plants, "
           "and supplies spares and services to contractors and mining companies across India and abroad.")
REPORT = ("We are a clinical-stage biotechnology company developing gene therapies for rare neuromuscular diseases. Our lead program is in a "
          "Phase 3 trial, and we have two further programs in clinical development with partners in the United States and Europe.")
ARTICLE = "Acme Bio is an American biotechnology company based in Boston, Massachusetts. It was founded in 2015 by scientists from a university."


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


def _hub(monkeypatch, pages=None, wiki=None):
    asked = {"profile": [], "wiki": []}

    def company(sym):
        asked["profile"].append(sym)
        if sym not in (pages or {}):
            raise SourceError("Screener.in", "Screener.in has nothing for that.")
        return pages[sym]
    hub = types.SimpleNamespace(screener=types.SimpleNamespace(company=company),
                                wiki=types.SimpleNamespace(company=lambda name: asked["wiki"].append(name) or (wiki or {}).get(name)))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None))
    return asked


# ---------- US: the company's own annual report first ----------
def test_a_us_companys_annual_report_is_read_first_and_the_encyclopedia_is_not_needed(store, monkeypatch):
    asked = _hub(monkeypatch, wiki={"Acme Bio": {"title": "Acme Bio", "extract": ARTICLE}})
    reads = []
    monkeypatch.setattr(TR, "_business_read", lambda sym: reads.append(sym) or REPORT)
    got, pending = TR.evidence_reader("US", {"ACME": "Acme Bio, Inc."})(["ACME"])
    assert not pending and reads == ["ACME"] and asked["wiki"] == []          # before: the article first, the report never read (40 words)
    assert got["ACME"]["about"] == REPORT
    rec = json.loads(store["theme:evidence:US:ACME"])
    assert rec["about"] == REPORT and rec.get("filed") is True and "owed" not in rec
    assert TB.own_words(TB.own_line(rec["about"], "Acme Bio, Inc."), "Acme Bio, Inc.").startswith("We are a clinical-stage biotechnology company")


def test_a_us_company_with_no_annual_report_gets_the_encyclopedia(store, monkeypatch):
    asked = _hub(monkeypatch, wiki={"Acme Bio": {"title": "Acme Bio", "extract": ARTICLE + " " + REPORT.replace("We are", "Acme Bio is")}})

    def none(sym):
        raise SourceError("The SEC", "ACME isn't a company that files with the SEC.")
    monkeypatch.setattr(TR, "_business_read", none)
    got, _ = TR.evidence_reader("US", {"ACME": "Acme Bio, Inc."})(["ACME"])
    assert asked["wiki"] == ["Acme Bio"] and got["ACME"]["about"].startswith("Acme Bio is an American biotechnology company")
    assert "owed" not in json.loads(store["theme:evidence:US:ACME"])


def test_a_report_still_owed_is_read_at_the_next_check_not_three_days_on(store, monkeypatch):
    _hub(monkeypatch)
    monkeypatch.setattr(TR, "_business_read", lambda sym: REPORT)
    for _ in range(TR.FILING_READS_PER_MINUTE):                 # the minute's annual-report reads all taken
        TR.filing_reads.hit("about", TR.FILING_READS_PER_MINUTE)
    got, _ = TR.evidence_reader("US", {"ACME": "Acme Bio, Inc."})(["ACME"])
    rec = json.loads(store["theme:evidence:US:ACME"])
    assert rec["owed"] and not rec["about"] and "ACME" not in got
    assert TR._has_description("US", "ACME") is False           # before: "looked for lately", not asked again for 3 days
    monkeypatch.setattr(TR, "filing_reads", TR.Window())          # the next minute
    TR.EVIDENCE_CACHE.clear()
    assert TR.describe_unplaced("US", {"value_chain": [{"layer": "Other", "official": True, "companies": [{"ticker": "ACME", "cap": 5}]}]},
                                {"ACME": "Acme Bio, Inc."}, None) == ["ACME"]
    assert json.loads(store["theme:evidence:US:ACME"])["about"] == REPORT and TR._has_description("US", "ACME")


def test_the_background_read_waits_for_the_next_minutes_reports_within_its_deadline(monkeypatch):
    hits = iter([False, True, False])
    monkeypatch.setattr(TR, "filing_reads", types.SimpleNamespace(hit=lambda key, n: next(hits)))
    clock = {"t": 120.0, "m": 0.0, "slept": []}

    def sleep(x):
        clock["slept"].append(x)
        clock["t"] += x
        clock["m"] += x
    monkeypatch.setattr(TR, "time", types.SimpleNamespace(time=lambda: clock["t"], monotonic=lambda: clock["m"], sleep=sleep))
    assert TR.filed_business("US", "ACME", read=lambda s: REPORT, until=90.0) == (REPORT, False)      # waited for the next minute
    assert clock["slept"] == [60.5]
    assert TR.filed_business("US", "ACME", read=lambda s: REPORT, until=clock["m"] + 10) == ("", True)   # past the deadline: owed


def test_annual_reports_for_descriptions_are_thirty_a_minute():
    assert TR.FILING_READS_PER_MINUTE == 30                        # was 6 (DESCRIBE_READS)


# ---------- India: the profile page under the symbol alone (a name/ticker match failure) ----------
def test_a_reit_listed_with_its_series_is_looked_up_under_its_symbol_alone():
    pages = {"EMBASSY": {"about": "Embassy Office Parks REIT owns and operates commercial office parks in India.", "industry_path": ["Realty"]}}

    def company(sym):
        if sym not in pages:
            raise SourceError("Screener.in", "Screener.in has nothing for that.")
        return pages[sym]
    scr = types.SimpleNamespace(company=company)
    assert TR.india_profile(scr, "EMBASSY-RR", code_of=lambda s: None)["about"].startswith("Embassy Office Parks REIT")
    assert TR.india_profile(scr, "BAJAJ-AUTO", code_of=lambda s: None) is None          # (a hyphen inside a symbol is no series)


# ---------- India: the profile its page build read is kept ----------
def test_a_profile_read_by_the_page_build_is_kept_as_the_companys_description(store):
    assert TR.keep_profile("IN", "ACME", PROFILE, "Capital Goods > Industrial Machinery") is True
    rec = json.loads(store["theme:evidence:IN:ACME"])
    assert rec["about"] == PROFILE and rec["industry"] == "Capital Goods > Industrial Machinery" and rec["v"] == TR.ABOUT_V
    assert TR._has_description("IN", "ACME") and TR.kept_about("IN")("ACME") == PROFILE
    assert not TR.thin_about(rec, "IN")
    assert TR._facts_reader("IN")("ACME")["industry"] == "Capital Goods > Industrial Machinery"


def test_a_current_description_stands_a_thin_profile_is_not_kept_and_an_old_one_is_replaced(store):
    now = datetime.now(timezone.utc)
    current = {"at": now.isoformat(timespec="seconds"), "about": PROFILE + " It also exports to Africa.", "industry": "X", "v": TR.ABOUT_V}
    store["theme:evidence:IN:CUR"] = json.dumps(current)
    assert TR.keep_profile("IN", "CUR", PROFILE) is False and json.loads(store["theme:evidence:IN:CUR"]) == current
    assert TR.keep_profile("IN", "THIN", "Acme Ltd makes machines.") is False and "theme:evidence:IN:THIN" not in store
    old = {**current, "at": (now - timedelta(days=TR.EVIDENCE_DAYS + 1)).isoformat(timespec="seconds")}
    store["theme:evidence:IN:OLD"] = json.dumps(old)
    assert TR.keep_profile("IN", "OLD", PROFILE, "Y") is True and json.loads(store["theme:evidence:IN:OLD"])["about"] == PROFILE
    none = {"at": now.isoformat(timespec="seconds"), "about": "", "industry": "", "v": TR.ABOUT_V, "no_page": True}
    store["theme:evidence:IN:NONE"] = json.dumps(none)
    assert TR.keep_profile("IN", "NONE", PROFILE) is True                  # none found before; its page has one now


def test_the_stock_page_build_keeps_the_profile_it_read(w_world, monkeypatch):
    from app import db, main as M
    db.set_setting("theme:evidence:IN:RELIANCE", "")
    TR.EVIDENCE_CACHE.clear()
    f = M.stock_page_facts("IN", {"sym": "RELIANCE", "bse": None})
    assert f and f["symbol"] == "RELIANCE"
    rec = json.loads(db.get_setting("theme:evidence:IN:RELIANCE"))
    assert rec["about"].startswith("Reliance Industries Limited is a Fortune 500 company") and rec["src"] == "profile"
    assert TR._has_description("IN", "RELIANCE")
    TR.EVIDENCE_CACHE.clear()


@pytest.fixture
def w_world(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    yield world
    world["close"]()


# ---------- a background read of the theme's next companies, on a view ----------
def test_a_view_starts_one_bounded_background_read_at_most_hourly_a_theme(store, monkeypatch):
    started = []
    monkeypatch.setenv("THEME_DESCRIBE_MORE", "1")
    monkeypatch.setattr(TR, "later", lambda key, work, wait=None: started.append(key) or {})
    TR._described_at.clear()
    m = {"value_chain": [{"layer": "L", "companies": [{"ticker": "A", "cap": 1}]}]}
    t0 = 1.8e9
    assert TR.describe_more("IN", "Capital goods", m, now=t0) is True
    assert TR.describe_more("IN", "Capital goods", m, now=t0 + TR.DESCRIBE_EVERY - 1) is False         # within the hour
    assert TR.describe_more("IN", "FMCG", m, now=t0 + 1) is True                                      # another theme
    assert TR.describe_more("IN", "Capital goods", m, now=t0 + TR.DESCRIBE_EVERY) is True
    assert started == [("describe-more", "IN", "capital goods"), ("describe-more", "IN", "fmcg"), ("describe-more", "IN", "capital goods")]
    monkeypatch.setenv("THEME_DESCRIBE_MORE", "0")
    assert TR.describe_more("IN", "Defence", m, now=t0) is False
    TR._described_at.clear()


def test_the_background_read_asks_the_next_companies_without_words_largest_first_one_at_a_time(store, monkeypatch):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store["theme:evidence:IN:BIG"] = json.dumps({"at": now, "about": PROFILE, "v": TR.ABOUT_V})
    cos = [{"ticker": "BIG", "cap": 900}] + [{"ticker": f"C{i:03d}", "cap": 500 - i} for i in range(200)]
    m = {"value_chain": [{"layer": "L", "companies": cos[:100]}, {"layer": "Other", "official": True, "companies": cos[100:]}]}
    asked, budgets = [], []
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names, budget=None: budgets.append(budget) or (lambda syms: asked.append(list(syms)) or ({}, set())))
    want = TR.describe_missing("IN", m)
    assert "BIG" not in want and want == [f"C{i:03d}" for i in range(TR.describe_reads(200))]      # largest first, bounded
    assert asked == [want] and budgets == [TR.DESCRIBE_BUDGET]
    with TR._describe_gate:                                                                          # another one running: none
        assert TR.describe_missing("IN", m) == []


# ---------- counting: description-verified only when its own description was read ----------
def _states(t: dict, extra: dict | None = None) -> dict:
    """Each company's evidence state as the dive works it out (theme_data.build), from its stored description (kept_about: the lines of its
    filings are not its description) and `extra` descriptions kept since."""
    extra = extra or {}
    checked = TB.with_sub_only(TD.by_industry({"value_chain": t["value_chain"], "placements": t["placements"], "sector": t["theme"]}), t["theme"])
    placed = {}
    for g in checked["value_chain"]:
        for c in g.get("companies") or []:
            placed.setdefault(c["ticker"], c)
    words, named = TD.theme_words(checked, t["theme"]), TD.name_words(checked, t["theme"])

    def about(s):
        e = extra.get(s) or t["evidence"].get(s)
        return None if not e or e.startswith("From its own filings:") else e
    segs = lambda s: (t["facts"].get(s) or {}).get("segments") or None      # noqa: E731
    out = {}
    for s, c in placed.items():
        st = TD.membership(c, words, about(s), lambda s=s: segs(s), named=named)
        out[s] = TD.evidence_state(c, words, about(s), lambda s=s: segs(s), st)
    return out


def test_on_the_live_inputs_no_company_is_description_verified_without_its_description_read():
    live = json.load(gzip.open(LIVE, "rt", encoding="utf8"))
    for t in live["themes"].values():
        st = _states(t)
        own = {s for s, e in t["evidence"].items() if e and not e.startswith("From its own filings:")}
        assert not [s for s, x in st.items() if x == "description_verified" and s not in own]


def test_the_live_fmcg_and_capital_goods_companies_with_no_description_become_description_verified_once_their_profile_is_kept(store):
    """The live R56 inputs: FMCG 128 of 208 and Capital goods 186 of 317 description-verified, every other one kept on its industry label
    with no description stored. The recorded profile pages of 30 of them (15 a theme, across the size range), kept through keep_profile as
    the page build keeps them and read back as every theme reads its descriptions (kept_about): 26 of the 30 are description-verified; the
    other 4 stay on their label: one has no profile, one a two-sentence profile too thin to keep here (the theme's own reader adds the
    encyclopedia to it), and a tea estate and a maker of photographic lights, whose words show no FMCG work."""
    live = json.load(gzip.open(LIVE, "rt", encoding="utf8"))
    want = {"fmcg": (208, 128, 140), "capgoods": (317, 186, 200)}
    for k, t in live["themes"].items():
        before = _states(t)
        assert (len(before), Counter(before.values())["description_verified"]) == want[k][:2]
        sample = live["profiles"][k]
        assert all(before[s] == "industry_code_supported" and not t["evidence"].get(s) for s in sample)
        for s, p in sample.items():
            TR.keep_profile("IN", s, p["about"], p["industry"])
        read = TR.kept_about("IN")
        after = _states(t, {s: read(s) for s in sample if read(s)})
        assert Counter(after.values())["description_verified"] == want[k][2]
        assert sum(1 for s in sample if after[s] == "description_verified") == want[k][2] - want[k][1]
