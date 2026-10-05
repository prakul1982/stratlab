"""The whole app wired to fakes: an in-memory database with signed-in users, fake market data for every market,
fake company, news, exchange and document sources, and a fake AI whose answers can be good, malformed or failing.
Real network calls are refused, so anything not faked behaves like a source that is down. Used by the stress tests."""
import json
import random
import sys

import httpx
from fastapi.testclient import TestClient

from app import ai_providers, db, main
from app.config import settings
from app.data import Registry
from app.data.coinbase import CoinbaseProvider
from app.intel import routes
from app.intel.company import Research
from app.intel.filings import NSEFilings
from app.intel.finnhub import Finnhub
from app.intel.news import GoogleNews, Wikipedia
from app.intel.screener import Screener
from app.intel.yahoo import Yahoo
from app.kite_service import TickHub
from app.live import LiveManager
from app.options.data import OptionsData
from app.options.session import IST
from datetime import date, datetime, timedelta
from tests import fake_cas, fake_fo_changes, fake_kite, fake_positioning
from tests.fake_options_kite import FakeOptionsKite
from tests.fake_db import FakeSupabase, headers
from tests.fake_intel import fake_finnhub, fake_news, fake_screener, fake_wiki
from tests.fake_yahoo import fake_yahoo
from tests.pdfmaker import make_pdf
from tests.test_notebooks import wavy_coinbase

AI_SHAPES = [
    lambda: {"summary": "A company.", "segments": [], "capex": [], "outlook": [], "guidance": [], "measures": []},
    lambda: {"name": "Idea", "tf": "1d", "entry": [], "exit": [], "risk": {}},
    lambda: {},
    lambda: [],
    lambda: {"summary": None, "segments": "not a list", "capex": [{"what": None}], "guidance": [{"metric": 5, "low": "x"}]},
    lambda: {"scores": {"moat": "high"}, "composite": "NaN", "ideas": [None, 3, {"text": 7}]},
]


class FakeAI:
    """mode: "ok" (shapes in turn), "garbage" (not JSON), "fail" (provider error), "busy" (all providers busy)."""

    def __init__(self):
        self.mode, self.i, self.calls = "ok", 0, 0

    def __call__(self, system, text, **kw):
        self.calls += 1
        if self.mode == "fail":
            raise ai_providers.AIError("The AI couldn't answer.")
        if self.mode == "busy":
            raise ai_providers.AIBusy("Every AI provider is busy.")
        if self.mode == "garbage":
            return "Sure! Here is the answer: {not json"
        self.i += 1
        return json.dumps(AI_SHAPES[self.i % len(AI_SHAPES)]())


class Switch(httpx.BaseTransport):
    """A fake source's transport with a fault switch: "down", "timeout", "500", "429", "403", "garbage" (a page
    instead of data), "empty" (valid but empty data) or None (normal)."""

    def __init__(self, inner: httpx.BaseTransport):
        self.inner, self.mode = inner, None

    def handle_request(self, request):
        m = self.mode
        if m == "down":
            raise httpx.ConnectError("connection refused", request=request)
        if m == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if m in ("500", "429", "403"):
            return httpx.Response(int(m), text="error", request=request)
        if m == "garbage":
            return httpx.Response(200, text="<html><body>Access denied. Please verify you are human.</body></html>",
                                  headers={"content-type": "text/html"}, request=request)
        if m == "empty":
            return httpx.Response(200, json={}, request=request)
        return self.inner.handle_request(request)


def board_meetings(today=None) -> list[dict]:
    """The exchange's board-meeting list, relative to today: RELIANCE's results in two days, TCS's next week, and an
    INFY meeting about a dividend (not results)."""
    t = today or date.today()
    f = lambda d: (t + timedelta(days=d)).strftime("%d-%b-%Y")
    return [{"bm_symbol": "RELIANCE", "sm_name": "Reliance Industries Limited", "bm_date": f(2), "bm_purpose": "Financial Results",
             "bm_desc": "To consider and approve the financial results for the quarter ended September 30, 2026",
             "attachment": "https://nsearchives.nseindia.com/bm.pdf"},
            {"bm_symbol": "TCS", "sm_name": "Tata Consultancy Services Limited", "bm_date": f(9), "bm_purpose": "Financial Results/Dividend",
             "bm_desc": "Financial results and interim dividend"},
            {"bm_symbol": "INFY", "sm_name": "Infosys Limited", "bm_date": f(3), "bm_purpose": "Dividend", "bm_desc": "Interim dividend"}]


def corporate_actions(today=None) -> list[dict]:
    """The exchange's corporate-actions list, relative to today: a TCS bonus going ex today and its dividend in three
    days, a RELIANCE dividend, an INFY split, an ITC buyback just gone, an AGM (not an action), and past dividends."""
    t = today or datetime.now(IST).date()
    f = lambda d: (t + timedelta(days=d)).strftime("%d-%b-%Y")
    rows = [("TCS", "Tata Consultancy Services Limited", "Bonus 1:1", 0), ("TCS", "Tata Consultancy Services Limited", "Interim Dividend - Rs 11 Per Share", 3),
            ("RELIANCE", "Reliance Industries Limited", "Dividend - Rs 5.50 Per Share", 5),
            ("INFY", "Infosys Limited", "Face Value Split (Sub-Division) - From Rs 5/- Per Share To Re 1/- Per Share", 12),
            ("ITC", "ITC Limited", "Buy Back", -3), ("HDFCBANK", "HDFC Bank Limited", "Annual General Meeting", 4),
            ("TCS", "Tata Consultancy Services Limited", "Final Dividend - Rs - 30.0000", -100),
            ("TCS", "Tata Consultancy Services Limited", "Interim Dividend - Rs 10 Per Share", -200),
            ("TCS", "Tata Consultancy Services Limited", "Special Dividend - Rs 66 Per Share", -400),
            ("RELIANCE", "Reliance Industries Limited", "Dividend - Rs 10 Per Share", -60),
            ("HDFCBANK", "HDFC Bank Limited", "Dividend - Rs 22 Per Share", -120)]
    return [{"symbol": s, "series": "EQ", "comp": n, "subject": sub, "exDate": f(d), "recDate": f(d), "faceVal": "1",
             "bcStartDate": "-", "bcEndDate": "-", "isin": "-"} for s, n, sub, d in rows]


# real ISINs for the fake exchange's list, so broker files that carry only an ISIN and a name can be matched
ISINS = [("TCS", "Tata Consultancy Services Limited", "INE467B01029"), ("INFY", "Infosys Limited", "INE009A01021"),
         ("HDFCBANK", "HDFC Bank Limited", "INE040A01034"), ("ITC", "ITC Limited", "INE154A01025"),
         ("SBIN", "State Bank of India", "INE062A01020"), ("TATASTEEL", "Tata Steel Limited", "INE081A01020"),
         ("ICICIBANK", "ICICI Bank Limited", "INE090A01021"), ("BHARTIARTL", "Bharti Airtel Limited", "INE397D01024"),
         ("LT", "Larsen & Toubro Limited", "INE018A01030"), ("ASIANPAINT", "Asian Paints Limited", "INE021A01026")]


def deal_rows(today=None) -> dict:
    """The exchange's disclosures for RELIANCE, relative to today: a promoter's open-market purchase, a director's sale,
    a pledge, stock options (not a decision to buy), a substantial acquisition, and a bulk and a block deal."""
    t = today or date.today()
    f = lambda d, fmt="%d-%b-%Y": (t - timedelta(days=d)).strftime(fmt)        # noqa: E731
    pit = [{"symbol": "RELIANCE", "acqName": "Mukesh Shah Family Trust", "personCategory": "Promoter Group", "secType": "Equity Shares",
            "secAcq": "25,000", "secVal": "72500000", "tdpTransactionType": "Buy", "acqMode": "Market Purchase",
            "acqfromDt": f(20), "acqtoDt": f(20), "date": f(18, "%d-%b-%Y 19:30"), "afterAcqSharesPer": "50.12",
            "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/PIT_1.xml"},
           {"symbol": "RELIANCE", "acqName": "Asha Rao", "personCategory": "Director", "secType": "Equity Shares", "secAcq": "4000",
            "secVal": "11600000", "tdpTransactionType": "Sell", "acqMode": "Market Sale", "acqtoDt": f(40), "date": f(38, "%d-%b-%Y 18:00")},
           {"symbol": "RELIANCE", "acqName": "Mukesh Shah Family Trust", "personCategory": "Promoter Group", "secType": "Equity Shares",
            "secAcq": "100000", "tdpTransactionType": "Pledge Creation", "acqMode": "Pledge Creation", "acqtoDt": f(60), "date": f(58)},
           {"symbol": "RELIANCE", "acqName": "Ravi Kumar", "personCategory": "Employees/Designated Employees", "secType": "Equity Shares",
            "secAcq": "500", "secVal": "-", "tdpTransactionType": "Buy", "acqMode": "ESOP", "acqtoDt": f(10), "date": f(9)},
           {"symbol": "RELIANCE", "acqName": "Someone", "personCategory": "Director", "secType": "Warrants", "secAcq": "10",
            "tdpTransactionType": "Buy", "acqMode": "Market Purchase", "acqtoDt": f(5)}]
    sast = [{"symbol": "RELIANCE", "acquirerName": "Long Horizon Fund", "acqSaleType": "Acquisition", "noOfShareAcq": "1500000",
             "acquisitionMode": "Market Purchase", "acqToDate": f(30), "timestamp": f(29, "%d-%b-%Y %H:%M"), "totAftShareAcqPer": "5.02"}]
    bulk = [{"BD_DT_DATE": f(15), "BD_SYMBOL": "RELIANCE", "BD_SCRIP_NAME": "Reliance Industries Ltd", "BD_CLIENT_NAME": "Index Fund One",
             "BD_BUY_SELL": "BUY", "BD_QTY_TRD": 800000, "BD_TP_WATP": 2901.5, "BD_REMARKS": "-"}]
    block = [{"BD_DT_DATE": f(3), "BD_SYMBOL": "RELIANCE", "BD_CLIENT_NAME": "Pension Plan Two", "BD_BUY_SELL": "SELL",
              "BD_QTY_TRD": 120000, "BD_TP_WATP": 2895}]
    return {"pit": pit, "sast": sast, "bulk_deals": bulk, "block_deals": block}


def _deals_answer(r: httpx.Request):
    """The exchange's deal feeds: one company's rows when a symbol is asked for, else the whole market's."""
    rows = deal_rows()
    key = {"/api/corporates-pit": "pit", "/api/corporate-sast-reg29": "sast"}.get(r.url.path) or r.url.params.get("optionType", "")
    got = rows.get(key, [])
    sym = r.url.params.get("symbol")
    if sym:
        got = [x for x in got if (x.get("symbol") or x.get("BD_SYMBOL")) == sym]
    return httpx.Response(200, json={"data": got})


def surveillance_answers(today=None) -> dict:
    """The exchange's surveillance lists as it publishes them: RELIANCE on long-term ASM Stage II, TATASTEEL on
    short-term ASM Stage I, ITC on GSM Stage II and trade-to-trade (BE series, 5% band), INFY in the F&O ban."""
    t = today or date.today()
    asm = {"longterm": {"data": [{"symbol": "RELIANCE", "companyName": "Reliance Industries Limited", "isin": "INE002A01018",
                                  "asmSurvIndicator": "LTASM Stage II"}]},
           "shortterm": {"data": [{"symbol": "TATASTEEL", "companyName": "Tata Steel Limited", "asmSurvIndicator": "Stage I"}]}}
    gsm = {"data": [{"symbol": "ITC", "companyName": "ITC Limited", "gsmStage": "II"}]}
    ban = f"Securities in Ban For Trade Date {t.strftime('%d-%b-%Y').upper()}:\n1,INFY\n"
    sec = ["Symbol,Series,Security Name,Band,Remarks"] + [f"CO{i},EQ,Company {i} Limited,20," for i in range(400)]
    sec += ["RELIANCE,EQ,Reliance Industries Limited,No Band,", "INFY,EQ,Infosys Limited,20,", "TCS,EQ,Tata Consultancy,No Band,",
            "ITC,BE,ITC Limited,5,", "TATASTEEL,EQ,Tata Steel Limited,10,", "GOVTBOND,GS,Some Bond,No Band,"]
    return {"/api/reportASM": asm, "/api/reportGSM": gsm, "/api/reportESM": {"data": []},
            "/content/fo/fo_secban.csv": ban, "/content/equities/sec_list.csv": "\n".join(sec)}


def _nse(sw=None):
    rows = [{"symbol": "RELIANCE", "desc": "Investor Presentation", "attchmntText": "Investor presentation for Q1 FY27",
             "sort_date": "2026-08-01 18:10:05", "seq_id": "1", "attchmntFile": "https://nsearchives.nseindia.com/p.pdf"},
            {"symbol": "RELIANCE", "desc": "Analysts/Institutional Investor Meet/Con. Call Updates",
             "attchmntText": "Transcript of the earnings call", "sort_date": "2026-08-05 18:10:05", "seq_id": "2",
             "attchmntFile": "https://nsearchives.nseindia.com/t.pdf"},
            {"symbol": "RELIANCE", "desc": "Qualified Institutions Placement", "attchmntText": "QIP opened",
             "sort_date": (date.today() - timedelta(days=13)).strftime("%Y-%m-%d 18:10:05"),     # recent whenever the tests run
             "seq_id": "3", "attchmntFile": "https://nsearchives.nseindia.com/q.pdf"}]

    def handler(r: httpx.Request):
        if r.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        if r.url.path == "/api/corporate-announcements":
            return httpx.Response(200, json=rows)
        if r.url.path in ("/api/corporates-pit", "/api/corporate-sast-reg29", "/api/historicalOR/bulk-block-short-deals"):
            return _deals_answer(r)
        surv = surveillance_answers().get(r.url.path)
        if surv is not None:
            return httpx.Response(200, text=surv) if isinstance(surv, str) else httpx.Response(200, json=surv)
        cas = fake_cas.answer(r.url.path, r.url.params)
        if cas is not None:            # the closing auction, just ended
            return httpx.Response(200, json=cas)
        fo = fake_fo_changes.answer(r.url.path)
        if fo is not None:             # the F&O contract file and the circulars
            return httpx.Response(200, text=fo) if isinstance(fo, str) else httpx.Response(200, json=fo)
        pos = fake_positioning.answer(r.url.path)
        if pos is not None:            # the participant-wise files and the FII/DII numbers
            return httpx.Response(pos[0], text=pos[1]) if isinstance(pos[1], str) else httpx.Response(pos[0], json=pos[1])
        if r.url.path == "/api/corporate-board-meetings":
            return httpx.Response(200, json=board_meetings())
        if r.url.path == "/api/corporates-corporateActions":
            acts, p = corporate_actions(), r.url.params
            if p.get("symbol"):
                acts = [x for x in acts if x["symbol"] == p["symbol"]]
            if p.get("from_date") and p.get("to_date"):
                frm, to = (datetime.strptime(p[k], "%d-%m-%Y").date() for k in ("from_date", "to_date"))
                acts = [x for x in acts if frm <= datetime.strptime(x["exDate"], "%d-%b-%Y").date() <= to]
            return httpx.Response(200, json=acts)
        if r.url.path == "/api/equity-stockIndices":
            idx = r.url.params.get("index", "")
            names = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC"] if idx == "NIFTY 500" else []
            return httpx.Response(200, json={"data": [{"symbol": idx, "priority": 1}] + [{"symbol": n} for n in names]})
        if r.url.path == "/content/equities/EQUITY_L.csv":
            lines = ["SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, ISIN NUMBER"]
            lines += [f"CO{i},Company {i} Limited,EQ,01-Jan-2010,10,INE{i:05d}A01{i % 10}" for i in range(120)]
            lines += ["RELIANCE,Reliance Industries Limited,EQ,29-Nov-1995,10,INE002A01018", "NEWCO,New Company Limited,EQ,"
                      + datetime.now().strftime("%d-%b-%Y") + ",10,INE999N01011", "SOMEBOND,Some Bond,N1,01-Jan-2020,1000,INE888B07019"]
            lines += [f"{s},{n},EQ,01-Jan-2000,1,{isin}" for s, n, isin in ISINS]
            return httpx.Response(200, text="\n".join(lines))
        from tests import fake_vix
        vx = fake_vix.answer(r.url.path, r.url.params)
        if vx is not None:                            # India VIX: the index list, its chart and its history (vix.py)
            return httpx.Response(200, json=vx)
        if r.url.path == "/api/etf":                  # every ETF's price and last NAV (etf_nav.py)
            from tests import fake_etf
            return httpx.Response(200, json=fake_etf.answer_live())
        if r.url.path == "/content/equities/eq_etfseclist.csv":   # the ETFs' ISINs (the list above has none)
            from tests import fake_etf
            return httpx.Response(200, text=fake_etf.securities_csv())
        if r.url.path == "/api/holiday-master":
            return httpx.Response(200, json={"CM": [{"tradingDate": "26-Jan-2027", "weekDay": "Tuesday", "description": "Republic Day"},
                                                    {"tradingDate": "22-Mar-2027", "weekDay": "Monday", "description": "Holi"}],
                                             "FO": []})
        if r.url.path == "/api/quote-equity":
            return httpx.Response(200, json={"industryInfo": {"macro": "Energy", "industry": "Refineries"},
                                             "priceInfo": {"lastPrice": 2900.5}})
        return httpx.Response(200, text="<html></html>")
    t = httpx.MockTransport(handler)
    return NSEFilings(transport=sw(t) if sw else t, sleep=lambda s: None)


def _docs(sw=None):
    pdf = make_pdf(["Investor presentation. Revenue grew 12%. We expect EBITDA margin of 24% in FY27."] * 60)
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=pdf))
    return main.Docs(transport=sw(t) if sw else t, check_host=lambda h: True, ocr=lambda data: "")


def _no_network(self, request):
    raise httpx.ConnectError("network disabled in tests", request=request)


def build(monkeypatch, real_clock: bool = False) -> dict:
    """Wire the app to fakes. Returns handles the tests use: the client, the fake AI, the fake database."""
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _no_network)
    # the sources' pacing waits are politeness towards real servers; against fakes they only make a busy test (the
    # fuzz) slow by chance, depending on what ran before it, so no source waits for its rate limit here
    from app.intel.net import RateLimit
    monkeypatch.setattr(RateLimit, "take", lambda self, max_wait=8.0: True)
    fake_db = FakeSupabase()
    monkeypatch.setattr(db, "_client", fake_db)
    db._profiles.clear()
    from app import invite_rewards, plans
    plans.forget_free_basic()                   # free Basic time another test gave
    invite_rewards._touched.clear()
    from app import corp_actions
    corp_actions._empty.clear()                 # company pages another test looked up with nothing found
    main._corp_tried.clear()                    # a calendar build another test tried a moment ago
    main._results.clear()                      # shared scan and rotation answers from an earlier test
    main._bse_map.clear()                       # the BSE-only list another test loaded
    from app import stock_pages
    stock_pages._companies.clear()              # public company pages: the list and built pages another test made
    main.stock_page_store.mem.clear()
    main.stock_page_store.recent.clear()
    main._isin.update(day=None, map={}, tried=0.0)   # the ISIN list another test loaded
    from app import scan as _scan
    _scan._cache.clear()                        # daily bars another test cached under the same instrument id
    main.trading_calendar._holiday_cache.clear()
    from app import surveillance
    surveillance._cache.clear()                 # the surveillance lists another test stored
    from app import etf_nav
    etf_nav.forget()                            # the ETF list and gap history another test stored
    from app import vix
    vix.forget()                                # India VIX quotes and history another test read
    from app import fo_changes
    fo_changes._cache.clear()                   # the F&O contract changes another test stored
    from app import closing_auction
    closing_auction.forget()                    # the closing auction another test stored
    from app import positioning
    positioning.clear_cache()                   # positioning days and live chains another test stored
    from app import auth
    auth._cache.clear()
    auth._rejected.clear()
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setattr(settings, "FINNHUB_API_KEY", "k")
    faults: dict[str, Switch] = {}

    def sw(name):
        def wrap(t):
            faults[name] = Switch(t)
            return faults[name]
        return wrap
    kite = fake_kite.online()
    markets = Registry(kite, CoinbaseProvider(transport=sw("crypto")(wavy_coinbase())),
                       yahoo=Yahoo(transport=sw("market data")(fake_yahoo(varied=True))))
    ticks = TickHub(kite)
    monkeypatch.setattr(ticks, "start", lambda: None)
    clock = (lambda: datetime.now(IST)) if real_clock else (lambda: datetime.now(IST).replace(hour=12, minute=0))
    options = OptionsData(FakeOptionsKite(live=True, drift={}, clock=clock))
    manager = LiveManager(kite, ticks, markets, options)
    for name, v in (("kite", kite), ("hub", ticks), ("markets", markets), ("options_data", options), ("manager", manager)):
        monkeypatch.setattr(main, name, v)
    hub = Research(kite, finnhub=Finnhub(transport=sw("us company data")(fake_finnhub())),
                   yahoo=Yahoo(transport=sw("research market data")(fake_yahoo(varied=True))),
                   screener=Screener(transport=sw("fundamentals")(fake_screener())), news=GoogleNews(transport=sw("news")(fake_news())),
                   wiki=Wikipedia(transport=sw("wikipedia")(fake_wiki())))
    monkeypatch.setattr(main, "research_hub", hub)
    routes.setup(hub, None, None)
    from app.intel.filings import BSEFilings, IndiaFilings
    from tests.fake_intel import fake_bse
    monkeypatch.setattr(main, "filings_feed", IndiaFilings(_nse(sw("exchange")), BSEFilings(transport=sw("bse filings")(fake_bse()), sleep=lambda s: None),
                                                           lambda s: main.bse_code(s)))
    monkeypatch.setattr(main.positioning_runner, "pace", 0)    # no pause between the fake exchange's files
    monkeypatch.setattr(main, "deep_docs", _docs(sw("documents")))
    from app.intel.sec import SEC
    from tests import fake_sec
    monkeypatch.setattr(main, "sec_feed", SEC(transport=sw("sec")(fake_sec.transport())))
    import importlib
    for m in ("app.intel.ai", "app.ask", "app.ideas", "app.deepdive", "app.report_card", "app.ai_writer", "app.importer"):
        importlib.import_module(m)              # load them now, so their copy of `complete` is swapped below
    ai, real_complete = FakeAI(), ai_providers.complete
    for name, mod in list(sys.modules.items()):
        if name.startswith("app.") and getattr(mod, "complete", None) is real_complete:
            monkeypatch.setattr(mod, "complete", ai)
    from app.intel import ai as intel_ai
    intel_ai._cache.clear()
    from app import audit
    runner = audit.Runner()
    monkeypatch.setattr(main, "audit_runner", runner)
    monkeypatch.setattr(main, "market_audit", audit.MarketAudit(lambda: main.filings_feed.all_equities(), main._market_check,
                                                                busy_fn=lambda: bool(runner.state.get("running")), pause=0))
    monkeypatch.setattr(main, "market_audit_us", audit.MarketAudit(lambda: main._sec_companies(), lambda s: main.audit_one(s, False, None, "US"),
                                                                   busy_fn=lambda: bool(runner.state.get("running")), pause=0,
                                                                   key="audit:market-us"))
    client = TestClient(main.app, raise_server_exceptions=False)

    def close():
        """Stop anything a test left running in the background: the audit, paper sessions."""
        runner.cancel()
        for sid in list(manager.sessions):
            try:
                manager.stop(sid, "test over")
            except Exception:
                manager.sessions.pop(sid, None)
    return {"client": client, "ai": ai, "db": fake_db, "rng": random.Random(7), "headers": headers, "kite": kite,
            "manager": manager, "faults": faults, "close": close}
