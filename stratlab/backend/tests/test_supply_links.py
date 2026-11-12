"""The customer and supplier map (MVP): extraction rules on real 10-K sentences and order-filing summaries, with their
precision; the quote check; matching and the Admin review queue; the nightly job (off by default, bounded, AI only when the
rules are unsure, within the monthly cap); the company card's plan gating, the CSV and the theme view."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app import supply_extract as X

FIX = Path(__file__).parent / "fixtures" / "supply"
UNIVERSE = {
    "IN": [{"symbol": "BEL", "name": "Bharat Electronics Limited"}, {"symbol": "NTPC", "name": "NTPC Limited"},
           {"symbol": "LT", "name": "Larsen & Toubro Limited"}, {"symbol": "POWERGRID", "name": "Power Grid Corporation of India Limited"},
           {"symbol": "TMPV", "name": "Tata Motors Passenger Vehicles Limited"}, {"symbol": "TATASTEEL", "name": "Tata Steel Limited"},
           {"symbol": "TCS", "name": "Tata Consultancy Services Limited"}, {"symbol": "IRCTC", "name": "Indian Railway Catering And Tourism Corporation Limited"},
           {"symbol": "BEML", "name": "BEML Limited"}, {"symbol": "COALINDIA", "name": "Coal India Limited"}],
    "US": [{"symbol": "WMT", "name": "Walmart Inc."}, {"symbol": "HD", "name": "The Home Depot, Inc."}, {"symbol": "COST", "name": "Costco Wholesale Corporation"},
           {"symbol": "ILMN", "name": "Illumina, Inc."}, {"symbol": "CENT", "name": "Central Garden & Pet Company"}, {"symbol": "AAPL", "name": "Apple Inc."}],
}


def _score():
    tp = fp = fn = 0
    for kind in ("annual_10k", "india_orders"):
        for d in json.loads((FIX / f"{kind}.json").read_text())["docs"]:
            got = X.extract_annual(d["text"], d["filer"])[0] if kind == "annual_10k" else X.extract_order(d["text"], d["filer"])[0]
            for x in got:
                assert X.kept(x, d["text"]), x                      # every link's quote is in its document, with the name in it
            g = {(x["direction"], x["counterparty"].lower()) for x in got}
            e = {(a, b.lower()) for a, b in d["expect"]}
            tp, fp, fn = tp + len(g & e), fp + len(g - e), fn + len(e - g)
    return tp, fp, fn


# ---------- extraction ----------
def test_fixture_precision_on_real_filing_sentences():
    tp, fp, fn = _score()
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    print(f"supply links fixture: {tp} right, {fp} wrong, {fn} missed; precision {precision:.2f}, recall {recall:.2f}")
    assert tp >= 25 and precision >= 0.95 and recall >= 0.8


def test_order_win_gives_the_named_buyer_as_customer_with_amount():
    links, unsure = X.extract_order("Larsen & Toubro Limited has informed the Exchange that it has received an order worth Rs 450 crore from "
                                    "Bharat Electronics Limited for supply of radar subsystems.", "Larsen & Toubro Limited")
    assert not unsure and len(links) == 1
    x = links[0]
    assert (x["counterparty"], x["direction"], x["basis"], x["amount"]) == ("Bharat Electronics Limited", "customer", "order_win", "Rs 450 crore")


@pytest.mark.parametrize("text", [
    "The Company has emerged as L1 bidder for a project of National Highways Authority of India.",
    "We are in discussions with Apple Inc. for an order of modules.",
    "The contract awarded by Mumbai Metro Rail Corporation has been terminated.",
    "An order passed by the Hon'ble National Company Law Tribunal against the Company.",
    "The Company has entered into a Memorandum of Understanding with Indian Railways for signalling.",
    "Analyst: do you supply to Bharat Electronics Limited, and is there an order from them?",
])
def test_prospects_lost_orders_court_orders_mous_and_analysts_give_no_link(text):
    assert X.extract_order(text, "Some Company Limited")[0] == []


def test_unnamed_buyer_is_never_guessed_and_a_bare_summary_is_unsure():
    assert X.extract_order("XYZ Limited has received orders from a leading global OEM.", "XYZ Limited") == ([], False)
    assert X.extract_order("XYZ Limited has informed the Exchange regarding receipt of orders worth Rs 572 crores.", "XYZ Limited") == ([], True)


def test_10k_concentration_supplier_and_unnamed_customer():
    text = ("Walmart, our largest customer, accounted for approximately 17% of total net sales in fiscal 2025. "
            "During fiscal 2025, Customer A accounted for 15% of total revenue. We rely on Illumina as a sole supplier for our sequencers. "
            "If Target were to reduce its purchases, which accounted for 12% of net sales, our results could suffer. "
            "Apple and Samsung accounted for 25% and 14% of our revenue, respectively.")
    links, unsure = X.extract_annual(text)
    got = {(x["counterparty"], x["direction"], x["share_pct"]) for x in links}
    assert got == {("Walmart", "customer", 17.0), ("Illumina", "supplier", None)}
    assert unsure == ["Apple and Samsung accounted for 25% and 14% of our revenue, respectively."]


def test_a_retailers_brand_share_goes_to_the_ai_not_a_customer_link():
    text = ("Three branded suppliers, Nike, Inc., Skechers U.S.A., Inc. and Crocs, Inc., collectively accounted for approximately 48% of our Net Sales. "
            "Nike accounted for approximately 24% of our Net Sales in Fiscal 2024.")
    links, unsure = X.extract_annual(text)
    assert links == [] and unsure == ["Nike accounted for approximately 24% of our Net Sales in Fiscal 2024."]


# ---------- the quote check ----------
def test_quote_must_be_verbatim_and_hold_the_name():
    doc = "Walmart Inc. accounted for 21% of our net sales in fiscal 2025."
    assert X.kept({"counterparty": "Walmart Inc.", "quote": doc}, doc)
    assert not X.kept({"counterparty": "Walmart Inc.", "quote": "Walmart Inc. accounted for 31% of our net sales in fiscal 2025."}, doc)
    assert not X.kept({"counterparty": "Target", "quote": doc}, doc)
    assert X.verbatim("Walmart Inc.  accounted for 21% of our net sales", "Walmart Inc. accounted for 21% of our net\nsales")


def test_ai_links_pass_the_same_checks():
    doc = "Sales to Acme Retail accounted for 22% of net sales. We are in talks with Beta Stores about a supply agreement."
    reply = json.dumps({"links": [
        {"counterparty": "Acme Retail", "direction": "customer", "current": True, "quote": "Sales to Acme Retail accounted for 22% of net sales."},
        {"counterparty": "Gamma Corp", "direction": "customer", "current": True, "quote": "Gamma Corp accounted for 30% of net sales."},   # made up
        {"counterparty": "Beta Stores", "direction": "customer", "current": True, "quote": "We are in talks with Beta Stores about a supply agreement."},
        {"counterparty": "Acme Retail", "direction": "customer", "current": False, "quote": "Sales to Acme Retail accounted for 22% of net sales."},
        {"counterparty": "Customer A", "direction": "customer", "current": True, "quote": "Sales to Acme Retail accounted for 22% of net sales."},
    ]})
    got = X.from_ai(reply, doc, "concentration")
    assert [(x["counterparty"], x["share_pct"], x["method"]) for x in got] == [("Acme Retail", 22.0, "ai")]
    assert X.from_ai("not json", doc, "concentration") == []


# ---------- matching and the review queue ----------
@pytest.fixture
def world(monkeypatch):
    from tests import world as W
    from app import supply_links as S
    w = W.build(monkeypatch)
    monkeypatch.setattr(S, "universe", lambda region: UNIVERSE[region])
    S._index_cache.clear()
    yield w
    S._index_cache.clear()
    w["close"]()


def test_matching_links_only_exact_or_known_names(world):
    from app import supply_links as S
    assert S.match("Bharat Electronics Limited", "IN")["symbol"] == "BEL"           # the whole name
    assert S.match("L&T", "IN") == {"state": "auto", "symbol": "LT", "candidates": None}   # a known short name
    assert S.match("NTPC", "IN")["state"] == "auto"                                 # the symbol
    tata = S.match("Tata", "IN")
    assert tata["state"] == "review" and {"TMPV", "TATASTEEL", "TCS"} <= {c["symbol"] for c in tata["candidates"]}
    assert S.match("Indian Railways", "IN")["state"] == "text"                       # a public body: kept as filed
    assert S.match("Mumbai Metro Rail Corporation", "IN")["state"] == "text"
    assert S.match("Samsung Electronics", "US")["state"] == "text"                  # not listed here
    assert S.match("Bharat Electronics Limited", "IN", "BEL") is None                # the filer itself


def _seed(S, n_own=5):
    for i in range(n_own):
        S.save_links([{"counterparty": "Bharat Electronics Limited" if i == 0 else f"Buyer Number{i} Works", "direction": "customer",
                       "basis": "order_win", "quote": f"q{i}", "amount": None, "method": "rule"}],
                     "IN", "LT", "Larsen & Toubro Limited", f"https://nsearchives.nseindia.com/o{i}.pdf", "Receipt of order", f"2026-10-{10 + i:02d}")
    S.save_links([{"counterparty": "Tata", "direction": "customer", "basis": "order_win", "quote": "order from Tata", "method": "rule"}],
                 "IN", "LT", "Larsen & Toubro Limited", "https://nsearchives.nseindia.com/t.pdf", "Receipt of order", "2026-09-01")


def test_review_queue_settles_a_name_and_remembers_it(world):
    from app import supply_links as S
    c, h = world["client"], world["headers"]
    _seed(S, 1)
    assert c.get("/admin/supply-links", headers=h("pro-token")).status_code == 403
    q = c.get("/admin/supply-links", headers=h("admin-token")).json()
    assert q["on"] is False and q["waiting"] == 1
    row = q["queue"][0]
    assert row["counterparty"] == "Tata" and row["quote"] == "order from Tata"
    assert c.post(f"/admin/supply-links/review/{row['id']}", headers=h("admin-token"), json={"symbol": "AAPL"}).status_code == 400
    r = c.post(f"/admin/supply-links/review/{row['id']}", headers=h("admin-token"), json={"symbol": "TATASTEEL"})
    assert r.status_code == 200
    assert c.get("/admin/supply-links", headers=h("admin-token")).json()["waiting"] == 0
    assert S.match("Tata", "IN") == {"state": "auto", "symbol": "TATASTEEL", "candidates": None}     # remembered
    named = c.get("/research/links/IN/TATASTEEL", headers=h("basic-token")).json()
    assert [(i["name"], i["relation"]) for i in named["items"]] == [("Larsen & Toubro Limited", "Named as a customer by")]


def test_rejected_link_is_hidden_everywhere(world):
    from app import supply_links as S
    c, h = world["client"], world["headers"]
    _seed(S, 1)
    rid = c.get("/admin/supply-links", headers=h("admin-token")).json()["queue"][0]["id"]
    c.post(f"/admin/supply-links/review/{rid}", headers=h("admin-token"), json={"action": "reject"})
    names = [i["name"] for i in c.get("/research/links/IN/LT", headers=h("pro-token")).json()["items"]]
    assert "Tata" not in names and "Bharat Electronics Limited" in names


# ---------- the company card's gating ----------
def test_card_gating_free_basic_pro(world):
    from app import supply_links as S
    c, h = world["client"], world["headers"]
    _seed(S, 5)
    assert c.get("/research/links/IN/LT").status_code == 401
    free = c.get("/research/links/IN/LT", headers=h("free-token")).json()
    assert free["total"] == 6 and len(free["items"]) == S.FREE_ROWS and free["locked"] == 3 and not free["full"]
    assert free["plan_for_all"] == "Basic" and free["items"][0]["said_on"] == "2026-10-14"        # the latest first
    basic = c.get("/research/links/IN/LT", headers=h("basic-token")).json()
    assert len(basic["items"]) == 6 and basic["locked"] == 0 and basic["full"] and not basic["csv"]
    one = next(i for i in basic["items"] if i["name"] == "Bharat Electronics Limited")
    assert (one["symbol"], one["relation"], one["basis"], one["doc_url"]) == ("BEL", "Names as customers", "Order win", "https://nsearchives.nseindia.com/o0.pdf")
    tata = next(i for i in basic["items"] if i["name"] == "Tata")
    assert tata["symbol"] is None and tata["as_filed"]                                             # in review: shown as filed, unlinked
    # the other side: BEL's page shows who names it
    bel = c.get("/research/links/IN/BEL", headers=h("basic-token")).json()
    assert [(i["name"], i["symbol"], i["relation"], i["group"]) for i in bel["items"]] == [("Larsen & Toubro Limited", "LT", "Named as a customer by", "named_customer_by")]
    assert c.get("/research/links/IN/LT/csv", headers=h("basic-token")).status_code == 402
    pro = c.get("/research/links/IN/LT/csv", headers=h("pro-token"))
    assert pro.status_code == 200 and pro.text.count("\n") == 7 and "Bharat Electronics Limited" in pro.text
    assert c.get("/research/links/XX/LT", headers=h("pro-token")).status_code == 400


def test_theme_view_is_pro_and_counts_links_by_layer(world, monkeypatch):
    from app import supply_links as S
    from app.intel import theme_library
    c, h = world["client"], world["headers"]
    _seed(S, 2)
    chain = [{"layer": "Equipment", "companies": [{"ticker": "BEL"}]}, {"layer": "Contractors", "companies": [{"ticker": "LT"}]}]
    monkeypatch.setattr(theme_library, "stored", lambda region, q: {"payload": {"value_chain": chain}} if q == "defence" else None)
    basic = c.get("/research/links/theme?region=IN&q=defence", headers=h("basic-token")).json()
    assert basic == {"available": True, "allowed": False, "members": 2, "links": 1, "plan": "Pro"}
    pro = c.get("/research/links/theme?region=IN&q=defence", headers=h("pro-token")).json()
    assert pro["layers"] == [{"from": "Contractors", "to": "Equipment", "links": 1}]
    assert pro["edges"][0]["supplier"] == "LT" and pro["edges"][0]["customer"] == "BEL"
    assert {o["name"] for o in pro["outside"]} == {"Buyer Number1 Works", "Tata"}
    assert c.get("/research/links/theme?region=IN&q=nothing", headers=h("pro-token")).json()["available"] is False


# ---------- the nightly job ----------
class Feed:
    def __init__(self, days):
        self.days, self.asked = days, []

    def market_orders(self, day):
        self.asked.append(day)
        return self.days.get(day.isoformat(), [])


class Docs:
    def __init__(self, text):
        self.text_, self.read = text, []

    def text(self, url):
        self.read.append(url)
        return self.text_


def _order(i, text, sym="LT", company="Larsen & Toubro Limited", day="2026-11-10"):
    return {"id": f"{sym}|{i}", "symbol": sym, "company": company, "at": f"{day}T18:00", "subject": "Bagging/Receiving of orders/contracts",
            "text": text, "url": f"https://nsearchives.nseindia.com/corporate/o{i}.pdf"}


def test_job_is_off_by_default_and_runs_once_a_night(world, monkeypatch):
    from app import supply_links as S
    called = []
    monkeypatch.setattr(S.job, "run", lambda *a, **k: called.append(a) or {"ok": True})
    night = datetime(2026, 11, 11, 20, 30, tzinfo=timezone.utc)                     # 2:00 AM IST
    assert S.job.tick(night) is None and not called                                 # off
    S.switch(True)
    assert S.job.tick(datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)) is None    # daytime
    S.job.tick(night)
    S.job.tick(night)
    assert len(called) == 1 and called[0][:2] == (S.ORDER_CAP, S.US_CAP)
    row = next(r for r in world["client"].get("/admin/jobs", headers=world["headers"]("admin-token")).json()["jobs"] if r["id"] == "supply-links")
    assert row["name"] == "Customer and supplier map" and "1:40 AM IST" in row["schedule"]


def test_job_reads_orders_one_at_a_time_with_ai_only_when_unsure_and_capped(world, monkeypatch):
    from app import ai_providers, db, supply_links as S
    asks = []

    def ai(system, text, **kw):
        asks.append((text, kw))
        return json.dumps({"links": [{"counterparty": "NTPC Limited", "direction": "customer", "current": True,
                                      "quote": "The order has been placed by NTPC Limited for the Singrauli project."}]})
    monkeypatch.setattr(ai_providers, "complete", ai)
    pdf = "Order details. The order has been placed by NTPC Limited for the Singrauli project. Value Rs 300 crore."
    feed = Feed({"2026-11-10": [_order(1, "L&T has received an order worth Rs 450 crore from Bharat Electronics Limited for radars."),
                                _order(2, "Larsen & Toubro Limited has informed the Exchange regarding receipt of orders."),
                                _order(3, "Larsen & Toubro Limited has informed the Exchange regarding receipt of orders, part two.")]})
    docs = Docs("Larsen & Toubro Limited order intimation. Please find attached the details.")   # the PDF names no one either
    S.setup(lambda: feed, lambda: None, lambda: docs)
    db.set_setting(S.AI_CAP_KEY, "1")
    docs.text_ = pdf.replace("NTPC Limited", "the client")                          # rules unsure on the PDF too
    out = S.job.run(10, 0, today=date(2026, 11, 11))
    assert out["ok"] and out["read"] == 3
    assert len(asks) == 1 and asks[0][1]["bulk"] is True                            # the cheapest model, once: the cap is 1
    assert S.ai_used() == 1
    # the AI's link was dropped: its quote isn't in the document read
    names = {r["counterparty"] for r in db.sb().table("supply_links").select("*").execute().data}
    assert names == {"Bharat Electronics Limited"}
    # read again: nothing is read twice, and the state moved on to yesterday
    asks.clear()
    again = S.job.run(10, 0, today=date(2026, 11, 11))
    assert again["read"] == 0 and not asks
    assert json.loads(db.get_setting(S.STATE_KEY))["in_through"] == "2026-11-10"


def test_job_ai_link_kept_when_its_quote_is_in_the_filing(world, monkeypatch):
    from app import ai_providers, db, supply_links as S
    monkeypatch.setattr(ai_providers, "complete", lambda system, text, **kw: json.dumps({"links": [
        {"counterparty": "NTPC Limited", "direction": "customer", "current": True, "quote": "The order has been placed by NTPC Limited for the Singrauli project."}]}))
    feed = Feed({"2026-11-10": [_order(9, "Larsen & Toubro Limited has informed the Exchange regarding receipt of orders.")]})
    S.setup(lambda: feed, lambda: None, lambda: Docs("Details. The order has been placed by NTPC Limited for the Singrauli project. Rs 300 crore."))
    monkeypatch.setattr(X, "extract_order", lambda text, filer=None: ([], True))     # the rules unsure, so the AI reads it
    S.job.run(5, 0, today=date(2026, 11, 11))
    rows = db.sb().table("supply_links").select("*").execute().data
    assert [(r["counterparty"], r["cp_symbol"], r["state"], r["method"]) for r in rows] == [("NTPC Limited", "NTPC", "auto", "ai")]


class SecFake:
    def __init__(self, text):
        from app.intel.net import TTLCache
        self.cache, self.text, self.read = TTLCache(max_items=10), text, []

    def submissions(self, cik):
        return {"cik": cik, "filings": {"recent": {"form": ["10-K"], "filingDate": [date.today().isoformat()], "accessionNumber": ["0000-25-1"],
                                                    "primaryDocument": ["a10k.htm"], "items": [""]}}}

    def document(self, url):
        self.read.append(url)
        self.cache.set(("doc", url), self.text, 600)
        return self.text


def test_job_reads_a_few_annual_reports_in_turn_and_drops_their_text(world, monkeypatch):
    from app import db, supply_links as S, universes
    report = ("Item 1. Business\n" + "We make garden products. " * 40 + "Walmart, our largest customer, accounted for approximately 17% of total net sales "
              "in fiscal 2025. We rely on Illumina as a sole supplier for our sequencers.\nItem 1A. Risk Factors\n" + "Risks. " * 100 + "\nItem 2. Properties\n")
    sec = SecFake(report)
    monkeypatch.setattr(universes, "sp500_ciks", lambda: {"CENT": 1, "AAPL": 2, "HD": 3})
    monkeypatch.setattr(universes, "sp500_names", lambda: {"CENT": "Central Garden & Pet Company"})
    S.setup(lambda: None, lambda: sec, lambda: None)
    out = S.job.run(0, 2)
    assert out["ok"] and len(sec.read) == 2 and not sec.cache.get(("doc", sec.read[0]))
    assert json.loads(db.get_setting(S.STATE_KEY))["us_cursor"] == 2
    rows = [r for r in db.sb().table("supply_links").select("*").execute().data if r["stated_by"] == "AAPL"]
    assert {(r["counterparty"], r["cp_symbol"], r["direction"], r["share_pct"]) for r in rows} == {
        ("Walmart", "WMT", "customer", 17.0), ("Illumina", "ILMN", "supplier", None)}


def test_admin_switch_and_ai_cap(world):
    from app import supply_links as S
    c, h = world["client"], world["headers"]
    assert c.post("/admin/supply-links/on", headers=h("admin-token")).status_code == 200 and S.enabled()
    assert c.post("/admin/supply-links/ai-cap", headers=h("admin-token"), json={"calls": 50}).status_code == 200 and S.ai_cap() == 50
    assert c.post("/admin/supply-links/ai-cap", headers=h("admin-token"), json={"calls": "lots"}).status_code == 400
    assert c.post("/admin/supply-links/off", headers=h("admin-token")).status_code == 200 and not S.enabled()
    assert c.post("/admin/supply-links/on", headers=h("basic-token")).status_code == 403
