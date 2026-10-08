"""The demo world's one price table: where each instrument trades, read by every fake source (the fake broker
fake_kite, the fake quote site fake_yahoo, the fake US company-data source, the fake exchange's closing auction, the
stored screener index, the fake company pages and the live breadth points), so one instrument shows the same price on
every page.

How a price is made: each instrument follows a slow wave around a gentle rise, `price(name, when)`. The wave is scaled
so that the latest session's close is exactly the instrument's level below: NIFTY 50 closed at 25,000.00, RELIANCE at
₹1,400.00. Out of market hours every price stands still at that close (the sources say "last close"); in hours it
moves from it, a little. The broad Indian indices move together (NIFTY 500 tracks NIFTY 50 and stays below it, as the
real ones do). Holidays are the app's own trading calendar's. The exceptions are the exchange-traded funds, which stand at the last close
in hours too (the exchange's ETF list is read at the close), so the ETF page, the holdings and the NAV gap agree whenever the page is opened."""
import functools
import math
import zlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
ET = ZoneInfo("America/New_York")

LEVELS = {
    # indices (the last close). NIFTY 500 sits below NIFTY 50 as the real one does (about 0.92 of it).
    "NIFTY 50": 25000.0, "NIFTY BANK": 55000.0, "SENSEX": 82000.0, "INDIA VIX": 15.03, "NIFTY 500": 23000.0,   # VIX: the exchange's reading in fake_vix
    # stocks (round numbers near their real levels)
    "RELIANCE": 1400.0, "TCS": 3050.0, "INFY": 1480.0, "HDFCBANK": 960.0, "ICICIBANK": 1350.0, "SBIN": 820.0,
    "AXISBANK": 1150.0, "ITC": 405.0, "HINDUNILVR": 2450.0, "HCLTECH": 1450.0, "WIPRO": 245.0, "LT": 3600.0,
    "BHARTIARTL": 1900.0, "TATASTEEL": 165.0, "ONGC": 240.0, "NTPC": 340.0, "COALINDIA": 385.0, "MARUTI": 12500.0,
    "NIFTYBEES": 270.5, "GOLDBEES": 81.2, "SILVERBEES": 105.2, "BANKBEES": 560.0, "LIQUIDBEES": 1000.0,   # as the ETF list (fake_etf)
    "JSWSTEEL": 1050.0, "NESTLEIND": 2400.0, "DABUR": 520.0, "VEDL": 460.0, "SAIL": 130.0, "ULTRACEMCO": 12000.0,
    "AMBUJACEM": 600.0, "TVSMOTOR": 3400.0,
    "ORIONPOLY": 140.0,       # a made-up company: the demo's loss-years case (fake_fundamentals), not a well-known profitable one
    # US: the companies the screener lists, Apple among them
    "AAPL": 183.0, "MSFT": 510.0, "XOM": 112.0, "JPM": 300.0, "KO": 68.0, "NUE": 140.0, "NVDA": 183.2,
    # the markets strip's other tiles: the S&P 500, the dollar in rupees and gold in dollars an ounce
    "^GSPC": 6700.0, "USDINR=X": 88.7, "GC=F": 2650.0,
}

# shares outstanding, in crore (India) or millions (US), so a market value is always shares x the same price
SHARES = {
    "RELIANCE": 1353.25, "TCS": 361.81, "INFY": 415.29, "HDFCBANK": 1541.67, "ICICIBANK": 712.0, "SBIN": 892.56,
    "AXISBANK": 309.5, "ITC": 1251.2, "HINDUNILVR": 234.96, "HCLTECH": 271.36, "WIPRO": 1046.0, "LT": 137.5,
    "BHARTIARTL": 609.0, "TATASTEEL": 1248.0, "ONGC": 1258.0, "NTPC": 969.67, "COALINDIA": 616.27, "MARUTI": 31.44,
    "JSWSTEEL": 244.5, "NESTLEIND": 192.8, "DABUR": 177.4, "VEDL": 391.0, "SAIL": 413.05, "ULTRACEMCO": 29.47,
    "AMBUJACEM": 246.3, "TVSMOTOR": 47.5, "ORIONPOLY": 60.0,
    "AAPL": 14840.0, "MSFT": 7430.0, "XOM": 4300.0, "JPM": 2760.0, "KO": 4300.0, "NUE": 230.0, "NVDA": 24300.0,
}

# the exchange's own names and broad sectors (its "macro" sector names for India) for the same companies, so the fake broker's instrument list, the screener's index
# and holdings read like the real thing ("HDFC Bank Ltd", Financials) instead of names built from tickers ("Hdfcbank")
COMPANIES = {
    "RELIANCE": ("Reliance Industries Ltd", "Energy"), "TCS": ("Tata Consultancy Services Ltd", "Information Technology"),
    "INFY": ("Infosys Ltd", "Information Technology"), "HDFCBANK": ("HDFC Bank Ltd", "Financial Services"),
    "ICICIBANK": ("ICICI Bank Ltd", "Financial Services"), "SBIN": ("State Bank of India", "Financial Services"),
    "AXISBANK": ("Axis Bank Ltd", "Financial Services"), "ITC": ("ITC Ltd", "Fast Moving Consumer Goods"),
    "HINDUNILVR": ("Hindustan Unilever Ltd", "Fast Moving Consumer Goods"), "HCLTECH": ("HCL Technologies Ltd", "Information Technology"),
    "WIPRO": ("Wipro Ltd", "Information Technology"), "LT": ("Larsen & Toubro Ltd", "Industrials"),
    "BHARTIARTL": ("Bharti Airtel Ltd", "Telecommunication"), "TATASTEEL": ("Tata Steel Ltd", "Commodities"),
    "JSWSTEEL": ("JSW Steel Ltd", "Commodities"), "ONGC": ("Oil and Natural Gas Corporation Ltd", "Energy"),
    "NTPC": ("NTPC Ltd", "Utilities"), "COALINDIA": ("Coal India Ltd", "Energy"), "MARUTI": ("Maruti Suzuki India Ltd", "Consumer Discretionary"),
    "NESTLEIND": ("Nestle India Ltd", "Fast Moving Consumer Goods"), "DABUR": ("Dabur India Ltd", "Fast Moving Consumer Goods"),
    "VEDL": ("Vedanta Ltd", "Commodities"), "SAIL": ("Steel Authority of India Ltd", "Commodities"),
    "ULTRACEMCO": ("UltraTech Cement Ltd", "Commodities"), "AMBUJACEM": ("Ambuja Cements Ltd", "Commodities"),
    "TVSMOTOR": ("TVS Motor Company Ltd", "Consumer Discretionary"), "ORIONPOLY": ("Orion Polymers Ltd", "Commodities"),
    "AAPL": ("Apple Inc.", "Information Technology"), "MSFT": ("Microsoft Corp.", "Information Technology"),
    "XOM": ("Exxon Mobil Corp.", "Energy"), "JPM": ("JPMorgan Chase & Co.", "Financials"), "KO": ("Coca-Cola Co.", "Consumer Staples"),
    "NUE": ("Nucor Corp.", "Materials"),
}

# exchange-traded funds the fake broker lists (the same ones the ETF vs NAV page reads, tests/fake_etf.py)
ETF_NAMES = {"NIFTYBEES": "Nippon India ETF Nifty 50 BeES", "GOLDBEES": "Nippon India ETF Gold BeES",
             "SILVERBEES": "Nippon India Silver ETF", "BANKBEES": "Nippon India ETF Nifty Bank BeES",
             "LIQUIDBEES": "Nippon India ETF Nifty 1D Rate Liquid BeES"}

# the quote site's tickers for the same instruments
YAHOO = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK", "^BSESN": "SENSEX", "^INDIAVIX": "INDIA VIX", "^CRSLDX": "NIFTY 500"}
US_NAMES = {"AAPL", "MSFT", "XOM", "JPM", "KO", "NUE", "NVDA", "^GSPC", "USDINR=X", "GC=F"}
BROAD = {"NIFTY 50", "NIFTY 500", "SENSEX", "NIFTY 100", "NIFTY NEXT 50"}     # move together, NIFTY 50's wave
SESSION = {"IN": ((9, 15), (15, 30), IST), "US": ((9, 30), (16, 0), ET)}


def name_of(symbol: str) -> str | None:
    """A company's or ETF's listed name, if the demo world knows it."""
    return COMPANIES.get(symbol, (ETF_NAMES.get(symbol),))[0]


def sector_of(symbol: str) -> str | None:
    hit = COMPANIES.get(symbol)
    return hit[1] if hit else None


def canonical(name: str) -> str:
    """The broker's name for a quote-site ticker (^NSEI -> NIFTY 50, RELIANCE.NS -> RELIANCE); others as they are."""
    if name in YAHOO:
        return YAHOO[name]
    return name[:-3] if name.endswith((".NS", ".BO")) else name


def known(name: str) -> bool:
    return canonical(name) in LEVELS


def market_of(name: str) -> str:
    return "US" if canonical(name) in US_NAMES else "IN"


@functools.lru_cache(maxsize=4096)
def trading_day(market: str, d: date) -> bool:
    from app.data.calendar import is_trading_day
    return is_trading_day(market, d)


def on_trading_day(d: date, market: str = "IN", back: bool = False) -> date:
    """The first trading day on or after `d` (before it with `back`, for past events). The exchange's events (ex-dates, results meetings, data releases) fall on
    trading days, so the demo's dates, which are counted from today, are moved to one instead of landing on a weekend."""
    while not trading_day(market, d):
        d += timedelta(days=-1 if back else 1)
    return d


def session_clock(now: datetime | None = None, market: str = "IN") -> datetime:
    """The time of the market's last trade: now while it is open (09:15 to 15:30 IST on a trading day; 09:30 to 16:00
    New York time for the US), else the close of the latest session. Out of hours quotes stand still at that close and
    say when it was, as the real ones do, so a page never claims a price from a moment nobody traded."""
    (oh, om), (ch, cm), tz = SESSION[market]
    now = (now or datetime.now(tz)).astimezone(tz)
    close = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if trading_day(market, now.date()) and now >= now.replace(hour=oh, minute=om, second=0, microsecond=0):
        return min(now, close)
    day = close - timedelta(days=1)
    while not trading_day(market, day.date()):
        day -= timedelta(days=1)
    return day


def last_close(market: str = "IN", now: datetime | None = None) -> datetime:
    """The close of the latest session that has ended: today's after the close, else the trading day before's."""
    (_, _), (ch, cm), tz = SESSION[market]
    now = (now or datetime.now(tz)).astimezone(tz)
    day = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if now < day:
        day -= timedelta(days=1)
    while not trading_day(market, day.date()):
        day -= timedelta(days=1)
    return day


def previous_close(market: str = "IN", now: datetime | None = None) -> datetime:
    """The close before the price now: the last close while the market is open, else the session's before it."""
    clock = session_clock(now, market)
    c = last_close(market, now)
    if clock < c or clock == c:          # out of hours: the price now is that close; the one before it is the day before's
        day = c - timedelta(days=1)
        while not trading_day(market, day.date()):
            day -= timedelta(days=1)
        return day
    return c


TRACKS = {"NIFTY 50", "NIFTY 500", "NIFTY 100", "NIFTY NEXT 50"}    # exactly NIFTY 50's wave (NIFTY 500 stays 0.92 of it)
AMP = {"USDINR=X": 0.012, "GC=F": 0.05, "^GSPC": 0.05, "NIFTY BANK": 0.06, "INDIA VIX": 0.15}     # how far a name swings


def _unit(name: str, salt: str) -> float:
    """A steady number in [0, 1) for a name: its own, whatever its level, spread over the range (never a handful of values)."""
    return (zlib.crc32(f"{salt}|{name}".encode()) % 10007) / 10007


def _phase(name: str) -> float:
    key = "NIFTY 50" if name in BROAD else name
    return 2 * math.pi * _unit(key, "phase")                   # each name keeps its own rhythm whatever its level


def _shape(name: str, epoch: float) -> float:
    """A name's wave: the broad Indian indices share NIFTY 50's, with SENSEX and the others on top of it a little of their
    own; every other name has its own phase, swing, period and a faster wave on top, so no two lines (or day changes, or
    distances from a 52-week high) are the same by accident."""
    d = epoch / 86400
    key = "NIFTY 50" if name in BROAD else name
    amp = 0.05 if name in BROAD else AMP.get(name, 0.05 + 0.05 * _unit(name, "amp"))
    wave = amp * math.sin(d / (11 if name in BROAD else 8 + 6 * _unit(key, "period")) + _phase(name))
    if name not in TRACKS:
        own = 0.004 if name in BROAD else amp * 0.4
        wave += own * math.sin(d / (2.3 + 2 * _unit(name, "fast")) + 2 * math.pi * _unit(name, "phase2"))
    return math.exp(0.0003 * (d - 20000)) * (1 + wave)


def base(name: str) -> float:
    """The level a name closed at last; one the table doesn't know gets a steady made-up level of its own."""
    name = canonical(name)
    return LEVELS.get(name) or float(100 + zlib.crc32(name.encode()) % 3000)


def level(name: str) -> float | None:
    """The table's level for a name (the latest close), by the broker's name or the quote site's ticker, else None."""
    return LEVELS.get(canonical(name))


def price(name: str, when: datetime | float, now: datetime | None = None) -> float:
    """The price of `name` at `when` (a time or seconds since 1970). The latest session's close is the table's level."""
    name = canonical(name)
    t = when.timestamp() if isinstance(when, datetime) else float(when)
    anchor = last_close(market_of(name), now).timestamp()
    if name in ETF_NAMES:
        t = min(t, anchor)           # the ETF list is read at the close and stands: the ETF page and holdings show one price
    return round(base(name) * _shape(name, t) / _shape(name, anchor), 2)


def last(name: str, now: datetime | None = None) -> float:
    """The price now: still at the last close out of hours."""
    return price(name, session_clock(now, market_of(name)), now)


def prev(name: str, now: datetime | None = None) -> float:
    """The close before the price now (what "today's change" is measured from)."""
    return price(name, previous_close(market_of(name), now), now)


def market_cap(symbol: str, at_price: float | None = None) -> float | None:
    """Market value in ₹ crore (India) or $ (US): shares x the price."""
    sh = SHARES.get(canonical(symbol))
    if sh is None:
        return None
    p = at_price if at_price is not None else last(symbol)
    return round(sh * p * (1e6 if market_of(symbol) == "US" else 1), 2)
