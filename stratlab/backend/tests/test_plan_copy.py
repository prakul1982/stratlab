"""The plans as the website shows them (frontend/src/lib/plans.ts, used by the landing page and Plans before sign-in)
must say exactly what plans.py enforces: the same prices, limits and paid features."""
import re
from pathlib import Path

from app.plans import FEATURES, PLANS

TS = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "plans.ts").read_text(encoding="utf-8")


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
            "stock_alerts", "screens", "holdings")
    for plan, p in PLANS.items():
        text = _plan(limits, plan)
        for k in keys:
            assert _num(text, k) == p[k], f"{plan}.{k}"
        shown = set(re.findall(r'"(\w+)"', re.search(r"features:\s*\[(.*?)\]", text, re.S).group(1)))
        assert shown == set(p["features"]), plan


def test_every_paid_feature_has_a_row():
    rows = set(re.findall(r'\["(\w+)",', TS[TS.index("export const FLAGS"):TS.index("export const EVERYONE")]))
    assert rows == set(FEATURES)
