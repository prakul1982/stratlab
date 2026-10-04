"""Rupees a dollar for Indian tax: the State Bank of India's telegraphic transfer (TT) buying rate on the dates the
Income-tax Rules name, with the RBI reference rate as a labelled fallback where SBI's rate for a day isn't known.

The rules (checked 4 Oct 2026; the register in rules.py keeps the sources):
- Rule 115 (Income-tax Rules 1962; rule 206 of the 2026 Rules from tax year 2026-27): income in a foreign currency is
  converted at SBI's TT buying rate on the "specified date". For capital gains that is the last day of the month
  before the month of the transfer; for dividends, the last day of the month before the month the dividend is
  declared, distributed or paid. https://www.incometaxindia.gov.in/w/rule-115-2
- Rule 128(5): foreign tax credit (Form 67) uses the TT buying rate on the last day of the month before the month the
  foreign tax was paid or deducted.
- Schedule FA: values are converted at the TT buying rate on the date itself (acquisition, peak, 31 December, the
  income's date). https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-03/Step%20by%20Step%20Guide%20FA%20FSI.pdf
- SBI publishes no rate on Sundays and bank holidays. The rules give no fallback; the accepted practice (followed
  here) is the last rate SBI published before that day, and the date of the rate used is always shown.

Where the rates come from: SBI's daily forex card-rate sheets, as mirrored in a public archive that has read every
sheet since January 2020 (github.com/sahilgupta/sbi-fx-ratekeeper, the "TT BUY" column); and, for older dates or a gap
of more than a week, the RBI reference rate (github.com/the-solipsist/rbi-forex-reference-rates, from RBI and FBIL's
daily publications since 1998). The fallback is labelled wherever it is used, since a return should use SBI's rate.
Both are refreshed at most once a day and stored (fxhist:USD), so the tax pages never wait on them twice."""
import csv
import io
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from . import db
from .intel.net import UA, TTLCache

KEY = "fxhist:"                    # fxhist:USD = {"sbi": {day: rate}, "rbi": {day: rate}, "at": when fetched}
SBI_URL = "https://raw.githubusercontent.com/sahilgupta/sbi-fx-ratekeeper/main/csv_files/SBI_REFERENCE_RATES_{cur}.csv"
RBI_URL = "https://raw.githubusercontent.com/the-solipsist/rbi-forex-reference-rates/main/rbi_forex_reference_rates_wide.csv"
SBI = "SBI TT buying rate"
RBI = "RBI reference rate (fallback: SBI's rate for this date isn't known)"
STEP_BACK = 7                      # days looked back for the last published rate (a long weekend, Diwali)
REFRESH_AFTER = 20 * 3600          # stored rates older than this are fetched again...
RETRY_AFTER = 3600                 # ...but at most once an hour when the fetch fails
RBI_FROM = "2005-01-01"            # older reference rates aren't kept: nobody's foreign lots go back that far here
MIN_RATE, MAX_RATE = 20.0, 500.0   # rupees a dollar outside this is a misread line, not a rate

_mem = TTLCache(max_items=8, max_bytes=8 * 1024 * 1024)     # the parsed history, per currency
_tried = TTLCache(max_items=8, max_bytes=64 * 1024)          # when a fetch was last tried, per currency
_lock = threading.Lock()


# ---------- reading the published files ----------
def _num(v) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if MIN_RATE <= x <= MAX_RATE else None


def parse_sbi(text: str) -> dict[str, float]:
    """{day: TT buying rate} from SBI's daily sheets as the archive keeps them (DATE "2025-12-31 09:18", TT BUY).
    A sheet with no TT rate (0.00, as on some Saturdays) is left out. Two sheets on one day: the later one wins."""
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(text)):
        d, v = str(row.get("DATE") or "")[:10], _num(row.get("TT BUY"))
        if len(d) == 10 and d[4] == "-" and v:
            out[d] = v
    return out


def parse_rbi(text: str, cur: str = "USD") -> dict[str, float]:
    """{day: RBI reference rate} for one currency from the archive's wide file (date, AED, EUR, GBP, IDR, JPY, USD)."""
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(text)):
        d, v = str(row.get("date") or "")[:10], _num(row.get(cur))
        if len(d) == 10 and d >= RBI_FROM and v:
            out[d] = v
    return out


# ---------- stored ----------
def load(cur: str = "USD") -> dict:
    """{"sbi": {day: rate}, "rbi": {day: rate}, "at"}: empty dicts when nothing is stored yet."""
    hit = _mem.get(cur)
    if hit is not None:
        return hit
    got = db.json_value(db.get_setting(f"{KEY}{cur}"), {})
    got = got if isinstance(got, dict) else {}
    out = {"sbi": {k: float(v) for k, v in (got.get("sbi") or {}).items() if isinstance(v, (int, float)) and MIN_RATE <= v <= MAX_RATE},
           "rbi": {k: float(v) for k, v in (got.get("rbi") or {}).items() if isinstance(v, (int, float)) and MIN_RATE <= v <= MAX_RATE},
           "at": got.get("at")}
    _mem.set(cur, out, 600)
    return out


def save(sbi: dict[str, float], rbi: dict[str, float], cur: str = "USD"):
    data = {"sbi": sbi, "rbi": rbi, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    db.set_setting(f"{KEY}{cur}", json.dumps(data, separators=(",", ":")))
    _mem.set(cur, data, 600)


def forget():
    """Drop what is held in memory (tests, or after the stored rates are replaced by hand)."""
    _mem.clear()
    _tried.clear()


def _get(url: str) -> str:
    with httpx.Client(timeout=20, headers={"User-Agent": UA}, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def refresh(cur: str = "USD") -> bool:
    """Fetch both histories again and store them. A source that fails keeps what was stored. True when either came."""
    old = load(cur)
    sbi, rbi = old["sbi"], old["rbi"]
    got = False
    try:
        new = parse_sbi(_get(SBI_URL.format(cur=cur)))
        if len(new) > 100:
            sbi, got = {**sbi, **new}, True
    except Exception as e:
        print("SBI TT rates:", str(e)[:120])
    try:
        new = parse_rbi(_get(RBI_URL), cur)
        if len(new) > 100:
            rbi, got = {**rbi, **new}, True
    except Exception as e:
        print("RBI reference rates:", str(e)[:120])
    if got:
        save(sbi, rbi, cur)
    return got


def ensure(cur: str = "USD", fetch: bool = True) -> dict:
    """The stored history, fetched again first when it is a day old (at most once an hour when that fails)."""
    got = load(cur)
    if not fetch:
        return got
    try:
        age = time.time() - datetime.fromisoformat(got["at"]).timestamp() if got["at"] else None
    except (TypeError, ValueError):
        age = None
    if age is not None and age < REFRESH_AFTER:
        return got
    with _lock:
        if _tried.get(cur):
            return load(cur)
        _tried.set(cur, True, RETRY_AFTER)
    refresh(cur)
    return load(cur)


# ---------- the rate for a date ----------
def _back(rates: dict[str, float], day: str, days: int = STEP_BACK) -> tuple[str, float] | None:
    d = date.fromisoformat(day)
    for i in range(days + 1):
        k = (d - timedelta(days=i)).isoformat()
        if k in rates:
            return k, rates[k]
    return None


def rate_on(hist: dict, day: str) -> dict | None:
    """The rate for a day: SBI's TT buying rate that day, or the last one it published in the week before; else the
    RBI reference rate the same way, labelled as the fallback. {rate, on (the rate's own date), asked, source,
    fallback} or None when neither is known."""
    hit = _back(hist.get("sbi") or {}, day)
    if hit:
        return {"rate": hit[1], "on": hit[0], "asked": day, "source": SBI, "fallback": False}
    hit = _back(hist.get("rbi") or {}, day)
    if hit:
        return {"rate": hit[1], "on": hit[0], "asked": day, "source": RBI, "fallback": True}
    return None


def month_end_before(day: str) -> str:
    """The last day of the month before the one `day` is in: Rule 115's specified date for capital gains and
    dividends (2025-08-14 -> 2025-07-31)."""
    d = date.fromisoformat(day)
    return (d.replace(day=1) - timedelta(days=1)).isoformat()


def rule115(hist: dict, day: str) -> dict | None:
    """The rate Rule 115 (and Rule 128 for the foreign tax credit) uses for income arising on `day`: the TT buying
    rate on the last day of the month before."""
    got = rate_on(hist, month_end_before(day))
    return {**got, "event": day} if got else None
