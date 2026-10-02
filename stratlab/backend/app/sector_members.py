"""The main stocks in each sector index and sector fund, for drilling from a sector into its stocks on the rotation
chart. These are the largest, most-traded members as of 2026, not the full official lists (those change with each
rebalance); a symbol the data source doesn't know is simply skipped."""

IN = {
    "NIFTY BANK": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "BANKBARODA", "PNB", "FEDERALBNK",
                   "IDFCFIRSTB", "AUBANK", "CANBK"],
    "NIFTY IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "PERSISTENT", "COFORGE", "MPHASIS", "OFSS"],
    "NIFTY AUTO": ["MARUTI", "M&M", "TMPV", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "TVSMOTOR", "ASHOKLEY", "BHARATFORG",
                   "BOSCHLTD", "MOTHERSON", "EXIDEIND", "TIINDIA", "MRF", "BALKRISIND"],
    "NIFTY FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "TATACONSUM", "DABUR", "GODREJCP", "MARICO", "COLPAL",
                   "UNITDSPR", "VBL", "PATANJALI", "RADICO", "EMAMILTD"],
    "NIFTY PHARMA": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "LUPIN", "ZYDUSLIFE", "AUROPHARMA", "TORNTPHARM", "ALKEM",
                     "MANKIND", "GLENMARK", "BIOCON", "IPCALAB", "LAURUSLABS", "ABBOTINDIA"],
    "NIFTY METAL": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "SAIL", "NMDC", "NATIONALUM", "HINDZINC",
                    "APLAPOLLO", "JSL", "HINDCOPPER", "ADANIENT", "WELCORP"],
    "NIFTY REALTY": ["DLF", "GODREJPROP", "LODHA", "OBEROIRLTY", "PRESTIGE", "PHOENIXLTD", "BRIGADE", "SOBHA", "ANANTRAJ"],
    "NIFTY ENERGY": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "BPCL", "IOC", "TATAPOWER", "ADANIGREEN",
                     "ADANIPOWER", "GAIL", "JSWENERGY", "NHPC"],
    "NIFTY MEDIA": ["ZEEL", "SUNTV", "PVRINOX", "NAZARA", "TIPSMUSIC", "SAREGAMA", "NETWORK18", "DBCORP"],
    "NIFTY PSU BANK": ["SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK", "INDIANB", "BANKINDIA", "IOB", "UCOBANK",
                       "CENTRALBK", "MAHABANK", "PSB"],
    "NIFTY PVT BANK": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK", "FEDERALBNK", "IDFCFIRSTB",
                       "BANDHANBNK", "RBLBANK", "CUB"],
    "NIFTY FIN SERVICE": ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE", "KOTAKBANK", "AXISBANK", "BAJAJFINSV", "SHRIRAMFIN",
                          "JIOFIN", "SBILIFE", "HDFCLIFE", "CHOLAFIN", "PFC", "RECLTD", "ICICIGI"],
    "NIFTY INFRA": ["RELIANCE", "LT", "BHARTIARTL", "NTPC", "POWERGRID", "ULTRACEMCO", "ONGC", "ADANIPORTS", "GRASIM",
                    "INDIGO", "APOLLOHOSP", "TATAPOWER", "SIEMENS", "AMBUJACEM"],
    "NIFTY HEALTHCARE": ["SUNPHARMA", "DIVISLAB", "CIPLA", "DRREDDY", "APOLLOHOSP", "MAXHEALTH", "LUPIN", "FORTIS",
                         "ZYDUSLIFE", "TORNTPHARM", "ALKEM", "AUROPHARMA", "GLENMARK", "BIOCON"],
    "NIFTY IND DEFENCE": ["HAL", "BEL", "BDL", "MAZDOCK", "SOLARINDS", "COCHINSHIP", "BEML", "DATAPATTNS", "GRSE", "ASTRAMICRO"],
    "NIFTY CAPITAL MKT": ["BSE", "MCX", "CDSL", "ANGELONE", "HDFCAMC", "CAMS", "KFINTECH", "NUVAMA", "MOTILALOFS", "IEX"],
    "NIFTY OIL AND GAS": ["RELIANCE", "ONGC", "IOC", "BPCL", "GAIL", "HINDPETRO", "OIL", "PETRONET", "IGL", "MGL", "GUJGASLTD"],
    "NIFTY CONSR DURBL": ["TITAN", "DIXON", "HAVELLS", "VOLTAS", "BLUESTARCO", "CROMPTON", "KALYANKJIL", "AMBER", "WHIRLPOOL",
                          "BATAINDIA"],
    "NIFTY CHEMICALS": ["PIDILITIND", "SRF", "SOLARINDS", "UPL", "DEEPAKNTR", "PIIND", "AARTIIND", "NAVINFLUOR", "TATACHEM"],
    "NIFTY COMMODITIES": ["RELIANCE", "ULTRACEMCO", "NTPC", "ONGC", "TATASTEEL", "JSWSTEEL", "COALINDIA", "HINDALCO",
                          "GRASIM", "VEDL", "PIDILITIND", "SHREECEM"],
    "NIFTY CPSE": ["NTPC", "ONGC", "POWERGRID", "COALINDIA", "BEL", "OIL", "NHPC", "SJVN", "NLCINDIA", "COCHINSHIP"],
    "NIFTY IND TOURISM": ["INDHOTEL", "INDIGO", "IRCTC", "JUBLFOOD", "EIHOTEL", "LEMONTREE", "CHALET", "DEVYANI", "WESTLIFE"],
}

US = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "ACN", "IBM", "QCOM", "TXN", "INTU", "NOW"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "AXP", "BLK", "C", "SCHW", "PGR", "CB"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "ISRG", "AMGN", "DHR", "PFE", "BSX", "SYK", "VRTX", "GILD"],
    "XLE": ["XOM", "CVX", "COP", "EOG", "WMB", "SLB", "PSX", "MPC", "OKE", "KMI", "VLO", "OXY", "BKR", "FANG"],
    "XLI": ["GE", "CAT", "RTX", "UBER", "HON", "UNP", "ETN", "BA", "DE", "LMT", "ADP", "GEV", "PH", "TT", "WM"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG", "LOW", "TJX", "SBUX", "NKE", "CMG", "ORLY", "MAR", "ABNB", "GM", "F"],
    "XLP": ["WMT", "COST", "PG", "KO", "PEP", "PM", "MDLZ", "MO", "CL", "TGT", "KMB", "KDP", "GIS", "STZ", "KR"],
    "XLU": ["NEE", "SO", "DUK", "CEG", "AEP", "SRE", "D", "VST", "EXC", "PCG", "XEL", "PEG", "ED", "WEC", "ETR"],
    "XLB": ["LIN", "SHW", "APD", "ECL", "FCX", "NEM", "CTVA", "DD", "NUE", "VMC", "MLM", "PPG", "DOW", "IFF", "LYB"],
    "XLRE": ["PLD", "AMT", "EQIX", "WELL", "SPG", "O", "PSA", "DLR", "CCI", "CBRE", "EXR", "AVB", "VICI", "IRM", "EQR"],
    "XLC": ["META", "GOOGL", "NFLX", "TMUS", "DIS", "CMCSA", "T", "VZ", "CHTR", "EA", "TTWO", "WBD", "OMC", "LYV"],
    "SMH": ["NVDA", "TSM", "AVGO", "AMD", "ASML", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC", "ADI", "INTC", "MRVL", "NXPI"],
    "IGV": ["MSFT", "ORCL", "CRM", "ADBE", "NOW", "INTU", "PANW", "PLTR", "CRWD", "SNPS", "CDNS", "WDAY", "FTNT", "ADSK", "DDOG"],
    "XBI": ["VRTX", "REGN", "GILD", "AMGN", "BIIB", "ALNY", "INCY", "EXEL", "NBIX", "SRPT", "BMRN", "UTHR", "IONS", "EXAS"],
    "KRE": ["CFG", "RF", "HBAN", "KEY", "FITB", "MTB", "ZION", "EWBC", "WAL", "FHN", "WBS", "CMA", "SNV", "PNFP"],
    "ITA": ["GE", "RTX", "BA", "LMT", "GD", "NOC", "TDG", "HWM", "LHX", "AXON", "TXT", "HEI", "CW", "HII"],
    "XOP": ["COP", "EOG", "OXY", "DVN", "FANG", "CTRA", "EQT", "APA", "MRO", "OVV", "AR", "RRC", "MTDR", "PR"],
    "GDX": ["NEM", "AEM", "GOLD", "WPM", "FNV", "KGC", "AU", "GFI", "RGLD", "AGI", "PAAS", "EGO"],
    "ITB": ["DHI", "LEN", "PHM", "NVR", "TOL", "HD", "LOW", "BLD", "MAS", "OC", "KBH", "MTH", "TMHC", "SHW"],
    "XRT": ["AMZN", "COST", "WMT", "TJX", "ROST", "BBY", "DG", "DLTR", "KR", "ULTA", "GPS", "ANF", "BURL", "M", "KSS"],
    "JETS": ["DAL", "UAL", "AAL", "LUV", "ALK", "JBLU", "SKYW", "ALGT", "RYAAY", "BA"],
}

US_NAMES = {"SMH": "Semiconductors", "IGV": "Software", "XBI": "Biotech", "KRE": "Regional banks", "ITA": "Aerospace & defense",
            "XOP": "Oil & gas producers", "GDX": "Gold miners", "ITB": "Homebuilders", "XRT": "Retail", "JETS": "Airlines",
            "TAN": "Solar", "IYT": "Transports", "CIBR": "Cybersecurity", "PAVE": "Infrastructure", "KBE": "Banks",
            "XHB": "Home & building"}

BY_MARKET = {"IN": IN, "US": US}


def members(market: str, symbol: str) -> list[str]:
    return BY_MARKET.get(market, {}).get(symbol, [])
