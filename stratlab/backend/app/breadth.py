"""Market breadth: how many stocks in a group are taking part in the market's moves, day by day.

For each group of stocks (all of NSE, the NIFTY 50, 500, Midcap 150 and Smallcap 250, and a list of US large caps)
and each trading day: how many rose, fell or stayed flat; how many closed above their 20-, 50- and 200-day averages;
how many made a 52-week high or low; how many moved 4% or more either way; how many are in Stage 2; and the volume of
the rising and falling stocks. From those counts come the advance/decline line, the McClellan oscillator and its
summation index, the breadth thrust measure and TRIN, all worked out when a page asks, so they are always consistent.

Every stock counts once, whatever its size. Facts only: nothing here says what the market will do or what to do.

The counts come from the daily candles the app already reads for its scans, one request per stock and paced, after
each market's close (a run marker, as the newsletters use, so a restart never repeats a day). The first run reaches
back about two years; later runs re-read the last few months, which also picks up corrected candles. The history is
stored per group (breadth:hist:<group>), with the last three months of sector counts beside it.

People can ask for a message when a group's share of stocks above the 50-day average crosses a level they pick; it is
checked once the run has stored the new day, and goes through the stock alerts' channels and message limits."""
import json
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import db, rotation, scan_presets, sector_members, universes
from .engine.indicators import stage
from . import deals  # noqa: F401  (before the newsletter job, which imports it back while loading)
from .newsletter import job as news_job

HIST_KEY = "breadth:hist:"            # breadth:hist:<group> = {"fields": [...], "rows": [[day, ...], ...], "at"}
SECTOR_KEY = "breadth:sectors:"       # breadth:sectors:<group> = {"days": [...], "sectors": {name: {"a": [...], "n": [...]}}}
MEMBERS_KEY = "breadth:members:"      # the last good list of a group's stocks
FILL_KEY = "breadth:fill-tried:"      # breadth:fill-tried:<region> = "<day>|<groups without days>": filled at the first chance once a day
BASE_KEY = "breadth:base:"            # breadth:base:<region> = {"day", "stocks": {symbol: base_row}} for the intraday view
STATUS_KEY = "breadth:status"         # {region: {ran_at, as_of, stocks, loaded, failed, last_error}}

MAS = (20, 50, 200)
YEAR = 252                            # sessions in 52 weeks
MOVE = 4.0                            # the "up 4% / down 4%" day
STAGE_AVG, STAGE_LOOK = 150, 20       # the same Stage the scans and screens use
BACKFILL_DAYS = 1130                  # calendar days read on the first run: two years of counts plus a year of lookback
RECENT_DAYS = 470                     # calendar days read on later runs: about three months of counts are re-made
LOOKBACK_DAYS = 380                   # calendar days before a count is complete (the 52-week high needs a full year)
KEEP_ROWS = 1300                      # about five years of stored days
SECTOR_KEEP = 70                      # sessions of sector counts kept (three months and a bit)
MIN_SECTOR = 5                        # sectors with fewer stocks with data are left out of the table
GAP = 0.25                            # seconds between stocks, on top of each source's own pacing
GIVE_UP = 25                          # this many failures in a row: the source is down, the run stops and keeps the old
MIN_MEMBERS = 20                      # an exchange list shorter than this is taken as a broken answer

# the counts kept for each day; the stored rows hold them in this order, then the group's index close
FIELDS = ("has", "adv", "dec", "unch", "up4", "dn4", "n20", "a20", "n50", "a50", "n200", "a200", "n52", "hi", "lo",
          "ns", "s2", "av", "dv")
COLS = FIELDS + ("idx",)

GROUPS = {
    "nse_all": {"region": "IN", "name": "All NSE stocks", "index": "NIFTY 500", "index_name": "NIFTY 500"},
    "nifty50": {"region": "IN", "name": "NIFTY 50", "nse": "NIFTY 50", "index": "NIFTY 50", "index_name": "NIFTY 50"},
    "nifty500": {"region": "IN", "name": "NIFTY 500", "nse": "NIFTY 500", "index": "NIFTY 500", "index_name": "NIFTY 500"},
    "midcap150": {"region": "IN", "name": "NIFTY Midcap 150", "nse": "NIFTY MIDCAP 150", "index": "NIFTY MIDCAP 150",
                  "index_name": "NIFTY Midcap 150"},
    "smallcap250": {"region": "IN", "name": "NIFTY Smallcap 250", "nse": "NIFTY SMALLCAP 250", "index": "NIFTY SMLCAP 250",
                    "index_name": "NIFTY Smallcap 250"},
    "us_large": {"region": "US", "name": "US large caps", "index": "SPY", "index_name": "SPY (an S&P 500 fund)"},
    "sp500": {"region": "US", "name": "S&P 500", "index": "SPY", "index_name": "SPY (an S&P 500 fund)"},
}
DEFAULT = "nifty500"
REGIONS = ("IN", "US")
CLOSE = {"IN": ("Asia/Kolkata", "15:45"), "US": ("America/New_York", "16:15")}     # a day's candle is final after this
RUN_AT = {"IN": ("Asia/Kolkata", "18:30"), "US": ("America/New_York", "17:45")}    # the daily run, after the close
RANGES = {"3m": 63, "6m": 126, "1y": 252, "2y": 504, "all": None}


def due_label(region: str) -> str | None:
    """When a market's daily count is usually in, as the pages say it: "5:45 PM ET" for the US run (RUN_AT). None for India,
    whose pages already say "18:30 IST" (stock_pages.DUE_AT)."""
    if region != "US":
        return None
    h, m = (int(x) for x in RUN_AT[region][1].split(":"))
    return f"{h % 12 or 12}:{m:02d} {'PM' if h >= 12 else 'AM'} ET"

# what each number means, in plain words: the page's (i) next to each figure and chart
HELP = {
    "ad": "Advances are stocks that closed higher than the day before; declines closed lower. The ratio is advances "
          "divided by declines: above 1, more stocks rose than fell.",
    "ad_line": "A running total of advances minus declines, added up day by day from the start of the history shown. "
               "It rises on days more stocks go up than down, and falls when more go down.",
    "ma": "The share of stocks whose last close is above their average close of the last 20, 50 or 200 trading days "
          "(about a month, ten weeks and ten months). Only stocks with that many days of prices count.",
    "index": "The group's index on the same days, on its own chart and scale, to set the breadth beside the price.",
    "highs_lows": "Stocks whose day's high was the highest of the last 52 weeks (252 trading days), and those whose low "
                  "was the lowest. Only stocks with a full year of prices count.",
    "mcclellan": "The McClellan oscillator: the 19-day average of each day's advances minus declines, less its 39-day "
                 "average (exponential averages). Each day's figure is scaled to the stocks that moved, (advances − "
                 "declines) ÷ (advances + declines) × 1,000, so groups of any size read alike. Above 0, the shorter "
                 "average is above the longer one.",
    "summation": "The McClellan summation index: every day's oscillator added up from the start of the stored history. "
                 "It moves with the longer swings of advances and declines.",
    "moves": "Stocks that rose 4% or more in the day, and stocks that fell 4% or more.",
    "stage2": "The share of stocks in Stage 2: the price above its 150-day average while that average is rising. Stage "
              "is the same one the scans and screens show.",
    "sectors": "For each sector, the share of its stocks in this group above their 50-day average, today and one week, "
               "one month and three months of trading days ago. Sectors with fewer than five stocks are left out.",
    "thrust": "The breadth thrust measure: a 10-day exponential average of advances ÷ (advances + declines). A thrust "
              "is the days that average went from under 40% to over 61.5% within 10 trading days; the dates it "
              "happened are listed. A description of what the counts did, not a forecast.",
    "trin": "TRIN (the Arms index): the advance/decline ratio divided by the ratio of the volume traded in rising stocks "
            "to the volume in falling ones. 1 means volume split in line with the count of stocks; under 1, rising "
            "stocks had more than their share of the volume; over 1, falling stocks did.",
    "members": "Each group uses its list of stocks as of today for every past day too, so a stock that joined or left "
               "an index lately is counted as if it had always been in it.",
}


# ---------- one stock ----------
def _frame(bars: list[dict], through: str | None) -> pd.DataFrame | None:
    """Daily candles as columns c, h, l, v by date ("YYYY-MM-DD"), one row a day, up to `through`."""
    rows = []
    for b in bars or []:
        try:
            d, c = str(b["t"])[:10], float(b["c"])
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(c) or c <= 0 or (through and d > through):
            continue
        h, low, v = (_pos(b.get(k)) for k in ("h", "l", "v"))
        rows.append((d, c, h or c, low or c, v or 0.0))
    if len(rows) < 2:
        return None
    df = pd.DataFrame(rows, columns=["d", "c", "h", "l", "v"]).drop_duplicates("d", keep="last").sort_values("d")
    return df.set_index("d")


def _pos(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) and f > 0 else None


def stock_flags(bars: list[dict], through: str | None = None) -> pd.DataFrame | None:
    """For one stock, each day's 0/1 counts (and volume on rising or falling days), one column per FIELDS entry.
    A day without a previous close counts toward nothing; an average or a 52-week window the stock doesn't yet have
    enough days for leaves it out of that count."""
    df = _frame(bars, through)
    if df is None:
        return None
    c, prev = df["c"], df["c"].shift(1)
    has = prev.notna()
    chg = (c / prev - 1) * 100
    out = pd.DataFrame(index=df.index)
    out["has"] = has
    out["adv"] = has & (c > prev)
    out["dec"] = has & (c < prev)
    out["unch"] = has & (c == prev)
    out["up4"] = has & (chg >= MOVE)
    out["dn4"] = has & (chg <= -MOVE)
    for n in MAS:
        avg = c.rolling(n).mean()
        out[f"n{n}"] = avg.notna()
        out[f"a{n}"] = avg.notna() & (c > avg)
    # a new high is a day's high above every high of the previous 251 sessions (a year with today); matching an old
    # high isn't a new one, so a stock that sits still doesn't count every day
    top, bottom = df["h"].shift(1).rolling(YEAR - 1).max(), df["l"].shift(1).rolling(YEAR - 1).min()
    out["n52"] = top.notna()
    out["hi"] = top.notna() & (df["h"] > top)
    out["lo"] = bottom.notna() & (df["l"] < bottom)
    st = stage(c, STAGE_AVG, STAGE_LOOK)
    out["ns"] = st.notna()
    out["s2"] = st == 2
    out = out.astype(float)
    out["av"] = np.where(out["adv"] > 0, df["v"], 0.0)
    out["dv"] = np.where(out["dec"] > 0, df["v"], 0.0)
    return out[list(FIELDS)]


def base_row(bars: list[dict], through: str | None = None) -> list | None:
    """What the intraday view needs of a stock's finished days: [last close, closes counted, sum of the last 19, 49 and
    199 closes] (a sum is None while the stock has fewer closes than that). Today's price then makes the 20-, 50- and
    200-day averages as (sum + price) / n."""
    df = _frame(bars, through)
    if df is None:
        return None
    c = df["c"]
    n = len(c)
    sums = [round(float(c.iloc[-k:].sum()), 4) if n >= k else None for k in (19, 49, 199)]
    return [round(float(c.iloc[-1]), 4), n, *sums]


# ---------- adding stocks up ----------
class Tally:
    """Each group's counts, added up one stock at a time (so a whole market never sits in memory at once), and each
    group's sector counts of stocks above the 50-day average for the last SECTOR_KEEP days."""

    def __init__(self):
        self.groups: dict[str, pd.DataFrame] = {}
        self.sectors: dict[str, dict[str, pd.DataFrame]] = {}
        self.stocks: dict[str, int] = {}

    def add(self, group: str, flags: pd.DataFrame, sector: str | None = None, sector_from: str | None = None):
        have = self.groups.get(group)
        self.groups[group] = flags if have is None else have.add(flags, fill_value=0)
        self.stocks[group] = self.stocks.get(group, 0) + 1
        if sector:
            part = flags.loc[flags.index >= sector_from, ["a50", "n50"]] if sector_from else flags[["a50", "n50"]]
            mine = self.sectors.setdefault(group, {})
            mine[sector] = part if sector not in mine else mine[sector].add(part, fill_value=0)


def rows_of(total: pd.DataFrame | None, index: dict[str, float] | None = None) -> dict[str, list]:
    """{day: [counts in COLS order]} from a group's added-up counts. Days on which fewer than half the usual number
    of stocks had prices (a source still catching up, a half-loaded day) are left out rather than shown wrong."""
    if total is None or total.empty:
        return {}
    usual = float(total["has"].median())
    out = {}
    for d, r in total.iterrows():
        if r["has"] <= 0 or r["has"] < usual * 0.5:
            continue
        vals = [int(round(r[f])) if f not in ("av", "dv") else float(r[f]) for f in FIELDS]
        out[d] = vals + [(index or {}).get(d)]
    return out


def merge(old: dict[str, list], new: dict[str, list], keep_from: str | None) -> dict[str, list]:
    """The stored days with the new run's days laid over them, from `keep_from` on (earlier new days lack a full
    year of lookback, so the stored ones stand). The latest KEEP_ROWS days are kept."""
    out = dict(old)
    for d, r in new.items():
        if keep_from is None or d >= keep_from:
            out[d] = r
    days = sorted(out)[-KEEP_ROWS:]
    return {d: out[d] for d in days}


# ---------- storage ----------
def load_hist(group: str) -> dict[str, list]:
    try:
        raw = db.json_value(db.get_setting(HIST_KEY + group), {})
    except Exception:                   # storage down: nothing to show, the page says so
        return {}
    fields = raw.get("fields") or list(COLS)
    out = {}
    for row in raw.get("rows") or []:
        if not isinstance(row, list) or len(row) != len(fields) + 1 or not isinstance(row[0], str):
            continue
        rec = dict(zip(fields, row[1:]))
        out[row[0]] = [rec.get(f) for f in COLS]
    return out


def save_hist(group: str, rows: dict[str, list]):
    db.set_setting(HIST_KEY + group, json.dumps({"fields": list(COLS), "at": _now(),
                                                 "rows": [[d, *rows[d]] for d in sorted(rows)]}))


def save_base(region: str, day: str, stocks: dict[str, list]):
    db.set_setting(BASE_KEY + region, json.dumps({"day": day, "at": _now(), "stocks": stocks}))


def load_base(region: str) -> dict:
    try:
        raw = db.json_value(db.get_setting(BASE_KEY + region), {})
    except Exception:
        return {}
    return raw if isinstance(raw.get("stocks"), dict) and raw.get("day") else {}


def load_sectors(group: str) -> dict:
    try:
        raw = db.json_value(db.get_setting(SECTOR_KEY + group), {})
    except Exception:
        return {}
    return raw if isinstance(raw.get("days"), list) and isinstance(raw.get("sectors"), dict) else {}


def sectors_of(tally: Tally, group: str) -> dict:
    """A group's sector counts as stored: the last SECTOR_KEEP days, each sector's stocks above and with a 50-day average."""
    parts = tally.sectors.get(group) or {}
    days = sorted({d for p in parts.values() for d in p.index})[-SECTOR_KEEP:]
    out = {}
    for name, p in parts.items():
        p = p.reindex(days)
        out[name] = {"a": [None if pd.isna(x) else int(x) for x in p["a50"]], "n": [None if pd.isna(x) else int(x) for x in p["n50"]]}
    return {"days": days, "sectors": out}


def status() -> dict:
    try:
        return db.json_value(db.get_setting(STATUS_KEY), {})
    except Exception:
        return {}


def _set_status(region: str, **kw):
    s = status()
    s[region] = {**(s.get(region) or {}), **kw}
    db.set_setting(STATUS_KEY, json.dumps(s))


def _now() -> str:
    return datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")


# ---------- who is in each group ----------
def us_large() -> list[str]:
    """StratLab's list of US large caps: the main stocks of each of the 11 S&P 500 sector funds and the 20 largest."""
    out: list[str] = []
    for fund in rotation.SECTORS["US"]["members"]:
        out += [s for s in sector_members.US.get(fund, []) if s not in out]
    for p in universes.PRESETS["US"]:
        out += [s for s in p["symbols"] if s not in out]
    return out


def members(group: str, index_members=None, all_equities=None) -> list[str]:
    """A group's stocks: from the exchange's own lists when they answer (kept as the last good list), else the last
    good list; the NIFTY 50 falls back to StratLab's own list, and the US group is StratLab's own list."""
    g = GROUPS[group]
    if group == "sp500":
        return universes.sp500_symbols()           # the committed list (data/sp500.json), never read from the web
    if g["region"] == "US":
        return us_large()
    fresh = None
    try:
        if g.get("nse") and index_members:
            fresh = index_members(g["nse"])
        elif group == "nse_all" and all_equities:
            fresh = [str(r.get("symbol") or "").upper() for r in all_equities()]
    except Exception as e:              # the exchange turning us away: the last good list
        print("breadth members:", group, str(e)[:120])
    fresh = [s for s in dict.fromkeys(fresh or []) if s and len(s) <= 20]
    if len(fresh) >= MIN_MEMBERS:
        db.set_setting(MEMBERS_KEY + group, json.dumps(fresh))
        return fresh
    try:
        kept = [s for s in db.json_value(db.get_setting(MEMBERS_KEY + group), []) if isinstance(s, str)]
    except Exception:
        kept = []
    if kept:
        return kept
    if group == "nifty50":
        return list(universes.PRESETS["IN"][0]["symbols"])
    return []


GICS_NAMES = {"Information Technology": "Technology", "Health Care": "Health care", "Consumer Discretionary": "Consumer discretionary",
              "Consumer Staples": "Consumer staples", "Real Estate": "Real estate", "Communication Services": "Communication"}


def sector_map(region: str) -> dict[str, str]:
    """{symbol: sector}: the sector the screens show for the company (from its industry), else the sector index or
    fund StratLab's own lists put it in."""
    from . import screens
    out: dict[str, str] = {}
    if region == "US":
        for fund in rotation.SECTORS["US"]["members"]:
            for s in sector_members.US.get(fund, []):
                out.setdefault(s, rotation.US_NAMES[fund])
    if region == "US":              # the rest of the S&P 500, by its list's sector, named as the sector funds are
        for sym, _name, sector, _cik in universes.sp500_doc()["rows"]:
            out.setdefault(sym, GICS_NAMES.get(sector, sector))
    try:
        for r in screens.load_index(region)["rows"]:
            if r.get("sector") and r["symbol"] not in out:
                out[r["symbol"]] = str(r["sector"])[:60]
    except Exception:
        pass
    if region == "IN":
        for idx in rotation.CORE_IN:
            for s in sector_members.IN.get(idx, []):
                out.setdefault(s, rotation.IN_NAMES.get(idx, idx))
    return out


def last_complete(region: str, now: datetime) -> str:
    """The latest day whose candle is final: today once the market has closed (with a margin), else yesterday."""
    tz, at = CLOSE[region]
    local = now.astimezone(ZoneInfo(tz))
    day = local.date() if local.strftime("%H:%M") >= at else local.date() - timedelta(days=1)
    return day.isoformat()


# ---------- the run ----------
class Runner:
    """Reads each stock's candles once, adds its counts into every group it's in, and stores the groups' history.

    `load(region, symbol, days)` gives a stock's daily candles; `index_bars(region, symbol, days)` an index's;
    `index_members(name)` an NSE index's stocks and `all_equities()` every NSE company ([{symbol}]); `sectors(region)`
    gives {symbol: sector}. Each may raise; one stock's failure only leaves it out."""

    def __init__(self, load, index_bars=None, index_members=None, all_equities=None, sectors=sector_map,
                 gap: float = GAP, sleep=time.sleep, after=None):
        self.load, self.index_bars, self.index_members, self.all_equities = load, index_bars, index_members, all_equities
        self.sectors, self.gap, self.sleep, self.after = sectors, gap, sleep, after
        self.lock = threading.Lock()
        self.running: str | None = None

    def run(self, region: str, now: datetime | None = None, full: bool | None = None) -> dict:
        """Work out and store every group of a market. `full`: read the whole two years (the first run does)."""
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "error": "A breadth run is already going."}
        try:
            self.running = region
            return self._run(region, now or datetime.now(ZoneInfo("UTC")), full)
        finally:
            self.running = None
            self.lock.release()

    def _run(self, region: str, now: datetime, full: bool | None) -> dict:
        groups = [g for g, v in GROUPS.items() if v["region"] == region]
        stored = {g: load_hist(g) for g in groups}
        through = last_complete(region, now)
        recent_from = (date.fromisoformat(through) - timedelta(days=RECENT_DAYS - LOOKBACK_DAYS)).isoformat()
        who = {g: members(g, self.index_members, self.all_equities) for g in groups}
        empty = [g for g in groups if not who[g]]
        if full is None:                # short of a year and a half of history, or a gap since the last run: the whole span
            # (a group with no list of stocks can't be counted, so it doesn't make every run read two years again)
            full = any(len(stored[g]) < 380 or max(stored[g]) < recent_from for g in groups if who[g])
        days = BACKFILL_DAYS if full else RECENT_DAYS
        keep_from = (date.fromisoformat(through) - timedelta(days=days - LOOKBACK_DAYS)).isoformat()
        sector_from = (date.fromisoformat(through) - timedelta(days=SECTOR_KEEP * 7 // 5 + 10)).isoformat()
        by_stock: dict[str, list[str]] = {}
        for g in groups:
            for s in who[g]:
                by_stock.setdefault(s, []).append(g)
        if not by_stock:
            raise RuntimeError("No list of stocks is available for this market yet.")
        try:
            sec = self.sectors(region) or {}
        except Exception:
            sec = {}
        tally, loaded, failed, streak, last_error = Tally(), 0, 0, 0, None
        bases: dict[str, list] = {}                              # each stock's finished days, for the intraday view
        scans: dict[str, dict[str, dict | None]] = {}            # group -> {symbol: scan_presets.evaluate answer}
        scan_secs, scan_groups = 0.0, set(scan_presets.STORED.values())
        for i, (sym, gs) in enumerate(sorted(by_stock.items())):
            if i and self.gap:
                self.sleep(self.gap)                     # leave the source room for people using the app
            try:
                bars = self.load(region, sym, days)
                flags = stock_flags(bars, through)
                streak = 0
            except Exception as e:
                failed, streak, last_error = failed + 1, streak + 1, f"{sym}: {str(e)[:120] or e.__class__.__name__}"
                if streak >= GIVE_UP and not loaded:
                    raise RuntimeError(f"The price source isn't answering ({last_error}).") from None
                continue
            if flags is None:
                continue
            loaded += 1
            base = base_row(bars, through)
            if base:
                bases[sym] = base
            for g in gs:
                tally.add(g, flags, sec.get(sym), sector_from)
            mine = [g for g in gs if g in scan_groups]
            if mine:                    # the trend scans' presets, from the candles just read (no second request)
                began = time.perf_counter()
                try:
                    res = scan_presets.evaluate(bars, through)
                except Exception as e:  # a scan problem never costs the breadth counts
                    res = None
                    print("breadth scans:", sym, str(e)[:120])
                scan_secs += time.perf_counter() - began
                for g in mine:
                    scans.setdefault(g, {})[sym] = res
        if not loaded:
            raise RuntimeError(f"No stock's prices could be read ({last_error or 'no data'}).")
        out = {}
        for g in groups:
            if not who[g]:              # nothing to count: the stored history stays as it is
                out[g] = {"days": len(stored[g]), "stocks": 0, "members": 0, "as_of": max(stored[g]) if stored[g] else None}
                continue
            index = self._index(region, GROUPS[g]["index"], days, through)
            rows = merge(stored[g], rows_of(tally.groups.get(g), index), None if not stored[g] else keep_from)
            if not stored[g]:           # the first run: only days with a full year behind them
                rows = {d: r for d, r in rows.items() if d >= keep_from}
            for d, r in rows.items():   # an index close the stored day didn't have yet
                if r[-1] is None and d in index:
                    r[-1] = index[d]
            save_hist(g, rows)
            db.set_setting(SECTOR_KEY + g, json.dumps(sectors_of(tally, g)))
            out[g] = {"days": len(rows), "stocks": tally.stocks.get(g, 0), "members": len(who[g]),
                      "as_of": max(rows) if rows else None}
        as_of = max((v["as_of"] for v in out.values() if v["as_of"]), default=None)
        if bases:
            try:
                save_base(region, through, bases)
            except Exception as e:      # the intraday view rebuilds it when it needs to
                print("breadth base save:", region, str(e)[:120])
        for g, found in scans.items():
            try:
                scan_presets.save(g, scan_presets.build(found))
            except Exception as e:
                print("breadth scans save:", g, str(e)[:120])
        # a group without its list of stocks is named in the run's status (the admin page), not passed over in silence
        if empty and not last_error:
            last_error = "No list of stocks for " + ", ".join(GROUPS[g]["name"] for g in empty)
        _set_status(region, ran_at=_now(), as_of=as_of, stocks=len(by_stock), loaded=loaded, failed=failed,
                    last_error=last_error, full=full, scan_seconds=round(scan_secs, 2), no_members=[GROUPS[g]["name"] for g in empty],
                    scan_stocks=sum(len(v) for v in scans.values()))
        if self.after:                  # the alerts on these groups, now their new day is stored
            try:
                self.after(region, groups, now)
            except Exception as e:
                print("breadth alerts failed:", region, str(e)[:160])
        return {"ok": True, "region": region, "as_of": as_of, "loaded": loaded, "failed": failed, "groups": out}

    def _index(self, region: str, symbol: str, days: int, through: str) -> dict[str, float]:
        if not self.index_bars:
            return {}
        try:
            df = _frame(self.index_bars(region, symbol, days), through)
        except Exception as e:          # the chart goes without the index, the counts still stand
            print("breadth index:", symbol, str(e)[:120])
            return {}
        return {} if df is None else {d: round(float(c), 2) for d, c in df["c"].items()}


# ---------- what the page shows ----------
def _ema(xs: list[float], n: int) -> list[float]:
    """Exponential average with weight 2/(n+1), started from the first value."""
    k, out = 2 / (n + 1), []
    for x in xs:
        out.append(x if not out else out[-1] + k * (x - out[-1]))
    return out


def _pct(a, n) -> float | None:
    return round(a / n * 100, 2) if n else None


def series(rows: dict[str, list]) -> dict:
    """Every chart's numbers, day by day, from the stored counts (oldest first)."""
    days = sorted(rows)
    r = [dict(zip(COLS, rows[d])) for d in days]
    net = [x["adv"] - x["dec"] for x in r]
    moved = [x["adv"] + x["dec"] for x in r]
    rana = [(x["adv"] - x["dec"]) / m * 1000 if m else 0.0 for x, m in zip(r, moved)]
    mcc = [a - b for a, b in zip(_ema(rana, 19), _ema(rana, 39))]
    share = [x["adv"] / m if m else 0.5 for x, m in zip(r, moved)]
    thrust = _ema(share, 10)
    line, total = [], 0
    for v in net:
        total += v
        line.append(total)
    summ, s = [], 0.0
    for v in mcc:
        s += v
        summ.append(round(s, 1))

    def trin(x):
        if x["adv"] and x["dec"] and x["av"] and x["dv"]:
            return round((x["adv"] / x["dec"]) / (x["av"] / x["dv"]), 3)
        return None

    return {
        "days": days, "adv": [x["adv"] for x in r], "dec": [x["dec"] for x in r], "unch": [x["unch"] for x in r],
        "stocks": [x["has"] for x in r], "net": net, "ad_line": line,
        "ad_ratio": [round(x["adv"] / x["dec"], 3) if x["dec"] else None for x in r],
        "pct20": [_pct(x["a20"], x["n20"]) for x in r], "pct50": [_pct(x["a50"], x["n50"]) for x in r],
        "pct200": [_pct(x["a200"], x["n200"]) for x in r],
        "highs": [x["hi"] for x in r], "lows": [x["lo"] for x in r], "net_highs": [x["hi"] - x["lo"] for x in r],
        "up4": [x["up4"] for x in r], "down4": [x["dn4"] for x in r],
        "stage2": [_pct(x["s2"], x["ns"]) for x in r],
        "mcclellan": [round(v, 2) for v in mcc], "summation": summ,
        "thrust": [round(v * 100, 2) for v in thrust], "trin": [trin(x) for x in r],
        "index": [x["idx"] for x in r],
    }


def thrusts(days: list[str], ema_pct: list[float]) -> list[str]:
    """The days a breadth thrust happened: the 10-day average over 61.5% with a reading under 40% within the last
    10 trading days. Only the first day of each run of such days is listed."""
    out, was = [], False
    for i, v in enumerate(ema_pct):
        now_ = v > 61.5 and min(ema_pct[max(0, i - 10):i + 1]) < 40
        if now_ and not was:
            out.append(days[i])
        was = now_
    return out


HEADLINE = ("adv", "dec", "unch", "ad_ratio", "pct20", "pct50", "pct200", "highs", "lows", "up4", "down4", "stage2",
            "mcclellan", "summation", "thrust", "trin", "stocks")


def today(s: dict) -> dict | None:
    """The latest day's numbers, each with the day before's and the change."""
    if not s["days"]:
        return None
    i = len(s["days"]) - 1
    out = {"day": s["days"][i], "prev_day": s["days"][i - 1] if i else None}
    for k in HEADLINE:
        cur, prev = s[k][i], s[k][i - 1] if i else None
        out[k] = {"value": cur, "prev": prev,
                  "change": round(cur - prev, 3) if isinstance(cur, (int, float)) and isinstance(prev, (int, float)) else None}
    return out


def sector_table(group: str) -> dict | None:
    """Each sector's share of stocks above the 50-day average today and 5, 21 and 63 trading days ago."""
    raw = load_sectors(group)
    days = raw.get("days") or []
    if not days:
        return None
    back = [("Today", 0), ("1 week ago", 5), ("1 month ago", 21), ("3 months ago", 63)]
    cols = [(label, len(days) - 1 - k) for label, k in back if len(days) - 1 - k >= 0]
    rows = []
    for name, v in (raw.get("sectors") or {}).items():
        a, n = v.get("a") or [], v.get("n") or []
        if len(a) != len(days) or len(n) != len(days) or not n[-1] or n[-1] < MIN_SECTOR:
            continue
        rows.append({"sector": name, "stocks": n[-1], "values": [_pct(a[i], n[i]) if a[i] is not None and n[i] else None for _, i in cols]})
    rows.sort(key=lambda x: x["sector"].lower())
    return {"columns": [{"label": label, "day": days[i]} for label, i in cols], "rows": rows}


def groups_list() -> list[dict]:
    out = []
    for gid, g in GROUPS.items():
        out.append({"id": gid, "name": g["name"], "region": g["region"], "index_name": g["index_name"]})
    return out


def view(group: str, range_: str = "1y", full: bool = True, brief: bool = False) -> dict:
    """What the page shows for a group: today's numbers (everyone), and with `full` the charts' history for the range
    and the sector table. Raises KeyError for an unknown group or range."""
    g = GROUPS[group]
    n = RANGES[range_]
    rows = load_hist(group)
    s = series(rows)
    out = {"group": {"id": group, **g}, "groups": groups_list(), "today": today(s), "as_of": s["days"][-1] if s["days"] else None,
           "since": s["days"][0] if s["days"] else None, "range": range_, "help": HELP,
           "status": (status().get(g["region"]) or {}).get("ran_at"), "locked": not full, "history": None, "sectors": None,
           "thrusts": None}
    if brief or not full or not s["days"]:
        return out
    cut = 0 if n is None else max(0, len(s["days"]) - n)
    out["history"] = {k: v[cut:] for k, v in s.items()}
    out["thrusts"] = thrusts(s["days"], s["thrust"])
    out["thrusts"] = [d for d in out["thrusts"] if d >= s["days"][cut]]
    out["sectors"] = sector_table(group)
    return out


# ---------- alerts: the share above the 50-day average crossing a level ----------
ALERT_KEY = "breadth:alerts:"         # breadth:alerts:<uid> = {"uid", "items": [{id, group, level, side, created_at, fired_at}]}
MAX_ALERTS = 5
_alock = threading.Lock()


class AlertError(ValueError):
    """An alert that can't be saved; the message says why in plain words."""


def _read_alerts(uid: str) -> dict:
    try:
        row = db.json_value(db.get_setting(ALERT_KEY + uid), {})
    except Exception:
        row = {}
    items = row.get("items")
    return {"uid": uid, "items": [a for a in items if isinstance(a, dict) and a.get("id")] if isinstance(items, list) else []}


def alerts_of(uid: str) -> list[dict]:
    return _read_alerts(uid)["items"]


def _side(v: float | None, level: float) -> str | None:
    return None if v is None else "above" if v >= level else "below"


def latest_pct50(group: str) -> tuple[str | None, float | None]:
    """The latest stored day of a group and its share of stocks above the 50-day average."""
    rows = load_hist(group)
    if not rows:
        return None, None
    day = max(rows)
    r = dict(zip(COLS, rows[day]))
    return day, _pct(r["a50"], r["n50"])


def add_alert(uid: str, group: str, level) -> dict:
    """An alert for when a group's share of stocks above their 50-day average crosses `level` (%), either way. It
    starts from where the share is now, so only a later cross sends a message; it keeps watching after each one."""
    if group not in GROUPS:
        raise AlertError("Pick a group of stocks from the list.")
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not np.isfinite(level) or not 1 <= level <= 99:
        raise AlertError("Enter a level between 1% and 99%.")
    level = round(float(level), 1)
    with _alock:
        row = _read_alerts(uid)
        if len(row["items"]) >= MAX_ALERTS:
            raise AlertError(f"You can keep up to {MAX_ALERTS} breadth alerts. Delete one to add another.")
        if any(a["group"] == group and a["level"] == level for a in row["items"]):
            raise AlertError("You already have that alert.")
        _, now_v = latest_pct50(group)
        a = {"id": secrets.token_hex(6), "group": group, "level": level, "side": _side(now_v, level),
             "created_at": _now(), "fired_at": None}
        row["items"].append(a)
        db.set_setting(ALERT_KEY + uid, json.dumps(row))
    return a


def delete_alert(uid: str, aid: str) -> bool:
    with _alock:
        row = _read_alerts(uid)
        keep = [a for a in row["items"] if a["id"] != aid]
        if len(keep) == len(row["items"]):
            return False
        row["items"] = keep
        db.set_setting(ALERT_KEY + uid, json.dumps(row))
    return True


def alert_text(a: dict, day: str, v: float) -> str:
    """"NIFTY 500: 61.2% of stocks closed above their 50-day average on 3 Oct, crossing above 60%"."""
    d = date.fromisoformat(day)
    return (f"{GROUPS[a['group']]['name']}: {v:.1f}% of stocks closed above their 50-day average on {d.day} {d:%b}, "
            f"crossing {'above' if v >= a['level'] else 'below'} {a['level']:g}%")


def check_alerts(groups: list[str], now: datetime, profile_fn, allowed_fn, send=None) -> int:
    """After a run: every alert on these groups whose level the latest share has crossed sends one message per user
    (through the stock alerts' channels and per-user limits). Users whose plan no longer has breadth alerts are
    left quiet, but their alerts still follow the share so they don't fire late. Returns messages sent."""
    from . import stock_alerts
    latest = {g: latest_pct50(g) for g in groups}
    sent = 0
    for key, raw in db.all_settings_with_prefix(ALERT_KEY):
        uid = key[len(ALERT_KEY):]
        try:
            texts = []
            with _alock:
                row = _read_alerts(uid)
                dirty = False
                for a in row["items"]:
                    day, v = latest.get(a.get("group"), (None, None))
                    side = _side(v, a.get("level", 50))
                    if side is None or side == a.get("side"):
                        continue
                    if a.get("side") is not None:
                        texts.append(alert_text(a, day, v))
                        a["fired_at"] = now.isoformat()
                    a["side"], dirty = side, True
                if dirty:
                    db.set_setting(ALERT_KEY + uid, json.dumps(row))
            if not texts:
                continue
            profile = profile_fn(uid)
            if not profile or not allowed_fn(profile):
                continue
            if not stock_alerts.may_send(stock_alerts._read(uid)["sent"], now):
                continue
            if stock_alerts.flush(uid, profile, texts, now, **({"send": send} if send else {})):
                sent += 1
        except Exception as e:          # one user's trouble never stops the others'
            print("breadth alert failed:", uid, str(e)[:160])
    return sent


# ---------- the daily job ----------
class Job(news_job.Job):
    """After each market's close on its trading days (RUN_AT), the run for that market, marked as done in the database
    (newsjob:breadth-<region>) only once it has stored its counts, so a restart doesn't repeat it and a failed run is
    tried again half an hour later. A market with no stored history yet is filled in at the first chance, any day."""

    def __init__(self, runner: Runner, ready=lambda region: True):
        super().__init__()
        self.runner, self.ready = runner, ready
        self.retry: dict[str, float] = {}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="breadth").start()

    def _loop(self):
        time.sleep(600)                 # after startup traffic and the morning data login
        super()._loop()

    def tick(self, now: datetime) -> int:
        ran = 0
        for region in REGIONS:
            name = f"breadth-{region}"
            if time.time() < self.retry.get(name, 0) or not self.ready(region):
                continue
            tz, at = RUN_AT[region]
            day = self.due(name, now, tz, at, region=region)
            if not day and (self.last.get(f"{name}-filled") or self._has_history(region, now)):
                continue
            try:
                result = self.runner.run(region, now)
            except Exception as e:
                self.retry[name] = time.time() + 1800
                self.status["last_error"] = f"{region}: {str(e)[:200]}"
                _set_status(region, last_error=str(e)[:200], failed_at=_now())
                continue
            if not result.get("ok"):
                continue
            if day:
                self.mark(name, day)
            self.last[f"{name}-filled"] = "1"
            ran += 1
            self.status.update(last_run=now.isoformat(), last_error=None)
        return ran

    def _has_history(self, region: str, now: datetime | None = None) -> bool:
        """Every group of the market has stored days (remembered, so storage is read once, not every check).

        R6O-007: this used to ask whether *some* group had days. NIFTY 500, Midcap 150 and Smallcap 250 got their lists
        of stocks (R5O-013) after the All NSE and NIFTY 50 groups had history, so the market counted as filled and the
        three empty groups waited for a scheduled run that, that day, had already been marked done before the fix was
        live. Now a group without days is filled at the first chance; the try is remembered for the day in the
        database, so a group the exchange gives no list for isn't read again on every check or restart."""
        empty = sorted(g for g, v in GROUPS.items() if v["region"] == region and not load_hist(g))
        if not empty:
            self.last[f"breadth-{region}-filled"] = "1"
            return True
        day = (now or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo(RUN_AT[region][0])).date().isoformat()
        mark = f"{day}|{','.join(empty)}"
        if db.get_setting(FILL_KEY + region) == mark:
            self.last[f"breadth-{region}-filled"] = "1"
            return True                 # tried today for these groups: the next scheduled run tries again
        db.set_setting(FILL_KEY + region, mark)
        return False
