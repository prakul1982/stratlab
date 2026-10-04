"""Exchange surveillance lists for Indian stocks: the Additional Surveillance Measure (long and short term, with
stages), the Graded Surveillance Measure, the Enhanced Surveillance Measure, trade-to-trade settlement (the BE/BZ
series), daily price-band changes, and the F&O ban period.

Facts only: which list a stock is on, at which stage, what the exchange's framework does at that stage, and the date
of the list it comes from. Nothing here calls a stock risky or says what to do about it.

The lists are read for the whole market twice a trading day (before the open, when the day's lists apply, and in the
evening, when the next day's are out) and kept in one app_settings row. Each list is read and kept on its own: one
that fails keeps the last good copy with its own date, so a page always says which day each list is from. Every
change (a stock entering, leaving or changing stage) is logged by day for the stock alerts and the My Stocks
newsletter."""
import json
import threading
from datetime import date, datetime, timedelta

from . import db
from .intel.filings import ist_now
from .intel.net import SourceError, TTLCache
from .newsletter import job as news_job

KEY = "surv:lists:IN"                # {part: {"as_of", "checked", "rows", "error", "tried"}}
CHANGES_KEY = "surv:changes:IN"      # [{"id", "day", "symbol", "list", "was", "now"}], the last KEEP_DAYS days
PARTS = ("asm", "gsm", "esm", "fo_ban", "bands")
KEEP_DAYS = 30                       # changes kept for alerts and the newsletter
MAX_CHANGES = 4000
BAND_DAYS = 7                        # a price-band change shows as a badge this long
STALE_DAYS = 4                       # a list older than this is marked as not current (long weekends included)
SOURCE = "exchange surveillance lists"
NOTE = ("From the exchange's published surveillance lists. These are the exchange's own measures, applied for a "
        "time; they say nothing about the company's business. The exchange's circulars have the full rules.")

# the lists people can filter and get alerts on: id -> (badge, name)
LISTS = {
    "asm_lt": ("LT-ASM", "Long-term ASM (Additional Surveillance Measure)"),
    "asm_st": ("ST-ASM", "Short-term ASM (Additional Surveillance Measure)"),
    "gsm": ("GSM", "GSM (Graded Surveillance Measure)"),
    "esm": ("ESM", "ESM (Enhanced Surveillance Measure)"),
    "t2t": ("T2T", "Trade-to-trade settlement"),
    "fo_ban": ("F&O ban", "F&O ban period"),
    "band": ("Band", "Price band changed"),
}
FAMILIES = {"asm": ("asm_lt", "asm_st"), "gsm": ("gsm",), "esm": ("esm",), "t2t": ("t2t",), "fo_ban": ("fo_ban",)}
FAMILY_NAME = {"asm": "ASM (long or short term)", "gsm": "GSM", "esm": "ESM", "t2t": "Trade-to-trade", "fo_ban": "F&O ban"}

# what each list is, and what the exchange's framework does at each stage: facts, as the exchange states them
ABOUT = {
    "asm_lt": "The exchange's long-term Additional Surveillance Measure list: stocks it watches more closely after "
              "unusual price moves or trading over weeks or months.",
    "asm_st": "The exchange's short-term Additional Surveillance Measure list: stocks it watches more closely after "
              "unusual price moves or trading over the last few days.",
    "gsm": "The exchange's Graded Surveillance Measure list: stocks whose price rise the exchange finds out of line "
           "with the company's financials.",
    "esm": "The exchange's Enhanced Surveillance Measure list: smaller companies (market value under ₹500 crore) "
           "whose price has moved widely.",
    "t2t": "The stock trades in the trade-to-trade segment (BE or BZ series): every trade is settled by delivery of the shares, so a "
           "position can't be opened and closed within the same day.",
    "fo_ban": "Open interest in the stock's futures and options has crossed 95% of the market-wide position limit. "
              "Until it falls below 80%, no new F&O positions can be opened; existing ones can only be reduced. "
              "Trading in the shares themselves goes on as usual.",
    "band": "The exchange changed the stock's daily price band (the circuit limit: how far the price may move in a day).",
}
STAGES = {
    "asm_lt": {1: "Stage 1: the exchange requires 100% margin.",
               2: "Stage 2: 100% margin, and the daily price band is cut to the next lower level.",
               3: "Stage 3: 100% margin, and the price band is cut one level further.",
               4: "Stage 4: 100% margin, a 5% price band, and trade-to-trade settlement."},
    "asm_st": {1: "Stage 1: a higher margin, 40% or 1.5 times the usual margin, whichever is more (at most 100%).",
               2: "Stage 2: a higher margin, 80% or 2.5 times the usual margin, whichever is more (at most 100%)."},
    "gsm": {0: "Stage 0: on the list, without the trading limits of the later stages.",
            1: "Stage 1: 100% margin and a price band of 5% or lower.",
            2: "Stage 2: trade-to-trade, a price band of 5% or lower, and the purchaser deposits 50% of the trade value with "
               "the exchange (an additional surveillance deposit).",
            3: "Stage 3: trade-to-trade, a price band of 5% or lower, trading only on the first trading day of each "
               "week, and the purchaser deposits 100% of the trade value.",
            4: "Stage 4: as Stage 3, and the price may not move up."},
    "esm": {1: "Stage 1: trade-to-trade settlement, 100% margin and a 5% price band.",
            2: "Stage 2: trade-to-trade settlement, 100% margin, a 2% price band and trading only in periodic call "
               "auctions."},
}
_cache = TTLCache(max_items=20)
_lock = threading.Lock()


# ---------- codes and words ----------
def code(lst: str, stage: int | None = None) -> str:
    """One flag as a short code: "asm_lt:2", "gsm:0", "t2t", "fo_ban", "band"."""
    return f"{lst}:{stage}" if stage is not None and lst in STAGES else lst


def split(c: str) -> tuple[str, int | None]:
    lst, _, s = str(c).partition(":")
    return lst, (int(s) if s.isdigit() else None)


def label(c: str) -> dict:
    """{"short": "LT-ASM 2", "label": "Long-term ASM …, Stage 2", "text": what the list and the stage mean}."""
    lst, stage = split(c)
    short, name = LISTS.get(lst, (lst, lst))
    about = ABOUT.get(lst, "")
    if lst in STAGES:
        if stage is None:
            return {"short": short, "label": name, "text": f"{about} The list doesn't state the stage."}
        what = STAGES[lst].get(stage, f"Stage {stage}: the exchange's circular for this list sets its measures.")
        return {"short": f"{short} {stage}", "label": f"{name}, Stage {stage}", "text": f"{about} {what}"}
    return {"short": short, "label": name, "text": about}


def _pct(v) -> str:
    return f"{v:g}%" if isinstance(v, (int, float)) else "no band"


def _day(iso: str | None) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day} {d:%b %Y}"


def change_text(c: dict) -> str:
    """One change in words: "entered Long-term ASM …, Stage 2", "moved from Stage 1 to Stage 2 of GSM …",
    "left the F&O ban period", "price band changed from 20% to 10%"."""
    lst = c.get("list")
    if lst == "band":
        return f"price band changed from {_pct(c.get('was_band'))} to {_pct(c.get('now_band'))}"
    was, now = c.get("was"), c.get("now")
    name = LISTS.get(lst, (lst, lst))[1]
    if was and now:
        return f"moved from Stage {split(was)[1]} to Stage {split(now)[1]} of {name}"
    if now:
        return f"entered {label(now)['label']}" if lst != "fo_ban" else "entered the F&O ban period"
    return f"left {name}" if lst != "fo_ban" else "left the F&O ban period"


# ---------- storage ----------
def load() -> dict:
    """The stored lists, from memory for five minutes; empty when storage can't be read."""
    hit = _cache.get("lists")
    if hit is not None:
        return hit
    try:
        st = db.json_value(db.get_setting(KEY), {})
    except Exception:
        return {}
    st = {p: v for p, v in st.items() if p in PARTS and isinstance(v, dict)}
    _cache.set("lists", st, 300)
    return st


def _flags_of(part: str, rows) -> dict[str, set]:
    """{symbol: {codes}} from one stored list."""
    out: dict[str, set] = {}
    if not isinstance(rows, dict):
        return out
    if part == "asm":
        for half, lst in (("lt", "asm_lt"), ("st", "asm_st")):
            for s, stage in (rows.get(half) or {}).items():
                out.setdefault(s, set()).add(code(lst, stage if isinstance(stage, int) else None))
    elif part in ("gsm", "esm"):
        for s, stage in rows.items():
            out.setdefault(s, set()).add(code(part, stage if isinstance(stage, int) else None))
    elif part == "fo_ban":
        for s in rows.get("symbols") or []:
            out.setdefault(str(s), set()).add("fo_ban")
    elif part == "bands":
        for s, v in (rows.get("series") or {}).items():
            if isinstance(v, list) and v and v[0] in ("BE", "BZ"):
                out.setdefault(s, set()).add("t2t")
    return out


def snapshot(today: date | None = None) -> dict:
    """Every flagged stock now: {"flags": {symbol: [codes]}, "bands": {symbol: {"band", "from", "day"}}} plus each
    list's date. Price-band changes count for BAND_DAYS."""
    today = today or ist_now().date()
    key = ("snap", today.isoformat())
    hit = _cache.get(key)
    if hit is not None:
        return hit
    st = load()
    flags: dict[str, set] = {}
    for part in PARTS:
        for s, cs in _flags_of(part, (st.get(part) or {}).get("rows")).items():
            flags.setdefault(s, set()).update(cs)
    bands = {}
    cut = (today - timedelta(days=BAND_DAYS)).isoformat()
    for s, m in (((st.get("bands") or {}).get("rows") or {}).get("moves") or {}).items():
        if isinstance(m, dict) and str(m.get("day") or "") >= cut:
            bands[s] = {"band": m.get("to"), "from": m.get("from"), "day": m.get("day")}
            flags.setdefault(s, set()).add("band")
    order = list(LISTS)
    out = {"flags": {s: sorted(cs, key=lambda c: (order.index(split(c)[0]) if split(c)[0] in order else 99, c))
                     for s, cs in flags.items()},
           "bands": bands, "lists": lists_info(st, today)}
    _cache.set(key, out, 300)
    return out


def lists_info(st: dict, today: date) -> list[dict]:
    """Each list's date and state, for the "as of" line: a list that couldn't be refreshed says so."""
    names = {"asm": "ASM", "gsm": "GSM", "esm": "ESM", "fo_ban": "F&O ban", "bands": "Trade-to-trade and price bands"}
    out = []
    for part in PARTS:
        p = st.get(part) or {}
        as_of = p.get("as_of")
        stale = not as_of or str(as_of) < (today - timedelta(days=STALE_DAYS)).isoformat()
        out.append({"id": part, "label": names[part], "as_of": as_of, "stale": stale,
                    "failed": bool(p.get("error")), "checked": p.get("checked")})
    return out


def flags_for(symbol: str, today: date | None = None) -> list[dict]:
    """One stock's flags with their words and the date of the list each comes from."""
    snap = snapshot(today)
    dates = {i["id"]: i["as_of"] for i in snap["lists"]}
    part_of = {"asm_lt": "asm", "asm_st": "asm", "gsm": "gsm", "esm": "esm", "t2t": "bands", "fo_ban": "fo_ban", "band": "bands"}
    out = []
    for c in snap["flags"].get(str(symbol).upper(), []):
        lst = split(c)[0]
        item = {"code": c, **label(c), "as_of": dates.get(part_of.get(lst, ""))}
        if lst == "band":
            b = snap["bands"].get(str(symbol).upper()) or {}
            item.update(short=f"Band {_pct(b.get('band'))}",
                        text=f"{ABOUT['band']} It is now {_pct(b.get('band'))}, from {_pct(b.get('from'))}, since {_day(b.get('day'))}.")
        out.append(item)
    return out


def view(today: date | None = None) -> dict:
    """Everything the app's badges need in one answer: the flagged stocks' codes, the words for each code in use,
    and each list's date."""
    snap = snapshot(today)
    used = {c for cs in snap["flags"].values() for c in cs}
    labels = {c: label(c) for c in sorted(used)}
    for s, b in snap["bands"].items():
        labels[f"band:{s}"] = {"short": f"Band {_pct(b.get('band'))}", "label": LISTS["band"][1],
                               "text": f"{ABOUT['band']} It is now {_pct(b.get('band'))}, from {_pct(b.get('from'))}, since {_day(b.get('day'))}."}
    dated = [i["as_of"] for i in snap["lists"] if i["as_of"]]
    return {"flags": snap["flags"], "labels": labels, "lists": snap["lists"], "as_of": max(dated) if dated else None,
            "note": NOTE, "source": SOURCE}


# ---------- reading the exchange ----------
def _read(feed, part: str):
    """(as_of day or None for today, rows to keep) for one list."""
    if part == "asm":
        got = feed.asm_list()
        return None, {"lt": dict(got.get("lt") or {}), "st": dict(got.get("st") or {})}
    if part == "gsm":
        return None, dict(feed.gsm_list())
    if part == "esm":
        return None, dict(feed.esm_list())
    if part == "fo_ban":
        day, syms = feed.fo_ban()
        return day, {"symbols": list(syms)}
    rows = feed.security_bands()
    return None, {"series": {s: [v.get("series"), v.get("band")] for s, v in rows.items()}}


def _diff(part: str, old_rows, new_rows, day: str) -> list[dict]:
    """The stocks that entered, left or changed stage between two copies of a list, one change per list."""
    out = []
    old, new = _flags_of(part, old_rows), _flags_of(part, new_rows)
    for s in sorted(set(old) | set(new)):
        for lst in {split(c)[0] for c in old.get(s, set()) | new.get(s, set())}:
            was = next((c for c in old.get(s, set()) if split(c)[0] == lst), None)
            now = next((c for c in new.get(s, set()) if split(c)[0] == lst), None)
            if was != now:
                out.append({"id": f"{day}:{s}:{lst}:{was}>{now}", "day": day, "symbol": s, "list": lst, "was": was, "now": now})
    if part == "bands":
        before = (old_rows or {}).get("series") or {}
        for s, v in ((new_rows or {}).get("series") or {}).items():
            b0 = before.get(s)
            if isinstance(b0, list) and len(b0) > 1 and isinstance(v, list) and len(v) > 1 and b0[1] != v[1] and b0[1] and v[1]:
                out.append({"id": f"{day}:{s}:band:{b0[1]}>{v[1]}", "day": day, "symbol": s, "list": "band",
                            "was": "band", "now": "band", "was_band": b0[1], "now_band": v[1]})
    return out


def refresh(feed, today: date | None = None, now: datetime | None = None) -> dict:
    """Read every list; keep each one that answered (with its date) and the old copy of each one that didn't. The
    stocks that entered, left or moved stage are logged and returned. A list read for the first time logs nothing:
    there is nothing to compare it with."""
    today = today or ist_now().date()
    now = now or ist_now()
    changes, problems = [], []
    with _lock:
        st = db.json_value(db.get_setting(KEY), {})
        for part in PARTS:
            old = st.get(part) if isinstance(st.get(part), dict) else {}
            try:
                day, rows = _read(feed, part)
            except (SourceError, ValueError, TypeError, AttributeError) as e:
                problems.append(f"{part}: {str(e)[:160]}")
                st[part] = {**old, "error": str(e)[:200], "tried": now.isoformat(timespec="minutes")}
                continue
            as_of = day or today.isoformat()
            if old.get("rows") is not None:
                changes += _diff(part, old.get("rows"), rows, as_of)
            if part == "bands":
                moves = {s: m for s, m in ((old.get("rows") or {}).get("moves") or {}).items()
                         if isinstance(m, dict) and str(m.get("day") or "") >= (today - timedelta(days=BAND_DAYS)).isoformat()}
                for c in changes:
                    if c["list"] == "band":
                        moves[c["symbol"]] = {"from": c["was_band"], "to": c["now_band"], "day": c["day"]}
                rows["moves"] = moves
            st[part] = {"as_of": as_of, "checked": now.isoformat(timespec="minutes"), "rows": rows, "error": None}
        db.set_setting(KEY, json.dumps(st))
        if changes:
            log = db.json_value(db.get_setting(CHANGES_KEY), [])
            seen = {c.get("id") for c in log if isinstance(c, dict)}
            cut = (today - timedelta(days=KEEP_DAYS)).isoformat()
            log = [c for c in log if isinstance(c, dict) and str(c.get("day") or "") >= cut]
            log += [c for c in changes if c["id"] not in seen]
            db.set_setting(CHANGES_KEY, json.dumps(log[-MAX_CHANGES:]))
    _cache.clear()
    return {"changes": changes, "problems": problems}


def changes_for(symbol: str, since: str) -> list[dict]:
    """A stock's logged changes from the day `since` (ISO) on, oldest first."""
    hit = _cache.get("changes")
    if hit is None:
        try:
            hit = db.json_value(db.get_setting(CHANGES_KEY), [])
        except Exception:
            hit = []
        _cache.set("changes", hit, 300)
    return [c for c in hit if isinstance(c, dict) and c.get("symbol") == symbol and str(c.get("day") or "") >= str(since)[:10]]


# ---------- screens ----------
def on_family(symbol: str, families: list[str] | None, today: date | None = None) -> bool:
    """The stock is on any of the lists in `families` (asm, gsm, esm, t2t, fo_ban), or on any list when none given."""
    lists = {split(c)[0] for c in snapshot(today)["flags"].get(symbol, [])} - {"band"}
    want = {lst for f in (families or FAMILIES) for lst in FAMILIES.get(f, ())}
    return bool(lists & want)


class Job(news_job.Job):
    """Twice a trading day: before the open, when the day's lists apply, and in the evening, when the next day's are
    published. Reads every list, keeps them, and sends the stock alerts on the stocks that entered or left one. Uses
    the newsletter job's run markers (newsjob:surv-am / surv-pm), so a restart never sends an alert twice. With
    nothing stored yet (a new server), it reads the lists at once."""
    RUNS = (("surv-am", "Asia/Kolkata", "08:20"), ("surv-pm", "Asia/Kolkata", "19:45"))

    def __init__(self, feed_fn, fire):
        super().__init__()
        self.feed_fn, self.fire = feed_fn, fire
        self.status.update(changes=0, problems=[])
        self._first_try = 0.0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="surveillance").start()

    def tick(self, now: datetime) -> int:
        import time
        for name, tz, at in self.RUNS:
            day = self.due(name, now, tz, at, region="IN")
            if day:
                self.mark(name, day)
                return self.run(now, day)
        if not load() and time.time() - self._first_try > 1800:
            self._first_try = time.time()
            self.run(now, ist_now().date())
        return 0

    def run(self, now: datetime, day: date) -> int:
        out = refresh(self.feed_fn(), day)
        sent = self.fire(out["changes"], now) if out["changes"] else 0
        self.status.update(last_run=now.isoformat(), sent=sent, changes=len(out["changes"]), problems=out["problems"][:5],
                           last_error=out["problems"][0][:200] if out["problems"] else None)
        return sent
