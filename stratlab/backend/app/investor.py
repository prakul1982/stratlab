"""The investor home: every India watchlist company on one page, with its price trend, its sector's place in the
rotation, its red-flag filings, the investor checklist and the management report card (when one has been read)."""
from . import rotation, sector_members

MAX = 20                       # watchlist companies on the page


def sector_of(market: str, symbol: str) -> str | None:
    """The sector index a stock belongs to, preferring the main sectors over thematic ones."""
    sectors = sector_members.BY_MARKET.get(market, {})
    hits = [k for k, v in sectors.items() if symbol in v]
    core = [k for k in hits if market != "IN" or k in rotation.CORE_IN]
    return (core or hits or [None])[0]


def row(symbol: str, name: str | None, trend: dict | None, sector: dict | None, fsum: dict | None,
        checks: dict | None, card: dict | None, has_read: bool, problem: str | None = None) -> dict:
    fails = [c["label"] for c in (checks or {}).get("checks", []) if c["state"] == "fail"]
    return {
        "symbol": symbol, "name": name or symbol, "problem": problem,
        "price": (trend or {}).get("price"), "chg": (trend or {}).get("chg"), "stage": (trend or {}).get("stage"),
        "st_up": (trend or {}).get("st_up"), "signal": (trend or {}).get("signal"),
        "sector": sector,
        "red": None if fsum is None else fsum.get("red", 0), "amber": None if fsum is None else fsum.get("amber", 0),
        "fund_raise": bool((fsum or {}).get("fund_raise")),
        "checks": (checks or {}).get("counts"), "fails": fails[:4],
        "card": None if not card or card.get("score") is None else {"met": card["met"], "missed": card["missed"], "score": card["score"]},
        "has_read": has_read,
    }
