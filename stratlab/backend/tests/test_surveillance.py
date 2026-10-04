"""Exchange surveillance lists: reading each list loosely (and surviving one that is down or changes shape), keeping
the last good copy with its date, logging who entered or left, the badges' answer, the public page, the screens'
filter, the alerts, the My Stocks newsletter's lines, the twice-a-day job and the Admin check."""
import json
import random
import re
from datetime import date, datetime, timedelta

import httpx
import pytest

from app import db, main, platform_check, screens, stock_alerts as sa, stock_pages, surveillance as S
from app.intel import filings as F
from app.intel.net import SourceError
from tests import world as W
from tests.fake_db import headers

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|risky|danger|beware|warning|signal)\b", re.I)
TODAY = date.today()


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    screens._mem.clear()
    yield world
    world["close"]()
    S._cache.clear()
    screens._mem.clear()


class Feed:
    """A stand-in exchange client whose lists the test sets, and can break one at a time."""

    def __init__(self, **kw):
        self.asm = kw.get("asm", {"lt": {"RELIANCE": 2}, "st": {}})
        self.gsm = kw.get("gsm", {"ITC": 2})
        self.esm = kw.get("esm", {})
        self.ban = kw.get("ban", (TODAY.isoformat(), ["INFY"]))
        self.bands = kw.get("bands", {"RELIANCE": {"series": "EQ", "band": None}, "ITC": {"series": "BE", "band": 5.0},
                                      "TATASTEEL": {"series": "EQ", "band": 20.0}})
        self.down: set[str] = set()

    def _give(self, name, v):
        if name in self.down:
            raise SourceError("the exchange", f"The exchange's {name} list isn't answering.", busy=True)
        return v

    def asm_list(self):
        return self._give("asm", self.asm)

    def gsm_list(self):
        return self._give("gsm", self.gsm)

    def esm_list(self):
        return self._give("esm", self.esm)

    def fo_ban(self):
        return self._give("fo_ban", self.ban)

    def security_bands(self):
        return self._give("bands", self.bands)


# ---------- reading the exchange's lists ----------
def test_stage_is_read_however_it_is_written():
    assert [F.stage_of(t) for t in ("Stage I", "LTASM Stage - IV", "stage-2", "Stage 0", "STAGE III", "no stage", None, "Stagecoach")] \
        == [1, 4, 2, 0, 3, None, None, None]
    assert F.stage_rows([{"Symbol": "abc", "gsmStage": "II"}, {"symbol": "XYZ", "survDesc": "GSM Stage IV"}, {"symbol": "Q"}]) \
        == {"ABC": 2, "XYZ": 4, "Q": None}


def test_asm_halves_by_key_or_by_each_rows_wording():
    a = F.asm_rows(W.surveillance_answers()["/api/reportASM"])
    assert a == {"lt": {"RELIANCE": 2}, "st": {"TATASTEEL": 1}}
    flat = F.asm_rows({"data": [{"symbol": "A", "asmSurvIndicator": "ST-ASM Stage 2"}, {"symbol": "B", "indicator": "Long Term ASM Stage 3"}]})
    assert flat == {"lt": {"B": 3}, "st": {"A": 2}}
    assert F.asm_rows({"longterm": {"data": []}, "shortterm": {"data": []}}) == {"lt": {}, "st": {}}     # empty lists are real
    with pytest.raises(ValueError):
        F.asm_rows({"data": [{"name": "no symbol here"}]})                                            # changed shape


def test_ban_file_and_price_band_file():
    assert F.fo_ban_rows("Securities in Ban For Trade Date 05-OCT-2026:\n1,ABC\n2,XYZ\n") == ("2026-10-05", ["ABC", "XYZ"])
    assert F.fo_ban_rows("Securities in Ban For Trade Date 05-OCT-2026: NIL") == ("2026-10-05", [])
    for bad in ("", "<html>blocked</html>", "nothing useful"):
        with pytest.raises(ValueError):
            F.fo_ban_rows(bad)
    rows = F.sec_list_rows("Symbol,Series,Security Name,Band,Remarks\nA,EQ,A Ltd,20,\nB,BE,B Ltd,5,\nC,EQ,C Ltd,No Band,\nD,N1,Bond,,\n")
    assert rows == {"A": {"series": "EQ", "band": 20.0}, "B": {"series": "BE", "band": 5.0}, "C": {"series": "EQ", "band": None}}


def test_fuzz_the_parsers_never_raise_anything_but_value_error():
    rng = random.Random(7)
    junk = [None, "", "x", 0, 1.5, True, [], {}, [1, "a"], {"data": None}, {"data": [None, 1, "s"]}, "<script>", "\x00",
            {"symbol": None}, {"symbol": "A" * 50}, {"longterm": {"data": [{"symbol": "OK", "stage": "Stage 9"}]}},
            [{"symbol": "Z", "stage": {"x": 1}}], {"a": {"b": {"c": {"d": {"e": {"f": {"g": [{"symbol": "DEEP"}]}}}}}}}]
    for _ in range(500):
        x = rng.choice(junk) if rng.random() < 0.5 else {rng.choice(["data", "longterm", "x"]): rng.choice(junk)}
        for fn in (F.asm_rows, F.stage_rows):
            try:
                out = fn(x)
                assert isinstance(out, dict)
            except ValueError:
                pass
        for fn in (F.fo_ban_rows, F.sec_list_rows):
            try:
                fn(rng.choice(["", "a,b\n1,2", str(x), "Symbol,Series,Band\n\x00,EQ,20", "1,ABC\n2,", "Trade Date 31-FEB-2026"]))
            except ValueError:
                pass


def test_exchange_client_reads_every_list_from_the_fake_exchange(w):
    feed = main.filings_feed
    assert feed.asm_list() == {"lt": {"RELIANCE": 2}, "st": {"TATASTEEL": 1}}
    assert feed.gsm_list() == {"ITC": 2} and feed.esm_list() == {}
    assert feed.fo_ban() == (TODAY.isoformat(), ["INFY"])
    bands = feed.security_bands()
    assert bands["ITC"] == {"series": "BE", "band": 5.0} and "GOVTBOND" not in bands


def test_a_changed_shape_or_a_page_instead_of_data_is_a_clear_error(w):
    def handler(r):
        if r.url.path == "/api/reportGSM":
            return httpx.Response(200, json={"data": [{"weird": 1}]})
        if r.url.path.endswith("fo_secban.csv"):
            return httpx.Response(200, text="<html>please wait</html>")
        if r.url.path.endswith("sec_list.csv"):
            return httpx.Response(200, text="Symbol,Series,Band\nA,EQ,20\n")
        return httpx.Response(200, text="<html></html>")
    feed = F.NSEFilings(transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError, match="GSM list wasn't in the expected shape"):
        feed.gsm_list()
    with pytest.raises(SourceError, match="F&O ban file"):
        feed.fo_ban()
    with pytest.raises(SourceError, match="price-band file looked wrong"):
        feed.security_bands()
    with pytest.raises(SourceError):
        feed.asm_list()                                       # a page instead of data


def test_the_surveillance_breaker_rests_after_three_outages_and_spares_the_filings(w):
    calls = []

    def handler(r):
        calls.append(r.url.path)
        if r.url.path.endswith(".csv"):
            return httpx.Response(503)
        return httpx.Response(200, json=[])
    feed = F.NSEFilings(transport=httpx.MockTransport(handler))
    for _ in range(3):
        with pytest.raises(SourceError):
            feed.fo_ban()
    n = len(calls)
    with pytest.raises(SourceError, match="aren't answering right now"):
        feed.security_bands()
    assert len(calls) == n                                    # resting: not asked
    assert feed.announcements("RELIANCE") == []               # the filings feed has its own breaker


# ---------- keeping the lists ----------
def test_refresh_keeps_each_list_with_its_date_and_logs_nothing_the_first_time(w):
    out = S.refresh(Feed(), TODAY)
    assert out["changes"] == [] and out["problems"] == []
    assert S.snapshot(TODAY)["flags"] == {"RELIANCE": ["asm_lt:2"], "ITC": ["gsm:2", "t2t"], "INFY": ["fo_ban"]}
    v = S.view(TODAY)
    assert v["as_of"] == TODAY.isoformat() and all(not i["stale"] and not i["failed"] for i in v["lists"])
    assert v["labels"]["asm_lt:2"]["short"] == "LT-ASM 2" and "100% margin" in v["labels"]["asm_lt:2"]["text"]
    assert "price band" in v["labels"]["asm_lt:2"]["text"]
    assert "95% of the market-wide position limit" in v["labels"]["fo_ban"]["text"]
    for lab in v["labels"].values():
        assert not ADVICE.search(lab["text"] + lab["label"]) and not PROVIDERS.search(lab["text"])


def test_a_failed_list_keeps_yesterdays_copy_clearly_dated(w):
    yday = TODAY - timedelta(days=1)
    S.refresh(Feed(), yday)
    feed = Feed(gsm={})
    feed.down = {"gsm", "fo_ban"}
    out = S.refresh(feed, TODAY)
    assert len(out["problems"]) == 2
    info = {i["id"]: i for i in S.view(TODAY)["lists"]}
    assert info["gsm"]["as_of"] == yday.isoformat() and info["gsm"]["failed"]
    assert info["asm"]["as_of"] == TODAY.isoformat() and not info["asm"]["failed"]
    assert S.snapshot(TODAY)["flags"]["ITC"] == ["gsm:2", "t2t"]                 # yesterday's GSM list still shows
    assert [f["as_of"] for f in S.flags_for("ITC", TODAY)] == [yday.isoformat(), TODAY.isoformat()]
    old = {i["id"]: i for i in S.view(TODAY + timedelta(days=10))["lists"]}
    assert old["gsm"]["stale"]


def test_entering_leaving_moving_stage_and_band_changes_are_logged(w):
    yday = TODAY - timedelta(days=1)
    S.refresh(Feed(), yday)
    feed = Feed(asm={"lt": {"RELIANCE": 3}, "st": {"TATASTEEL": 1}}, gsm={}, ban=(TODAY.isoformat(), []),
                bands={"RELIANCE": {"series": "EQ", "band": None}, "ITC": {"series": "EQ", "band": 5.0},
                       "TATASTEEL": {"series": "EQ", "band": 10.0}})
    out = S.refresh(feed, TODAY)
    said = sorted(f"{c['symbol']} {S.change_text(c)}" for c in out["changes"])
    assert said == ["INFY left the F&O ban period",
                    "ITC left GSM (Graded Surveillance Measure)", "ITC left Trade-to-trade settlement",
                    "RELIANCE moved from Stage 2 to Stage 3 of Long-term ASM (Additional Surveillance Measure)",
                    "TATASTEEL entered Short-term ASM (Additional Surveillance Measure), Stage 1",
                    "TATASTEEL price band changed from 20% to 10%"]
    assert S.snapshot(TODAY)["flags"]["TATASTEEL"] == ["asm_st:1", "band"]
    band = [f for f in S.flags_for("TATASTEEL", TODAY) if f["code"] == "band"][0]
    assert band["short"] == "Band 10%" and "from 20%" in band["text"]
    assert "band" not in S.snapshot(TODAY + timedelta(days=S.BAND_DAYS + 1))["flags"].get("TATASTEEL", [])
    assert len(S.changes_for("ITC", yday.isoformat())) == 2 and S.changes_for("ITC", (TODAY + timedelta(days=1)).isoformat()) == []
    S.refresh(feed, TODAY)                                     # the same lists again: nothing new logged
    assert len(db.json_value(db.get_setting(S.CHANGES_KEY), [])) == 6


def test_the_badges_answer_and_admin_refresh(w):
    c = w["client"]
    r = c.get("/research/surveillance", headers=headers("pro-token"))
    assert r.status_code == 200 and r.json()["flags"] == {}                     # nothing read yet
    r = c.post("/admin/surveillance/refresh", headers=headers("admin-token"))
    assert r.status_code == 200 and r.json()["problems"] == []
    assert c.post("/admin/surveillance/refresh", headers=headers("pro-token")).status_code in (401, 403)
    v = c.get("/research/surveillance", headers=headers("free-token")).json()
    assert v["flags"]["RELIANCE"] == ["asm_lt:2"] and v["flags"]["INFY"] == ["fo_ban"] and v["flags"]["ITC"] == ["gsm:2", "t2t"]
    assert v["flags"]["TATASTEEL"] == ["asm_st:1"] and v["source"] == "exchange surveillance lists"
    assert not PROVIDERS.search(json.dumps(v)) and not ADVICE.search(json.dumps(v["labels"]))
    assert c.get("/research/surveillance").status_code == 401


def test_public_company_page_shows_the_flags(w):
    S.refresh(main.filings_feed)
    page = w["client"].get("/stocks/in/RELIANCE").text
    assert "Exchange surveillance" in page and "LT-ASM 2" in page and "Stage 2" in page and "100% margin" in page
    block = stock_pages.surveillance_html(S.flags_for("RELIANCE"))
    assert block in page and not PROVIDERS.search(block) and not ADVICE.search(block)
    assert "Exchange surveillance" not in w["client"].get("/stocks/in/TCS").text
    stored = '<h1>X</h1><div class="card grid"></div>'
    flags = S.flags_for("RELIANCE")
    assert stock_pages.with_surveillance(stored, flags).index("data-surveillance") < stored.index("card grid") + 60
    assert stock_pages.with_surveillance(stored, []) == stored
    assert "&lt;b&gt;" in stock_pages.surveillance_html([{"short": "<b>", "label": "x", "text": "y", "as_of": None}])


def test_platform_check_reads_every_list(w):
    r = platform_check.check_surveillance(main.filings_feed)
    assert r["state"] == "pass" and "ASM 2" in r["detail"] and "F&O ban 1" in r["detail"]
    f = Feed()
    f.down = {"esm"}
    assert platform_check.check_surveillance(f)["state"] == "warn"
    f.down = {"asm", "gsm", "esm", "fo_ban", "bands"}
    assert platform_check.check_surveillance(f)["state"] == "fail"
    assert "Surveillance lists" in [c[0] for c in main.platform_checks()]


# ---------- screens ----------
def test_screen_filter_on_surveillance_lists(w):
    from tests.test_screens import store_pages
    store_pages()
    idx = screens.build_index("IN")
    S.refresh(Feed(), TODAY)
    run = lambda f: sorted(r["symbol"] for r in screens.run("IN", f, index=idx)["rows"])     # noqa: E731
    everyone = run({})
    assert run({"surveillance": "on"}) == sorted(s for s in ("RELIANCE", "ITC", "INFY") if s in everyone)
    assert "RELIANCE" in run({"surveillance": "on", "surv_lists": ["asm"]}) and "ITC" not in run({"surveillance": "on", "surv_lists": ["asm"]})
    assert "RELIANCE" not in run({"surveillance": "off"}) and len(run({"surveillance": "off"})) == len(everyone) - len(run({"surveillance": "on"}))
    rows = {r["symbol"]: r for r in screens.run("IN", {}, index=idx)["rows"]}
    assert rows["RELIANCE"]["surveillance"] == ["asm_lt:2"]
    for bad in ({"surveillance": "maybe"}, {"surveillance": "on", "surv_lists": ["xyz"]}, {"surv_lists": "asm"}):
        with pytest.raises(screens.ScreenError):
            screens.clean("IN", bad)
    assert screens.clean("US", {"surveillance": "on"})["surveillance"] is None
    f = screens.clean("IN", {"surveillance": "off", "surv_lists": ["gsm", "fo_ban"]})
    assert screens.describe("IN", f) == ["Not on GSM or F&O ban"]
    meta = screens.meta("IN")
    assert [x["id"] for x in meta["surveillance"]["lists"]] == ["asm", "gsm", "esm", "t2t", "fo_ban"] and screens.meta("US")["surveillance"] is None
    assert not ADVICE.search(meta["help"]["surveillance"]) and not PROVIDERS.search(meta["help"]["surveillance"])


# ---------- alerts ----------
def surv_alert(symbol="RELIANCE", created=None):
    a = sa.clean({"region": "IN", "symbol": symbol, "kind": "surveillance"})
    return {**a, "id": "a1", "status": "active", "rev": 1, "state": {},
            "created_at": created or f"{(TODAY - timedelta(days=5)).isoformat()}T00:00:00+00:00"}


def test_surveillance_alert_is_india_only_and_fires_once_per_change():
    assert sa.describe(surv_alert()).startswith("Enters or leaves an exchange surveillance list")
    with pytest.raises(sa.AlertError, match="Indian stocks"):
        sa.clean({"region": "US", "symbol": "AAPL", "kind": "surveillance"})
    rows = [{"id": "d:RELIANCE:asm_lt:None>asm_lt:1", "kind": "surveillance", "day": TODAY.isoformat(), "symbol": "RELIANCE",
             "list": "asm_lt", "was": None, "now": "asm_lt:1"},
            {"id": "d:TCS:fo_ban", "kind": "surveillance", "day": TODAY.isoformat(), "symbol": "TCS", "list": "fo_ban", "was": None, "now": "fo_ban"}]
    text, st = sa.evaluate_event(surv_alert(), rows)
    assert text == ("RELIANCE entered Long-term ASM (Additional Surveillance Measure), Stage 1. "
                    "From exchange surveillance lists")
    assert not ADVICE.search(text) and not PROVIDERS.search(text)
    assert sa.evaluate_event({**surv_alert(), "state": st}, rows)[0] is None
    assert sa.evaluate_event(surv_alert(created=f"{(TODAY + timedelta(days=1)).isoformat()}T00:00:00+00:00"), rows)[0] is None
    assert sa.evaluate_event({**surv_alert(), "kind": "deal"}, rows)[0] is None       # other event alerts ignore these


def test_the_job_reads_twice_a_day_and_fires_alerts_on_changes(w):
    feed = Feed()
    sent = []
    job = S.Job(lambda: feed, lambda changes, now: sa.fire_events([{**c, "kind": "surveillance"} for c in changes], now,
                                                                   lambda p: 10, send=lambda p, s, t: sent.append(t) or ["push"]))
    a = sa.create("u-pro", {"region": "IN", "symbol": "INFY", "kind": "surveillance"}, 10)
    assert a["kind"] == "surveillance"
    row = json.loads(db.get_setting(sa.KEY + "u-pro"))
    row["items"][0]["created_at"] = f"{(TODAY - timedelta(days=30)).isoformat()}T00:00:00+00:00"
    db.set_setting(sa.KEY + "u-pro", json.dumps(row))
    monday = TODAY
    while monday.weekday() != 0:
        monday -= timedelta(days=1)
    from app.data import calendar
    morning = datetime.combine(monday, datetime.min.time()).replace(hour=8, minute=30, tzinfo=F.IST)
    is_day = calendar.is_trading_day("IN", monday)
    job.tick(morning)
    if is_day:
        assert db.get_setting("newsjob:surv-am") == monday.isoformat()
    assert S.load()                                           # read (a run, or the first read on an empty store)
    feed.ban = (monday.isoformat(), [])
    evening = morning.replace(hour=20)
    job.tick(evening)
    if is_day:
        assert db.get_setting("newsjob:surv-pm") == monday.isoformat()
        assert sent and "INFY left the F&O ban period" in sent[0] and "Facts, not advice" in sent[0]
        assert job.status["changes"] == 1
        assert job.tick(evening) == 0                          # once per run


def test_alert_endpoint_says_what_the_stock_is_on_now(w):
    S.refresh(Feed(), TODAY)
    r = w["client"].post("/alerts", headers=headers("pro-token"), json={"region": "IN", "symbol": "RELIANCE", "kind": "surveillance"})
    assert r.status_code == 200
    body = r.json()
    assert body["alert"]["text"].startswith("Enters or leaves") and "Long-term ASM" in body["note"] and "Stage 2" in body["note"]
    r = w["client"].post("/alerts", headers=headers("pro-token"), json={"region": "IN", "symbol": "TCS", "kind": "surveillance"})
    assert "isn't on an exchange surveillance list now" in r.json()["note"]


# ---------- the newsletter ----------
def test_newsletter_lines_for_changes_and_current_lists(w):
    from app.newsletter import content, write
    yday = TODAY - timedelta(days=1)
    S.refresh(Feed(), yday)
    S.refresh(Feed(gsm={"ITC": 3}), TODAY)
    s = content.surveillance_lines("ITC", yday.isoformat())
    assert s["changes"][0]["text"] == "moved from Stage 2 to Stage 3 of GSM (Graded Surveillance Measure)"
    r = {"symbol": "ITC", "price": 100.0, "change_pct": 0.5, "stage": 2, "surveillance": s}
    lines = [ln["text"] for ln in write.stock_lines(r, yday.isoformat())]
    assert any(t.startswith("Exchange surveillance: moved from Stage 2 to Stage 3 of GSM") for t in lines)
    still = content.surveillance_lines("RELIANCE", TODAY.isoformat())
    assert still == {"changes": [], "now": ["Long-term ASM (Additional Surveillance Measure), Stage 2"]}
    lines = [ln["text"] for ln in write.stock_lines({**r, "symbol": "RELIANCE", "surveillance": still}, TODAY.isoformat())]
    assert "On exchange surveillance lists: Long-term ASM (Additional Surveillance Measure), Stage 2" in lines
    assert content.surveillance_lines("TCS", TODAY.isoformat()) is None
    for t in lines:
        assert not write.banned(t) and not PROVIDERS.search(t)
