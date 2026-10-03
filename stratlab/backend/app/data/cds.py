"""Indian currency futures (NSE's currency segment, CDS), through the same Kite login as Indian stocks: USDINR,
EURINR, GBPINR and JPYINR, front month, in whole lots. Built exactly like MCX futures (see mcx.py).

One lot is 1,000 dollars, euros or pounds, or 100,000 yen. Prices are rupees per unit of the currency (JPYINR per
100 yen), so a lot is 1,000 price units. The segment trades 09:00 to 17:00 IST and closes on its own holiday list."""
from .mcx import MCXProvider

# pair: (name, price units in one lot, what one price unit is)
CONTRACTS = {
    "USDINR": ("US dollar – rupee", 1000, "US dollar"), "EURINR": ("Euro – rupee", 1000, "euro"),
    "GBPINR": ("British pound – rupee", 1000, "pound"), "JPYINR": ("Japanese yen – rupee", 1000, "100 yen"),
}
DEFAULTS = ["USDINR", "EURINR", "GBPINR", "JPYINR"]
ALIASES = {"USD": "USDINR", "DOLLAR": "USDINR", "USD/INR": "USDINR", "USD INR": "USDINR", "EUR": "EURINR", "EURO": "EURINR",
           "EUR/INR": "EURINR", "GBP": "GBPINR", "POUND": "GBPINR", "GBP/INR": "GBPINR", "JPY": "JPYINR", "YEN": "JPYINR",
           "JPY/INR": "JPYINR"}
PER_DAY = {"1h": 8, "15m": 32, "5m": 96}               # 09:00 to 17:00


class CDSProvider(MCXProvider):
    market = exchange = "CDS"
    contracts, default_names, aliases, per_day = CONTRACTS, DEFAULTS, ALIASES, PER_DAY
    noun = "Currency futures"
