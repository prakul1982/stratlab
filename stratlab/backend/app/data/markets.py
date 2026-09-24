"""The markets StratLab knows about. `provider` names the data source that serves a
market; a market without one is shown as coming soon."""

MARKETS = [
    {"id": "IN", "name": "India", "venues": "NSE and BSE", "currency": "INR", "symbol": "₹",
     "tz": "Asia/Kolkata", "hours": {"open": "09:15", "close": "15:30", "days": "Mon–Fri"},
     "what": "Stocks, indices, F&O", "costs": "STT, stamp duty, GST", "provider": "kite", "brokerage": 20},
    {"id": "CRYPTO", "name": "Crypto", "venues": "Coinbase", "currency": "USD", "symbol": "₿",
     "tz": "UTC", "hours": {"open": None, "close": None, "days": "Every day, 24 hours"},
     "what": "BTC, ETH and hundreds of pairs", "costs": "0.1% exchange fee each way", "provider": "coinbase",
     "brokerage": 0},
    {"id": "US", "name": "United States", "venues": "NYSE and NASDAQ", "currency": "USD", "symbol": "$",
     "tz": "America/New_York", "hours": {"open": "09:30", "close": "16:00", "days": "Mon–Fri"},
     "what": "Stocks, ETFs", "costs": "Commission, SEC and FINRA fees", "provider": "yahoo", "brokerage": 0},
    {"id": "UK", "name": "United Kingdom", "venues": "London Stock Exchange", "currency": "GBP", "symbol": "£",
     "tz": "Europe/London", "hours": {"open": "08:00", "close": "16:30", "days": "Mon–Fri"},
     "what": "Stocks, ETFs", "costs": "0.5% stamp duty on share buys", "provider": "yahoo", "brokerage": 0},
    {"id": "EU", "name": "Europe", "venues": "Xetra and Euronext", "currency": "EUR", "symbol": "€",
     "tz": "Europe/Berlin", "hours": {"open": "09:00", "close": "17:30", "days": "Mon–Fri"},
     "what": "Stocks, ETFs", "costs": "Commission", "provider": "yahoo", "brokerage": 0},
    {"id": "JP", "name": "Japan", "venues": "Tokyo Stock Exchange", "currency": "JPY", "symbol": "¥",
     "tz": "Asia/Tokyo", "hours": {"open": "09:00", "close": "15:30", "days": "Mon–Fri"},
     "what": "Stocks, ETFs", "costs": "Commission", "provider": "yahoo", "brokerage": 0},
    {"id": "FX", "name": "Forex", "venues": "Major and minor pairs", "currency": "USD", "symbol": "€$",
     "tz": "UTC", "hours": {"open": None, "close": None, "days": "24 hours, Mon–Fri"},
     "what": "EUR/USD, USD/JPY, GBP/USD…", "costs": "Spread", "provider": "yahoo", "brokerage": 0},
    {"id": "CSV", "name": "Your own data", "venues": "Upload a CSV of candles", "currency": None, "symbol": "+",
     "tz": "UTC", "hours": None, "what": "Any instrument, any timeframe", "costs": "Brokerage you set",
     "provider": "csv", "brokerage": 0},
]

BY_ID = {m["id"]: m for m in MARKETS}
