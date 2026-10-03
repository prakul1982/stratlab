"""Indian currency futures (NSE's currency segment, CDS), through the same Kite login as Indian stocks: USDINR,
EURINR, GBPINR and JPYINR, and the cross pairs EURUSD, GBPUSD and USDJPY, front month, in whole lots. Built exactly
like MCX futures (see mcx.py).

One lot is 1,000 dollars, euros or pounds, or 100,000 yen. Rupee pairs are priced in rupees per unit of the currency
(JPYINR per 100 yen), so a lot is 1,000 price units. Cross pairs are priced in the second currency (dollars per euro or
pound, yen per dollar), one lot being 1,000 euros, pounds or dollars, so their profit is counted in dollars or yen; the
exchange settles it in rupees at the RBI reference rate of the day. The segment trades 09:00 to 17:00 IST and closes on its own holiday list."""
from .mcx import MCXProvider

# pair: (name, price units in one lot, what one price unit is, currency of the price)
CONTRACTS = {
    "USDINR": ("US dollar – rupee", 1000, "US dollar"), "EURINR": ("Euro – rupee", 1000, "euro"),
    "GBPINR": ("British pound – rupee", 1000, "pound"), "JPYINR": ("Japanese yen – rupee", 1000, "100 yen"),
    "EURUSD": ("Euro – US dollar", 1000, "euro, in dollars", "USD"),
    "GBPUSD": ("British pound – US dollar", 1000, "pound, in dollars", "USD"),
    "USDJPY": ("US dollar – Japanese yen", 1000, "dollar, in yen", "JPY"),
}
DEFAULTS = ["USDINR", "EURINR", "GBPINR", "JPYINR"]
ALIASES = {"USD": "USDINR", "DOLLAR": "USDINR", "USD/INR": "USDINR", "USD INR": "USDINR", "EUR": "EURINR", "EURO": "EURINR",
           "EUR/INR": "EURINR", "GBP": "GBPINR", "POUND": "GBPINR", "GBP/INR": "GBPINR", "JPY": "JPYINR", "YEN": "JPYINR",
           "JPY/INR": "JPYINR", "EUR/USD": "EURUSD", "EUR USD": "EURUSD", "GBP/USD": "GBPUSD", "GBP USD": "GBPUSD",
           "CABLE": "GBPUSD", "USD/JPY": "USDJPY", "USD JPY": "USDJPY"}
PER_DAY = {"1h": 8, "15m": 32, "5m": 96}               # 09:00 to 17:00


class CDSProvider(MCXProvider):
    market = exchange = "CDS"
    contracts, default_names, aliases, per_day = CONTRACTS, DEFAULTS, ALIASES, PER_DAY
    noun = "Currency futures"
