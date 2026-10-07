"""Where the fake market's best-known instruments trade, shared by the fake broker (fake_kite) and the fake quote site
(fake_yahoo), so one instrument shows about the same price on every page of the demo world: NIFTY 50 near 25,000 on
the markets strip, in a backtest and at the closing auction; RELIANCE near the ₹1,408 its fundamentals page was read at.
Anything not listed keeps the fakes' made-up levels."""
import time

LEVELS = {
    # indices
    "NIFTY 50": 25000.0, "NIFTY BANK": 55000.0, "SENSEX": 82000.0, "INDIA VIX": 13.0, "NIFTY 500": 23000.0,
    # stocks (round numbers near their real levels)
    "RELIANCE": 1400.0, "TCS": 3050.0, "INFY": 1480.0, "HDFCBANK": 960.0, "ICICIBANK": 1350.0, "SBIN": 820.0,
    "AXISBANK": 1150.0, "ITC": 405.0, "HINDUNILVR": 2450.0, "HCLTECH": 1450.0, "WIPRO": 245.0, "LT": 3600.0,
    "BHARTIARTL": 1900.0, "TATASTEEL": 165.0, "ONGC": 240.0, "NTPC": 340.0, "COALINDIA": 385.0, "MARUTI": 12500.0,
    "NIFTYBEES": 270.0, "GOLDBEES": 81.5, "SILVERBEES": 104.0, "BANKBEES": 560.0, "LIQUIDBEES": 1000.0,
    "JSWSTEEL": 1050.0, "NESTLEIND": 2400.0, "DABUR": 520.0, "VEDL": 460.0, "SAIL": 130.0, "ULTRACEMCO": 12000.0,
    "AMBUJACEM": 600.0, "TVSMOTOR": 3400.0,
    # US: Apple near the fake company-data quote ($183.20, 52-week high $195.60), so its chart and header agree
    "AAPL": 183.0,
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
    "TVSMOTOR": ("TVS Motor Company Ltd", "Consumer Discretionary"),
    "AAPL": ("Apple Inc.", "Information Technology"), "MSFT": ("Microsoft Corp.", "Information Technology"),
    "XOM": ("Exxon Mobil Corp.", "Energy"), "JPM": ("JPMorgan Chase & Co.", "Financials"), "KO": ("Coca-Cola Co.", "Consumer Staples"),
    "NUE": ("Nucor Corp.", "Materials"),
}

# exchange-traded funds the fake broker lists (the same ones the ETF vs NAV page reads, tests/fake_etf.py)
ETF_NAMES = {"NIFTYBEES": "Nippon India ETF Nifty 50 BeES", "GOLDBEES": "Nippon India ETF Gold BeES",
             "SILVERBEES": "Nippon India Silver ETF", "BANKBEES": "Nippon India ETF Nifty Bank BeES",
             "LIQUIDBEES": "Nippon India ETF Nifty 1D Rate Liquid BeES"}


def name_of(symbol: str) -> str | None:
    """A company's or ETF's listed name, if the demo world knows it."""
    return COMPANIES.get(symbol, (ETF_NAMES.get(symbol),))[0]


def sector_of(symbol: str) -> str | None:
    hit = COMPANIES.get(symbol)
    return hit[1] if hit else None

# the quote site's tickers for the same instruments
YAHOO = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK", "^BSESN": "SENSEX", "^INDIAVIX": "INDIA VIX"}


def level(name: str, drift_from: float | None = None) -> float | None:
    """The level a name trades near, by the broker's name or the quote site's ticker (RELIANCE.NS), else None.
    Both fakes add a slow rise of 0.03% a day since a day of their own (`drift_from`, days since 1970); the base is
    taken back by that rise, so today's price lands near the level whichever fake draws it."""
    if name in YAHOO:
        v = LEVELS[YAHOO[name]]
    else:
        v = LEVELS.get(name[:-3] if name.endswith((".NS", ".BO")) else name)
    if v is None or drift_from is None:
        return v
    return v / (1 + 0.0003 * (time.time() / 86400 - drift_from))
