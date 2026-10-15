"""Review 12A: EPF passbook updates, MF NAV dates in net worth, Kite priority, the monthly snapshot, IBKR left-outs, rounding."""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest
import time_machine

from app import db, holdings, holdings_file, main, money_mf
from app import money_networth as nw
from app.connect import docs, ibkr, kite_user, state, sync
from tests import world

PRO = world.headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    from tests import fake_prices
    day = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(fake_prices, "FROZEN", day)
    with time_machine.travel(day, tick=True):
        built = world.build(monkeypatch)
        main._nw_prices.clear()
        yield built
        built["close"]()


def test_epf_update_keeps_the_users_edits_and_skips_an_older_passbook(w):
    p = main.connect_sync.profile_for("u-pro")
    docs.confirm(p, "epf", {"balance": "500000", "as_of": "2026-03-31"})
    iid = nw.load("u-pro")["items"][0]["id"]
    r = w["client"].put(f"/money/net-worth/items/{iid}", headers=PRO,
                        json={"kind": "epf", "name": "My EPF", "balance": 500000, "monthly": 8000, "rate": 8.1, "as_of": "2026-03-31"})
    assert r.status_code == 200
    docs.confirm(p, "epf", {"balance": "560000", "as_of": "2026-08-31"})
    e = nw.load("u-pro")["items"][0]
    assert (e["name"], e["monthly"], e["rate"], e["balance"], e["as_of"]) == ("My EPF", 8000, 8.1, 560000, "2026-08-31")
    out = docs.confirm(p, "epf", {"balance": "400000", "as_of": "2025-03-31"})
    e = nw.load("u-pro")["items"][0]
    assert (e["balance"], e["as_of"]) == (560000, "2026-08-31")
    assert "newer" in out["detail"]


def test_net_worth_mf_carries_the_nav_date_and_flags_a_statement_nav(w):
    k = "f1"
    money_mf.save("u-pro", {"schemes": [{"k": k, "name": "Zzz Unknown Fund", "amc": "", "folio": "1", "isin": "", "amfi": "", "hint": "",
                                         "stmt_nav": 100.0, "stmt_date": "2025-01-31"}],
                            "txns": [{"k": k, "d": "2024-06-01", "t": "purchase", "u": 10.0, "a": 900.0, "n": 90.0}],
                            "files": [], "kinds": {}, "fmv": {}})
    v = w["client"].get("/money/net-worth", headers=PRO).json()
    row = next(r for r in v["assets"] if r["id"] == "mf")
    assert row["as_of"] == "2025-01-31"
    assert "statement's NAV" in row["rule"]
    assert any("statement" in n for n in v["totals"]["notes"])
    assert v["totals"]["oldest_as_of"] == "2025-01-31"


KITE = [{"symbol": "INFY", "exchange": "NSE", "qty": 10.0, "avg": 1400.0, "via": "kite", "since": "2026-08-01"}]
CAS = [{"symbol": "INFY", "exchange": "NSE", "qty": 4.0, "avg": None, "accts": {"CDSL:abc": 4.0}}]


def test_statement_dated_after_the_last_kite_read_wins():
    items, c = sync.merge_sync(KITE, CAS, "cas", True, {"CDSL:abc"}, "2026-09-10", {"kite": "2026-09-01"})
    assert (items[0]["qty"], items[0]["via"], c["skipped"]) == (4.0, "cas", 0)


def test_statement_not_after_the_last_kite_read_is_skipped_and_counted():
    items, c = sync.merge_sync(KITE, CAS, "cas", True, {"CDSL:abc"}, "2026-09-01", {"kite": "2026-09-01"})
    assert (items[0]["qty"], items[0]["via"], c["skipped"]) == (10.0, "kite", 1)


def test_kite_disconnect_drops_the_via_tag(w):
    holdings.save("u-pro", [dict(KITE[0], name="Infosys")], "Zerodha Kite")
    state.update("u-pro", "kite", refreshed_at="2026-09-01T10:00:00+00:00")
    kite_user.disconnect("u-pro")
    got = holdings.load("u-pro")["items"]
    assert got[0]["qty"] == 10.0 and "via" not in got[0]


def test_monthly_job_covers_a_user_with_only_holdings(w):
    holdings.save("u-pro", [{"symbol": "RELIANCE", "exchange": "NSE", "name": "Reliance", "qty": 10.0, "avg": 2400.0}], "Statement")
    assert db.get_setting("networth:u-pro") is None
    n = main.networth_job.tick(datetime(2026, 11, 1, 11, 0, tzinfo=timezone.utc))
    assert n >= 1
    assert nw.history("u-pro")


def test_monthly_job_dates_a_weekend_first_by_the_last_close(w):
    sat = datetime(2026, 11, 1, 11, 0, tzinfo=timezone.utc)      # a Sunday
    seen = {}
    job = nw.Job(lambda uid: {"assets": [1], "liabilities": [], "as_of": "2026-10-30", "totals": {"net": 1}})
    orig = nw.record
    nw.record = lambda uid, totals, why, d: seen.setdefault("d", d)
    try:
        holdings.save("u-pro", [{"symbol": "RELIANCE", "exchange": "NSE", "name": "Reliance", "qty": 1.0, "avg": 1.0}], "Statement")
        job.tick(sat)
    finally:
        nw.record = orig
    assert str(seen["d"]) == "2026-10-30"


def _stmt(pos):
    return ET.fromstring("<FlexQueryResponse><FlexStatements><FlexStatement><OpenPositions>%s</OpenPositions></FlexStatement></FlexStatements></FlexQueryResponse>" % pos)


def test_ibkr_left_out_positions_make_a_partial_note(w):
    ibkr.ingest("u-pro", _stmt('<OpenPosition assetCategory="STK" currency="USD" symbol="AAPL" position="10" costBasisPrice="150" levelOfDetail="SUMMARY"/>'
                               '<OpenPosition assetCategory="STK" currency="EUR" symbol="SAP" position="5" costBasisPrice="100" levelOfDetail="SUMMARY"/>'))
    st = ibkr.status("u-pro")
    assert st["status"] == "partial"
    assert "1 position in another currency or asset type isn't counted" in st["detail"]


def test_holdings_weights_and_sectors_add_to_100():
    items = [{"symbol": s, "qty": 1, "avg": 100.0, "exchange": "NSE", "sector": sec} for s, sec in zip("ABC", ["Energy", "Healthcare", "Realty"])]
    q = {s: {"price": 100.0, "change": 1.0, "change_pct": 1.0, "at": "2026-10-15T10:00:00+05:30"} for s in "ABC"}
    v = holdings.view(items, q)
    assert round(sum(r["weight"] for r in v["rows"]), 1) == 100.0
    assert round(sum(a["pct"] for a in v["allocation"]), 1) == 100.0


def test_net_total_row_is_a_totals_row():
    got = holdings_file.parse(b"Symbol,Quantity,Average Price\nINFY,10,1400\nNet Total,15,1000\n", "x.csv")
    assert [r["symbol"] for r in got["rows"]] == ["INFY"]
    assert not got["problems"]


def test_gold_price_is_stamped_with_the_last_close_when_the_exchange_is_shut():
    sat = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)
    assert main._gold_read_at(sat).startswith("2026-10-16T23:")
    mon = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)       # 13:30 India time, the exchange trading
    assert main._gold_read_at(mon) == "2026-10-05T08:00+00:00"
