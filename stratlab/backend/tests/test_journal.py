"""The real-trade journal: pairing fills into round trips (part fills, scaling in and out, reversals, shorts, F&O and
expiry), tax P&L lines, charges, the stats, the verdict's checks on real trades, the API, plan limits and deletion."""
import io
import math
import zipfile
from datetime import date
from pathlib import Path

import pytest

from app import db, journal as J, journal_routes, main, plans, tax_lots
from app.config import settings
from app.engine import costs as C
from tests import world

PRO, FREE, BASIC = world.headers("pro-token"), world.headers("free-token"), world.headers("basic-token")
FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 4)
S = J.clean_settings({})


def fill(d, side, qty, price, sym="INFY", t="", tid="", **kw):
    return {"d": d, "t": t, "side": side, "qty": qty, "price": price, "symbol": sym, "tid": tid, **kw}


def pair(fills, s=S):
    return J.pair_fills(fills, s, TODAY)


# ---------- pairing ----------
def test_part_fills_of_one_order_are_one_trade():
    got, open_, _ = pair([fill("2026-03-02", "B", 4, 100, t="09:20:01"), fill("2026-03-02", "B", 6, 100.5, t="09:20:01"),
                          fill("2026-03-02", "S", 3, 104, t="11:00:00"), fill("2026-03-02", "S", 7, 105, t="11:00:02")])
    assert len(got) == 1 and not open_
    t = got[0]
    assert t["side"] == "long" and t["qty"] == 10 and t["fills"] == 4 and t["segment"] == "eq_intraday"
    assert t["entry"] == pytest.approx(100.3) and t["exit"] == pytest.approx(104.7)
    assert t["gross"] == pytest.approx(3 * 104 + 7 * 105 - 4 * 100 - 6 * 100.5)
    assert t["hold_s"] == pytest.approx(5999 + 2) and t["entry_t"] == "2026-03-02T09:20:01" and t["exit_t"] == "2026-03-02T11:00:02"


def test_scaling_in_and_out_stays_one_trade_until_flat():
    fs = [fill("2026-01-05", "B", 10, 100, t="10:00"), fill("2026-01-06", "B", 10, 110, t="10:00"),
          fill("2026-01-07", "S", 5, 120, t="10:00"), fill("2026-01-08", "B", 5, 115, t="10:00"), fill("2026-01-09", "S", 20, 125, t="10:00")]
    got, open_, _ = pair(fs)
    assert len(got) == 1 and not open_
    t = got[0]
    assert t["qty"] == 25 and t["entry"] == pytest.approx((1000 + 1100 + 575) / 25) and t["exit"] == pytest.approx((600 + 2500) / 25)
    assert t["gross"] == pytest.approx(3100 - 2675) and t["segment"] == "eq_delivery" and t["hold_days"] == 4
    # delivery: STT both ways, stamp on buys, no brokerage by default
    want = sum(C.total(C.order_costs("in_eq", sd, q, p, 0)) for sd, q, p in
               (("buy", 10, 100), ("buy", 10, 110), ("buy", 5, 115), ("sell", 5, 120), ("sell", 20, 125)))
    assert t["charges"] == pytest.approx(want) and t["net"] == pytest.approx(t["gross"] - want)


def test_selling_more_than_held_closes_the_long_and_opens_a_short():
    fs = [fill("2026-02-02", "B", 10, 100, sym="NIFTY26FEBFUT", t="09:30"), fill("2026-02-02", "S", 15, 110, sym="NIFTY26FEBFUT", t="10:30"),
          fill("2026-02-03", "B", 5, 105, sym="NIFTY26FEBFUT", t="09:45")]
    got, open_, _ = pair(fs)
    assert [(t["side"], t["qty"], t["segment"]) for t in got] == [("long", 10, "fut"), ("short", 5, "fut")]
    assert got[0]["gross"] == pytest.approx(100) and got[1]["gross"] == pytest.approx(25)
    assert got[1]["entry"] == 110 and got[1]["exit"] == 105 and not open_
    # the 15-lot sale's brokerage is split 10:5 between the two trades
    b = S["brokerage_other"]
    assert got[0]["charges"] == pytest.approx(C.total(C.order_costs("in_fut", "buy", 10, 100, b)) + C.total(C.order_costs("in_fut", "sell", 10, 110, b * 10 / 15)))
    assert got[0]["id"] != got[1]["id"]


def test_intraday_short_and_an_unmatched_sale():
    got, open_, unmatched = pair([fill("2026-04-01", "S", 50, 200, sym="SBIN", t="09:16"), fill("2026-04-01", "B", 50, 196, sym="SBIN", t="14:00"),
                                  fill("2026-04-02", "S", 5, 1500, sym="TCS")])
    assert len(got) == 1 and got[0]["side"] == "short" and got[0]["gross"] == pytest.approx(200) and got[0]["segment"] == "eq_intraday"
    k = "in_eq_mis"
    assert got[0]["charges"] == pytest.approx(C.total(C.order_costs(k, "sell", 50, 200, 20)) + C.total(C.order_costs(k, "buy", 50, 196, 20)))
    assert not open_ and unmatched[0]["symbol"] == "TCS"                         # bought before the earliest file


def test_open_position_keeps_what_its_closed_part_made():
    got, open_, _ = pair([fill("2026-01-01", "B", 100, 400, sym="ITC"), fill("2026-02-01", "S", 40, 450, sym="ITC")])
    assert not got and open_ == [{"symbol": "ITC", "side": "long", "qty": 60, "since": "2026-01-01", "avg": 400.0, "realised": 2000.0}]


def test_options_left_open_past_expiry_close_at_zero():
    fs = [fill("2026-09-10", "B", 75, 120, sym="NIFTY26SEP25000CE", t="10:00", exchange="NFO"),
          fill("2026-09-15", "S", 75, 80, sym="NIFTY2692225500PE", t="10:00", exchange="NFO"),        # a weekly, sold
          fill("2026-10-01", "B", 75, 50, sym="NIFTY26OCT26000CE", t="10:00", exchange="NFO")]       # not expired yet
    got, open_, _ = pair(fs)
    by = {t["symbol"]: t for t in got}
    assert by["NIFTY26SEP25000CE"]["expired"] and by["NIFTY26SEP25000CE"]["exit"] == 0 and by["NIFTY26SEP25000CE"]["exit_t"] == "2026-09-30T15:30:00"
    assert by["NIFTY26SEP25000CE"]["gross"] == pytest.approx(-9000) and by["NIFTY26SEP25000CE"]["segment"] == "opt"
    short = by["NIFTY2692225500PE"]
    assert short["side"] == "short" and short["gross"] == pytest.approx(6000) and short["exit_t"].startswith("2026-09-22")
    assert [o["symbol"] for o in open_] == ["NIFTY26OCT26000CE"]
    assert J.expiry("BANKNIFTY26O0753000CE") == date(2026, 10, 7) and J.expiry("RELIANCE") is None


def test_instruments_and_cost_models():
    assert J.classify("NIFTY26SEP25000CE")["kind"] == "in_opt" and J.classify("SENSEX26SEP80000PE")["kind"] == "in_bse_opt"
    assert J.classify("CRUDEOIL26OCTFUT")["group"] == "com" and J.classify("USDINR26OCTFUT")["kind"] == "in_cds_fut"
    assert J.classify("NSE:RELIANCE-EQ") == {"u": "RELIANCE", "group": "eq", "kind": "in_eq", "opt": False}
    assert J.classify("BANKNIFTY26OCTFUT")["u"] == "BANKNIFTY"


# ---------- files ----------
def test_the_tax_pnl_zip_gives_every_exit_with_its_charges():
    got = J.parse((FIX / "taxpnl" / "zerodha_taxpnl_2024_2025.zip").read_bytes(), "taxpnl.zip")
    assert got["broker"] == "Zerodha" and not got["fills"] and len(got["lines"]) == 16
    assert any("summary workbook" in s["reason"] for s in got["skipped"])
    ts = {(t["symbol"], t["entry_t"]): t for t in J.line_trades(got["lines"], S)}
    fut = ts[("BANKNIFTY24OCTFUT", "2024-10-01T09:20:00")]
    assert fut["segment"] == "fut" and fut["gross"] == -2500 and fut["charges"] == pytest.approx(120) and fut["charges_from"] == "file"
    assert fut["side"] is None and fut["hold_s"] == pytest.approx(2 * 86400 + 5 * 3600 + 50 * 60)
    infy = [t for t in ts.values() if t["symbol"] == "INFY"]
    assert len(infy) == 1 and infy[0]["qty"] == 30 and infy[0]["fills"] == 2 and infy[0]["segment"] == "eq_intraday"   # two lines, one trade
    assert {t["segment"] for t in ts.values()} == {"eq_delivery", "eq_intraday", "opt", "fut", "com", "cur"}


def test_a_tradebook_keeps_its_fno_lines_and_times():
    got = J.parse((FIX / "tradebooks" / "zerodha_console_tradebook.csv").read_bytes(), "tradebook.csv")
    assert got["broker"] == "Zerodha Console" and len(got["fills"]) == 8 and not got["lines"]
    nifty = [f for f in got["fills"] if f["symbol"] == "NIFTY24SEP25000CE"][0]
    assert nifty["seg"] == "FO" and nifty["t"] == "10:00:00"
    trades, open_, _ = pair(got["fills"])
    infy = [t for t in trades if t["symbol"] == "INFY"][0]
    assert infy["entry_t"] == "2024-09-02T09:20:00" and infy["hold_s"] == pytest.approx(5 * 3600 + 41 * 60 + 12)
    assert [o["symbol"] for o in open_] == ["TCS"]


def test_every_broker_tradebook_reads(tmp_path):
    for f in (FIX / "tradebooks").iterdir():
        got = J.parse(f.read_bytes(), f.name)
        assert got["fills"] or got["lines"], f.name
    hdfc = J.parse((FIX / "tradebooks" / "hdfc_securities_tradebook.xls").read_bytes(), "hdfc.xls")
    assert pair(hdfc["fills"])[0][0]["symbol"] == "HDFC BANK LTD"                 # the company's name when there's no symbol


def test_bad_files_get_a_plain_answer():
    for data, name, words in ((b"", "x.csv", "empty"), (b"hello,world\n1,2\n", "x.csv", "couldn't find any trades"),
                              (b"Symbol,Quantity,Average price\nINFY,5,1500\n", "h.csv", "holdings")):
        with pytest.raises(J.hf.FileError) as e:
            J.parse(data, name)
        assert words in str(e.value).lower()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.csv", "x")
    with pytest.raises(J.hf.FileError, match="paths"):
        J.parse(buf.getvalue(), "evil.zip")


def test_tax_pnl_lines_a_tradebook_covers_count_once():
    fills = [fill("2026-01-05", "B", 10, 100, sym="ITC"), fill("2026-03-05", "S", 10, 110, sym="ITC"),
             fill("2026-09-02", "B", 75, 100, sym="NIFTY26SEP25000CE")]
    line = {"sym": "ITC", "ed": "2026-01-05", "et": "", "xd": "2026-03-05", "xt": "", "qty": 10.0, "bv": 1000, "sv": 1100, "charges": None, "side": None}
    later = {**line, "ed": "2026-04-01", "xd": "2026-05-01"}
    opt = {**line, "sym": "NIFTY26SEP25000CE", "ed": "2026-09-02", "xd": "2026-09-29"}        # its expiry, after the last fill
    assert J.covered(fills, [line, later, opt]) == [later]


def test_tax_report_trades_come_across():
    got = J.from_tax([{"d": "2024-01-02", "side": "B", "qty": 5, "price": 100, "symbol": "INFY", "src": "trades"},
                      {"d": "2024-01-02", "side": "B", "qty": 2, "price": 50, "symbol": "ITC", "src": "pnl", "tid": "pnl:1:b"},
                      {"d": "2024-03-02", "side": "S", "qty": 2, "price": 60, "symbol": "ITC", "src": "pnl", "tid": "pnl:1:s"}])
    assert len(got["fills"]) == 1 and got["lines"] == [{"sym": "ITC", "ed": "2024-01-02", "et": "", "xd": "2024-03-02", "xt": "", "qty": 2.0,
                                                         "bv": 100, "sv": 120, "charges": None, "side": None, "exchange": ""}]


# ---------- stats ----------
def T(net, exit_t, gross=None, charges=0.0, entry_t=None, hold_days=0, hold_s=None, **kw):
    return {"net": net, "gross": net + charges if gross is None else gross, "charges": charges, "exit_t": exit_t,
            "entry_t": entry_t or exit_t, "hold_days": hold_days, "hold_s": hold_s, "note": kw.pop("note", {}), "u": kw.pop("u", "X"),
            "symbol": "X", "segment": kw.pop("segment", "eq_delivery"), "side": kw.pop("side", "long"), **kw}


def test_summary_maths():
    nets = [100, -50, 200, -100, -100, 300]
    ts = [T(v, f"2026-01-0{i + 1}", charges=10) for i, v in enumerate(nets)]
    s = J.summary(ts, capital=1000)
    assert (s["n"], s["wins"], s["losses"], s["win_rate"]) == (6, 3, 3, 50.0)
    assert s["avg_win"] == 200 and s["avg_loss"] == pytest.approx(-83.33) and s["expectancy"] == pytest.approx(58.33)
    assert s["profit_factor"] == pytest.approx(600 / 250) and s["net"] == 350 and s["charges"] == 60 and s["gross"] == 410
    assert s["charges_pct"] == pytest.approx(60 / 410 * 100, abs=0.05)
    # running P&L 100, 50, 250, 150, 50, 350: deepest fall 200 from the 250 high (200 / 1,250 of capital)
    assert s["max_dd"] == 200 and s["max_dd_pct"] == pytest.approx(16.0)
    assert s["streaks"] == {"longest_win": 1, "longest_loss": 2, "current": {"kind": "win", "n": 1}}
    assert [p["v"] for p in s["equity"]] == [100, 50, 250, 150, 50, 350]
    empty = J.summary([])
    assert empty["n"] == 0 and empty["win_rate"] is None and empty["equity"] == [] and empty["profit_factor"] is None


def test_breakdowns_by_day_hour_tag_and_holding_time():
    ts = [T(100, "2026-03-02T10:30:00", entry_t="2026-03-02T09:20:00", hold_s=4200, note={"tag": "ORB", "mistakes": ["Exited early"]}),   # Monday
          T(-40, "2026-03-02T09:25:00", entry_t="2026-03-02T09:21:00", hold_s=240, note={"tag": "ORB"}),
          T(60, "2026-03-10", entry_t="2026-03-04", hold_days=6, u="TCS"),                                           # Wednesday
          T(-10, "2026-03-05", entry_t="2026-03-05", side="short", segment="eq_intraday")]
    b = J.breakdowns(ts)
    assert [(r["key"], r["n"], r["net"]) for r in b["weekday"]] == [("Monday", 2, 60), ("Wednesday", 1, 60), ("Thursday", 1, -10)]
    assert b["hour"] == [{"key": "09:00", "n": 2, "win_rate": 50.0, "net": 60, "avg": 30, "gross": 60, "charges": 0, "label": "09:00–09:59"}]
    assert {r["key"]: r["net"] for r in b["tag"]} == {"ORB": 60, "Untagged": 50}
    assert {r["key"]: r["n"] for r in b["hold"]} == {"m15": 1, "day": 1, "sameday": 1, "d30": 1}
    assert b["mistake"][0]["key"] == "Exited early" and b["side"][1]["key"] == "Short"
    assert {r["key"] for r in b["instrument"]} == {"X", "TCS"}


def test_r_multiples():
    t = {"net": 300, "entry": 100, "exit": 106, "qty": 50, "side": "long", "note": {"stop": 98, "target": 106}}
    assert J.r_multiple(t) == pytest.approx(3.0)
    assert J.r_multiple({**t, "side": "short", "note": {"stop": 102}}) == pytest.approx(3.0)
    assert J.r_multiple({**t, "note": {"stop": 101}}) is None                      # a stop above a long's entry
    assert J.r_multiple({**t, "side": None}) is None
    d = J.r_distribution([{**t, "r": 3.0}, {**t, "r": -1.0, "exit": 98}, {**t, "r": None}])
    assert d["n"] == 2 and d["of"] == 3 and d["avg"] == 1.0 and d["planned_rr"] == 3.0 and d["hit_target"] == 1
    assert [x["n"] for x in d["buckets"]] == [0, 0, 1, 0, 0, 0, 1]                 # −1R exactly is in "−1R to 0"


# ---------- the verdict's checks on real trades ----------
def test_too_few_trades_says_a_win_rate_could_be_luck():
    nets = [100] * 14 + [-80] * 9                       # 23 trades, 61% winners
    ts = [T(v, f"2026-01-{i + 1:02d}", charges=5) for i, v in enumerate(nets)]
    v = J.verdict(ts)
    luck = next(c for c in v["checks"] if c["id"] == "luck")
    assert "With 23 trades, a 61% win rate could easily be luck" in luck["detail"]
    assert v["verdict"] in ("mixed", "luck") and v["headline"] in ("Mixed evidence.", "Probably luck.")
    small = J.verdict(ts[:10])
    assert small["verdict"] == "not_enough" and small["summary"].startswith("Only 10 closed trades here.")
    assert next(c for c in small["checks"] if c["id"] == "sample")["detail"] == "Too few trades to tell skill from luck."


def test_a_steady_record_passes_and_a_costly_one_fails():
    good = [T(v, f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", charges=2) for i, v in enumerate([120, 90, -40, 150, 80, -30] * 8)]
    v = J.verdict(good, capital=100000)
    assert v["verdict"] == "edge" and v["headline"] == "Likely a real edge." and v["passed"] == 4
    shuffle = next(c for c in v["checks"] if c["id"] == "shuffle")
    assert shuffle["data"]["unit"] == "pct" and "your trades'" in shuffle["detail"] and "backtest" not in shuffle["detail"]
    costly = [T(v - 70, d["exit_t"], gross=v, charges=70) for v, d in zip([120, 90, -40, 150, 80, -30] * 8, good)]
    c = J.verdict(costly)
    assert c["verdict"] == "no_edge"
    thin = [T(v - 40, d["exit_t"], gross=v, charges=40) for v, d in zip([120, 90, -40, 150, 80, -30] * 8, good)]
    costs = next(x for x in J.verdict(thin)["checks"] if x["id"] == "costs")
    assert costs["status"] == "warn" and "With charges doubled, the profit would be gone." in costs["detail"]


def test_luck_check_needs_the_later_half_too():
    nets = [200] * 30 + [-10] * 10
    ts = [T(v, f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}") for i, v in enumerate(nets[::-1][::-1])]
    late_loss = [T(v, x["exit_t"]) for v, x in zip([300] * 20 + [50, -40] * 10, ts)]
    c = J.check_luck([t["net"] for t in late_loss])
    assert c["data"]["earlier"] == 6000 and c["data"]["later"] == 100
    worse = J.check_luck([300] * 20 + [-50] * 20)
    assert worse["status"] == "warn" and "later half of your trades lost money" in worse["detail"]


def test_drawdown_in_rupees_without_capital_and_shuffles_stay_fixed():
    nets = [100, -300, 50, 200, -150, 400, -50, 20]
    a, b = J.check_drawdown(nets, None), J.check_drawdown(nets, None)
    assert a == b and a["data"]["unit"] == "rupees" and a["data"]["yours"] == 300 and "₹" in a["detail"]
    assert J.check_drawdown(nets[:3], None)["status"] == "skip"


def test_big_journal_reshuffles_in_blocks():
    nets = [((i * 37) % 11 - 5) * 10.0 for i in range(6000)]
    assert J.check_drawdown(nets, None)["data"]["runs"] == 1000
    assert J.check_drawdown(nets, 1e6)["data"]["unit"] == "pct"
    assert J.check_luck(nets)["status"] in ("pass", "warn", "fail")


def test_paper_trades_of_each_kind_of_session():
    row = {"state": {"trades": [{"pnl": 50, "entry_t": "2026-01-01T09:15:00", "exit_t": "2026-01-01T10:15:00", "costs": 5},
                                {"pnl": -20, "opened": "2026-01-02T09:20:00+05:30", "closed": "2026-01-03T09:20:00+05:30"}, {"pnl": "x"}],
                     "members": {"a": {"trades": [{"pnl": 10, "entry_t": "2026-01-04", "exit_t": "2026-01-05"}]}}}}
    ts = J.paper_trades(row)
    assert [t["net"] for t in ts] == [50, -20, 10] and ts[0]["hold_s"] == 3600 and ts[1]["hold_days"] == 1
    out = J.compare([T(5, "2026-01-01")], ts)
    assert out["paper"]["n"] == 3 and out["real"]["n"] == 1 and out["paper"]["win_rate"] == pytest.approx(66.7)


# ---------- the API ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    J._paired.clear()
    yield built
    J._paired.clear()
    built["close"]()


def payments_live(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)


def upload(c, path, headers=PRO, name=None, mode="add"):
    r = c.post(f"/trade/journal/import?filename={name or path.name}&mode={mode}", headers={**headers, "Content-Type": "application/octet-stream"},
               content=path.read_bytes())
    assert r.status_code == 200, r.text
    return r.json()


def manual(c, headers=PRO, **kw):
    body = {"symbol": "INFY", "segment": "eq", "side": "long", "entry_date": "2026-03-02", "entry_time": "09:30", "exit_date": "2026-03-02",
            "exit_time": "11:00", "qty": 10, "entry_price": 1500, "exit_price": 1510, **kw}
    return c.post("/trade/journal/trades", headers=headers, json=body)


def test_import_pairs_skips_duplicates_and_shows_the_checks(w):
    c = w["client"]
    got = upload(c, FIX / "taxpnl" / "zerodha_taxpnl_2024_2025.zip")
    assert got["added"] == 16 and got["duplicates"] == 0 and got["broker"] == "Zerodha"
    j = got["journal"]
    assert j["count"] == 15 and j["full"] and j["verdict"]["verdict"] == "mixed" and len(j["verdict"]["checks"]) == 4
    assert j["breakdowns"]["segment"] and j["trades"][0]["exit_t"] >= j["trades"][-1]["exit_t"]          # newest first
    again = upload(c, FIX / "taxpnl" / "zerodha_taxpnl_2024_2025.zip")
    assert again["added"] == 0 and again["duplicates"] == 16 and again["journal"]["count"] == 15
    tb = upload(c, FIX / "tradebooks" / "zerodha_console_tradebook.csv")
    # the tradebook has the INFY intraday and NIFTY option trades the tax P&L has too: counted once, the tradebook's way
    assert tb["added"] == 8 and tb["journal"]["count"] == 15 and tb["journal"]["overlap"] == 4
    assert tb["journal"]["open"][0]["symbol"] == "TCS"
    infy = [t for t in tb["journal"]["trades"] if t["symbol"] == "INFY"]
    assert len(infy) == 1 and infy[0]["src"] == "tradebook" and infy[0]["entry_t"] == "2024-09-02T09:20:00"
    rep = upload(c, FIX / "tradebooks" / "zerodha_console_tradebook.csv", mode="replace")
    assert rep["journal"]["count"] == 3 and len(rep["journal"]["files"]) == 1
    bad = c.post("/trade/journal/import?filename=x.csv", headers={**PRO, "Content-Type": "application/octet-stream"}, content=b"a,b\n1,2\n")
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "bad_file"


def test_json_upload_and_the_tax_report_import(w):
    import base64
    c = w["client"]
    data = base64.b64encode((FIX / "tradebooks" / "upstox_tradebook.csv").read_bytes()).decode()
    r = c.post("/trade/journal/import", headers=PRO, json={"filename": "upstox.csv", "data": data})
    assert r.status_code == 200 and r.json()["journal"]["count"] == 2
    assert c.post("/trade/journal/import-tax", headers=PRO).status_code == 404               # nothing in the tax report yet
    tax_lots.save("u-pro", [{"d": "2025-01-02", "side": "B", "qty": 5, "price": 100, "symbol": "ITC", "src": "trades"},
                            {"d": "2025-02-02", "side": "S", "qty": 5, "price": 110, "symbol": "ITC", "src": "trades"}], [])
    r = c.post("/trade/journal/import-tax", headers=PRO)
    assert r.status_code == 200 and r.json()["added"] == 2 and r.json()["journal"]["count"] == 3


def test_manual_trades_notes_r_and_removal(w):
    c = w["client"]
    r = manual(c)
    assert r.status_code == 200
    t = r.json()["trades"][0]
    assert t["src"] == "manual" and t["gross"] == 100 and t["segment"] == "eq_intraday" and t["charges"] > 0
    assert manual(c, exit_date="2026-03-01").status_code == 400                        # exit before entry
    assert manual(c, entry_time="25:00").status_code == 422
    note = {"tag": "ORB", "notes": "Waited for the range.", "links": ["https://example.com/chart.png"], "emotions": ["Calm", "Nope"],
            "mistakes": ["Exited early"], "stop": 1495, "target": 1520}
    r = c.put(f"/trade/journal/trades/{t['id']}/note", headers=PRO, json=note)
    assert r.status_code == 200
    t2 = r.json()["trades"][0]
    assert t2["note"]["emotions"] == ["Calm"] and t2["note"]["tag"] == "ORB" and t2["r"] == pytest.approx((100 - t["charges"]) / 50, abs=0.01)
    assert r.json()["tags"] == ["ORB"] and r.json()["r"]["n"] == 1 and r.json()["breakdowns"]["tag"][0]["key"] == "ORB"
    assert c.put("/trade/journal/trades/nope/note", headers=PRO, json=note).status_code == 404
    assert c.put(f"/trade/journal/trades/{t['id']}/note", headers=FREE, json=note).status_code == 404     # someone else's
    upload(c, FIX / "tradebooks" / "upstox_tradebook.csv")
    j = c.get("/trade/journal", headers=PRO).json()
    imported = next(x for x in j["trades"] if x["src"] == "tradebook")
    j = c.delete(f"/trade/journal/trades/{imported['id']}", headers=PRO).json()
    assert j["count"] == 2 and j["removed"] == 1
    j = c.post("/trade/journal/restore", headers=PRO).json()
    assert j["count"] == 3 and j["removed"] == 0
    j = c.delete(f"/trade/journal/trades/{t['id']}", headers=PRO).json()
    assert j["count"] == 2 and all(x["src"] != "manual" for x in j["trades"])


def test_side_set_on_a_pnl_line_flips_its_entry(w):
    c = w["client"]
    j = upload(c, FIX / "taxpnl" / "zerodha_taxpnl_2024_2025.zip")["journal"]
    fut = next(t for t in j["trades"] if t["symbol"] == "BANKNIFTY24OCTFUT")
    assert fut["side"] is None and fut["entry"] == 52000
    j = c.put(f"/trade/journal/trades/{fut['id']}/note", headers=PRO, json={"side": "short", "stop": 52100}).json()
    fut = next(t for t in j["trades"] if t["symbol"] == "BANKNIFTY24OCTFUT")
    assert fut["side"] == "short" and fut["entry"] == pytest.approx(777500 / 15) and fut["exit"] == 52000 and fut["r"] is not None


def test_settings_change_charges_and_the_drawdown_unit(w):
    c = w["client"]
    manual(c)
    before = c.get("/trade/journal", headers=PRO).json()["trades"][0]["charges"]
    r = c.put("/trade/journal/settings", headers=PRO, json={"capital": 500000, "brokerage_delivery": 0, "brokerage_other": 0})
    assert r.status_code == 200 and r.json()["settings"]["capital"] == 500000
    assert r.json()["trades"][0]["charges"] == pytest.approx(before - 2 * 20 * 1.18, abs=0.01)
    assert c.put("/trade/journal/settings", headers=PRO, json={"capital": -5}).status_code == 422


def test_paper_vs_real(w):
    c = w["client"]
    for p in (1500, 1490, 1520):
        manual(c, exit_price=p)
    j = c.get("/trade/journal", headers=PRO).json()
    for t in j["trades"]:
        c.put(f"/trade/journal/trades/{t['id']}/note", headers=PRO, json={"tag": "Breakout"})
    row = db.sb().table("live_sessions").insert({"user_id": "u-pro", "name": "Breakout", "strategy": {}, "instrument": {"symbol": "INFY"},
                                                  "status": "stopped", "state": {"trades": [{"pnl": 40, "entry_t": "2026-01-01T09:15:00",
                                                                                              "exit_t": "2026-01-01T09:45:00"}]}}).execute().data[0]
    j = c.get("/trade/journal", headers=PRO).json()
    assert any(p["id"] == row["id"] and p["name"] == "Breakout" for p in j["paper"])
    r = c.get(f"/trade/journal/compare?tag=breakout&session={row['id']}", headers=PRO)
    assert r.status_code == 200, r.text
    assert r.json()["real"]["n"] == 3 and r.json()["paper"]["n"] == 1 and r.json()["paper"]["net"] == 40
    assert c.put("/trade/journal/links", headers=PRO, json={"tag": "Breakout", "session": row["id"]}).json()["links"] == {"Breakout": row["id"]}
    assert c.get(f"/trade/journal/compare?tag=x&session={row['id']}", headers=BASIC).status_code == 404     # not theirs
    assert c.put("/trade/journal/links", headers=PRO, json={"tag": "Breakout", "session": None}).json()["links"] == {}


def test_free_keeps_fifty_trades_and_basic_stats_once_payments_are_live(w, monkeypatch):
    payments_live(monkeypatch)
    c = w["client"]
    assert plans.journal_limit("free") == 50 and plans.journal_limit("basic") is None and plans.allows("basic", "journal")
    assert not plans.allows("free", "journal")
    j = journal_routes.J
    data = j.load("u-free")
    data["manual"] = [{"id": f"m{i}", "sym": "INFY", "side": "long", "ed": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "et": "",
                       "xd": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "xt": "", "qty": 1, "entry": 100, "exit": 101 + i % 3} for i in range(60)]
    j.save("u-free", data)
    v = c.get("/trade/journal", headers=FREE).json()
    assert v["count"] == 50 and v["total"] == 60 and v["beyond_limit"] == 10 and v["limit"] == 50
    assert v["summary"]["n"] == 50 and v["verdict"] is None and v["breakdowns"] is None and v["r"] is None and v["paper"] == []
    assert v["trades"][-1]["id"] == "m10"                                        # the latest 50
    r = manual(c, FREE)
    assert r.status_code == 402 and "50 trades" in r.json()["detail"]["message"] and "Basic" in r.json()["detail"]["message"]
    assert c.get("/trade/journal/compare?tag=a&session=00000000-0000-0000-0000-000000000000", headers=FREE).status_code == 402
    assert c.put("/trade/journal/links", headers=FREE, json={"tag": "a"}).status_code == 402
    b = c.get("/trade/journal", headers=BASIC).json()
    assert b["full"] and b["limit"] is None


def test_journal_is_private_and_deleted_in_one_step(w):
    c = w["client"]
    upload(c, FIX / "tradebooks" / "upstox_tradebook.csv")
    assert c.get("/trade/journal").status_code == 401
    assert c.get("/trade/journal", headers=FREE).json()["count"] == 0
    c.delete("/trade/journal", headers=FREE)
    assert c.get("/trade/journal", headers=PRO).json()["count"] == 2
    assert db.get_setting("journal:u-pro")
    assert c.delete("/trade/journal", headers=PRO).json() == {"deleted": True}
    assert db.get_setting("journal:u-pro") is None and c.get("/trade/journal", headers=PRO).json()["count"] == 0


def test_damaged_rows_never_break_the_page(w):
    c = w["client"]
    db.set_setting("journal:u-pro", '{"fills": [{"side": "B"}, 5, {"d": "x", "side": "S", "qty": 1, "price": 1, "symbol": "A"}],'
                                    '"lines": [{"sym": "A"}], "manual": [null], "notes": {"a": 5, "b": {"stop": "x", "emotions": ["Calm"]}},'
                                    '"settings": {"capital": "lots"}, "links": [1], "hidden": "x"}')
    v = c.get("/trade/journal", headers=PRO)
    assert v.status_code == 200 and v.json()["count"] == 0 and v.json()["settings"]["capital"] is None
    db.set_setting("journal:u-pro", "not json")
    assert c.get("/trade/journal", headers=PRO).status_code == 200


def test_upload_size_cap(w):
    c = w["client"]
    big = b"a" * (J.hf.FNO_MAX_BYTES + 10)
    r = c.post("/trade/journal/import?filename=big.csv", headers={**PRO, "Content-Type": "application/octet-stream"}, content=big)
    assert r.status_code == 413
