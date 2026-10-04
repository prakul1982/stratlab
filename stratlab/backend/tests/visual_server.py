"""The app on the fake world, for the browser tests in stratlab/frontend/e2e: every source faked, plus a company with
loss years (TCS stands in for one, as only listed symbols open) so the charts' handling of losses can be checked.

    python -m tests.visual_server            # serves on 127.0.0.1:8765
"""
import base64
import copy
import os
import sys
from pathlib import Path

import pytest
import uvicorn

sys.path.insert(0, ".")
_web = os.environ.get("E2E_WEB_PORT", "5599")
os.environ.setdefault("FRONTEND_ORIGIN", f"http://127.0.0.1:{_web},http://localhost:{_web}")   # the browser tests' page
from app import main  # noqa: E402
from tests import world  # noqa: E402

PORT = int(os.environ.get("E2E_API_PORT", "8765"))     # another port lets two test runs share a machine
LOSS = "TCS"


def loss_company(p: dict) -> dict:
    """RELIANCE's page with SML-like numbers: losses for three years, then profits."""
    p = copy.deepcopy(p)
    pl = p["pl"]
    n = len(pl["cols"])
    shape = [-21.3, -133.4, -100.2, 20.05, 108.6, 122.4, 160.3]
    pl["rows"]["Net Profit"] = ([None] * max(0, n - len(shape)) + shape)[-n:]
    p["name"] = "Loss Company Ltd"
    return p


def build():
    mp = pytest.MonkeyPatch()
    w = world.build(mp)
    from app import guard
    for limit in ("PER_MINUTE_USER", "PER_MINUTE_ANON", "PER_MINUTE_ADDRESS"):   # the sweep opens hundreds of pages a minute as one user
        mp.setattr(guard, limit, 100_000)
    scr = main.research_hub.screener
    real = scr.company
    mp.setattr(scr, "company", lambda sym: loss_company(real("RELIANCE")) if sym.upper() == LOSS else real(sym))
    from datetime import datetime, timezone
    from app import db
    # brand-new accounts, for the first-steps checklist on Home (u-load-201 and 204: the new-user walkthrough's own)
    for uid in ("u-free", "u-basic", "u-load-201", "u-load-204"):
        db.update_profile(uid, created_at=datetime.now(timezone.utc).isoformat())
    # the owner's holdings, imported from a Zerodha Console file, for the My Holdings page
    sample = Path(__file__).parent / "fixtures" / "holdings" / "zerodha_console_holdings.xlsx"
    w["client"].post("/holdings/import", headers=world.headers("admin-token"),
                     json={"filename": sample.name, "data": base64.b64encode(sample.read_bytes()).decode()})
    invite_rewards()
    main.corp_job.refresh("IN")             # the corporate-actions calendar, as the morning job would have built it
    screen_index()
    # keep that index: the background job would rebuild it from stored pages a few minutes in, mid-run
    mp.setattr(main.screen_indexer, "loop", lambda: None)
    return w


def invite_rewards():
    """The owner invited friends: one became active (a free month each), and a link with too many sign-ups in a day
    left two rewards waiting for review in Admin (one for the desktop run to reject, one for the phone run to
    approve)."""
    import json
    from app import db, plans
    joined = [{"id": f"u-load-{i}", "at": "2026-10-01T10:00:00+00:00"} for i in range(1, 4)]
    db.set_setting("ref:joined:u-admin", json.dumps(joined))
    given = {"by": "u-admin", "at": "2026-10-01T10:00:00+00:00", "status": "given", "signups_that_day": 3,
             "referrer_months": 1, "newcomer_months": 1, "given_at": "2026-10-03T10:00:00+00:00"}
    db.set_setting("reward:u-load-3", json.dumps(given))
    for i in (1, 2):
        db.set_setting(f"reward:u-load-{i}", json.dumps({**given, "status": "review", "signups_that_day": 6,
                                                        "referrer_months": 0, "newcomer_months": 0, "given_at": None}))
    plans.add_free_basic(db.get_profile("u-load-3"), 30)


def screen_index():
    """The stock screens' index, as the background job would gather it from stored company pages (written straight to
    the index, so the public company pages still build from the fake sources)."""
    import json
    import random
    from datetime import date, timedelta
    from app import db, screens
    rng = random.Random(5)
    sectors = ["Energy", "Information Technology", "Financials", "Consumer Staples", "Materials"]
    names = {"IN": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "ONGC", "ITC", "HINDUNILVR", "TATASTEEL", "JSWSTEEL",
                    "WIPRO", "HCLTECH", "NTPC", "COALINDIA", "SBIN", "AXISBANK", "NESTLEIND", "DABUR", "VEDL", "SAIL"],
             "US": ["AAPL", "MSFT", "XOM", "JPM", "KO", "NUE"]}
    for region, syms in names.items():
        rows = []
        for i, sym in enumerate(syms):
            price = round(rng.uniform(50, 3000), 2)
            f = {"region": region, "symbol": sym, "name": f"{sym.title()} {'Ltd' if region == 'IN' else 'Inc.'}",
                 "industry": [sectors[i % len(sectors)]], "price": price, "high52": round(price * rng.uniform(1, 1.6), 2),
                 "low52": round(price * 0.7, 2), "price_at": "2026-10-01", "market_cap": round(rng.uniform(200, 900000)),
                 "pe": None if i % 7 == 3 else round(rng.uniform(6, 60), 1), "roe": round(rng.uniform(-5, 35), 1),
                 "roce": round(rng.uniform(0, 40), 1), "div_yield": round(rng.uniform(0, 4), 2), "net_margin": round(rng.uniform(-5, 30), 1),
                 "opm": round(rng.uniform(5, 40), 1), "debt_equity": round(rng.uniform(0, 2), 2), "bank": False,
                 "growth": {"sales_cagr_3y": round(rng.uniform(-10, 30), 1)}, "stage": 1 + i % 4,
                 "red_flags": (i % 5 == 0) * 2 if region == "IN" else None, "filings": [], "built_at": "2026-10-01T12:00:00+00:00"}
            r = screens.row(region, sym, f)
            if region == "IN":          # a promoter or insider bought on the open market: 10 days ago for every fourth
                r["insider_buy_at"] = (date.today() - timedelta(days=10 if i % 4 == 1 else 200)).isoformat() if i % 2 else None
            rows.append(r)
        rows.sort(key=lambda r: r["name"].lower())
        db.set_setting(screens.INDEX_KEY + region, json.dumps({"region": region, "at": "2026-10-01T18:00:00+00:00", "rows": rows}))


if __name__ == "__main__":
    build()
    uvicorn.run(main.app, host="127.0.0.1", port=PORT, log_level="warning")
