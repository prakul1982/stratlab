"""fix11 (17 Nov 2026): open LIVE10A / LIVE10B / CX2 findings. Each test fails before its fix and passes after."""
from app import main  # noqa: F401, I001
from app.engine import costs as C


# ---------- LIVE10A-033: the backtest's tax estimate carries a year's loss on, and its note says so ----------
def test_tax_estimate_sets_a_years_loss_off_against_later_gains_and_says_so():
    t = lambda a, b, p: {"pnl": p, "qty": 0, "entry": 0, "exit": 0, "entry_t": a, "exit_t": b}  # noqa: E731
    trades = [t("2022-05-02", "2022-06-01", 23_300), t("2023-05-02", "2023-06-01", 18_200),
              t("2024-05-02", "2024-06-03", -2_000), t("2025-05-02", "2025-06-02", -1_500),
              t("2026-05-04", "2026-06-01", 2_900)]                         # FY27's +2,900 is absorbed by FY25/FY26's −3,500
    got = C.tax_estimate("in_eq", trades)
    assert got["amount"] == round(0.2 * (23_300 + 18_200), 2)
    assert "net loss is set off against the next years' gains" in got["note"]
    assert "Losses and your other income can change it" not in got["note"]


# ---------- LIVE10A-035 / CX2 #2: a loss is never "and returned more than buy and hold" ----------
def test_a_loss_smaller_than_buy_and_holds_leads_with_the_loss_and_says_both_returns():
    from app import library
    from app.engine import verdict as V
    e = {"verdict": {"verdict": "no_edge", "headline": "No edge here."}, "stats": {"ret": -4.1, "buy_hold": -7.3, "trades": 30}}
    head = library.restated(e)["fact_headline"]
    assert "returned more than buy and hold" not in head
    assert head.startswith("Lost money after costs (−4.1%); buying and holding lost more (−7.3%)")
    assert V.fact_headline("no_edge", [], 30, -4.1, -7.3) == "Lost money after costs (−4.1%); buying and holding lost more (−7.3%)."
    assert V.fact_headline("no_edge", [], 30, -4.1, -4.5) == "Lost money after costs (−4.1%), within a point of buying and holding (−4.5%)."
    # behind buy and hold the shortfall still leads (R6V-005)
    assert V.fact_headline("no_edge", [], 30, -4.1, 20.0) == "24.1 points behind buy and hold; lost money after costs."


# ---------- LIVE10A-036: the briefs list reads its issues in one database call ----------
def test_the_briefs_list_reads_its_issues_in_one_call(monkeypatch):
    import json
    from app import db
    from app.newsletter import job
    store = {"news-index:market:US": json.dumps(["market.US.2026-11-16", "market.US.2026-11-13"]),
             "news:market:US:2026-11-16": json.dumps({"id": "market.US.2026-11-16", "kind": "my_stocks", "day": "2026-11-16"}),
             "news:market:US:2026-11-13": json.dumps({"id": "market.US.2026-11-13", "kind": "my_stocks", "day": "2026-11-13"})}
    asked = []
    monkeypatch.setattr(db, "get_setting", store.get)
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: asked.append(list(keys)))
    got = job.recent("market", "US", 20)
    assert [i["id"] for i in got] == ["market.US.2026-11-16", "market.US.2026-11-13"]
    assert asked == [["news:market:US:2026-11-16", "news:market:US:2026-11-13"]]
