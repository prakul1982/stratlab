"""Review DC (Trade market-data pages): F&O changes read from the exchange's own circular files (renames as renames,
entries and exits by name with their dates, lot revisions was -> now, equity F&O circulars only, real circular dates),
the Muhurat session, index notices of every layout and the warning when a source fails, the Fed's range written with a
non-breaking hyphen, the option chain re-read from the exchange's end-of-day file and its lots from the contract file.
The circulars, the contract file and the bhavcopy are the exchange's own (fixtures/fo_changes, fixtures/positioning);
every figure a test checks is read from those files, never typed in. Every clock is fixed."""
import csv
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import main  # noqa: F401  (first: the app loads the newsletter job before the modules built on it)
from app import db, fo_changes as F, market_events as M, positioning as P
from tests import world as W

FX = Path(__file__).parent / "fixtures"
FO = FX / "fo_changes"
TODAY = date(2026, 10, 24)
RULE = lambda sym, month: F.rule_expiry(month)  # noqa: E731


def text(name: str) -> str:
    return (FO / name).read_text()


def lots() -> dict:
    return F.read_lots(text("fo_mktlots_live_2026-10-23.csv"))


def known() -> set[str]:
    return set(lots()["rows"]) | F.INDEX_NAMES


def circs() -> dict[str, dict]:
    return {c["no"]: c for c in F.read_circulars(json.loads(text("circulars_live_2026-10-23.json")), known())}


def annexure() -> dict:
    return F._xlsx_sheets((FO / "annexure_FAOP76657.xlsx").read_bytes())


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    F._cache.clear()
    M._cache.clear()
    P.clear_cache()


# ---------- DC-021: equity F&O circulars only, with their own dates ----------
def test_only_the_equity_fo_desks_circulars_are_kept_each_with_its_date():
    got = circs()
    assert got and all(no.startswith("NSE/FAOP/") for no in got)          # commodity, SME lots, clearing: gone
    raw = json.loads(text("circulars_live_2026-10-23.json"))["data"]
    for r in raw:
        if r["circDisplayNo"] in got:
            assert got[r["circDisplayNo"]]["date"] == F.iso_day(r["cirDisplayDate"])
    assert not any("Mock trading" in c["subject"] for c in got.values())
    assert F.equity_fo("NSE/FAOP/77091") and not F.equity_fo("NCL/CMPT/76433") and not F.equity_fo("NSE/CMTR/76578") and F.equity_fo("")


def test_the_page_drops_kept_circulars_of_other_desks_and_keeps_one_line_a_circular():
    events = [{"id": "circ:a", "source": "circular", "kind": "entry", "no": "NCL/CMPT/76433", "subject": "Introduction of API Facility in NMASS-Margins-FO", "seen": "2026-10-05"},
              {"id": "circ:b", "source": "circular", "kind": "lot", "no": "NSE/CMTR/76578", "subject": "BONUS: Adjustment of Market Lot", "seen": "2026-10-05"},
              {"id": "circ:c", "source": "circular", "kind": "lot", "no": "NSE/FAOP/76657", "subject": "Revision in Market Lot", "seen": "2026-10-05"},
              {"id": "circ:d", "source": "circular", "kind": "lot", "no": "NSE/FAOP/76657", "subject": "Revision in Market Lot", "date": "2026-09-30", "seen": "2026-10-24"}]
    got = F.tidy(events, {})
    assert [e["id"] for e in got] == ["circ:d"]


# ---------- DC-017: a rename is a rename ----------
def test_a_rename_circular_gives_the_old_and_the_new_symbol():
    c = circs()["NSE/FAOP/77013"]
    assert c["kind"] == "rename"
    got = F.circular_changes(c, text("circular_FAOP77013.txt"), {}, known(), RULE)
    assert len(got) == 1 and got[0]["kind"] == "rename"
    assert got[0]["symbol"] in lots()["rows"] and got[0]["was_symbol"] not in lots()["rows"]       # the file lists the new one only
    assert got[0]["effective"] == "2026-10-23"
    assert "not a stock leaving or entering" in F.text_of(got[0])


def test_the_files_exit_and_entry_for_a_renamed_stock_are_dropped_and_its_changes_move_to_the_new_symbol():
    new, old = "ICICILIFE", "ICICIPRULI"
    rename = {"id": f"rename:{old}>{new}", "kind": "rename", "symbol": new, "was_symbol": old, "effective": "2026-10-23", "circ": "circ:r"}
    events = [rename,
              {"id": f"exit:{old}:2026-12", "kind": "exit", "symbol": old, "series": "2026-12", "expiry": "2026-12-29"},
              {"id": f"entry:{new}:2026-10", "kind": "entry", "symbol": new, "series": "2026-10", "effective": "2026-10-23", "lot": 925},
              {"id": f"lot:{old}:2027-01:925>1100", "kind": "lot", "symbol": old, "series": "2027-01", "was": 925, "now": 1100,
               "effective": "2026-10-28", "circ": "circ:l"}]
    got = {e["id"]: e for e in F.tidy(events, lots()["rows"])}
    assert set(got) == {rename["id"], f"lot:{old}:2027-01:925>1100"}
    assert got[f"lot:{old}:2027-01:925>1100"]["symbol"] == new and got[f"lot:{old}:2027-01:925>1100"]["was_symbol"] == old


def test_an_entry_is_never_sourced_to_a_circular_whose_file_names_other_stocks():
    intro = {**circs()["NSE/FAOP/76899"]}
    F.circular_changes(intro, text("circular_FAOP76899.txt"), {}, known(), RULE)
    e = {"id": "entry:ICICILIFE:2026-10", "kind": "entry", "symbol": "ICICILIFE", "effective": "2026-10-23"}
    assert [c["no"] for c in F.sources_for(e, [{**intro, "symbols": [], "read": True}])] == []            # read, named nobody
    named = {**intro, "symbols": [s for s, _, _ in F._table_symbols(text("circular_FAOP76899.txt"))], "read": True}
    assert "ICICILIFE" not in named["symbols"] and F.sources_for(e, [named]) == []


# ---------- DC-018: the stocks entering, by name ----------
def test_an_introduction_circular_names_each_new_stock_its_day_and_first_series():
    c = circs()["NSE/FAOP/76899"]
    got = F.circular_changes(c, text("circular_FAOP76899.txt"), {}, known(), RULE)
    table = F._table_symbols(text("circular_FAOP76899.txt"))
    assert len(got) == len(table) >= 6 and {e["symbol"] for e in got} == {s for s, _, _ in table}
    eff = got[0]["effective"]
    assert eff and all(e["effective"] == eff and e["lot"] is None and e["circ"] == c["id"] for e in got)
    first = got[0]["series"]
    assert F.rule_expiry(first).isoformat() >= eff > F.rule_expiry(F._next_month(first, -1)).isoformat()    # the near month that day
    assert "hasn't published its lot size" in F.text_of(got[0])
    with_lots = F.circular_changes(circs()["NSE/FAOP/76606"], text("circular_FAOP76606.txt"), {}, known(), RULE)
    assert with_lots and all(isinstance(e["lot"], int) and e["lot"] > 0 for e in with_lots)
    assert f"with a lot of {with_lots[0]['lot']:,}" in F.text_of(with_lots[0])


# ---------- DC-019: the stocks leaving, by name, with the day none is left ----------
@pytest.mark.parametrize("no", ["NSE/FAOP/77091", "NSE/FAOP/76865"])
def test_an_exclusion_circular_gives_the_stock_its_last_series_and_the_day_none_is_left(no):
    c = circs()[no]
    got = F.circular_changes(c, text(f"circular_FAOP{no.split('/')[-1]}.txt"), {}, known(), RULE)
    assert len(got) == 1 and got[0]["symbol"] in c["subject"]
    e = got[0]
    assert e["until"] > e["expiry"] and e["expiry"] == F.rule_expiry(e["series"]).isoformat()
    row = F.badge_of(e, TODAY)
    assert row and row["kind"] == "exit"
    # the contract file lists it to the far month, and the exit stays all the same
    assert F.still_leaving([e], {"lots": {"rows": lots()["rows"], "months": lots()["months"]}}) == [e]
    assert f"No {e['symbol']} contracts trade from" in F.text_of(e, TODAY)


# ---------- DC-020: each lot revision, was -> now, and from which series ----------
def test_a_lot_revision_names_every_stock_with_its_old_and_new_lot_and_series():
    c = circs()["NSE/FAOP/76657"]
    sheets = annexure()
    got = F.circular_changes(c, text("circular_FAOP76657.txt"), sheets, known(), RULE)
    rows = {r[2]: r for rows in sheets.values() for r in rows[1:] if len(r) >= 5 and r[3].isdigit() and r[4].isdigit()}
    assert len(got) == len(rows) and len(got) > 30
    dates = F._annexure_dates(text("circular_FAOP76657.txt"))
    assert dates and len({d for d, _ in dates.values()}) == 1
    for e in got:
        r = rows[e["symbol"]]
        assert (e["was"], e["now"]) == (int(r[3]), int(r[4])) and e["effective"] == next(iter(dates.values()))[0]
    by_sheet = {}
    for name, srows in sheets.items():
        n = int(name.split("-")[1][0])
        for r in srows[1:]:
            if len(r) >= 5:
                by_sheet[r[2]] = dates[n][1]
    assert all(e["series"] == by_sheet[e["symbol"]] for e in got)
    assert len({e["series"] for e in got}) == 2                         # some from the next series, some from later
    one = got[0]
    assert f"from {one['was']:,} to {one['now']:,}" in F.text_of(one) and F.series_name(one["series"]) in F.text_of(one)


def test_a_circular_file_is_a_pdf_or_a_zip_of_the_pdf_and_its_annexures():
    from pypdf import PdfWriter
    pdf = io.BytesIO()
    wr = PdfWriter()
    wr.add_blank_page(width=200, height=200)
    wr.write(pdf)
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("FAOP1.pdf", pdf.getvalue())
        f.writestr("Annexure.xlsx", (FO / "annexure_FAOP76657.xlsx").read_bytes())
    txt, sheets = F.circular_file(z.getvalue())
    assert isinstance(txt, str) and set(sheets) == set(annexure())
    assert F.circular_file(pdf.getvalue())[1] == {}
    for bad in (b"", b"<html>", b"PK\x03\x04broken", b"x" * (F.MAX_FILE + 1)):
        with pytest.raises((ValueError, zipfile.BadZipFile)):
            F.circular_file(bad)


class Nse:
    def __init__(self, lots_text, circulars):
        self.lots_text, self.circulars, self.files = lots_text, circulars, []

    def _surv_text(self, url):
        return self.lots_text

    def _get(self, path, params, referer=None, circuit="main"):
        self.window = params
        return self.circulars

    def _surv_bytes(self, url):
        self.files.append(url)
        return url.encode()


class Feed:
    def __init__(self, nse):
        self.nse = nse


def test_the_page_after_two_runs_names_entries_exits_lots_and_the_rename(w, monkeypatch):
    by_url = {}
    for c in circs().values():
        name = f"circular_FAOP{c['no'].split('/')[-1]}.txt"
        if (FO / name).exists():
            by_url[c["url"]] = (text(name), annexure() if c["no"].endswith("76657") else {})
    monkeypatch.setattr(F, "circular_file", lambda data: by_url[data.decode()])
    new_lots = text("fo_mktlots_live_2026-10-23.csv")
    old_lots = new_lots.replace("ICICILIFE ", "ICICIPRULI").replace("ICICI LIFE INSURANCE LTD", "ICICI PRU LIFE INS CO LTD")
    data = json.loads(text("circulars_live_2026-10-23.json"))
    F.refresh(Feed(Nse(old_lots, {"data": []})), TODAY - timedelta(days=3), sleep=lambda s: None)
    nse = Nse(new_lots, data)
    for _ in range(3):                                   # a few circular files a run
        F.refresh(Feed(nse), TODAY, sleep=lambda s: None)
    v = F.view(TODAY)
    rows = v["events"]
    kinds = {}
    for r in rows:
        kinds.setdefault(r["kind"], []).append(r)
    assert not any(r["kind"] == "exit" and r["symbol"] == "ICICIPRULI" for r in rows)
    assert not any(r["kind"] == "entry" and r["symbol"] == "ICICILIFE" for r in rows)
    assert [r["was_symbol"] for r in kinds["rename"]] == ["ICICIPRULI"]
    exits = {r["symbol"]: r for r in kinds["exit"]}
    assert {"POLYCAB", "INOXWIND"} <= set(exits) and all(exits[s]["upcoming"] and exits[s]["until"] for s in ("POLYCAB", "INOXWIND"))
    entries = {r["symbol"] for r in kinds["entry"] if r["upcoming"]}
    assert {s for s, _, _ in F._table_symbols(text("circular_FAOP76899.txt"))} <= entries
    lots_rows = [r for r in kinds["lot"] if r.get("was") and r.get("now")]
    assert len(lots_rows) > 30 and any(r["symbol"] == "ICICILIFE" and r["was_symbol"] == "ICICIPRULI" for r in lots_rows)
    assert all(not r["no"] or r["no"].startswith("NSE/FAOP/") for r in rows if r.get("source") == "circular")
    for r in rows:                                      # each named change rests on its own circular
        if r["kind"] in ("exit", "entry", "lot", "rename") and r.get("source") != "circular" and r["symbol"] in ("POLYCAB", "COROMANDEL", "ABCAPITAL"):
            assert any(s["no"].startswith("NSE/FAOP/") for s in r["sources"])
    muhurat = [e for e in F.load_events() if e.get("session")]
    assert muhurat and muhurat[0]["session"] == F.muhurat_session(text("circular_FAOP76940.txt"))


def test_a_circular_kept_without_its_date_is_read_again_and_dated(w):
    c = circs()["NSE/FAOP/76657"]
    kept = {**c, "date": None, "seen": "2026-10-05"}
    db.set_setting(F.EVENTS_KEY, json.dumps([kept]))
    nse = Nse(text("fo_mktlots_live_2026-10-23.csv"), json.loads(text("circulars_live_2026-10-23.json")))
    F.refresh(Feed(nse), TODAY, sleep=lambda s: None)
    frm = datetime.strptime(nse.window["fromDate"], "%d-%m-%Y").date()
    assert frm <= date(2026, 10, 5) - timedelta(days=F.CIRCULAR_DAYS)
    got = next(e for e in F.load_events() if e["id"] == c["id"])
    assert got["date"] == c["date"]


# ---------- DC-014: the Muhurat session ----------
def test_the_muhurat_circular_gives_the_sessions_day_and_hours():
    got = F.muhurat_session(text("circular_FAOP76940.txt"))
    assert got and date.fromisoformat(got["day"]).weekday() >= 5
    assert got["start"] < got["end"] and len(got["start"]) == 5
    c = {"source": "circular", "no": "NSE/FAOP/76940", "subject": "Muhurat Trading Session on account of Diwali", "session": got}
    assert got["start"] in F.text_of(c) and got["end"] in F.text_of(c)


def test_the_calendar_shows_the_muhurat_session_from_the_circular_or_the_holiday_list(w, monkeypatch):
    ses = F.muhurat_session(text("circular_FAOP76940.txt"))
    monkeypatch.setattr(F, "load_events", lambda: [{"id": "circ:m", "source": "circular", "no": "NSE/FAOP/76940", "url": "https://x/m.pdf", "session": ses}])
    d = date.fromisoformat(ses["day"])
    got = M.special_sessions(TODAY, TODAY, TODAY + timedelta(days=60))
    assert len(got) == 1 and got[0]["date"] == ses["day"] and got[0]["time"] == ses["start"] and ses["end"] in got[0]["detail"]
    from app.data import calendar as tc
    monkeypatch.setattr(F, "load_events", lambda: [])
    monkeypatch.setattr(tc, "auto_status", lambda market="IN": {"names": {ses["day"]: "Diwali Laxmi Pujan*", "2026-11-10": "Diwali-Balipratipada"}})
    got = M.special_sessions(TODAY, TODAY, TODAY + timedelta(days=60))
    assert [e["date"] for e in got] == [d.isoformat()] and "Diwali Laxmi Pujan" in got[0]["title"] and "*" not in got[0]["title"]


# ---------- DC-013: every index notice, a warning when the source failed, the latest first ----------
def test_index_notices_in_the_exchanges_table_layout_and_without_headings_are_read():
    got = M.read_index_changes(text("circular_FAOP76610.txt"), "Change in the Constituents of Indices")
    secs = {s["index"]: s for s in got["sections"]}
    assert got["effective"] and len(secs) >= 3
    rows = [l for l in text("circular_FAOP76610.txt").splitlines() if l.strip().endswith(("Included", "Excluded"))]
    assert sum(len(s["in"]) + len(s["out"]) for s in secs.values()) == len(rows)
    assert any(n not in M.MAIN_INDICES for n in secs)                     # an index outside the main list is kept
    one = M.read_index_changes("The following company is being excluded:\nSr. No. Company Name Symbol\n1 Alpha Ltd. ALPHA\n"
                               "The following company is being included:\n1 Beta Ltd. BETA\n", "Replacement of scrip in Nifty Smallcap 250 index")
    assert one["sections"] == [{"index": "Nifty Smallcap 250", "in": [["BETA", "Beta Ltd."]], "out": [["ALPHA", "Alpha Ltd."]]}]
    adhoc = M.read_index_changes("Index Name: NIFTY Midcap 150\nStock being excluded\n1 Alpha Ltd. ALPHA\nStock being included\n1 Beta Ltd. BETA",
                                 "Replacement in indices")
    assert adhoc["sections"][0]["index"] == "Nifty Midcap 150" and adhoc["sections"][0]["out"] == [["ALPHA", "Alpha Ltd."]]


def test_a_notice_read_to_nothing_by_an_older_reader_is_read_again_and_one_never_read_is_still_listed(w):
    class Web:
        def __init__(self):
            self.asked = []

        def text(self, url, ua=None):
            return ('<div data-date="Oct 23, 2026"><p>x</p><a href="/Press_Release/a.pdf">Replacements in indices w.e.f. October 30, 2026</a></div>'
                    '<div data-date="Oct 13, 2026"><p>x</p><a href="/Press_Release/b.pdf">Changes in indices</a></div>')

        def pdf_text(self, url, pages=0):
            self.asked.append(url)
            if url.endswith("b.pdf"):
                return "nothing to read"
            return text("circular_FAOP76610.txt")
    old = {"changes": [{"id": "x", "url": M.INDEX_BASE + "/Press_Release/a.pdf", "title": "Replacements", "announced": "2026-10-23",
                        "effective": "2026-10-30", "sections": []}]}
    web = Web()
    part = M.refresh_index(web, old, TODAY)
    assert M.INDEX_BASE + "/Press_Release/a.pdf" in web.asked
    by = {c["url"].rsplit("/", 1)[-1]: c for c in part["changes"]}
    assert by["a.pdf"]["sections"] and by["a.pdf"]["reader"] == M.INDEX_READER and by["b.pdf"]["sections"] == []
    evs = M.index_events(part, TODAY)
    assert {e["change"] for e in evs} == {by["a.pdf"]["id"], by["b.pdf"]["id"]}
    unread = next(e for e in evs if e["change"] == by["b.pdf"]["id"])
    assert unread["title"].startswith("Index notice:") and unread["url"].endswith("b.pdf")
    web2 = Web()
    M.refresh_index(web2, part, TODAY)
    assert web2.asked == []                               # read by this reader already: not asked again


def test_the_latest_index_change_comes_first_and_a_failed_source_is_flagged(w):
    st = {"index": {"changes": [{"id": "a", "url": "u1", "title": "t", "announced": "2026-08-10", "effective": "2026-09-30", "sections": [{"index": "Nifty 50", "in": [], "out": [["X", "X"]]}]},
                                {"id": "b", "url": "u2", "title": "t2", "announced": "2026-10-23", "effective": "2026-10-30", "sections": []}],
                    "error": "too many redirects", "as_of": "2026-10-20"}}
    db.set_setting(M.KEY, json.dumps(st))
    M._cache.clear()
    assert [c["id"] for c in M.index_changes(TODAY)] == ["b", "a"]
    src = {s["id"]: s for s in M.sources()}
    assert src["index"]["failed"] and src["index"]["unread"] == 1


# ---------- DC-015: published figures ----------
def test_a_fed_statement_with_a_non_breaking_hyphen_gives_its_range():
    body = "In support of its goals, the Committee decided to maintain the target range for the federal funds rate at 3‑1/2 to 3‑3/4 percent."
    assert M.read_fed_statement(body) == {"low": 3.5, "high": 3.75, "move": "unchanged"}


def test_us_releases_are_dates_with_the_bureaus_link_not_a_promised_figure():
    got = M.us_events({"releases": [{"kind": "us_cpi", "date": "2026-10-14", "time": "08:30"}]}, TODAY)
    assert got[0]["url"] == M.US_PAGES["us_cpi"] and "date only" in got[0]["detail"].lower() and got[0]["figure"] is None
    assert "dates only" in M.NOTE


def test_an_india_release_whose_figure_wasnt_read_is_tried_again(w):
    class Web:
        def __init__(self):
            self.pdfs = []

        def json(self, url, body=None):
            if "latest" in url:
                return {"data": {"url": "/arc.pdf", "filename": "arc"}}
            return {"data": [{"year": 2026, "month": 7, "day": 14, "title": "Consumer Price Index", "doc_url": "cpi_jun.pdf"}]}

        def pdf_text(self, url, pages=0):
            self.pdfs.append(url)
            return "no figure here"
    st = {"arc": "arc", "arc_read": TODAY.isoformat(), "calendar": [{"kind": "cpi", "date": "2026-07-14"}],
          "figures": [{"id": "cpi:2026-07-14", "kind": "cpi", "date": "2026-07-14", "pdf": M.MOSPI_SITE + "cpi_jun.pdf", "figure": None}]}
    web = Web()
    part = M.refresh_india(web, st, TODAY)
    assert web.pdfs == [M.MOSPI_SITE + "cpi_jun.pdf"] and part["figures"][0]["tries"] == 2
    for _ in range(3):
        part = M.refresh_india(web, part, TODAY)
    assert len(web.pdfs) == M.FIGURE_TRIES - 1 and part["figures"][0]["tries"] == M.FIGURE_TRIES      # then left


# ---------- DC-003: the chain's open interest from the exchange's end-of-day file ----------
def bhav() -> str:
    return (FX / "positioning" / "fo_bhav_nifty_2026-10-23.csv").read_text()


def test_the_end_of_day_file_gives_each_strikes_final_open_interest_and_volume_in_shares():
    got = P.bhav_chains(bhav(), ["NIFTY"])
    day = got["NIFTY"]["2026-10-27"]
    rows = {r[0]: r for r in P.final_rows(day)}
    src = [r for r in csv.DictReader(io.StringIO(bhav())) if r["FinInstrmTp"] == "IDO"]
    lot = int(src[0]["NewBrdLotQty"])
    assert day["lot"] == lot and day["spot"] == float(src[0]["UndrlygPric"])
    for r in src[:20]:
        k, side = float(r["StrkPric"]), r["OptnTp"]
        if k not in rows:
            continue
        oi_at, vol_at = (4, 9) if side == "CE" else (8, 10)
        assert rows[k][oi_at] == int(r["OpnIntrst"]) and rows[k][vol_at] == int(r["TtlTradgVol"]) * lot
    with pytest.raises(ValueError):
        P.bhav_chains("a,b\n1,2\n", ["NIFTY"])


def test_the_end_of_day_chain_is_kept_as_the_days_last_recording_and_the_page_says_so(w, monkeypatch):
    day = date(2026, 10, 23)
    intraday = {"taken_at": "2026-10-23T10:11:00+00:00", "expiry": "2026-10-27", "spot": 22610.0,
                "chain": [[22600.0, 1, 2, 3, 100, 1, 2, 3, 200, 10, 20]]}
    saved = []
    monkeypatch.setattr(P, "recorded_last", lambda name, d: [intraday] if name == "NIFTY" and d == day else [])
    n = P.keep_final_chains(bhav(), day, save=saved.append)
    assert n == 1 and saved[0]["name"] == "NIFTY" and P.is_final(saved[0]) and not P.is_final(intraday)
    assert datetime.fromisoformat(saved[0]["taken_at"]).astimezone(P.IST).date() == day
    monkeypatch.setattr(P, "recorded_last", lambda name, d: saved + [intraday] if name == "NIFTY" and d == day else [])
    assert P.keep_final_chains(bhav(), day, save=saved.append) == 0          # kept once
    s = P.summarise_day("NIFTY", day)
    assert s["final"] is False                                                # the other expiry's recording isn't final
    monkeypatch.setattr(P, "recorded_last", lambda name, d: saved if name == "NIFTY" and d == day else [])
    s = P.summarise_day("NIFTY", day)
    assert s["final"] is True
    rec = P.recorded_chain("NIFTY", "current", day)
    assert rec["final"] is True and rec["chain"] == saved[0]["chain"]


def test_a_day_whose_file_isnt_out_yet_is_tried_again_later(w, monkeypatch):
    day = date(2026, 10, 23)
    monkeypatch.setattr(P, "recorded_last", lambda name, d: [{"taken_at": "2026-10-23T10:00:00+00:00", "expiry": "2026-10-27", "chain": []}])

    class Files:
        def __init__(self, *a, **k):
            pass

        def text(self, url, want=".csv"):
            return None
    import app.exchange_days as X
    monkeypatch.setattr(X, "Files", Files)
    runner = P.Runner(lambda: P.Feed(object()), sleep=lambda s: None, pace=0)
    assert runner.final_day(P.Feed(object()), day) == "missing"
    assert (P.state().get("finals") or {}).get("days", {}).get(day.isoformat()) == 1
    monkeypatch.setattr(P, "recorded_last", lambda name, d: [])
    assert runner.final_day(P.Feed(object()), day + timedelta(days=3)) == "none"


# ---------- DC-004, DB-011: lots from the exchange's contract file ----------
def test_an_index_lot_comes_from_the_contract_file_when_the_feed_has_none(w):
    db.set_setting(F.KEY, json.dumps({"lots": {"rows": lots()["rows"], "months": lots()["months"], "as_of": "2026-10-23"}}))
    F._cache.clear()

    class Offline:
        def ready(self):
            return False
    want = lots()["rows"]["NIFTY"]["lots"]["2026-10"]
    assert P.lot_of(Offline(), "NIFTY", "2026-10-27", {"lot": None}) == want
    assert P.in_lots(want * 7, P.lot_of(Offline(), "NIFTY", "2026-10-27")) == 7
    assert P.lot_of(Offline(), "SENSEX", "2026-10-29") is None             # not on the exchange's NSE file


# ---------- DC-006: "Prop desks", not "Pro" ----------
def test_the_exchanges_pro_participants_are_named_prop_desks():
    assert P.PARTICIPANT_NAME["pro"] == "Prop desks"
