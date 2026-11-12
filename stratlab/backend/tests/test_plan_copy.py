"""The plans as the website shows them (frontend/src/lib/plans.ts, used by the landing page and Plans before sign-in)
must say exactly what plans.py enforces: the same prices, limits and paid features."""
import re
from pathlib import Path

from app.plans import FEATURE_PLAN, FEATURES, PLANS

_LIB = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib"
# LIVE4-020: the full feature lists (FEATURES) moved to planFeatures.ts, loaded with the landing page's fold; read with plans.ts as one text
# (updated on purpose, Release 43) the cards' part (PRICE, LIMITS, WHO, KEY) moved to planCore.ts, the only plan file the landing page
# downloads; plans.ts keeps the comparison table's rows: all three are read as one text
TS = "\n".join((_LIB / f).read_text(encoding="utf-8") for f in ("planCore.ts", "plans.ts", "planFeatures.ts"))


def _block(name: str) -> str:
    """The text of `export const NAME ... = { ... };`."""
    m = re.search(rf"export const {name}\b[^=]*=\s*\{{(.*?)\n\}};", TS, re.S)
    assert m, f"{name} not found in plans.ts"
    return m.group(1)


def _plan(block: str, plan: str) -> str:
    """One plan's entry inside a block: from `plan:` to the next plan's key (or the end)."""
    m = re.search(rf"\b{plan}:\s*(.*?)(?=\n\s*(?:free|basic|pro):|\Z)", block, re.S)
    assert m, f"{plan} not found"
    return m.group(1)


def _num(text: str, key: str):
    m = re.search(rf"\b{key}:\s*(null|\d+)", text)
    assert m, f"{key} missing"
    return None if m.group(1) == "null" else int(m.group(1))


def test_prices_match():
    prices = _block("PRICE")
    for plan, p in PLANS.items():
        m = re.search(rf"\b{plan}:\s*\[(\d+),\s*(\d+)\]", prices)
        assert m, plan
        assert (int(m.group(1)), int(m.group(2))) == (p["price"], p["price_year"]), plan


def test_limits_and_features_match():
    limits = _block("LIMITS")
    keys = ("backtests_per_month", "ai_builds_per_month", "live_limit", "group_size", "deepdives_per_month", "decks_per_month",
            "stock_alerts", "screens", "holdings", "networth_items", "mf_schemes", "journal_trades",
            "watchlists", "watchlist_symbols", "chart_saves", "chart_indicators",
            # (updated on purpose, FREE-TIER: the new theme limit and the per-plan daily AI reads are in both copies too)
            "themes_per_month", "ai_reads_per_day")
    for plan, p in PLANS.items():
        text = _plan(limits, plan)
        for k in keys:
            assert _num(text, k) == p[k], f"{plan}.{k}"
        shown = set(re.findall(r'"(\w+)"', re.search(r"features:\s*\[(.*?)\]", text, re.S).group(1)))
        # (updated on purpose, f4) plus the features planFeatures.ts adds (MORE_FLAGS): plans.ts is held for the landing page's budget
        shown |= {f for f, need in _more() if RANK[plan] >= RANK[need]}
        assert shown == set(p["features"]), plan


RANK = {"free": 0, "basic": 1, "pro": 2}


def _more() -> list[tuple[str, str]]:
    """planFeatures.ts MORE_FLAGS: (flag, the cheapest plan that has it) (f4)."""
    block = TS[TS.index("export const MORE_FLAGS"):]
    block = block[:block.index("];")]
    return re.findall(r'\["(\w+)",\s*".*?",\s*"(free|basic|pro)"\]', block, re.S)


def test_every_paid_feature_has_a_row():
    rows = set(re.findall(r'\["(\w+)",', TS[TS.index("export const FLAGS"):TS.index("export const EVERYONE")]))
    rows |= {f for f, _ in _more()}                   # (updated on purpose, f4) the comparison table's rows from planFeatures.ts too
    assert rows == set(FEATURES)
    assert all(FEATURE_PLAN[f] == need for f, need in _more())


# the words on a plan card (FEATURES in plans.ts) that name each paid feature; a new feature fails here until the card of
# the plan that adds it says so
CARD_WORDS = {
    "indicators": "20+ indicators", "group_live": "whole groups", "options": "options at set times", "alerts": "trade notifications",
    "daily_report": "daily report", "newsletter": "daily Market Brief", "scans": "Stage 2 scan", "filings": "watchlist red flags",
    "investor_home": "Watchlist at a glance", "networth": "net worth entry", "mf_gains": "fund capital gains",
    "dividends": "dividends with TDS", "money_reminders": "money reminders", "breadth": "market breadth charts",
    "positioning": "positioning history", "journal": "full trade journal", "fno": "Indian F&O",
    "options_signal": "your own rules' signals", "fast_entries": "faster entries", "export": "Export a notebook's rules",
    "tax_tools": "Advance tax amounts", "itr_export": "ITR-ready", "us_tax": "US stocks in Indian tax",
    "mf_costs": "fund costs in rupees",
    "etf_gaps": "ETF gap alerts",
    "fo_alerts": "F&O change alerts",
    "options_whatif": "what-if sliders",
    "cas_history": "closing auction history",
    "vix_filter": "India VIX entry filter",
    "strike_rules": "strikes picked by delta or premium",
    "chart_replay": "chart replay practice",
    "signal_webhooks": "alert webhooks",
    "event_reminders": "market event reminders",
    "biz_updates": "business updates in numbers",
    "holders": "named-holder search",
    "assistant": "in your AI assistant",
    "stock_futures": "stock futures history",
    "mtf": "margin funding history",
    "mf_behaviour": "fund behaviour",
    "sip_luck": "SIP dip rules",
    "rates_slab": "after your own tax",
    "loan_check": "floating-rate loan check",
    "ipo_summary": "IPO offer document summaries",
    "ipo_alerts": "IPO alerts",
    "movers": "market movers in full",
    # (updated on purpose: two new Basic features, the earnings-call calendar in full and business group figures, f5)
    "earnings_calls": "earnings-call calendar in full",
    "group_figures": "business group figures",
    # (updated on purpose, lane b1: two new paid features, the filings search on Basic and its every-year archive and CSV on Pro)
    "doc_search": "search inside filings and call transcripts",
    "doc_search_all": "every year of a company's filings",
    "tables": "ten years of statements and shareholding",
    # (updated on purpose, f3: a new Basic feature, the watchlist import from a file)
    "watchlist_import": "watchlist import from a file",
    "tax_export": "tax report downloads",          # (updated on purpose, FREE-TIER: the tax report's CSV and PDF move to Basic)
    # (updated on purpose, f4: two new Basic features, a theme's full change log and its workbook)
    "theme_changes": "theme change logs",
    "theme_workbook": "theme's workbook in Excel",
    # (updated on purpose: lane b2's new features)
    "supply": "customers and suppliers named in filings",
    "supply_pro": "links across a theme's companies",
}


def test_every_paid_feature_is_on_its_plan_card():
    assert set(CARD_WORDS) == set(FEATURES)
    cards = _block("FEATURES")
    for f, words in CARD_WORDS.items():
        plan = FEATURE_PLAN[f]
        assert words in _plan(cards, plan), f"the {plan} card doesn't mention {f} ({words!r})"
        for other in ("free", "basic", "pro"):
            if other != plan:
                assert words not in _plan(cards, other), f"{f} ({words!r}) is on the {other} card too"


def test_share_links_match_and_each_plan_names_them():
    """Bet 3: the public share links a month (plans.py share_links_per_month) as planFeatures.ts says them (SHARE_LINKS), and each
    plan's full feature list names them with that number."""
    m = re.search(r"export const SHARE_LINKS\b[^=]*=\s*\{([^}]*)\}", TS)
    assert m, "SHARE_LINKS not found in planFeatures.ts"
    for plan, p in PLANS.items():
        assert _num(m.group(1), plan) == p["share_links_per_month"], plan
    cards = _block("FEATURES")
    assert "${SHARE_LINKS.free} share link" in _plan(cards, "free")
    assert "${SHARE_LINKS.basic} public share links" in _plan(cards, "basic")
    assert "with unlimited share links" in _plan(cards, "pro")


# ---------- FREE-TIER: every place that states Free's limits says the server's numbers ----------
_ROOT = Path(__file__).resolve().parents[3]


def _readme_row(start: str) -> list[str]:
    text = (_ROOT / "README.md").read_text(encoding="utf-8")
    line = next(x for x in text.splitlines() if x.startswith(f"| {start}"))
    return [c.strip() for c in line.strip("|").split("|")]


def test_readme_plan_table_says_the_free_tier():
    f = PLANS["free"]
    assert _readme_row("Backtests")[1] == f"{f['backtests_per_month']} a month"
    assert _readme_row("AI strategy builds")[1] == f"{f['ai_builds_per_month']} a month"
    assert _readme_row("Instruments in a group test")[1:3] == [str(f["group_size"]), str(PLANS["basic"]["group_size"])]
    assert _readme_row("Company deep dives")[1] == f"{f['deepdives_per_month']} a month"
    assert f["decks_per_month"] == 0 and _readme_row("Slide decks")[1].startswith("None (a sample deck")
    assert _readme_row("New themes mapped")[1:4] == [f"{f['themes_per_month']} a month", f"{PLANS['basic']['themes_per_month']} a month", "Unlimited"]
    assert _readme_row("Fresh AI reads a day")[1:4] == [str(f["ai_reads_per_day"]), str(PLANS["basic"]["ai_reads_per_day"]), "Unlimited"]
    assert _readme_row("AI answers in the search box")[1:4] == [str(PLANS[p]["search_ai_per_day"]) for p in ("free", "basic", "pro")]
    # a Refresh is one fresh AI read (LIVE7B-002): Basic and Pro have it, Free none
    from app import plans
    assert not plans.refreshes_allowed("free") and _readme_row("Refresh of a stored result")[1:4] == ["None", "✓", "✓"]
    assert _readme_row("Stock alerts on at once")[1] == f"{f['stock_alerts']} / {f['screens']} / {f['holdings']}"
    assert _readme_row("The tax report's CSV and PDF downloads")[1:4] == ["–", "✓", "✓"]


def test_features_doc_and_cards_say_the_free_tier():
    f = PLANS["free"]
    doc = (_ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    assert f"{f['ai_reads_per_day']} fresh AI reads and {f['search_ai_per_day']} search answers a day, no refreshes" in doc
    assert f"{f['themes_per_month']} new theme, {f['deepdives_per_month']} deep dive, {f['backtests_per_month']} backtests and {f['ai_builds_per_month']} AI builds a month" in doc
    assert "sample deck" in doc and "14 days" in doc
    # the cards (plans.ts KEY) never say "0 slide deck"; Free's card says its deep dive and daily reads from LIMITS
    key = _block("KEY")
    assert "slide deck a month" not in _plan(key, "free")
    assert "${L.free.deepdives_per_month} company deep dive a month, ${L.free.ai_reads_per_day} fresh AI reads a day" in _plan(key, "free")
    assert "${L.free.screens} saved screen," in _plan(key, "free")


def test_supply_free_rows_match_the_free_card():
    """(lane b2) The Free card's number of customer and supplier links is the server's own (supply_links.FREE_ROWS)."""
    from app.supply_links import FREE_ROWS
    m = re.search(r"latest (\d+) customer and supplier links", _plan(_block("FEATURES"), "free"))
    assert m and int(m.group(1)) == FREE_ROWS
