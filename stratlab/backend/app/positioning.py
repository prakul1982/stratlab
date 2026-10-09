"""Derivatives positioning: who holds what in index futures and options, and what the option chains show.

Three kinds of facts, each with its date:
- Participant-wise open interest and volume: the exchange's daily files of contracts held (and traded) long and short
  by clients, DIIs, FIIs and proprietary traders in index and stock futures and options, published each evening
  (fao_participant_oi_DDMMYYYY.csv and fao_participant_vol_DDMMYYYY.csv).
- FII/FPI and DII buying and selling in the cash market: the exchange's provisional numbers for the day, in ₹ crore.
- Option-chain facts for the index options: the put-call ratio by open interest and by volume, the max-pain strike,
  open interest and its change by strike, the strikes with the most call and put open interest, and the at-the-money
  implied volatility with its percentile and rank over StratLab's own recorded chains.

Facts and arithmetic only: nothing here reads a number as a signal, or says what anyone should do with it.

A job reads the exchange's files after they are published (from 18:40 India time, retried until 21:30), keeps a
history by day and fills in the past from the exchange's archives, a few files at a time and politely paced; at other
times it catches up on whatever an evening run missed (a restart, a server started on a weekend). The
option-chain history comes from the recorded option chains (options/recorder.py), one summary per day."""
import csv
import io
import json
import math
import re
import threading
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from . import db
from .intel.net import SourceError, TTLCache, num
from .data.expiries import cycle as expiry_cycle, fits as expiry_fits
from .newsletter import job as news_job
from .options.greeks import black76, implied_vol, years_to  # noqa: F401  (Black's formula lives with the Greeks)

IST = ZoneInfo("Asia/Kolkata")
UNDERLYINGS = (("NFO", "NIFTY"), ("NFO", "BANKNIFTY"), ("NFO", "FINNIFTY"), ("NFO", "MIDCPNIFTY"), ("BFO", "SENSEX"))
NAMES = {n: ex for ex, n in UNDERLYINGS}
PARTICIPANTS = (("client", "Client"), ("dii", "DII"), ("fii", "FII"), ("pro", "Pro"))
PARTICIPANT_NAME = dict(PARTICIPANTS) | {"total": "Total"}
# the exchange's column names (lower case, spaces collapsed) -> our keys
COLUMNS = {
    "future index long": "fut_idx_long", "future index short": "fut_idx_short",
    "future stock long": "fut_stk_long", "future stock short": "fut_stk_short",
    "option index call long": "opt_idx_call_long", "option index put long": "opt_idx_put_long",
    "option index call short": "opt_idx_call_short", "option index put short": "opt_idx_put_short",
    "option stock call long": "opt_stk_call_long", "option stock put long": "opt_stk_put_long",
    "option stock call short": "opt_stk_call_short", "option stock put short": "opt_stk_put_short",
    "total long contracts": "total_long", "total short contracts": "total_short",
}
KINDS = ("oi", "vol")
# each file at its address on the archive host, then the older host the exchange still answers on
FILE_URLS = ("https://nsearchives.nseindia.com/content/nsccl/fao_participant_{kind}_{d}.csv",
             "https://archives.nseindia.com/content/nsccl/fao_participant_{kind}_{d}.csv")
CASH_PATHS = ("/api/fiidiiTradeReact", "/api/fiidiiTradeNse")
CASH_PAGE = "https://www.nseindia.com/reports/fii-dii"
PUBLISH_FROM, PUBLISH_UNTIL = "18:40", "21:30"     # the job's window, India time: the files usually land 18:30-20:00
RETRY_MINUTES = 20
BACKFILL_DAYS = 365          # how far back the archives are read on a new server
BACKFILL_STEP = 25           # days of archive files read per run, so one run never hammers the exchange
MISS_RUN = 5                 # trading days in a row the archive hasn't got: it's refusing, not missing them
CATCH_UP_DAYS = 10           # recent days whose files the catch-up looks for when the evening run missed them
CATCH_UP_TRIES = 3           # times the catch-up asks for a recent day's file before it takes the day as not there
PACE = 1.5                   # seconds between two archive files
KEEP_CHAIN_DAYS = 400        # daily option-chain summaries kept per index
AROUND_LIVE = 40             # strikes each side of the money read for today's chain
NEAR = 15                    # strikes each side of the money the recorder keeps: the history's window
IV_MIN_DAYS = 20             # recorded days needed before the IV percentile and rank mean anything
RANGES = {"3m": 92, "6m": 183, "1y": 366, "all": 3660}
STATE_KEY = "pos:state"
SOURCE = "the exchange's daily participant-wise open interest and volume files, its provisional FII/DII cash market " \
         "numbers, and StratLab's own recordings of the option chains"
NOTE = ("Exchange data as published, and arithmetic on recorded option chains. These numbers describe positions that "
        "were open; they say nothing about what anyone will do next.")
_cache = TTLCache(max_items=200, max_bytes=8 * 1024 * 1024)
_lock = threading.Lock()


def ist_now() -> datetime:
    return datetime.now(IST)


# ---------- reading the exchange's files ----------
def _key(h) -> str:
    return re.sub(r"\s+", " ", str(h or "").replace("\t", " ")).strip().lower()


def _int(v) -> int | None:
    n = num(v)
    return int(round(n)) if n is not None else None


def _who(v) -> str | None:
    s = _key(v)
    if s in ("client", "clients"):
        return "client"
    if s.startswith("dii"):
        return "dii"
    if s.startswith(("fii", "fpi")):
        return "fii"
    if s.startswith("pro"):
        return "pro"
    if s.startswith("total"):
        return "total"
    return None


def _title_day(text: str) -> str | None:
    """The date in a file's title line: "... as on Oct 03, 2026" or "as on 03-Oct-2026"."""
    for pat, fmt in ((r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})", "%b %d %Y"), (r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", "%d %b %Y")):
        m = re.search(pat, text)
        if m:
            try:
                return datetime.strptime(" ".join(m.groups()).title(), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def participant_rows(text: str) -> dict:
    """One participant-wise file (open interest or volume): {"as_of": ISO day from its title or None, "rows":
    {"client"|"dii"|"fii"|"pro"|"total": {fut_idx_long: contracts, ...}}}. A page instead of the file, or a file
    without the four participants, is an error."""
    text = str(text or "").replace("\x00", "").lstrip("﻿")
    if not text.strip() or "<html" in text[:500].lower():
        raise ValueError("not a participant file")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    head = next((i for i, ln in enumerate(lines) if "client type" in ln.lower()), None)
    if head is None:
        raise ValueError("no header row")
    title = " ".join(lines[:head])
    reader = csv.reader(io.StringIO("\n".join(lines[head:])))
    cols = [COLUMNS.get(_key(h).strip('"')) for h in next(reader)]
    rows = {}
    for r in reader:
        who = _who(r[0] if r else "")
        if not who:
            continue
        rows[who] = {c: _int(v) for c, v in zip(cols, r) if c}
    if not all(p in rows for p, _ in PARTICIPANTS) or not any(rows["fii"].values()):
        raise ValueError("the four participants aren't all there")
    return {"as_of": _title_day(title), "rows": rows}


def cash_rows(data) -> dict:
    """The provisional cash-market numbers: {"as_of": ISO day, "fii": {"buy", "sell", "net"}, "dii": {...}} in ₹ crore."""
    rows = data.get("data") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("not a list")
    out: dict = {"as_of": None}
    for r in rows:
        if not isinstance(r, dict):
            continue
        cat = str(r.get("category") or "").upper()
        who = "fii" if ("FII" in cat or "FPI" in cat) else "dii" if "DII" in cat else None
        if not who:
            continue
        buy, sell, net = num(r.get("buyValue")), num(r.get("sellValue")), num(r.get("netValue"))
        if net is None and buy is not None and sell is not None:
            net = buy - sell
        out[who] = {"buy": buy, "sell": sell, "net": round(net, 2) if net is not None else None}
        try:
            out["as_of"] = datetime.strptime(str(r.get("date") or "").strip().title(), "%d-%b-%Y").date().isoformat()
        except ValueError:
            pass
    if "fii" not in out or "dii" not in out or not out["as_of"]:
        raise ValueError("FII and DII rows with a date weren't there")
    return out


class Feed:
    """The exchange's files and the cash numbers, through the exchange client (its cookies, browser headers and
    rate limit), with a breaker of its own: three outages in a row and it rests a minute. A file that isn't at any
    of its addresses (404) isn't an outage: it's not published yet, or the archive doesn't have that day."""
    name = "the exchange"

    def __init__(self, nse, sleep=time.sleep):
        self.nse, self.sleep = nse, sleep
        self._fails, self._down = 0, 0.0

    def _outage(self):
        self._fails += 1
        if self._fails >= 3:
            self._fails, self._down = 0, time.time() + 60

    def _text(self, url: str) -> str | None:
        """One file's text; None when it isn't there (404, or a page instead of the file)."""
        r = self._response(url)
        return r.text if r is not None else None

    def raw(self, url: str) -> bytes | None:
        """One file's bytes (a zip or a gzip as published); None when it isn't there. The per-stock desks
        (exchange_days.py) read the exchange's daily files through this, with the same cookies, retry and breaker."""
        r = self._response(url)
        return r.content if r is not None else None

    def _response(self, url: str):
        if time.time() < self._down:
            raise SourceError(self.name, "The exchange's files aren't answering right now. Try again in a minute.", busy=True)
        try:
            self.nse._prime()                        # the archive host checks for the cookies the website hands out
        except SourceError:
            pass
        for attempt in range(2):
            try:
                r = self.nse.http.get(url, headers={"Accept": "text/csv,text/plain,*/*", "Referer": "https://www.nseindia.com/"})
            except httpx.HTTPError as e:
                self._outage()
                raise SourceError(self.name, f"Couldn't reach the exchange's files ({e.__class__.__name__}).", busy=True) from None
            if r.status_code in (401, 403, 429) and attempt == 0:
                self.sleep(2.0)
                try:
                    self.nse._prime(force=True)
                except SourceError:
                    pass
                continue
            break
        if r.status_code == 404:
            self._fails = 0
            return None
        if r.status_code == 429 or r.status_code >= 500 or r.status_code in (401, 403):
            self._outage()
            raise SourceError(self.name, f"The exchange's file was refused ({r.status_code}).", busy=True)
        if r.status_code >= 400:
            raise SourceError(self.name, f"The exchange's file was refused ({r.status_code}).")
        self._fails = 0
        if b"<html" in r.content[:500].lower():
            return None
        return r

    def participants(self, kind: str, day: date) -> dict | None:
        """A day's participant-wise file, parsed; None when it isn't published (or archived)."""
        shape = False
        for url in FILE_URLS:
            text = self._text(url.format(kind=kind, d=day.strftime("%d%m%Y")))
            if text is None:
                continue
            try:
                got = participant_rows(text)
            except ValueError:
                shape = True
                continue
            if got["as_of"] and got["as_of"] != day.isoformat():
                continue                                # another day's file under this name
            got["as_of"] = day.isoformat()
            return got
        if shape:
            raise SourceError(self.name, "The exchange's participant-wise file wasn't in the expected shape.")
        return None

    def cash(self) -> dict:
        """Today's provisional FII/DII cash-market numbers (the exchange keeps only the latest day)."""
        last = None
        for path in CASH_PATHS:
            try:
                return cash_rows(self.nse._get(path, {}, referer=CASH_PAGE, circuit="positioning"))
            except SourceError as e:
                last = e
                if e.busy:
                    raise
            except (ValueError, TypeError, AttributeError):
                last = SourceError(self.name, "The exchange's FII/DII numbers weren't in the expected shape.")
        raise last or SourceError(self.name, "The exchange's FII/DII numbers weren't there.")


# ---------- storage ----------
def _year_key(prefix: str, year: int) -> str:
    return f"pos:{prefix}:{year}"


def _load(key: str, default):
    hit = _cache.get(("k", key))
    if hit is not None:
        return hit
    try:
        v = db.json_value(db.get_setting(key), default)
    except Exception:
        return default
    _cache.set(("k", key), v, 300)
    return v


def _save(key: str, value):
    db.set_setting(key, json.dumps(value, separators=(",", ":")))
    _cache.set(("k", key), value, 300)


def _by_day(prefix: str, years: list[int]) -> dict:
    out = {}
    for y in years:
        out.update(_load(_year_key(prefix, y), {}))
    return out


def store_day(prefix: str, day: str, value: dict):
    """Keep one day's numbers under its year (pos:part:2026, pos:cash:2026)."""
    key = _year_key(prefix, int(day[:4]))
    with _lock:
        cur = db.json_value(db.get_setting(key), {})
        cur[day] = value
        _save(key, dict(sorted(cur.items())))


def history(prefix: str, since: str | None = None) -> list[tuple[str, dict]]:
    """Every stored day from `since` (ISO) on, oldest first."""
    today = ist_now().date()
    first = int(since[:4]) if since else today.year - 10
    years = [y for y in range(max(first, 2000), today.year + 1)]
    rows = _by_day(prefix, years)
    return sorted((d, v) for d, v in rows.items() if isinstance(v, dict) and (not since or d >= since))


def latest(prefix: str, before: str | None = None, need: str | None = None) -> tuple[str, dict] | None:
    """The newest stored day (before `before`, with the part `need` when given)."""
    today = ist_now().date()
    for y in range(today.year, today.year - 3, -1):
        rows = _load(_year_key(prefix, y), {})
        for d in sorted(rows, reverse=True):
            if (before is None or d < before) and isinstance(rows[d], dict) and (need is None or rows[d].get(need)):
                return d, rows[d]
    return None


def state() -> dict:
    return _load(STATE_KEY, {})


def _set_state(**parts):
    with _lock:
        st = db.json_value(db.get_setting(STATE_KEY), {})
        st.update(parts)
        _save(STATE_KEY, st)


def clear_cache():
    _cache.clear()
    _last_live.clear()


# ---------- the maths ----------
# a recorded chain row: [strike, ce bid, ce ask, ce ltp, ce oi, pe bid, pe ask, pe ltp, pe oi, ce volume, pe volume]
def _at(r, i):
    v = r[i] if len(r) > i else None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def near(rows: list[list], spot: float | None, each_side: int = NEAR) -> list[list]:
    """The strikes within `each_side` steps of the one nearest the spot: the recorder's window."""
    rows = sorted((r for r in rows if r and _at(r, 0) is not None), key=lambda r: r[0])
    if not rows or spot is None:
        return rows
    i = min(range(len(rows)), key=lambda k: abs(rows[k][0] - spot))
    return rows[max(0, i - each_side): i + each_side + 1]


def pcr(rows: list[list]) -> dict:
    """The put-call ratio: total put open interest over total call open interest, and the same for the day's volume.
    None when the calls have none (or the chain has no volume, as older recordings don't)."""
    def ratio(ci, pi):
        calls = sum(_at(r, ci) or 0 for r in rows)
        puts = sum(_at(r, pi) or 0 for r in rows)
        have = any(_at(r, ci) is not None or _at(r, pi) is not None for r in rows)
        return (round(puts / calls, 3) if calls > 0 and have else None), calls, puts
    oi, coi, poi = ratio(4, 8)
    vol, cv, pv = ratio(9, 10)
    return {"oi": oi, "vol": vol, "call_oi": coi, "put_oi": poi, "call_vol": cv if vol is not None else None,
            "put_vol": pv if vol is not None else None}


def max_pain(rows: list[list]) -> float | None:
    """The strike at which the options open now would be worth the least in total at expiry: for each strike S, every
    call's open interest times max(0, S − its strike) plus every put's times max(0, its strike − S). The lowest
    strike wins a tie. None without open interest."""
    pts = [(r[0], _at(r, 4) or 0, _at(r, 8) or 0) for r in rows if _at(r, 0) is not None]
    if not pts or not any(c or p for _, c, p in pts):
        return None
    best = None
    for s, _, _ in sorted(pts):
        pay = sum(c * max(0.0, s - k) + p * max(0.0, k - s) for k, c, p in pts)
        if best is None or pay < best[1] - 1e-9:
            best = (s, pay)
    return best[0]


def top_strikes(rows: list[list]) -> dict:
    """The strikes with the most call and the most put open interest."""
    def top(i):
        have = [(r[0], _at(r, i)) for r in rows if _at(r, i)]
        if not have:
            return None
        k, v = max(have, key=lambda x: (x[1], -x[0]))
        return {"strike": k, "oi": v}
    return {"call": top(4), "put": top(8)}


def _price(bid, ask, ltp):
    if bid and ask and ask >= bid > 0:
        return (bid + ask) / 2
    return ltp if ltp and ltp > 0 else None


def atm_iv(rows: list[list], spot: float | None, expiry: str, at: datetime) -> dict | None:
    """The at-the-money implied volatility in percent: at the strike nearest the spot, the forward from put-call parity
    (strike + call − put), then the call's and the put's implied volatility from Black's formula with no interest
    rate, averaged. Prices are the bid-ask middle, else the last trade. None when the prices can't give one."""
    if spot is None or not rows:
        return None
    t = years_to(expiry, at)
    if t <= 0:
        return None
    r = min((r for r in rows if _at(r, 0) is not None), key=lambda r: abs(r[0] - spot), default=None)
    if r is None:
        return None
    k = r[0]
    c, p = _price(_at(r, 1), _at(r, 2), _at(r, 3)), _price(_at(r, 5), _at(r, 6), _at(r, 7))
    f = k + c - p if c is not None and p is not None else spot
    if f <= 0:
        return None
    ivs = [v for v in (implied_vol(c, f, k, t, "CE") if c else None, implied_vol(p, f, k, t, "PE") if p else None) if v]
    if not ivs:
        return None
    return {"iv": round(100 * sum(ivs) / len(ivs), 2), "strike": k, "forward": round(f, 2), "days": round(t * 365, 2)}


def iv_stats(today: float | None, past: list[float]) -> dict:
    """Where today's IV sits among the recorded days': the percentile (the share of days with a lower IV) and the
    rank ((today − lowest) / (highest − lowest)), both 0-100. Empty until IV_MIN_DAYS days are recorded."""
    past = [v for v in past if isinstance(v, (int, float)) and math.isfinite(v)]
    out = {"days": len(past), "need": IV_MIN_DAYS, "percentile": None, "rank": None, "low": None, "high": None}
    if today is None or len(past) < IV_MIN_DAYS:
        return out
    lo, hi = min(past), max(past)
    out.update(percentile=round(100 * sum(1 for v in past if v < today) / len(past), 1),
               rank=round(100 * (today - lo) / (hi - lo), 1) if hi > lo else None, low=lo, high=hi)
    if out["rank"] is not None:
        out["rank"] = max(0.0, min(100.0, out["rank"]))
    return out


def chain_stats(rows: list[list], spot: float | None, expiry: str, at: datetime) -> dict:
    """Every fact the page and the daily summary keep for one chain."""
    win = near(rows, spot)
    iv = atm_iv(rows, spot, expiry, at)
    return {"expiry": expiry, "spot": spot, "pcr": pcr(rows), "pcr_near": pcr(win)["oi"], "pcr_near_vol": pcr(win)["vol"],
            "max_pain": max_pain(rows), "top": top_strikes(rows), "atm_iv": iv["iv"] if iv else None,
            "atm": iv["strike"] if iv else None}


# ---------- participant views ----------
def _net(row: dict, a: str, b: str):
    x, y = row.get(a), row.get(b)
    return x - y if isinstance(x, int) and isinstance(y, int) else None


# the long/short pairs in the file: (segment, long column, short column)
SEGMENTS = (("fut_idx", "fut_idx_long", "fut_idx_short"), ("fut_stk", "fut_stk_long", "fut_stk_short"),
            ("opt_idx_call", "opt_idx_call_long", "opt_idx_call_short"), ("opt_idx_put", "opt_idx_put_long", "opt_idx_put_short"),
            ("opt_stk_call", "opt_stk_call_long", "opt_stk_call_short"), ("opt_stk_put", "opt_stk_put_long", "opt_stk_put_short"))


def shares(row: dict, a: str, b: str) -> tuple[float | None, float | None]:
    """The long and the short side's share of long + short, in percent (one decimal, adding up to 100); None, None
    when either side is missing or both are zero."""
    lo, sh = row.get(a), row.get(b)
    if not isinstance(lo, int) or not isinstance(sh, int) or lo < 0 or sh < 0 or lo + sh <= 0:
        return None, None
    long_pct = round(100 * lo / (lo + sh), 1)
    return long_pct, round(100 - long_pct, 1)


def participant_view(rows: dict, prev: dict | None) -> list[dict]:
    """Each participant's index and stock futures and options: long, short and net, each side's share of long +
    short, with the change from the day before."""
    out = []
    for p, label in (*PARTICIPANTS, ("total", "Total")):
        r = rows.get(p) or {}
        if not r:
            continue
        q = (prev or {}).get(p) or {}
        item = {"id": p, "label": label}
        for k in COLUMNS.values():
            item[k] = r.get(k)
            if q and isinstance(r.get(k), int) and isinstance(q.get(k), int):
                item[k + "_chg"] = r[k] - q[k]
        for seg, a, b in SEGMENTS:
            name = seg + "_net"
            item[name] = _net(r, a, b)
            was = _net(q, a, b) if q else None
            if item[name] is not None and was is not None:
                item[name + "_chg"] = item[name] - was
            item[seg + "_long_pct"], item[seg + "_short_pct"] = shares(r, a, b)
            was_pct = shares(q, a, b)[0] if q else None
            if item[seg + "_long_pct"] is not None and was_pct is not None:
                item[seg + "_long_pct_chg"] = round(item[seg + "_long_pct"] - was_pct, 1)
        out.append(item)
    return out


def expected_day(now: datetime) -> date | None:
    """The latest trading day whose files should be out by `now`: today from 18:30, else the trading day before."""
    from .data.calendar import is_trading_day
    local = now.astimezone(IST)
    d = local.date() if local.strftime("%H:%M") >= "18:30" else local.date() - timedelta(days=1)
    for _ in range(12):
        if is_trading_day("IN", d):
            return d
        d -= timedelta(days=1)
    return None


def trading_today(now: datetime) -> bool:
    from .data.calendar import is_trading_day
    return is_trading_day("IN", now.astimezone(IST).date())


WHAT = {"participants": "participant files", "cash": "FII/DII numbers"}


def _day_words(iso: str | None) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day} {d:%b %Y}"


def reason(st: dict, part: str) -> str | None:
    """Why the expected day's numbers aren't shown, in a line: not read yet, not published yet, or what went wrong
    the last time they were asked for. None when they're there."""
    what = WHAT[part]
    if st.get("status") == "ok":
        return None
    if st.get("error"):
        return f"The last try ({_day_words(st.get('checked'))}, {str(st.get('checked'))[11:16]} IST) didn't get them: {st['error']}"
    if st.get("status") == "none" and not st.get("checked"):
        return (f"Not read yet. StratLab reads the {what} each trading evening once the exchange publishes them, "
                f"and catches up within {RETRY_MINUTES} minutes when a run was missed.")
    if st.get("expected"):
        return f"The exchange hasn't published {_day_words(st['expected'])}'s {what} yet."
    return None


def _status(have: str | None, now: datetime, part: str) -> dict:
    """Whether the newest stored day is the one expected: "ok", "pending" (not published yet), "none"; and `reason`,
    a line on why when it isn't "ok"."""
    exp = expected_day(now)
    local = now.astimezone(IST)
    st = (state().get("parts") or {}).get(part) or {}
    out = {"as_of": have, "expected": exp.isoformat() if exp else None, "error": st.get("error"), "checked": st.get("checked")}
    if have and exp and have >= exp.isoformat():
        out["status"] = "ok"
    elif not have:
        out["status"] = "none"
    else:
        out["status"] = "pending"
    if trading_today(now) and local.strftime("%H:%M") >= "15:30" and (not have or have < local.date().isoformat()):
        out["today"] = "pending"           # today's numbers come in the evening
    out["reason"] = reason(out, part)
    return out


def participants_today(now: datetime | None = None) -> dict:
    """The newest day's participant-wise open interest and volume, each with the change from the day before."""
    now = now or ist_now()
    got = latest("part", need="oi")
    out = {"kind": "participants", **_status(got[0] if got else None, now, "participants"), "oi": [], "vol": [], "prev": None}
    if not got:
        return out
    day, v = got
    prev = latest("part", before=day, need="oi")
    out["prev"] = prev[0] if prev else None
    out["oi"] = participant_view(v.get("oi") or {}, (prev[1].get("oi") if prev else None))
    pv = latest("part", before=day, need="vol")
    out["vol"] = participant_view(v.get("vol") or {}, (pv[1].get("vol") if pv else None)) if v.get("vol") else []
    return out


def cash_today(now: datetime | None = None) -> dict:
    now = now or ist_now()
    got = latest("cash", need="fii")
    out = {"kind": "cash", **_status(got[0] if got else None, now, "cash")}
    if got:
        out.update(fii=got[1].get("fii"), dii=got[1].get("dii"))
    return out


# ---------- the option chains ----------
def _ist_day_bounds(day: date) -> tuple[str, str]:
    start = datetime.combine(day, dtime(0, 0), IST).astimezone(timezone.utc)
    return start.isoformat(), (start + timedelta(days=1)).isoformat()


def recorded_last(name: str, day: date) -> list[dict]:
    """The last recorded chain of each expiry on a day (India time), nearest expiry first."""
    key = ("day", name, day.isoformat())
    hit = _cache.get(key)
    if hit is not None:
        return hit
    since, until = _ist_day_bounds(day)
    rows = db.option_snapshots(name, since, until, limit=12)
    out: dict[str, dict] = {}
    for r in rows:
        e = str(r.get("expiry") or "")[:10]
        if e and e not in out and isinstance(r.get("chain"), list):
            out[e] = r
    got = [out[e] for e in sorted(out)]
    _cache.set(key, got, 120)                 # today's recordings grow every few minutes; a past day's never change
    return got


def recorded_before(name: str, expiry: str, day: date) -> dict | None:
    """The last recorded chain of an expiry before a day began (for the change in open interest)."""
    key = ("before", name, expiry, day.isoformat())
    hit = _cache.get(key)
    if hit is not None:
        return hit or None
    since, _ = _ist_day_bounds(day)
    found = None
    try:
        for r in db.option_snapshots(name, _ist_day_bounds(day - timedelta(days=10))[0], since, limit=12):
            if str(r.get("expiry") or "")[:10] == expiry and isinstance(r.get("chain"), list):
                found = r
                break
    except Exception:
        found = None
    _cache.set(key, found or {}, 600)
    return found


def _taken(r: dict) -> datetime:
    try:
        t = datetime.fromisoformat(str(r.get("taken_at")).replace("Z", "+00:00"))
    except ValueError:
        return ist_now()
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def front(expiries: list[str], day: date) -> str | None:
    """The nearest expiry after the day itself (an expiry-day chain is mostly time running out)."""
    later = sorted(e for e in expiries if e > day.isoformat())
    return later[0] if later else (sorted(expiries)[-1] if expiries else None)


def summarise_day(name: str, day: date) -> dict | None:
    """One day's chain facts from its last recordings: {"front": expiry, "x": {expiry: stats}}; None unrecorded."""
    snaps = recorded_last(name, day)
    if not snaps:
        return None
    x = {}
    for r in snaps:
        e = str(r["expiry"])[:10]
        x[e] = chain_stats(r["chain"], r.get("spot"), e, _taken(r))
    return {"front": front(list(x), day), "x": x, "at": max(_taken(r) for r in snaps).isoformat(timespec="minutes")}


def chain_history(name: str) -> dict:
    return _load(f"pos:chain:{name}", {})


def store_chain_day(name: str, day: str, summary: dict):
    key = f"pos:chain:{name}"
    with _lock:
        cur = db.json_value(db.get_setting(key), {})
        cur[day] = summary
        keep = dict(sorted(cur.items())[-KEEP_CHAIN_DAYS:])
        _save(key, keep)


def chain_series(name: str, since: str | None = None) -> list[dict]:
    """The front expiry's facts on each recorded day: day, expiry, PCR (near the money, by OI and volume), max pain,
    ATM IV, spot."""
    out = []
    for d, s in sorted(chain_history(name).items()):
        if since and d < since or not isinstance(s, dict):
            continue
        st = (s.get("x") or {}).get(s.get("front") or "") or {}
        out.append({"day": d, "expiry": s.get("front"), "pcr_oi": st.get("pcr_near"), "pcr_vol": st.get("pcr_near_vol"),
                    "max_pain": st.get("max_pain"), "atm_iv": st.get("atm_iv"), "spot": st.get("spot")})
    return out


def _compact(chain: dict) -> list[list]:
    from .options.recorder import compact
    return compact(chain)


_live_lock = threading.Lock()


# The last chain read for each index, kept a few minutes past its minute: when the minute is up, a page gets that one
# at once while the next read runs in the background, instead of waiting a second or more on the feed.
_last_live: dict[tuple, tuple[float, dict]] = {}
LIVE_STALE_FOR = 600
_refreshing: set[tuple] = set()
_refreshing_lock = threading.Lock()


def live_chains(options_data, names: tuple, choice: str) -> dict[str, dict | None]:
    """Today's chains for several indices from the live feed, compacted like a recording and kept a minute; None for an
    index when the feed is offline. Every index's quotes go out together (one request for the spots, then the
    contracts in as few requests as the feed allows), since the feed takes about one request a second for everyone.
    Once the minute is up, the last chain (up to LIVE_STALE_FOR old) answers while a fresh one is read behind it."""
    out, need, behind = {}, [], []
    for name in names:
        key = ("live", NAMES[name], name, choice)
        hit = _cache.get(key)
        if hit is not None:
            out[name] = hit or None
        elif (last := _last_live.get(key)) and time.time() - last[0] < LIVE_STALE_FOR:
            out[name] = last[1]
            behind.append(name)
        else:
            need.append(name)
    # a chain the recorder saved in the last few minutes answers at once while the live one is read behind it: the
    # first visitor after a quiet spell waited 6 to 16 s for the feed's one-request-a-second reads (R5O-025)
    for name in list(need):
        rec = _fresh_recording(name, choice)
        if rec:
            out[name] = rec
            need.remove(name)
            behind.append(name)
    if behind:
        _refresh_behind(options_data, behind, choice)
    if not need:
        return out
    with _live_lock:                        # a second caller waits for the first one's answer instead of asking again
        for name in list(need):
            hit = _cache.get(("live", NAMES[name], name, choice))
            if hit is not None:
                out[name] = hit or None
                need.remove(name)
        got = _read_live(options_data, need, choice) if need else {}
        for name in need:
            out[name] = got.get(name)
            _keep_live(name, choice, got.get(name))
    return out


RECORDED_FRESH = 300          # seconds a recording stands in for the live chain while that one is read


def _fresh_recording(name: str, choice: str) -> dict | None:
    """The recorder's chain for this index and expiry, when it was taken in the last RECORDED_FRESH seconds; else None."""
    try:
        today = ist_now().date()
        if not recorded_last(name, today):          # nothing recorded today: don't walk back through older days
            return None
        got = recorded_chain(name, choice, today)
        at = datetime.fromisoformat(str((got or {}).get("taken_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError, KeyError):
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return got if 0 <= time.time() - at.timestamp() <= RECORDED_FRESH else None


def _keep_live(name: str, choice: str, chain: dict | None):
    key = ("live", NAMES[name], name, choice)
    _cache.set(key, chain or {}, 60 if chain else 30)
    if chain:
        _last_live[key] = (time.time(), chain)
    else:
        _last_live.pop(key, None)          # the feed went offline: no older chain stands in for it


def _refresh_behind(options_data, names: list[str], choice: str):
    """Read these indices' chains again in a background thread (one at a time per index and choice)."""
    with _refreshing_lock:                  # not _live_lock: that one is held while a chain is read
        todo = [n for n in names if (n, choice) not in _refreshing]
        _refreshing.update((n, choice) for n in todo)
    if not todo:
        return

    def work():
        try:
            with _live_lock:
                left = [n for n in todo if _cache.get(("live", NAMES[n], n, choice)) is None]
                got = _read_live(options_data, left, choice) if left else {}
                for n in left:
                    _keep_live(n, choice, got.get(n))
        except Exception as e:
            print("positioning: background chain read failed:", str(e)[:120])
        finally:
            with _refreshing_lock:
                _refreshing.difference_update((n, choice) for n in todo)
    threading.Thread(target=work, daemon=True, name="positioning-live").start()


def _read_live(options_data, names: list[str], choice: str) -> dict[str, dict]:
    got: dict[str, dict] = {}
    try:
        if not options_data.ready():
            return got
        cs = {n: options_data.contracts(NAMES[n], n, choice) for n in names}
        cs = {n: c for n, c in cs.items() if c}
        sk = {n: options_data.spot_key(NAMES[n], n, c.expiry) for n, c in cs.items()}
        spots = options_data.quotes([k for k in sk.values() if k])
        plan = {}
        for n, c in cs.items():
            q = spots.get(sk[n]) if sk[n] else None
            spot = q.get("ltp") if q else None
            mid = c.atm(spot) if spot else c.strikes[len(c.strikes) // 2]
            i = c.strikes.index(mid)
            plan[n] = (c, spot, c.strikes[max(0, i - AROUND_LIVE): i + AROUND_LIVE + 1])
        keys = [k for c, _, ks in plan.values() for s in ks for o in ("CE", "PE") if (k := c.key(o, s))]
        q = options_data.quotes(keys)
        now, source = chain_time(ist_now())
        for n, (c, spot, ks) in plan.items():
            rows = [{"strike": s, "ce": q.get(c.key("CE", s)), "pe": q.get(c.key("PE", s))} for s in ks]
            if spot is None or not any(r["ce"] or r["pe"] for r in rows):
                continue
            got[n] = {"expiry": c.expiry, "expiries": options_data.expiries(NAMES[n], n)[:6], "spot": spot,
                      "chain": _compact({"rows": rows}), "taken_at": now, "source": "live", "at_close": source == "close"}
    except Exception as e:
        print("positioning: live chains", ",".join(names), str(e)[:120])
    return got


def chain_time(now: datetime) -> tuple[str, str]:
    """(the time a chain read from the feed is of, "live" or "close"): now during market hours; outside them the
    feed's prices are the last session's close, so the chain is of that close (R6O-019: "Live chain, 8 Oct, 23:45
    IST" after a 15:30 close)."""
    from .data.calendar import is_trading_day
    local = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
    hm = local.strftime("%H:%M")
    if is_trading_day("IN", local.date()) and "09:15" <= hm < "15:30":
        return local.isoformat(timespec="seconds"), "live"
    day = local.date() if is_trading_day("IN", local.date()) and hm >= "15:30" else local.date() - timedelta(days=1)
    for _ in range(10):
        if is_trading_day("IN", day):
            break
        day -= timedelta(days=1)
    return datetime(day.year, day.month, day.day, 15, 30, tzinfo=IST).isoformat(timespec="seconds"), "close"


def live_chain(options_data, exchange: str, name: str, choice: str) -> dict | None:
    return live_chains(options_data, (name,), choice).get(name)


def recorded_chain(name: str, choice: str, today: date) -> dict | None:
    """The newest recorded chain for the expiry asked for, when the live feed is offline."""
    for back in range(0, 8):
        # a monthly-only index's recordings of a date it can't expire on (an old weekly list) are left out
        snaps = [s for s in recorded_last(name, today - timedelta(days=back)) if expiry_fits(NAMES[name], name, str(s["expiry"])[:10])]
        if not snaps:
            continue
        exps = [str(s["expiry"])[:10] for s in snaps]
        if choice == "current":
            pick = snaps[0]
        elif choice == "next":
            pick = snaps[1] if len(snaps) > 1 else snaps[0]
        else:
            pick = next((s for s, e in zip(snaps, exps) if e == choice), None)
            if pick is None:
                continue
        return {"expiry": str(pick["expiry"])[:10], "expiries": exps, "spot": pick.get("spot"), "chain": pick["chain"],
                "taken_at": _taken(pick).astimezone(IST).isoformat(timespec="minutes"), "source": "recorded"}
    return None


def chain_view(options_data, name: str, choice: str = "current", full: bool = False, now: datetime | None = None) -> dict:
    """One index's option chain as facts: open interest and its change by strike, the PCR, max pain, the strikes with
    the most open interest and the ATM IV; with `full` (Basic), the IV's percentile and rank over recorded days."""
    now = now or ist_now()
    ex = NAMES[name]
    got = live_chain(options_data, ex, name, choice) or recorded_chain(name, choice, now.date())
    out = {"name": name, "exchange": ex, "choice": choice, "source": None, "rows": [], "note": NOTE,
           "recorded": chain_coverage(name)}
    if not got:
        return out
    rows = sorted(got["chain"], key=lambda r: r[0])
    expiry = got["expiry"]
    # a chain's own time: a recording's, or the close a live read before the open stands for (its change is then against
    # the day before that close, not against the close itself, which made every change zero before 9:15 IST)
    at = datetime.fromisoformat(got["taken_at"]) if got["source"] == "recorded" or got.get("at_close") else now
    stats = chain_stats(rows, got.get("spot"), expiry, at)
    taken_day = at.astimezone(IST).date()
    prev = recorded_before(name, expiry, taken_day)
    before = {r[0]: r for r in (prev or {}).get("chain") or []}
    strikes = []
    for r in near(rows, got.get("spot"), 20):
        p = before.get(r[0])
        co, po = _at(r, 4), _at(r, 8)
        strikes.append({"strike": r[0], "call_oi": co, "put_oi": po, "call_vol": _at(r, 9), "put_vol": _at(r, 10),
                        "call_chg": co - _at(p, 4) if p and co is not None and _at(p, 4) is not None else None,
                        "put_chg": po - _at(p, 8) if p and po is not None and _at(p, 8) is not None else None})
    out.update(source=got["source"], at_close=bool(got.get("at_close")), as_of=got["taken_at"], expiry=expiry, expiries=got.get("expiries") or [],
               spot=got.get("spot"), rows=strikes, change_from=_taken(prev).astimezone(IST).isoformat(timespec="minutes") if prev else None,
               strikes_counted=len(rows), **{k: stats[k] for k in ("pcr", "pcr_near", "pcr_near_vol", "max_pain", "top", "atm_iv", "atm")})
    out["iv"] = None
    if full:
        past = [p["atm_iv"] for p in chain_series(name) if p["day"] < taken_day.isoformat()]
        out["iv"] = iv_stats(stats["atm_iv"], past)
    return out


def pcr_table(options_data, now: datetime | None = None, names: tuple = tuple(NAMES)) -> list[dict]:
    """Each index's nearest-expiry PCR now (the live chain, else the newest recording)."""
    now = now or ist_now()
    out = []
    live = live_chains(options_data, tuple(names), "current")
    for name in names:
        ex = NAMES[name]
        got = live.get(name) or recorded_chain(name, "current", now.date())
        if not got:
            out.append({"name": name, "exchange": ex, "source": None})
            continue
        p = pcr(got["chain"])
        out.append({"name": name, "exchange": ex, "expiry": got["expiry"], "cycle": expiry_cycle(ex, name), "pcr_oi": p["oi"], "pcr_vol": p["vol"],
                    "pcr_near": pcr(near(got["chain"], got.get("spot")))["oi"], "spot": got.get("spot"),
                    "source": got["source"], "at_close": bool(got.get("at_close")), "as_of": got["taken_at"]})
    return out


def summary(options_data, full: bool, brief: bool = False, with_pcr: bool = True, now: datetime | None = None) -> dict:
    """The page's opening answer: the newest participant numbers and cash flows, and each index's PCR (the page asks
    for those on their own, so the stored numbers show without waiting on the live chains)."""
    now = now or ist_now()
    out = {"participants": participants_today(now), "cash": cash_today(now),
           "pcr": pcr_table(options_data, now, ("NIFTY",) if brief else tuple(NAMES)) if with_pcr else None,
           "names": list(NAMES), "full": full, "note": NOTE, "source": SOURCE, "today": now.date().isoformat()}
    if not brief:
        out["coverage"] = coverage()
    if brief:
        out["participants"].pop("vol", None)
        out["participants"]["oi"] = [r for r in out["participants"]["oi"] if r["id"] == "fii"]
    return out


def _point(r: dict) -> dict:
    """One participant's day for the history charts: each segment's net and long share, and the futures' two sides."""
    out = {"fut_idx_long": r.get("fut_idx_long"), "fut_idx_short": r.get("fut_idx_short")}
    for seg, a, b in SEGMENTS:
        out[seg + "_net"] = _net(r, a, b)
        out[seg + "_long_pct"] = shares(r, a, b)[0]
    return out


def _span(days: list[str]) -> dict:
    return {"days": len(days), "first": days[0] if days else None, "last": days[-1] if days else None}


def chain_coverage(name: str) -> dict:
    """The days of an index's chain StratLab has summarised from its own recordings: how many, the first and last."""
    return _span(sorted(d for d, v in chain_history(name).items() if isinstance(v, dict)))


def coverage() -> dict:
    """How much history is stored, for the page's source lines: the participant files' days (and whether the archive
    walk has finished), the cash numbers' days, and each index's recorded chain days."""
    bf = state().get("backfill") or {}
    parts = [d for d, v in history("part") if v.get("oi")]
    return {"participants": {**_span(parts), "backfill_done": bool(bf.get("done")), "backfill_target": BACKFILL_DAYS},
            "cash": _span([d for d, v in history("cash") if v.get("fii")]),
            "chains": {n: chain_coverage(n) for n in NAMES}}


def history_view(kind: str, name: str | None, rng: str, now: datetime | None = None) -> dict:
    """The stored history for the Basic charts: participants' positions, the cash flows, or one index's chain facts."""
    now = now or ist_now()
    since = (now.date() - timedelta(days=RANGES[rng])).isoformat()
    if kind == "participants":
        pts = []
        for d, v in history("part", since):
            oi = v.get("oi") or {}
            if not oi:
                continue
            pts.append({"day": d, **{p: _point(oi.get(p) or {}) for p, _ in PARTICIPANTS}})
        return {"kind": kind, "range": rng, "points": pts, "stored": coverage()["participants"]}
    if kind == "cash":
        pts = [{"day": d, "fii": (v.get("fii") or {}).get("net"), "dii": (v.get("dii") or {}).get("net")}
               for d, v in history("cash", since)]
        return {"kind": kind, "range": rng, "points": pts}
    return {"kind": kind, "range": rng, "name": name, "points": chain_series(name or "NIFTY", since),
            "recorded": chain_coverage(name or "NIFTY")}


# ---------- the daily run ----------
class Runner:
    """Reads one day's files and cash numbers, and summarises the day's recorded chains; and walks the archives back a
    few days at a time. Every result is stored as soon as it's read, so a stop half-way loses nothing."""

    def __init__(self, feed_fn, sleep=time.sleep, pace: float = PACE):
        self.feed_fn, self.sleep, self.pace = feed_fn, sleep, pace
        self.running = False

    def _feed(self) -> Feed:
        f = self.feed_fn()
        return f if isinstance(f, Feed) else Feed(getattr(f, "nse", f), sleep=self.sleep)

    def participants_day(self, feed: Feed, day: date) -> str:
        """Read both of a day's files: "ok", "missing" (not published) or the error."""
        got = {}
        for kind in KINDS:
            try:
                r = feed.participants(kind, day)
            except SourceError as e:
                return str(e)[:200]
            if r:
                got[kind] = r["rows"]
            if self.pace:
                self.sleep(self.pace)
        if "oi" not in got:
            return "missing"
        old = _load(_year_key("part", day.year), {}).get(day.isoformat()) or {}
        store_day("part", day.isoformat(), {**old, **got})
        return "ok"

    def cash(self, feed: Feed, day: date) -> str:
        try:
            c = feed.cash()
        except SourceError as e:
            return str(e)[:200]
        store_day("cash", c["as_of"], {"fii": c["fii"], "dii": c["dii"]})
        return "ok" if c["as_of"] >= day.isoformat() else "missing"

    def chains(self, day: date) -> int:
        n = 0
        for name in NAMES:
            try:
                s = summarise_day(name, day)
            except Exception as e:
                print("positioning: chain summary", name, str(e)[:120])
                continue
            if s:
                store_chain_day(name, day.isoformat(), s)
                n += 1
        return n

    def run_day(self, day: date, now: datetime | None = None) -> dict:
        """The evening run for one trading day."""
        now = now or ist_now()
        self.running = True
        try:
            feed = self._feed()
            parts = state().get("parts") or {}
            res = {"participants": self.participants_day(feed, day), "cash": self.cash(feed, day), "chains": self.chains(day)}
            stamp = now.astimezone(IST).isoformat(timespec="minutes")
            for part in ("participants", "cash"):
                r = res[part]
                parts[part] = {"checked": stamp, "error": None if r in ("ok", "missing") else r,
                               "missing": day.isoformat() if r == "missing" else None}
            _set_state(parts=parts, last_run=stamp)
            return res
        finally:
            self.running = False

    def backfill(self, today: date, step: int = BACKFILL_STEP, days: int = BACKFILL_DAYS) -> dict:
        """Read up to `step` more past days of archive files, walking back from the oldest one tried, and summarise any
        recorded chains not yet summarised. Stops for good when it reaches `days` back."""
        from .data.calendar import is_trading_day
        bf = dict(state().get("backfill") or {})
        if bf.get("done"):
            return bf
        self.running = True
        try:
            feed = self._feed()
            d = date.fromisoformat(bf["next"]) if bf.get("next") else today - timedelta(days=1)
            stop = today - timedelta(days=days)
            have = {k for k, _ in history("part", stop.isoformat())}
            read, misses, streak = 0, 0, None
            stuck = dict(bf.get("stuck") or {})
            while d >= stop and read < step:
                if is_trading_day("IN", d) and d.isoformat() not in have:
                    r = self.participants_day(feed, d)
                    if r not in ("ok", "missing"):
                        bf["error"] = r
                        break                       # the exchange is busy or refusing: try again on the next run
                    read += 1
                    bf["read"] = bf.get("read", 0) + (r == "ok")
                    misses, streak = (misses + 1, streak or d) if r == "missing" else (0, None)
                    # the archive keeps every trading day's files: five in a row not there is the archive turning us
                    # away (a page instead of the file), so walk back from the first of them on the next run instead
                    # of passing them by for good; after three such runs at the same day, take them as not there
                    if misses >= MISS_RUN and stuck.get(streak.isoformat(), 0) < 3:
                        stuck = {streak.isoformat(): stuck.get(streak.isoformat(), 0) + 1}
                        bf["stuck"] = stuck
                        bf["error"] = f"The archive had none of {MISS_RUN} trading days in a row from {_day_words(streak.isoformat())}; trying again later."
                        d = streak
                        break
                d -= timedelta(days=1)
            else:
                bf.pop("error", None)
            bf["next"] = d.isoformat()
            if d < stop:
                bf["done"] = True
                bf["chains"] = self.chain_backfill(today)
            _set_state(backfill=bf)
            return bf
        finally:
            self.running = False

    def catch_up(self, now: datetime | None = None) -> dict:
        """Fill in what the evening run missed (a restart, a server started on a weekend or holiday, an evening the
        exchange was slow): the participant files of the last few trading days that aren't stored, and the cash
        numbers when the stored ones are older than the latest trading day's. The exchange's cash numbers only ever
        show its latest day, so they're read as soon as they're found missing: a day passed by can't be read later."""
        from .data.calendar import is_trading_day
        now = now or ist_now()
        exp = expected_day(now)
        if not exp:
            return {}
        self.running = True
        try:
            st = state()
            tries = dict(st.get("catch_up") or {})
            have = {d for d, v in history("part", (exp - timedelta(days=CATCH_UP_DAYS)).isoformat()) if v.get("oi")}
            res: dict = {}
            feed = None
            d = exp
            while d > exp - timedelta(days=CATCH_UP_DAYS):
                key = d.isoformat()
                if is_trading_day("IN", d) and key not in have and tries.get(key, 0) < CATCH_UP_TRIES:
                    feed = feed or self._feed()
                    r = self.participants_day(feed, d)
                    res.setdefault("participants", {})[key] = r
                    if r == "missing":
                        tries[key] = tries.get(key, 0) + 1
                    elif r != "ok":
                        break                          # busy or refusing: the next catch-up tries again
                d -= timedelta(days=1)
            got = latest("cash", need="fii")
            if not got or got[0] < exp.isoformat():
                feed = feed or self._feed()
                res["cash"] = self.cash(feed, exp)
            stamp = now.astimezone(IST).isoformat(timespec="minutes")
            parts = dict(st.get("parts") or {})
            if res.get("participants"):
                newest = res["participants"].get(exp.isoformat())
                bad = next((r for r in res["participants"].values() if r not in ("ok", "missing")), None)
                if newest is not None or bad:
                    parts["participants"] = {"checked": stamp, "error": bad, "missing": exp.isoformat() if newest == "missing" else None}
            if "cash" in res:
                r = res["cash"]
                parts["cash"] = {"checked": stamp, "error": None if r in ("ok", "missing") else r,
                                 "missing": exp.isoformat() if r == "missing" else None}
            cutoff = (exp - timedelta(days=CATCH_UP_DAYS)).isoformat()
            _set_state(parts=parts, catch_up={k: v for k, v in tries.items() if k > cutoff}, last_catch_up=stamp)
            return res
        finally:
            self.running = False

    def chain_backfill(self, today: date, days: int = 130) -> int:
        """Summarise every recorded day not summarised yet (the recordings are kept a few months)."""
        n = 0
        from .data.calendar import is_trading_day
        for name in NAMES:
            have = chain_history(name)
            for back in range(1, days + 1):
                d = today - timedelta(days=back)
                if d.isoformat() in have or not is_trading_day("IN", d):
                    continue
                try:
                    s = summarise_day(name, d)
                except Exception:
                    s = None
                if s:
                    store_chain_day(name, d.isoformat(), s)
                    n += 1
        return n


class Job(news_job.Job):
    """Every five minutes: on a trading day from 18:40 India time, read the day's files until they're all in (every
    twenty minutes until 21:30, when it gives up for the day); the newsletter job's run marker (newsjob:positioning)
    remembers a finished day across restarts. At any other time it catches up on what an evening run missed (every
    twenty minutes while something is behind), and outside market hours it walks the archives back a few days."""

    status_key = "positioning"

    def __init__(self, runner: Runner):
        super().__init__()
        self.runner = runner
        self._tried = self._caught = 0.0
        self.status.update(last_result=None, backfill=None, catch_up=None)

    @staticmethod
    def _behind(now: datetime) -> bool:
        """Whether the stored participant files or cash numbers are older than the latest trading day's."""
        exp = expected_day(now)
        if not exp:
            return False
        part, cash = latest("part", need="oi"), latest("cash", need="fii")
        return any(not got or got[0] < exp.isoformat() for got in (part, cash))

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="positioning").start()

    def tick(self, now: datetime) -> int:
        local = now.astimezone(IST)
        if self.runner.running:                  # an admin's run is going: wait for the next check
            return 0
        day = self.due("positioning", now, "Asia/Kolkata", PUBLISH_FROM, region="IN")
        if day and time.time() - self._tried >= RETRY_MINUTES * 60:
            self._tried = time.time()
            res = self.runner.run_day(day, now)
            self.status.update(last_run=now.isoformat(), last_result=res, last_error=None)
            finished = res["participants"] == "ok" and res["cash"] == "ok"
            if finished or local.strftime("%H:%M") >= PUBLISH_UNTIL:
                self.mark("positioning", day)
            return 0
        # any other time (a weekend, a holiday, after a restart), fill in what the evening run missed, every twenty minutes
        if not day and time.time() - self._caught >= RETRY_MINUTES * 60 and self._behind(now):
            self._caught = time.time()
            self.status["catch_up"] = self.runner.catch_up(now)
            return 0
        hhmm = local.strftime("%H:%M")
        if not ("09:00" <= hhmm <= "15:45") and not (state().get("backfill") or {}).get("done"):
            self.status["backfill"] = self.runner.backfill(local.date())
        return 0
