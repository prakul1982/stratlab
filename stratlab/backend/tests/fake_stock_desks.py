"""Made-up exchange files in the exchange's own formats for the per-stock desks (stock futures, stock lending, margin
funding), for any trading day, for the desks' tests and the browser tests' fake world. The real samples these copy
are in fixtures/stock_desks (trimmed from the exchange's files for 30 Sep and 1 Oct 2026).

The made-up market, every trading day:
- RELIANCE's futures rise with open interest rising (a long buildup every day); AMBUJACEM's MWPL use is over 95%
  (no fresh positions); SAIL's sits near 82%; the others between 20% and 50%.
- RELIANCE lends every day in two series, HDFCBANK on even days, SBIN once a week; TCS is eligible and never lends.
- Every stock below has margin funding; RELIANCE's grows a little each day."""
import functools
import gzip
import io
import random
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "stock_desks"
# symbol: (price, lot, MWPL use %, shares issued)
STOCKS = {"RELIANCE": (1167.0, 500, 25.0, 13532538722), "HDFCBANK": (720.0, 650, 28.0, 15416700168),
          "TCS": (3050.0, 175, 22.0, 3618087518), "INFY": (1500.0, 400, 30.0, 4152920000), "ITC": (410.0, 1600, 35.0, 12512000000),
          "SBIN": (815.0, 750, 40.0, 8925611590), "ICICIBANK": (1250.0, 700, 32.0, 7120000000),
          "AMBUJACEM": (362.0, 1200, 96.5, 2484817186), "SAIL": (174.0, 4700, 82.0, 4130525289)}
CASH_ONLY = {"WIPRO": (301.6, 10460000000), "LT": (3600.0, 1375000000), "TATASTEEL": (150.0, 12480000000),
             "BHARTIARTL": (1900.0, 6090000000), "ASIANPAINT": (2500.0, 959200000)}
FO_HEAD = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,"
           "FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,"
           "TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4")
CM_HEAD = FO_HEAD


def trading(d: date) -> bool:
    from app.data.calendar import is_trading_day
    return is_trading_day("IN", d)


@functools.lru_cache(maxsize=4096)
def _n(d: date) -> int:
    """Trading days from a fixed start, so each day's numbers follow on from the day before's."""
    n, x = 0, date(2025, 1, 1)
    while x < d:
        x += timedelta(days=1)
        n += trading(x)
    return n


def last_tuesday(y: int, m: int) -> date:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != 1:
        d -= timedelta(days=1)
    return d


def expiries(d: date) -> list[date]:
    out, y, m = [], d.year, d.month
    while len(out) < 3:
        e = last_tuesday(y, m)
        if e >= d:
            out.append(e)
        y, m = (y + (m == 12), m % 12 + 1)
    return out


def price(sym: str, d: date) -> tuple[float, float]:
    """(close, previous close): a drift seeded by the stock and the day; RELIANCE rises every day. Around the level the
    demo world's price table (fake_prices) gives the stock, so the desks show the price every other page shows;
    RELIANCE's rise reaches that level on the latest trading day."""
    from tests import fake_prices
    base = fake_prices.level(sym) or STOCKS.get(sym, (CASH_ONLY.get(sym, (100.0,))[0],))[0]
    n = _n(d)
    latest = _n(fake_prices.last_close("IN").date())

    def at(k):
        if sym == "RELIANCE":
            return round(base * (1 + 0.0004 * (k - latest)), 2)
        r = random.Random(f"{sym}:{k}")
        return round(base * (1 + 0.04 * r.uniform(-1, 1)), 2)
    return at(n), at(n - 1)


def oi(sym: str, d: date) -> tuple[int, int]:
    """(total futures open interest, the day's change): RELIANCE's grows every day."""
    lot = STOCKS[sym][1]
    n = _n(d)

    def at(k):
        if sym == "RELIANCE":
            return int((300000 + 600 * (k - 400)) * lot)
        return int(random.Random(f"oi:{sym}:{k}").uniform(190000, 210000)) * lot
    return at(n), at(n) - at(n - 1)


def fo_csv(d: date) -> str:
    rows = [FO_HEAD]
    exps = expiries(d)
    for sym, (_, lot, _, _) in STOCKS.items():
        close, prev = price(sym, d)
        total, chg = oi(sym, d)
        days_left = (exps[0] - d).days
        near_share = 0.98 if days_left > 7 else 0.55          # positions move to the next expiry in its last week
        parts = [int(total * near_share) // lot * lot, 0, 0]
        parts[2] = int(total * 0.01) // lot * lot
        parts[1] = total - parts[0] - parts[2]
        for i, e in enumerate(exps):
            fut = round(close * (1 + 0.006 * (i + 1)), 2)
            pfut = round(prev * (1 + 0.006 * (i + 1)), 2)
            c = chg if i == 0 else 0
            rows.append(f"{d},{d},FO,NSE,STF,{50000 + i},,{sym},,{e},{e},,,{sym}{e:%y%b}FUT,{pfut},{fut},{pfut},{fut},{fut},"
                        f"{pfut},{close},{fut},{parts[i]},{c},{1000 // (i + 1)},{fut * 1000 * lot:.2f},900,F1,{lot},,,,,")
    rows.append(f"{d},{d},FO,NSE,IDF,35001,,NIFTY,,{exps[0]},{exps[0]},,,NIFTY{exps[0]:%y%b}FUT,25000,25100,24900,25050,25050,"
                f"25000,25010,25050,1500000,1000,100,1.0,10,F1,75,,,,,")
    return "\n".join(rows) + "\n"


def combine_csv(d: date) -> str:
    rows = ["Date, ISIN, Scrip Name, NSE Symbol, MWPL, Open Interest, Future Equivalent Open Interest, Limit for Next Day"]
    for sym, (_, lot, use, _) in STOCKS.items():
        total, _ = oi(sym, d)
        pct = use + (0.0 if sym in ("AMBUJACEM",) else random.Random(f"mw:{sym}:{_n(d)}").uniform(-1.5, 1.5))
        feq = total * 0.8
        mwpl = int(feq / (pct / 100))
        limit = "No Fresh Positions" if sym == "AMBUJACEM" else str(int(mwpl * 0.95 - feq))
        rows.append(f"{d:%d-%b-%Y}".upper() + f",INE000X01010,{sym} LIMITED,{sym},{mwpl},{total},{feq:.4f},{limit}")
    return "\n".join(rows) + "\n"


def cash_csv(d: date) -> str:
    rows = [CM_HEAD]
    for sym in [*STOCKS, *CASH_ONLY]:
        close, prev = price(sym, d)
        rows.append(f"{d},{d},CM,NSE,STK,1,INE000X01010,{sym},EQ,,,,,{sym} LIMITED,{prev},{close},{prev},{close},{close},{prev},,"
                    f"{close},,,100000,1000000.00,1000,F1,1,,,,,")
    return "\n".join(rows) + "\n"


def _slb_line(sym: str, series: str, expiry: date, fee: float, qty: int, d: date, trades: int) -> str:
    return (f"{sym + ' LIMITED':<30},{sym:<10},{series},{expiry:%d-%b-%Y}".upper() + f",N,{fee:010.2f},{fee:010.2f},"
            f"{fee * 1.2:010.2f},{fee * 0.8:010.2f},{fee:010.2f},    ,{qty:>14},{qty * fee:>18.2f},{fee * 2:010.2f},"
            f"{0.01:010.2f}," + f"{d:%d-%b-%Y}".upper() + f",{trades:>8}")


def slb_dat(d: date) -> str:
    n = _n(d)
    e1, e2 = expiries(d + timedelta(days=20))[:2]
    lines = []
    close, _ = price("RELIANCE", d)
    lines.append(_slb_line("RELIANCE", "X1", e1, round(close * 0.0006, 2), 80000 + 100 * (n % 50), d, 9))
    lines.append(_slb_line("RELIANCE", "X2", e2, round(close * 0.0012, 2), 10000, d, 3))
    if n % 2 == 0:
        lines.append(_slb_line("HDFCBANK", "X1", e1, 0.3, 244370, d, 51))
    if n % 5 == 0:
        lines.append(_slb_line("SBIN", "X1", e1, 1.25, 5000, d, 2))
    return "\n".join(lines) + "\n"


def eligible_csv() -> str:
    syms = [*STOCKS, "WIPRO", "LT"] + [f"CO{i}" for i in range(20)]
    return "Sr.No.,Symbol,Series,Normal Eligibility,Recall Eligibility,Repay Eligibility,Market Type\n" + \
        "\n".join(f"{i},{s},01,E,D,D,N" for i, s in enumerate(syms, 1)) + "\n"


def mtf_csv(d: date) -> str:
    n = _n(d)
    rows, total = [], 0.0
    for sym in [*STOCKS, *CASH_ONLY]:
        close, _ = price(sym, d)
        issued = STOCKS[sym][3] if sym in STOCKS else CASH_ONLY[sym][1]
        share = 0.0016 + (0.00002 * n if sym == "RELIANCE" else random.Random(f"mtf:{sym}:{n}").uniform(-0.0001, 0.0001))
        if sym == "SBIN":
            share = 0.012
        qty = int(issued * share)
        lakh = round(qty * close * 0.97 / 1e5, 2)
        total += lakh
        rows.append(f"{sym},{sym} LIMITED,{qty},{lakh}")
    start = round(total * 0.995, 2)
    head = ["SEBI REPORT AS ON Reporting date " + f"{d:%d-%b-%Y}".upper() + ",,,",
            ",,,", ",,,", "Sr.No.,Particulars,Rs. In Lakhs ,",
            f"1,Scripwise Total Outstanding on the beginning of the day,{start},",
            f"2,Fresh Exposure taken during the day,{round(total * 0.03, 2)},",
            f"3,Exposure liquidated during the day,{round(total * 0.03 - (total - start), 2)},",
            f"4,Net scripwise outstanding at the end of the day,{round(total, 2)},", ",,,", ",,,",
            "Symbol,Name,Qty Fin by all the members(No.of Shares),Amt Fin by all the members(Rs. In Lakhs)"]
    return "\n".join(head + rows + [",,,", " * Figures are rounded to the nearest decimal. ,,,"]) + "\n"


def security_csv() -> str:
    head = (FIXTURES / "NSE_CM_security_01102026.csv").read_text().splitlines()[0]
    cols = head.split(",")
    out = [head]
    every = {**{s: v[3] for s, v in STOCKS.items()}, **{s: v[1] for s, v in CASH_ONLY.items()}, **{f"CO{i}": 1000000 for i in range(120)}}
    for sym, n in every.items():
        r = {c: "" for c in cols}
        r.update(FinInstrmId="1", TckrSymb=sym, SctySrs="EQ", FinInstrmNm=f"{sym} LIMITED", IssdCptl=f"{float(n):.14E}")
        out.append(",".join(r[c] for c in cols))
    return "\n".join(out) + "\n"


def _zip(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text)
    return buf.getvalue()


def _d(dd: str, mm: str, yy: str) -> date:
    return date(int(yy) + (2000 if len(yy) == 2 else 0), int(mm), int(dd))


def answer(path: str, today: date | None = None) -> tuple[int, bytes] | None:
    """(status, body) for one of the desks' files on the exchange's archive host; None for any other path. Every
    trading day up to today is published."""
    today = today or date.today()
    pats = (
        (r"/content/fo/BhavCopy_NSE_FO_0_0_0_(\d{4})(\d{2})(\d{2})_F_0000\.csv\.zip", "ymd", lambda d: _zip("fo.csv", fo_csv(d))),
        (r"/content/cm/BhavCopy_NSE_CM_0_0_0_(\d{4})(\d{2})(\d{2})_F_0000\.csv\.zip", "ymd", lambda d: _zip("cm.csv", cash_csv(d))),
        (r"/archives/nsccl/mwpl/combineoi_(\d{2})(\d{2})(\d{4})\.zip", "dmy", lambda d: _zip(f"combineoi_{d:%d%m%Y}.csv", combine_csv(d))),
        (r"/archives/slbs/bhavcopy/SLBM_BC_(\d{2})(\d{2})(\d{4})\.DAT", "dmy", lambda d: slb_dat(d).encode()),
        (r"/archives/slbs/seclist/SLB_ELG_SEC_(\d{2})(\d{2})(\d{4})\.csv", "dmy", lambda d: eligible_csv().encode()),
        (r"/content/equities/mrg_trading_(\d{2})(\d{2})(\d{2})\.zip", "dmy", lambda d: _zip(f"mrg_trading_{d:%d%m%Y}.csv", mtf_csv(d))),
        (r"/content/cm/NSE_CM_security_(\d{2})(\d{2})(\d{4})\.csv\.gz", "dmy", lambda d: gzip.compress(security_csv().encode())),
    )
    for pat, order, make in pats:
        m = re.fullmatch(pat, path)
        if not m:
            continue
        g = m.groups()
        d = date(int(g[0]), int(g[1]), int(g[2])) if order == "ymd" else _d(*g)
        if d > today or not trading(d):
            return 404, b"Not Found"
        return 200, make(d)
    return None
