"""A stand-in for the broker's API (KiteConnect): NSE stocks and indices, NFO futures and options, MCX futures, with
deterministic wavy candles at every interval, last prices and quotes. `online()` returns a KiteService that is
logged in and serves all of it, so every Indian feature runs in tests."""
import math
import zlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import rotation, sector_members, universes
from app.data.mcx import CONTRACTS
from app.kite_service import KiteService, today_ist
from tests.fake_names import name_of

IST = ZoneInfo("Asia/Kolkata")
STEP = {"day": 1440, "60minute": 60, "15minute": 15, "5minute": 5, "minute": 1}
OPTIONS = {"NIFTY": ("NIFTY 50", 50, 75), "BANKNIFTY": ("NIFTY BANK", 100, 35)}


def _base(name: str) -> float:
    return 100 + zlib.crc32(name.encode()) % 3000


def price_of(name: str, t: datetime) -> float:
    d = t.timestamp() / 86400
    b = _base(name)
    return round(b * (1 + 0.0003 * (d - 20000)) + b * 0.08 * math.sin(d / 11 + _base(name) % 7), 2)


def _expiries(n=3):
    from tests.fake_options_kite import _expiries as weekly
    return weekly()[:n]


class FakeKiteConnect:
    def __init__(self):
        self.rows = {"NSE": [], "NFO": [], "MCX": [], "BFO": [], "CDS": [], "BSE": []}
        token = 1000
        stocks = set()
        for p in universes.PRESETS["IN"]:
            stocks |= set(p["symbols"])
        for syms in sector_members.IN.values():
            stocks |= set(syms)
        indices = {"NIFTY 50", "NIFTY BANK", "INDIA VIX", "NIFTY 500"}
        for g in rotation.SECTORS.values():
            for v in (g.values() if isinstance(g, dict) else [g]):
                if isinstance(v, (list, tuple, set)):
                    indices |= {x for x in v if isinstance(x, str)}
        for s in sorted(indices):
            token += 1
            self.rows["NSE"].append({"instrument_token": token, "tradingsymbol": s, "name": s, "segment": "INDICES",
                                     "instrument_type": "EQ", "lot_size": 1, "expiry": None, "strike": 0})
        for s in sorted(stocks):
            token += 1
            self.rows["NSE"].append({"instrument_token": token, "tradingsymbol": s, "name": name_of(s), "segment": "NSE",
                                     "instrument_type": "EQ", "lot_size": 1, "expiry": None, "strike": 0})
        # NSE stocks in a restricted series: the broker lists them as SYMBOL-BE
        token += 1
        self.rows["NSE"].append({"instrument_token": token, "tradingsymbol": "SLOWCO-BE", "name": "SLOW CO", "segment": "NSE",
                                 "instrument_type": "EQ", "lot_size": 1, "expiry": None, "strike": 0})
        # BSE: one company listed only there, Reliance (on NSE too, so it stays NSE's) and a bond (not a stock)
        for ts, code, name, itype in (("TINYCO", 543210, "TINY CO", "EQ"), ("RELIANCE", 500325, "RELIANCE", "EQ"),
                                      ("GSEC2030", 700001, "GOVT BOND", "GS"), ("TBILL91", 978260, "978260", "EQ")):
            token += 1
            self.rows["BSE"].append({"instrument_token": token, "exchange_token": code, "tradingsymbol": ts, "name": name,
                                     "segment": "BSE", "instrument_type": itype, "lot_size": 1, "expiry": None, "strike": 0})
        for name, (_, gap, lot) in OPTIONS.items():
            for e in _expiries():
                token += 1
                self.rows["NFO"].append({"instrument_token": token, "tradingsymbol": f"{name}{e:%y%b}FUT".upper(), "name": name,
                                         "segment": "NFO-FUT", "instrument_type": "FUT", "lot_size": lot, "expiry": e, "strike": 0})
        for name in CONTRACTS:
            for i, e in enumerate(_expiries(2)):
                token += 1
                exp = e + timedelta(days=30 * i + 20)
                self.rows["MCX"].append({"instrument_token": token, "tradingsymbol": f"{name}{exp:%y%b}FUT".upper(), "name": name,
                                         "segment": "MCX-FUT", "instrument_type": "FUT", "lot_size": 1, "expiry": exp, "strike": 0})
        from app.data.cds import CONTRACTS as PAIRS
        for name in PAIRS:
            for i, e in enumerate(_expiries(2)):
                token += 1
                exp = e + timedelta(days=30 * i + 25)
                self.rows["CDS"].append({"instrument_token": token, "tradingsymbol": f"{name}{exp:%y%b}FUT".upper(), "name": name,
                                         "segment": "CDS-FUT", "instrument_type": "FUT", "lot_size": 1, "expiry": exp, "strike": 0})
        self.by_token = {r["instrument_token"]: r for rows in self.rows.values() for r in rows}
        self.by_key = {f"{ex}:{r['tradingsymbol']}": r for ex, rows in self.rows.items() for r in rows}
        self.calls = 0
        self.fail = None            # set to an exception to make every call raise it

    def _hit(self):
        self.calls += 1
        if self.fail:
            raise self.fail

    def set_access_token(self, tok):
        pass

    def login_url(self):
        return "https://kite.example.com/connect/login?v=3&api_key=fake"

    def instruments(self, exch):
        self._hit()
        return [dict(r) for r in self.rows.get(exch, [])]

    def historical_data(self, token, frm, to, interval, continuous=False, oi=False):
        self._hit()
        r = self.by_token.get(int(token))
        if not r:
            raise ValueError("invalid token")
        step = STEP[interval]
        out = []
        t = frm.replace(second=0, microsecond=0)
        if step == 1440:
            t = t.replace(hour=0, minute=0)
        else:
            t = t.replace(minute=(t.minute // step) * step)
        while t <= to:
            day_ok = t.weekday() < 5
            in_hours = step == 1440 or (t.hour, t.minute) >= (9, 15) and (t.hour, t.minute) < (15, 30)
            if day_ok and in_hours:
                o, c = price_of(r["tradingsymbol"], t), price_of(r["tradingsymbol"], t + timedelta(minutes=step))
                out.append({"date": t.replace(tzinfo=IST), "open": o, "high": max(o, c) * 1.004, "low": min(o, c) * 0.996,
                            "close": c, "volume": 1000})
            t += timedelta(minutes=step)
            if len(out) > 20000:
                break
        return out

    def ltp(self, keys):
        self._hit()
        now = datetime.now(IST)
        out = {}
        for k in keys:
            r = self.by_key.get(k)
            if r:
                out[k] = {"instrument_token": r["instrument_token"], "last_price": price_of(r["tradingsymbol"], now)}
        return out

    def quote(self, keys):
        self._hit()
        now = datetime.now(IST)
        out = {}
        for k in keys:
            r = self.by_key.get(k)
            if r:
                p = price_of(r["tradingsymbol"], now)
                out[k] = {"instrument_token": r["instrument_token"], "last_price": p, "volume": 1000,
                          "last_trade_time": now.replace(tzinfo=None, microsecond=0),
                          "ohlc": {"open": p * 0.99, "high": p * 1.01, "low": p * 0.98, "close": p * 0.995},
                          "depth": {"buy": [{"price": p - 0.05, "quantity": 100}], "sell": [{"price": p + 0.05, "quantity": 100}]}}
        return out


def online() -> KiteService:
    k = KiteService()
    fake = FakeKiteConnect()
    k.kite = fake
    k.access_token, k.token_day = "fake-token", today_ist()
    k._throttle = lambda: None
    return k
