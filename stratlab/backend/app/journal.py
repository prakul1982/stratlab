"""Trade journal: the user's real trades, paired into round trips, with their own notes, and judged by the same
honesty checks as a backtest's verdict.

Four sources, kept apart and paired when the page opens:
- fills, from a broker's tradebook (every buy and sale, equity and F&O), paired first in, first out per instrument
  from flat to flat: scaling in and out stays one trade, a part-filled order is one trade, and a reversal (selling
  more than you hold) closes one trade and opens the next one short;
- lines, from a tax P&L (each exit with its entry, as the broker matched it; equity and F&O from the ZIP), which come
  already paired, with the charges the broker listed;
- trades added by hand;
- practice trades from chart replay (replay.py), already paired and charged, marked "practice" so the page can show
  real trades, practice or both.
Charges on fills are worked out with engine/costs.py at the published rates and the brokerage the user sets. An option
still open after its expiry is closed at ₹0 on its expiry (a tradebook has no line for expiry; one that expired in the
money settled at its intrinsic value, so the trade is marked and the page says so).

The stats are facts about past trades: the checks reuse the backtest verdict's wording (engine/verdict.py) and never
say what to do next. Stored per user in app_settings (journal:<uid>), seen only by that user, deleted in one step."""
import hashlib
import io
import itertools
import json
import math
import re
import secrets
import zipfile
from datetime import date, datetime, timezone

import numpy as np

from . import db
from . import holdings_file as hf
from .engine import costs as C
from .engine import verdict as V
from .intel.net import TTLCache

KEY = "journal:"
MAX_FILLS = 20000                 # tradebook lines kept (a very busy year)
MAX_LINES = 20000                 # tax P&L exits kept
MAX_MANUAL = 2000
MAX_PRACTICE = 2000               # practice trades from chart replay
SHOWS = ("all", "real", "practice")
MAX_NOTES = 5000                  # trades with a journal entry
MAX_FILES = 40
MAX_LIST = 2000                   # trades sent to the page at once (the stats use all of them)
EPS = 1e-9
SHUFFLES = 1000
CHUNK = 2_000_000                 # numbers in one reshuffle block, so a long journal never builds a huge array
BSE_INDEX = {"SENSEX", "BANKEX", "SENSEX50"}
SEGMENTS = {"eq_delivery": "Equity delivery", "eq_intraday": "Equity intraday", "fut": "Futures", "opt": "Options",
            "com": "Commodity", "cur": "Currency", "us": "US stocks", "crypto": "Crypto"}
# The markets a journal can hold. Each has its own currency, so its stats are worked out apart (a dollar is never added to
# a rupee). India covers every segment but the last two; US stocks and crypto are added by hand (no Indian charges apply,
# so their charges are the ones entered, else none).
MARKETS = {"in": {"label": "India", "currency": "INR", "symbol": "₹"},
           "us": {"label": "US stocks", "currency": "USD", "symbol": "$"},
           "crypto": {"label": "Crypto", "currency": "USD", "symbol": "$"}}
OTHER_SEGMENTS = ("us", "crypto")


def market_of(segment: str) -> str:
    return segment if segment in OTHER_SEGMENTS else "in"
EMOTIONS = ["Calm", "Confident", "Focused", "Anxious", "Fearful", "Greedy", "Impatient", "Bored", "Frustrated", "Euphoric",
            "Revenge"]
MISTAKES = ["Entered early", "Entered late", "Chased the price", "No stop", "Moved my stop", "Exited early",
            "Held too long", "Position too big", "Ignored my plan", "Overtraded", "Averaged down", "Traded the news"]
DEFAULTS = {"capital": None, "brokerage_delivery": 0.0, "brokerage_other": 20.0, "show": "all"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
HOLDS = [("m15", "Under 15 minutes"), ("h1", "15 minutes to 1 hour"), ("day", "Over an hour, same day"),
         ("sameday", "Same day (no times in the file)"), ("d5", "1 to 5 days"), ("d30", "6 to 30 days"),
         ("y1", "1 to 12 months"), ("long", "Over a year")]
R_BUCKETS = [(-math.inf, -2, "Under −2R"), (-2, -1, "−2 to −1R"), (-1, 0, "−1 to 0R"), (0, 1, "0 to 1R"), (1, 2, "1 to 2R"),
             (2, 3, "2 to 3R"), (3, math.inf, "3R or more")]
ASSUMPTIONS = ("Round trips are paired first in, first out per instrument, from flat to flat. Charges on tradebook lines "
               "are STT/CTT, exchange and SEBI fees, stamp duty and GST at today's published rates plus the brokerage you "
               "set for each line of the file; tax P&L lines keep the charges your broker listed. An option in a tradebook "
               "with no exit by its expiry is counted as expiring at ₹0 (one that expired in the money settled at a price "
               "the tradebook doesn't show; your tax P&L has it).")
MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
OPT = re.compile(r"\d.*(CE|PE)$")
FUT = re.compile(r"\d.*FUT$")

_paired = TTLCache(max_items=200, max_bytes=32 * 1024 * 1024)     # (uid, saved at) -> the round trips, for repeat opens


class FileError(hf.FileError):
    pass


# ---------- reading files ----------
def _clock(v) -> str:
    """A time of day as HH:MM:SS from "09:20", "9:20:15 AM" or a date-time; "" when there's none."""
    m = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?", str(v or ""))
    if not m:
        return ""
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if m.group(4):
        h = h % 12 + (12 if m.group(4).lower() == "pm" else 0)
    return f"{h:02d}:{mi:02d}:{s:02d}" if h < 24 and mi < 60 and s < 60 else ""


def clean_symbol(s) -> str:
    return re.sub(r"^(NSE|BSE|NFO|BFO|MCX|CDS)[:\s]+|(-EQ|\.NS|\.BO)$", "", str(s or "").strip().upper())[:40]


def classify(symbol: str, exchange: str = "", seg: str = "") -> dict:
    """What an instrument is: {"u": underlying, "group": "eq"|"fut"|"opt"|"com"|"cur", "kind": its cost model}."""
    s, ex, sg = clean_symbol(symbol), str(exchange or "").upper(), str(seg or "").upper()
    opt, fut = bool(OPT.search(s)), bool(FUT.search(s))
    if not (opt or fut):
        return {"u": s, "group": "eq", "kind": "in_eq", "opt": False}
    u = hf.underlying(s)
    if ex == "MCX" or "MCX" in sg or "COM" in sg or hf.COMMODITIES.match(u):
        return {"u": u, "group": "com", "kind": "in_mcx_opt" if opt else "in_mcx_fut", "opt": opt}
    if ex in ("CDS", "BCD") or "CDS" in sg or "CUR" in sg or hf.CURRENCIES.match(u):
        return {"u": u, "group": "cur", "kind": "in_cds_opt" if opt else "in_cds_fut", "opt": opt}
    if opt:
        return {"u": u, "group": "opt", "kind": "in_bse_opt" if ex == "BFO" or u in BSE_INDEX else "in_opt", "opt": True}
    return {"u": u, "group": "fut", "kind": "in_fut", "opt": False}


def expiry(symbol: str) -> date | None:
    """When a contract expires, from its name: NIFTY24SEP25000CE is September 2024 (counted as its last day, since
    the exact Thursday or Tuesday isn't in the name); NIFTY2491925000CE is 19 September 2024 (a weekly)."""
    s = clean_symbol(symbol)
    m = re.match(r"^[A-Z&\-]+?(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)", s)
    try:
        if m:
            y, mo = 2000 + int(m.group(1)), MONTHS[m.group(2)]
            nxt = date(y + (mo == 12), mo % 12 + 1, 1)
            return date.fromordinal(nxt.toordinal() - 1)
        m = re.match(r"^[A-Z&\-]+?(\d{2})([1-9OND])(\d{2})\d", s)
        if m:
            mo = {"O": 10, "N": 11, "D": 12}.get(m.group(2)) or int(m.group(2))
            return date(2000 + int(m.group(1)), mo, int(m.group(3)))
    except ValueError:
        return None
    return None


def _charge_cols(header: list[str]) -> tuple[int | None, list[int], list[int]]:
    keys = [hf.key(c) for c in header]
    total = next((i for i, k in enumerate(keys) if k in hf.CHARGE_TOTAL), None)
    parts = [i for i, k in enumerate(keys) if k in hf.CHARGE_PARTS]
    taxes = [i for i, k in enumerate(keys) if k in hf.BIZ_TAX]
    return total, parts, taxes


def _lines(rows, header: list[str], cols: dict, start: int, label: str, out: list, problems: list):
    """Read a tax P&L table's exits (each with its entry) into `out`: rows after the header, streamed."""
    total, parts, taxes = _charge_cols(header)
    listed = total is not None or bool(parts) or bool(taxes)
    line = start
    for row in rows:
        line += 1
        if line - start > hf.FNO_MAX_ROWS:
            raise FileError(f"{label} has more than {hf.FNO_MAX_ROWS:,} lines. Upload it a quarter at a time.")
        sym = clean_symbol(hf._cell(row, cols.get("symbol")) or hf._cell(row, cols.get("name")))
        if not sym or re.match(r"(?i)^(total|grand total|sub ?total)\b", sym):
            continue
        text = f"{label} · {sym}"[:120]
        qty = hf.number(hf._cell(row, cols.get("qty")))
        qty = abs(qty) if qty else qty
        if not qty:
            if any(hf.number(c) is not None for c in row):
                problems.append({"line": line, "text": text, "reason": "No quantity on this line."})
            continue
        bcell, scell = hf._cell(row, cols.get("buy_date")), hf._cell(row, cols.get("sell_date"))
        bd, sd = hf.day(bcell), hf.day(scell)
        bp, sp = hf.number(hf._cell(row, cols.get("buy_price"))), hf.number(hf._cell(row, cols.get("sell_price")))
        bv = bp * qty if bp is not None else hf.number(hf._cell(row, cols.get("buy_value")))
        sv = sp * qty if sp is not None else hf.number(hf._cell(row, cols.get("sell_value")))
        if not bd or not sd:
            problems.append({"line": line, "text": text, "reason": "The entry or exit date couldn't be read."})
            continue
        if bv is None or sv is None or bv < 0 or sv < 0 or max(bv, sv) > 1e12:
            problems.append({"line": line, "text": text, "reason": "The purchase or sale value couldn't be read."})
            continue
        sd_ = hf.side(hf._cell(row, cols.get("side"))) if cols.get("side") is not None else None
        tax = sum(abs(hf.number(hf._cell(row, i)) or 0) for i in taxes)
        if total is not None:
            ch = max(abs(hf.number(hf._cell(row, total)) or 0), tax)
        else:
            ch = sum(abs(hf.number(hf._cell(row, i)) or 0) for i in parts) + tax
        bt, st = _clock(bcell), _clock(scell)
        # the entry is whichever came first; a short's entry is its sale (the file says buy and sale, not which first)
        out.append({"sym": sym, "ed": bd, "et": bt, "xd": sd, "xt": st, "qty": float(qty), "bv": round(bv, 4),
                    "sv": round(sv, 4), "charges": round(min(ch, 1e10), 2) if listed else None,
                    "side": {"B": "long", "S": "short"}.get(sd_ or ""), "exchange": hf._cell(row, cols.get("exchange")).upper()[:6]})
        if len(out) >= MAX_LINES:
            break


def _fill(t: dict) -> dict:
    out = {k: t[k] for k in ("d", "t", "side", "qty", "price", "symbol", "isin", "exchange", "seg", "tid") if t.get(k) not in (None, "")}
    out["t"] = _clock(t.get("t"))                   # "2024-09-10T10:00:00" or "10:00 AM": the time of day only
    if not out["t"]:
        del out["t"]
    if not out.get("symbol") and t.get("name"):
        out["name"] = str(t["name"])[:40]          # a broker that gives the company's name and ISIN, not its symbol
    return out


def _table(rows, filename: str, label: str, got: dict):
    """One table of any shape a broker gives: a tradebook's fills or a tax P&L's exits, added to `got`."""
    it = iter(rows)
    head: list[list[str]] = []
    for row in it:
        head.append(row)
        if len(head) >= hf.HEADER_SCAN:
            break
    found = hf._trade_header(head)
    if not found:
        if hf.summary(head):
            raise FileError("That is the summary page of a tax P&L, without each trade. Upload the whole ZIP or the "
                            "\"Tradewise Exits\" files in it.")
        if hf._header(head):
            raise FileError("That looks like a holdings file, which has no trades. Upload your tradebook or tax P&L.")
        raise FileError("We couldn't find any trades in that file. It needs columns for the date, the symbol, buy or "
                        "sell, the quantity and the price (a tradebook), or the entry and exit dates with the buy and sell "
                        "values (a tax P&L).")
    at, cols, kind = found
    if kind == "trades":
        rest = list(itertools.islice(it, hf.MAX_TRADE_ROWS + 1))
        if len(rest) + len(head) > hf.MAX_TRADE_ROWS + hf.HEADER_SCAN:
            raise FileError(f"That tradebook has more than {hf.MAX_TRADE_ROWS:,} lines. {hf.TOO_BIG}")
        read = hf._read_trades(head + rest, filename, derivatives=True)
        got["fills"] += [_fill(t) for t in read["trades"]]
        got["problems"] += [{**p, "text": f"{label} · {p['text']}"[:120]} for p in read["problems"]]
        got["brokers"].append(read["broker"])
        return len(read["trades"])
    before = len(got["lines"])
    _lines(itertools.chain(head[at + 1:], it), head[at], cols, at + 1, label, got["lines"], got["problems"])
    got["brokers"].append(hf.trade_broker(head[at], head[:at], filename))
    if len(got["lines"]) == before:
        raise FileError(f"{label}: no trades could be read." + (f" Line {got['problems'][-1]['line']}: {got['problems'][-1]['reason']}" if got["problems"] else ""))
    return len(got["lines"]) - before


def _rows(data: bytes):
    """The rows of a CSV (streamed) or a workbook."""
    try:
        return hf.business_rows(data)
    except hf.FileError:
        raise
    except Exception:
        raise FileError("We couldn't read that file. Export it again from your broker as CSV or Excel.") from None


def parse(data: bytes, filename: str = "") -> dict:
    """A tradebook, a tax P&L file or a broker's ZIP of them, equity and F&O. {"broker", "fills", "lines", "problems",
    "skipped", "files"}. Raises FileError when there's nothing to read."""
    got = {"fills": [], "lines": [], "problems": [], "skipped": [], "files": [], "brokers": []}
    if data[:4] == b"PK\x03\x04" and not hf._is_xlsx(data):
        _zip(data, filename, got)
    else:
        if len(data) > hf.FNO_MAX_BYTES:
            raise FileError(f"That file is larger than {hf.FNO_MAX_BYTES // (1024 * 1024)} MB. {hf.TOO_BIG}")
        k = hf._skipped_kind(filename)
        if k:
            raise FileError(f"That is the {k[0]} file: {k[1]}, so the journal leaves it out.")
        try:
            n = _table(_rows(data), filename, hf._base(filename or "file"), got)
        except FileError:
            raise
        except hf.FileError as e:
            raise FileError(str(e)) from None
        got["files"].append({"name": hf._base(filename or "file"), "lines": n})
    if not got["fills"] and not got["lines"]:
        left = "; ".join(f"{s['name']} ({s['reason'].rstrip('.')})" for s in got["skipped"][:6])
        raise FileError("No trades were found in that file." + (f" Left out: {left}." if left else ""))
    names = [b for b in got.pop("brokers") if b != "CSV"]
    zerodha = any(re.match(r"(?i)(tradewise exits|taxpnl)", f["name"]) for f in got["files"])
    return {**got, "broker": "Zerodha" if zerodha else names[0] if names else "CSV", "problems": got["problems"][:500]}


def _zip(data: bytes, filename: str, got: dict):
    """A broker's ZIP of tax P&L files, with the same guards as the tax report's (size, number of files, what they
    unpack to, unsafe paths, ZIPs inside); every equity, F&O, commodity and currency file is read line by line."""
    if len(data) > hf.TAX_MAX_BYTES:
        raise FileError(f"That file is larger than {hf.TAX_MAX_BYTES // (1024 * 1024)} MB. {hf.TOO_BIG}")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except Exception:
        raise FileError("That ZIP file couldn't be opened. Download it again from your broker.") from None
    if len(infos) > hf.ZIP_MAX_ENTRIES:
        raise FileError(f"That ZIP has more than {hf.ZIP_MAX_ENTRIES} files in it. Upload the files from it on their own.")
    for info in infos:
        if not hf._safe_name(info.filename):
            raise FileError("That ZIP has file paths we don't accept. Unzip it and upload the CSV files in it instead.")
        if not hf._junk(info.filename) and hf.ARCHIVE_EXT.search(info.filename):
            raise FileError("That ZIP has another ZIP inside it. Unzip it and upload the files in it instead.")
    budget = [hf.ZIP_MAX_UNPACKED]
    try:
        for info in infos:
            if hf._junk(info.filename):
                continue
            base = hf._base(info.filename)
            if not hf.TABLE_EXT.search(base):
                got["skipped"].append({"name": base, "reason": "Not a CSV or Excel file."})
                continue
            k = hf._skipped_kind(base)
            if k:
                got["skipped"].append({"name": base, "reason": f"{k[0]}: {k[1]}."})
                continue
            if info.flag_bits & 0x1:
                raise FileError("That ZIP is password-protected. Unzip it on your computer and upload the CSV files in it.")
            try:
                if re.search(r"(?i)\.(csv|txt|tsv)$", base):
                    with zf.open(info) as f:
                        capped = hf._Capped(f, base, hf.FNO_MAX_BYTES, budget)
                        try:
                            n = _table(hf._csv_stream(capped), base, base, got)
                        finally:
                            budget[0] -= capped.seen
                else:
                    raw = hf._unpack(zf, info, budget, hf.FNO_MAX_BYTES)
                    if raw[:4] == b"PK\x03\x04" and not hf._is_xlsx(raw):
                        raise FileError("That ZIP has another ZIP inside it. Unzip it and upload the files in it instead.")
                    n = _table(_rows(raw), base, base, got)
            except hf.FileError as e:
                if "ZIP" in str(e) and ("inside" in str(e) or "unpacks" in str(e)):
                    raise
                why = "The summary workbook: totals only (the trades are in the other files)." \
                    if str(e).startswith("That is the summary page") else str(e)
                got["skipped"].append({"name": base, "reason": why})
                continue
            got["files"].append({"name": base, "lines": n})
            if len(got["fills"]) >= MAX_FILLS and len(got["lines"]) >= MAX_LINES:
                break
    except hf.FileError:
        raise
    except Exception:
        raise FileError("That ZIP file is damaged. Download it again from your broker.") from None


def from_tax(trades: list[dict]) -> dict:
    """The tax report's saved trades as journal input: tradebook lines become fills, and each tax P&L sale with its
    own buy (ids ending :b and :s) becomes one exit line. F&O isn't kept line by line there, so it isn't included."""
    fills, lines, pairs = [], [], {}
    for t in trades:
        if t.get("src") == "pnl" and str(t.get("tid", "")).endswith((":b", ":s")):
            pairs.setdefault(t["tid"][:-2], {})[t["side"]] = t
        elif t.get("side") in ("B", "S"):
            fills.append(_fill({**t, "symbol": t.get("sym") or t.get("symbol")}))
    for p in pairs.values():
        b, s = p.get("B"), p.get("S")
        if b and s:
            lines.append({"sym": clean_symbol(b.get("sym") or b.get("symbol") or b.get("isin")), "ed": b["d"], "et": "", "xd": s["d"],
                          "xt": "", "qty": float(s["qty"]), "bv": round(b["qty"] * b["price"], 4), "sv": round(s["qty"] * s["price"], 4),
                          "charges": None, "side": None, "exchange": str(s.get("exchange") or "")})
    return {"fills": fills, "lines": lines}


# ---------- stored ----------
def _key(uid: str) -> str:
    return KEY + uid


def _num(v, lo: float = 0.0, hi: float = 1e12) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi else None


def _day_ok(v) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v))


def _fill_ok(f) -> bool:
    return (isinstance(f, dict) and f.get("side") in ("B", "S") and _num(f.get("qty"), EPS) is not None
            and _num(f.get("price")) is not None and _day_ok(f.get("d")) and bool(f.get("symbol") or f.get("isin")))


def _line_ok(x) -> bool:
    return (isinstance(x, dict) and isinstance(x.get("sym"), str) and bool(x["sym"]) and _day_ok(x.get("ed")) and _day_ok(x.get("xd"))
            and _num(x.get("qty"), EPS) is not None and _num(x.get("bv")) is not None and _num(x.get("sv")) is not None)


def _manual_ok(m) -> bool:
    return (isinstance(m, dict) and isinstance(m.get("id"), str) and isinstance(m.get("sym"), str) and m.get("side") in ("long", "short")
            and _day_ok(m.get("ed")) and _day_ok(m.get("xd")) and _num(m.get("qty"), EPS) is not None
            and _num(m.get("entry")) is not None and _num(m.get("exit")) is not None)


def clean_settings(s) -> dict:
    s = s if isinstance(s, dict) else {}
    cap = _num(s.get("capital"), 1, 1e11)
    return {"capital": cap, "brokerage_delivery": _num(s.get("brokerage_delivery"), 0, 1000) or 0.0,
            "brokerage_other": DEFAULTS["brokerage_other"] if _num(s.get("brokerage_other"), 0, 1000) is None else float(s["brokerage_other"]),
            "show": s.get("show") if s.get("show") in SHOWS else "all"}


def load(uid: str) -> dict:
    """{"fills", "lines", "manual", "practice", "notes": {trade id: entry}, "hidden": [ids], "settings", "links": {tag:
    session id}, "files", "updated_at"}. Damaged rows are dropped, never shown."""
    got = db.json_value(db.get_setting(_key(uid)), {})
    notes = got.get("notes") if isinstance(got.get("notes"), dict) else {}
    links = got.get("links") if isinstance(got.get("links"), dict) else {}
    return {"fills": [f for f in got.get("fills") or [] if _fill_ok(f)][:MAX_FILLS],
            "lines": [x for x in got.get("lines") or [] if _line_ok(x)][:MAX_LINES],
            "manual": [m for m in got.get("manual") or [] if _manual_ok(m)][:MAX_MANUAL],
            "practice": [m for m in got.get("practice") or [] if _manual_ok(m)][-MAX_PRACTICE:],
            "notes": {k: clean_note(v) for k, v in notes.items() if isinstance(k, str) and isinstance(v, dict)},
            "hidden": [h for h in got.get("hidden") or [] if isinstance(h, str)][:MAX_FILLS],
            "settings": clean_settings(got.get("settings")),
            "links": {k[:40]: v for k, v in links.items() if isinstance(k, str) and isinstance(v, str)},
            "files": [f for f in got.get("files") or [] if isinstance(f, dict)][-MAX_FILES:],
            "updated_at": got.get("updated_at") if isinstance(got.get("updated_at"), str) else None}


def save(uid: str, data: dict) -> dict:
    data = {**data, "updated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
    data.setdefault("practice", [])
    out = {k: data[k] for k in ("fills", "lines", "manual", "practice", "notes", "hidden", "settings", "links", "files", "updated_at")}
    out["notes"] = dict(list(out["notes"].items())[-MAX_NOTES:])
    db.set_setting(_key(uid), json.dumps(out, separators=(",", ":")))
    return data


def delete(uid: str):
    db.delete_setting(_key(uid))


def _merge(old: list[dict], new: list[dict], key) -> tuple[list[dict], int, int]:
    """(rows, added, duplicates): the new rows beside the saved ones, without any already saved. Two identical lines in
    one file both count (two fills at one price); the same file uploaded again adds nothing."""
    have: dict = {}
    for r in old:
        k = key(r)
        have[k] = have.get(k, 0) + 1
    out, added, dup = list(old), 0, 0
    for r in new:
        k = key(r)
        if have.get(k, 0) > 0:
            have[k] -= 1
            dup += 1
            continue
        out.append(r)
        added += 1
    return out, added, dup


def _fill_key(f: dict) -> tuple:
    who = f.get("isin") or clean_symbol(f.get("symbol"))
    if f.get("tid"):
        return (f["d"], f["side"], who, f["tid"])
    return (f["d"], f["side"], who, round(float(f["qty"]), 4), round(float(f["price"]), 4), f.get("t") or "")


def _line_key(x: dict) -> tuple:
    return (x["sym"], x["ed"], x.get("et") or "", x["xd"], x.get("xt") or "", round(x["qty"], 4), round(x["bv"], 2), round(x["sv"], 2))


def add(data: dict, parsed: dict) -> dict:
    """The parsed file's fills and lines added to the journal: {"added", "duplicates", "over"}."""
    fills, fa, fd = _merge(data["fills"], parsed["fills"], _fill_key)
    lines, la, ld = _merge(data["lines"], parsed["lines"], _line_key)
    over = max(0, len(fills) - MAX_FILLS) + max(0, len(lines) - MAX_LINES)
    data["fills"], data["lines"] = fills[:MAX_FILLS], lines[:MAX_LINES]
    return {"added": fa + la, "duplicates": fd + ld, "over": over}


# ---------- one journal entry ----------
def _text(v, n: int) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(v or "")).strip()[:n]


def clean_note(v: dict) -> dict:
    """What a trade's journal entry keeps: the setup tag, notes, links (text only), feelings and mistakes from the
    lists, the planned stop and target, and the side when the file didn't say."""
    out = {}
    tag = _text(v.get("tag"), 40)
    if tag:
        out["tag"] = tag
    notes = _text(v.get("notes"), 2000)
    if notes:
        out["notes"] = notes
    links = [_text(x, 300) for x in (v.get("links") or [])[:5] if isinstance(x, str) and _text(x, 300)] if isinstance(v.get("links"), list) else []
    if links:
        out["links"] = links
    for k, allowed in (("emotions", EMOTIONS), ("mistakes", MISTAKES)):
        picked = [x for x in allowed if isinstance(v.get(k), list) and x in v[k]]
        if picked:
            out[k] = picked
    for k in ("stop", "target"):
        n = _num(v.get(k), 0, 1e11)
        if n is not None and n > 0:
            out[k] = n
    if v.get("side") in ("long", "short"):
        out["side"] = v["side"]
    return out


# ---------- pairing ----------
def _at(d: str, t: str) -> str:
    return f"{d}T{t}" if t else d


def _seg(group: str, intraday: bool) -> str:
    return ("eq_intraday" if intraday else "eq_delivery") if group == "eq" else group


def _hold(ed: str, et: str, xd: str, xt: str) -> tuple[float | None, float]:
    """(seconds held when both times are known, else None; days between the dates)."""
    try:
        days = (date.fromisoformat(xd) - date.fromisoformat(ed)).days
    except ValueError:
        days = 0
    if et and xt:
        try:
            s = (datetime.fromisoformat(_at(xd, xt)) - datetime.fromisoformat(_at(ed, et))).total_seconds()
            return max(0.0, s), days
        except ValueError:
            pass
    return None, days


def _hid(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _brokerage(kind: str, s: dict) -> float:
    return s["brokerage_delivery"] if kind == "in_eq" else s["brokerage_other"]


def _cost(kind: str, side: str, qty: float, price: float, brokerage: float) -> float:
    return C.total(C.order_costs(kind, side, qty, price, brokerage))


class _Episode:
    """One position from flat to flat: its entry and exit portions of fills."""

    def __init__(self, key: str, sign: int, f: dict, info: dict):
        self.key, self.sign, self.info = key, sign, info
        self.symbol = clean_symbol(f.get("symbol") or f.get("name") or f.get("isin"))
        self.entries: list[tuple[dict, float]] = []
        self.exits: list[tuple[dict, float]] = []
        self.pos = 0.0
        self.expired = False

    def trade(self, s: dict) -> dict:
        first, last = self.entries[0][0], self.exits[-1][0]
        intraday = first["d"] == last["d"]
        kind = self.info["kind"]
        if kind == "in_eq" and intraday:
            kind = "in_eq_mis"
        bought = [(f, q) for f, q in (self.entries if self.sign > 0 else self.exits)]
        sold = [(f, q) for f, q in (self.exits if self.sign > 0 else self.entries)]
        bv = sum(f["price"] * q for f, q in bought)
        sv = sum(f["price"] * q for f, q in sold)
        charges = 0.0
        for side, part in (("buy", bought), ("sell", sold)):
            for f, q in part:
                brk = 0.0 if f.get("expired") else _brokerage(kind, s) * (q / f["qty"])
                charges += _cost(kind, side, q, f["price"], brk)
        qty = sum(q for _, q in self.entries)
        entry = sum(f["price"] * q for f, q in self.entries) / qty
        exit_ = sum(f["price"] * q for f, q in self.exits) / max(sum(q for _, q in self.exits), EPS)
        hold_s, days = _hold(first["d"], first.get("t") or "", last["d"], last.get("t") or "")
        gross = sv - bv
        return {"id": _hid("f", self.key, first["d"], first.get("t") or "", first.get("tid") or first["price"], self.sign),
                "symbol": self.symbol, "u": self.info["u"], "segment": _seg(self.info["group"], intraday),
                "side": "long" if self.sign > 0 else "short", "entry_t": _at(first["d"], first.get("t") or ""),
                "exit_t": _at(last["d"], last.get("t") or ""), "qty": round(qty, 6), "entry": entry, "exit": exit_,
                "gross": gross, "charges": charges, "net": gross - charges, "hold_s": hold_s, "hold_days": days,
                "fills": len(self.entries) + len(self.exits), "src": "tradebook", "expired": self.expired, "charges_from": "rates"}


def _fill_order(f: dict) -> tuple:
    return (f["d"], f.get("t") or "")


def pair_fills(fills: list[dict], s: dict, today: date) -> tuple[list[dict], list[dict], list[dict]]:
    """(closed trades, open positions, sales with no purchase before them) from tradebook fills."""
    groups: dict[str, list[tuple[int, dict]]] = {}
    for i, f in enumerate(fills):
        k = f.get("isin") or clean_symbol(f.get("symbol"))
        groups.setdefault(k, []).append((i, f))
    trades, open_, unmatched = [], [], []
    for k, fs in groups.items():
        fs.sort(key=lambda x: (_fill_order(x[1]), x[0]))      # by time; the file's order within a time
        info = classify(fs[0][1].get("symbol") or k, fs[0][1].get("exchange", ""), fs[0][1].get("seg", ""))
        ep: _Episode | None = None
        for _, f in fs:
            sign = 1 if f["side"] == "B" else -1
            q = float(f["qty"])
            while q > EPS:
                if ep is None:
                    ep = _Episode(k, sign, f, info)
                if sign == ep.sign:
                    ep.entries.append((f, q))
                    ep.pos += q
                    q = 0.0
                else:
                    c = min(q, ep.pos)
                    ep.exits.append((f, c))
                    ep.pos -= c
                    q -= c
                    if ep.pos <= EPS:
                        trades.append(ep.trade(s))
                        ep = None
        if ep is None:
            continue
        exp = expiry(ep.symbol) if info["opt"] else None
        if exp and exp < today:
            # an option with no exit after its expiry: counted as expiring worthless (one that expired in the money
            # settled at its intrinsic value, which a tradebook doesn't show; the trade is marked so the page says so)
            ep.exits.append(({"d": exp.isoformat(), "t": "15:30:00", "price": 0.0, "qty": ep.pos, "expired": True}, ep.pos))
            ep.expired = True
            trades.append(ep.trade(s))
            continue
        avg = sum(f["price"] * q for f, q in ep.entries) / max(sum(q for _, q in ep.entries), EPS)
        row = {"symbol": ep.symbol, "side": "long" if ep.sign > 0 else "short", "qty": round(ep.pos, 6),
               "since": _at(ep.entries[0][0]["d"], ep.entries[0][0].get("t") or ""), "avg": round(avg, 4),
               # what the part already closed made before charges (the trade counts once it's flat)
               "realised": round(sum(ep.sign * (f["price"] - avg) * q for f, q in ep.exits), 2)}
        if info["group"] == "eq" and ep.sign < 0 and not ep.exits:
            unmatched.append(row)              # shares sold that were bought before the earliest file
        else:
            open_.append(row)
    return trades, open_, unmatched


def line_trades(lines: list[dict], s: dict) -> list[dict]:
    """Tax P&L exits as trades: a part-filled exit (the same contract, entry and exit) is one trade."""
    merged: dict[tuple, dict] = {}
    for x in lines:
        k = (x["sym"], x["ed"], x.get("et") or "", x["xd"], x.get("xt") or "", x.get("side"))
        m = merged.get(k)
        if m is None:
            merged[k] = {**x, "n": 1}
        else:
            for f in ("qty", "bv", "sv"):
                m[f] += x[f]
            m["charges"] = None if m["charges"] is None or x.get("charges") is None else m["charges"] + x["charges"]
            m["n"] += 1
    out, seen = [], {}
    for k, x in merged.items():
        info = classify(x["sym"], x.get("exchange", ""))
        intraday = x["ed"] == x["xd"]
        kind = "in_eq_mis" if info["kind"] == "in_eq" and intraday else info["kind"]
        qty = x["qty"]
        bp, sp = x["bv"] / qty, x["sv"] / qty
        if x.get("charges") is None:
            brk = _brokerage(kind, s)
            charges, src = _cost(kind, "buy", qty, bp, brk) + _cost(kind, "sell", qty, sp, brk), "rates"
        else:
            charges, src = float(x["charges"]), "file"
        hold_s, days = _hold(x["ed"], x.get("et") or "", x["xd"], x.get("xt") or "")
        tid = _hid("l", *k, round(qty, 4), round(x["bv"], 2))
        seen[tid] = seen.get(tid, 0) + 1
        if seen[tid] > 1:
            tid = f"{tid}{seen[tid]}"
        side = x.get("side")
        out.append({"id": tid, "symbol": x["sym"], "u": info["u"], "segment": _seg(info["group"], intraday), "side": side,
                    "entry_t": _at(x["ed"], x.get("et") or ""), "exit_t": _at(x["xd"], x.get("xt") or ""), "qty": round(qty, 6),
                    "entry": sp if side == "short" else bp, "exit": bp if side == "short" else sp, "buy": bp, "sell": sp,
                    "gross": x["sv"] - x["bv"], "charges": charges, "net": x["sv"] - x["bv"] - charges, "hold_s": hold_s,
                    "hold_days": days, "fills": x["n"], "src": "pnl", "expired": False, "charges_from": src})
    return out


def manual_trades(manual: list[dict], s: dict, src: str = "manual") -> list[dict]:
    """Trades added by hand, or practice trades from chart replay (src "practice", their charges worked out when they
    were played)."""
    out = []
    for m in manual:
        info = classify(m["sym"], m.get("exchange", ""))
        if m.get("segment") in OTHER_SEGMENTS:
            info = {"u": clean_symbol(m["sym"]), "group": m["segment"], "kind": None, "opt": False}
        elif m.get("segment") in ("fut", "opt", "com", "cur") and info["group"] == "eq":
            info = {**info, "group": m["segment"], "kind": {"fut": "in_fut", "opt": "in_opt", "com": "in_mcx_fut", "cur": "in_cds_fut"}[m["segment"]]}
        intraday = m["ed"] == m["xd"]
        kind = "in_eq_mis" if info["kind"] == "in_eq" and intraday else info["kind"]
        qty, sign = m["qty"], 1 if m["side"] == "long" else -1
        gross = sign * (m["exit"] - m["entry"]) * qty
        if _num(m.get("charges")) is not None:
            charges, src_c = float(m["charges"]), "you" if src == "manual" else "replay"
        elif info["kind"] is None:
            charges, src_c = 0.0, "none"
        else:
            brk = _brokerage(kind, s)
            buy_px, sell_px = (m["entry"], m["exit"]) if sign > 0 else (m["exit"], m["entry"])
            charges, src_c = _cost(kind, "buy", qty, buy_px, brk) + _cost(kind, "sell", qty, sell_px, brk), "rates"
        hold_s, days = _hold(m["ed"], m.get("et") or "", m["xd"], m.get("xt") or "")
        out.append({"id": m["id"], "symbol": clean_symbol(m["sym"]), "u": info["u"], "segment": _seg(info["group"], intraday),
                    "side": m["side"], "entry_t": _at(m["ed"], m.get("et") or ""), "exit_t": _at(m["xd"], m.get("xt") or ""),
                    "qty": qty, "entry": m["entry"], "exit": m["exit"], "gross": gross, "charges": charges, "net": gross - charges,
                    "hold_s": hold_s, "hold_days": days, "fills": 2, "src": src, "expired": False, "charges_from": src_c})
    return out


def trades(uid: str, data: dict, today: date) -> dict:
    """{"trades": every closed trade, oldest exit first, with its journal entry; "open"; "unmatched"}. Worked out once
    per saved version of the journal and kept in a bounded cache."""
    ck = (uid, data["updated_at"], today.isoformat())
    hit = _paired.get(ck)
    if hit is None:
        s = data["settings"]
        a, open_, unmatched = pair_fills(data["fills"], s, today)
        lines = covered(data["fills"], data["lines"])
        all_ = a + line_trades(lines, s) + manual_trades(data["manual"], s) + manual_trades(data.get("practice") or [], s, "practice")
        ids: dict[str, int] = {}
        for t in all_:                         # the same id twice (identical trades): number the later ones
            ids[t["id"]] = ids.get(t["id"], 0) + 1
            if ids[t["id"]] > 1:
                t["id"] = f"{t['id']}-{ids[t['id']]}"
        all_.sort(key=lambda t: (t["exit_t"], t["entry_t"], t["id"]))
        hit = {"trades": all_, "open": open_[:200], "unmatched": unmatched[:200], "overlap": len(data["lines"]) - len(lines)}
        _paired.set(ck, hit, ttl=600)
    hidden = set(data["hidden"])
    out = []
    for t in hit["trades"]:
        if t["id"] in hidden:
            continue
        note = data["notes"].get(t["id"]) or {}
        t = {**t, "note": note}
        if note.get("side") and t["src"] == "pnl" and note["side"] != t["side"]:
            t["side"] = note["side"]
            t["entry"], t["exit"] = (t["sell"], t["buy"]) if note["side"] == "short" else (t["buy"], t["sell"])
        t["r"] = r_multiple(t)
        out.append(t)
    return {"trades": out, "open": hit["open"], "unmatched": hit["unmatched"], "overlap": hit["overlap"]}


def covered(fills: list[dict], lines: list[dict]) -> list[dict]:
    """The tax P&L lines a tradebook doesn't already cover: a line for a symbol whose fills span its entry and exit
    dates is the same trade seen twice (the tradebook and the tax P&L of one year), so the tradebook's version, with
    its times and side, is kept. An option's span runs to its expiry, where a tradebook has no line."""
    span: dict[str, tuple[str, str]] = {}
    for f in fills:
        k = clean_symbol(f.get("symbol") or f.get("name") or f.get("isin"))
        a, b = span.get(k, (f["d"], f["d"]))
        exp = expiry(k) if OPT.search(k) else None
        span[k] = (min(a, f["d"]), max(b, f["d"], exp.isoformat() if exp else ""))
    return [x for x in lines if not (x["sym"] in span and span[x["sym"]][0] <= x["ed"] and x["xd"] <= span[x["sym"]][1])]


def r_multiple(t: dict) -> float | None:
    """The result in units of the risk planned: net P&L ÷ (distance from entry to the planned stop × quantity)."""
    stop = (t.get("note") or {}).get("stop")
    if not stop or t.get("side") not in ("long", "short") or not t.get("qty"):
        return None
    risk = abs(t["entry"] - stop) * t["qty"]
    if risk <= EPS or (t["side"] == "long" and stop >= t["entry"]) or (t["side"] == "short" and stop <= t["entry"]):
        return None
    return t["net"] / risk


# ---------- stats ----------
def _r(v, dp: int = 2):
    return None if v is None or not math.isfinite(v) else round(float(v), dp)


def _dd(nets: list[float], capital: float | None) -> tuple[float, float | None]:
    """(the deepest fall in rupees from a high of the running P&L, the same as a % of capital plus P&L at that high)."""
    path = np.concatenate([[0.0], np.cumsum(nets)]) if nets else np.array([0.0])
    peak = np.maximum.accumulate(path)
    rupees = float(np.max(peak - path))
    pct = None
    if capital:
        cpath, cpeak = capital + path, capital + peak
        pct = float(np.max((cpeak - cpath) / cpeak) * 100)
    return rupees, pct


def _streaks(nets: list[float]) -> dict:
    best = {"win": 0, "loss": 0}
    cur_kind, cur = None, 0
    for v in nets:
        kind = "win" if v > 0 else "loss" if v < 0 else None
        if kind and kind == cur_kind:
            cur += 1
        else:
            cur_kind, cur = kind, (1 if kind else 0)
        if kind:
            best[kind] = max(best[kind], cur)
    return {"longest_win": best["win"], "longest_loss": best["loss"], "current": {"kind": cur_kind, "n": cur}}


def summary(ts: list[dict], capital: float | None = None) -> dict:
    """Win rate, average win and loss, expectancy, profit factor, the deepest fall, streaks, charges against the gross
    result, and the running P&L, for trades in order of their exit."""
    nets = [t["net"] for t in ts]
    wins, losses = [v for v in nets if v > 0], [v for v in nets if v < 0]
    gross, charges, net = sum(t["gross"] for t in ts), sum(t["charges"] for t in ts), sum(nets)
    dd, dd_pct = _dd(nets, capital)
    holds = [t["hold_s"] / 86400 if t.get("hold_s") is not None else t["hold_days"] for t in ts]
    eq, run = [], 0.0
    step = max(1, len(ts) // 1500)                # at most ~1,500 points drawn; every high and low is still in the stats
    for i, t in enumerate(ts):
        run += t["net"]
        if i % step == 0 or i == len(ts) - 1:
            eq.append({"t": t["exit_t"], "v": round(run, 2)})
    return {"n": len(ts), "wins": len(wins), "losses": len(losses), "flat": len(ts) - len(wins) - len(losses),
            "win_rate": _r(len(wins) / len(ts) * 100, 1) if ts else None,
            "avg_win": _r(sum(wins) / len(wins)) if wins else None, "avg_loss": _r(sum(losses) / len(losses)) if losses else None,
            "expectancy": _r(net / len(ts)) if ts else None,
            "profit_factor": _r(sum(wins) / -sum(losses)) if losses else None, "best": _r(max(nets)) if nets else None,
            "worst": _r(min(nets)) if nets else None, "gross": _r(gross), "charges": _r(charges), "net": _r(net),
            "charges_pct": _r(charges / gross * 100, 1) if gross > 0 else None,
            "max_dd": _r(dd), "max_dd_pct": _r(dd_pct, 1), "avg_hold_days": _r(sum(holds) / len(holds), 2) if holds else None,
            "streaks": _streaks(nets), "first": ts[0]["entry_t"][:10] if ts else None, "last": ts[-1]["exit_t"][:10] if ts else None,
            "equity": eq}


def _group(ts: list[dict], keyfn, order: list | None = None, top: int | None = None) -> list[dict]:
    rows: dict = {}
    for t in ts:
        for k in keyfn(t):
            r = rows.setdefault(k, {"n": 0, "wins": 0, "net": 0.0, "gross": 0.0, "charges": 0.0})
            r["n"] += 1
            r["wins"] += t["net"] > 0
            r["net"] += t["net"]
            r["gross"] += t["gross"]
            r["charges"] += t["charges"]
    items = list(rows.items())
    if order is not None:
        items.sort(key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order))
    else:
        items.sort(key=lambda kv: -abs(kv[1]["net"]))
    if top and len(items) > top:
        rest = items[top:]
        items = items[:top] + [("Others", {f: sum(x[f] for _, x in rest) for f in ("n", "wins", "net", "gross", "charges")})]
    return [{"key": k, "n": r["n"], "win_rate": _r(r["wins"] / r["n"] * 100, 1), "net": _r(r["net"]), "avg": _r(r["net"] / r["n"]),
             "gross": _r(r["gross"]), "charges": _r(r["charges"])} for k, r in items]


def _hold_bucket(t: dict) -> str:
    if t["hold_days"] == 0:
        if t.get("hold_s") is None:
            return "sameday"
        return "m15" if t["hold_s"] < 900 else "h1" if t["hold_s"] < 3600 else "day"
    d = t["hold_days"]
    return "d5" if d <= 5 else "d30" if d <= 30 else "y1" if d <= 365 else "long"


def _weekday(t: dict) -> str:
    try:
        return WEEKDAYS[date.fromisoformat(t["entry_t"][:10]).weekday()]
    except ValueError:
        return "?"


def breakdowns(ts: list[dict]) -> dict:
    """The net result by weekday, entry hour (intraday trades with times), setup tag, instrument, holding time,
    segment, side, feeling and mistake: each a list of {key, n, win_rate, net, avg, gross, charges}."""
    hold_names = dict(HOLDS)
    timed = [t for t in ts if "T" in t["entry_t"] and t["hold_days"] == 0]
    hours = _group(timed, lambda t: [f"{t['entry_t'][11:13]}:00"])
    hours.sort(key=lambda r: r["key"])
    hold = _group(ts, lambda t: [_hold_bucket(t)], [k for k, _ in HOLDS])
    return {"weekday": _group(ts, lambda t: [_weekday(t)], WEEKDAYS),
            "hour": [{**r, "label": f"{r['key']}–{r['key'][:2]}:59"} for r in hours],
            "tag": _group(ts, lambda t: [t["note"].get("tag") or "Untagged"], top=30),
            "instrument": _group(ts, lambda t: [t["u"] or t["symbol"]], top=25),
            "hold": [{**r, "label": hold_names.get(r["key"], r["key"])} for r in hold],
            "segment": [{**r, "label": SEGMENTS.get(r["key"], r["key"])} for r in _group(ts, lambda t: [t["segment"]], list(SEGMENTS))],
            "side": _group(ts, lambda t: [{"long": "Long", "short": "Short"}.get(t["side"] or "", "Not in the file")],
                           ["Long", "Short", "Not in the file"]),
            "emotion": _group([t for t in ts if t["note"].get("emotions")], lambda t: t["note"]["emotions"], EMOTIONS),
            "mistake": _group([t for t in ts if t["note"].get("mistakes")], lambda t: t["note"]["mistakes"], MISTAKES)}


def r_distribution(ts: list[dict]) -> dict:
    """How many trades ended in each band of R (trades with a planned stop), the average R and the planned
    reward-to-risk from the targets."""
    rs = [t["r"] for t in ts if t.get("r") is not None]
    buckets = [{"label": lab, "n": sum(1 for r in rs if lo <= r < hi)} for lo, hi, lab in R_BUCKETS]
    plans = []
    for t in ts:
        n = t.get("note") or {}
        if t.get("r") is not None and n.get("target"):
            risk, reward = abs(t["entry"] - n["stop"]), abs(n["target"] - t["entry"])
            if risk > EPS:
                plans.append(reward / risk)
    return {"n": len(rs), "of": len(ts), "avg": _r(sum(rs) / len(rs)) if rs else None, "buckets": buckets,
            "planned_rr": _r(sum(plans) / len(plans)) if plans else None, "planned_n": len(plans),
            "hit_target": sum(1 for t in ts if t.get("r") is not None and (t.get("note") or {}).get("target")
                              and ((t["side"] == "long" and t["exit"] >= t["note"]["target"]) or (t["side"] == "short" and t["exit"] <= t["note"]["target"])))}


# ---------- the verdict's checks, on real trades ----------
def _coin(wins: int, n: int) -> float:
    """The chance of `wins` or more heads in `n` tosses of a fair coin (a normal approximation for long runs)."""
    if n <= 0:
        return 1.0
    if n <= 400:
        return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n
    z = (wins - 0.5 - n / 2) / math.sqrt(n / 4)
    return 0.5 * math.erfc(z / math.sqrt(2))


def win_rate_line(n: int, wins: int) -> str | None:
    """"With 23 trades, a 61% win rate could easily be luck…" when a coin would do as well often enough."""
    if not n or wins * 2 <= n:
        return None
    p = _coin(wins, n)
    if p <= 0.05:
        return None
    return (f"With {n} trades, a {wins / n * 100:.0f}% win rate could easily be luck: tossing a coin {n} times gives "
            f"{wins} or more heads {p * 100:.0f}% of the time.")


def _flips(nets: np.ndarray) -> float:
    """The share of random sign flips of the same trade sizes that make at least as much as the real trades: how
    often trades with no edge at all would have done as well."""
    rng = np.random.default_rng(42)
    size, total, hits, done = np.abs(nets), float(nets.sum()), 0, 0
    rows = max(1, CHUNK // max(len(nets), 1))
    while done < SHUFFLES:
        k = min(rows, SHUFFLES - done)
        signs = rng.integers(0, 2, size=(k, len(nets)), dtype=np.int8) * 2 - 1
        hits += int(np.sum(signs @ size >= total - 1e-9))
        done += k
    return (hits + 1) / (SHUFFLES + 1)


def check_luck(nets: list[float]) -> dict:
    """Luck or edge: would random wins and losses of the same sizes have done as well? And did the later half of the
    trades make money too (the real-trade version of the backtest's unseen-data check)?"""
    n = len(nets)
    title = "Luck or edge"
    if n < 5:
        return {"id": "luck", "title": title, "status": "skip", "detail": "Too few trades to test against luck.", "data": None}
    arr = np.array(nets, dtype=float)
    k = n // 2
    wins = int(np.sum(arr > 0))
    data = {"earlier": _r(float(arr[:k].sum())), "later": _r(float(arr[k:].sum())), "earlier_n": k, "later_n": n - k,
            "wins": wins, "trades": n, "p": None, "runs": SHUFFLES, "coin": _r(_coin(wins, n) * 100, 1)}
    if arr.sum() <= 0:
        return {"id": "luck", "title": title, "status": "fail", "data": data,
                "detail": "After charges your trades lost money, so there's no edge to tell from luck."}
    p = _flips(arr)
    data["p"] = _r(p * 100, 1)
    pct = f"{p * 100:.0f}%" if p >= 0.01 else "under 1%"
    if p <= 0.05:
        status, detail = "pass", f"Random wins and losses of the same sizes did as well only {pct} of the time, so luck alone is an unlikely explanation."
        if data["later"] <= 0:
            status, detail = "warn", detail + " But the later half of your trades lost money."
    elif p <= 0.2:
        status, detail = "warn", f"Random wins and losses of the same sizes did as well {pct} of the time. It could be skill or a lucky run."
    else:
        status, detail = "fail", f"Random wins and losses of the same sizes did as well {pct} of the time, so this result could easily be luck."
    line = win_rate_line(n, wins)
    return {"id": "luck", "title": title, "status": status, "detail": f"{line} {detail}" if line and status != "pass" else detail, "data": data}


def _rupee_dds(pnls: np.ndarray, rng) -> np.ndarray:
    out, rows = [], max(1, CHUNK // max(len(pnls), 1))
    for i in range(0, SHUFFLES, rows):
        m = np.stack([rng.permutation(pnls) for _ in range(min(rows, SHUFFLES - i))])
        path = np.concatenate([np.zeros((m.shape[0], 1)), np.cumsum(m, axis=1)], axis=1)
        out.append(np.max(np.maximum.accumulate(path, axis=1) - path, axis=1))
    return np.concatenate(out)


def money(v: float, sym: str = "₹") -> str:
    return sym + f"{abs(v):,.0f}"


def check_drawdown(nets: list[float], capital: float | None, sym: str = "₹") -> dict:
    """The backtest's bad-luck drawdown check on real trades: as a % of the capital the user entered, else in rupees."""
    if capital:
        c = V.check_shuffle([{"pnl": v} for v in nets], capital, who="Your trades", whose="your trades'")
        if c["data"]:
            c["data"] = {**c["data"], "unit": "pct"}
        return c
    pnls = np.array(nets, dtype=float)
    if len(pnls) < 5:
        return {"id": "shuffle", "title": "Bad-luck drawdown", "status": "skip", "detail": "Too few trades to reshuffle.", "data": None}
    dds = _rupee_dds(pnls, np.random.default_rng(42))
    yours, p95, worst = _dd(nets, None)[0], float(np.percentile(dds, 95)), float(dds.max())
    if p95 > max(1.5 * yours, yours + 1):
        status = "warn"
        detail = f"Your trades fell {money(yours, sym)} at worst from a high, but with worse luck the same trades could have fallen {money(p95, sym)}."
    else:
        status = "pass"
        detail = f"Even with worse luck, falls stay around {money(p95, sym)}, close to your trades' {money(yours, sym)}."
    return {"id": "shuffle", "title": "Bad-luck drawdown", "status": status, "detail": detail,
            "data": {"yours": yours, "p95": p95, "worst": worst, "runs": SHUFFLES, "unit": "rupees"}}


def check_costs(ts: list[dict], sym: str = "₹") -> dict:
    """Cost sensitivity: would the result survive charges twice as high (a costlier broker, more slippage)?"""
    gross, charges = sum(t["gross"] for t in ts), sum(t["charges"] for t in ts)
    net, doubled = gross - charges, gross - 2 * charges
    title = "Cost sensitivity"
    data = {"gross": _r(gross), "charges": _r(charges), "net": _r(net), "doubled": _r(doubled),
            "pct": _r(charges / gross * 100, 1) if gross > 0 else None}
    if not ts:
        return {"id": "costs", "title": title, "status": "skip", "detail": "No trades yet.", "data": None}
    if gross <= 0:
        status, detail = "fail", f"Before charges your trades already lost {money(gross, sym)}; charges of {money(charges, sym)} added to it."
    elif net <= 0:
        status, detail = "fail", f"Charges of {money(charges, sym)} turned a gross profit of {money(gross, sym)} into a loss."
    elif doubled > 0:
        status, detail = "pass", f"Charges took {data['pct']:.0f}% of the gross profit. Even with charges doubled, your trades would still be {money(doubled, sym)} up."
    else:
        status, detail = "warn", f"Charges took {data['pct']:.0f}% of the gross profit. With charges doubled, the profit would be gone."
    return {"id": "costs", "title": title, "status": status, "detail": detail, "data": data}


def verdict(ts: list[dict], capital: float | None = None, sym: str = "₹") -> dict:
    """The four checks on real trades and a verdict in the backtest verdict's words: enough trades (the verdict's own
    check), luck or edge, bad-luck drawdown, and cost sensitivity. The nearby-settings check needs rules to nudge, so
    it doesn't apply to real trades."""
    nets = [t["net"] for t in ts]
    checks = [V.check_sample(len(ts)), check_luck(nets), check_drawdown(nets, capital, sym), check_costs(ts, sym)]
    return decide(checks, len(ts), sum(nets), sum(1 for v in nets if v > 0))


def decide(checks: list[dict], n: int, net: float, wins: int) -> dict:
    by = {c["id"]: c["status"] for c in checks}
    line = win_rate_line(n, wins)
    if n < 15:
        verdict_ = "not_enough"
        summary_ = (f"Only {n} closed trade{'s' if n != 1 else ''} here. That's too few to tell a real edge from a lucky "
                    "streak, whatever the P&L says." + (f" {line}" if line else ""))
    elif net <= 0:
        verdict_ = "no_edge"
        summary_ = "After charges, your trades lost money over this period, so there's no edge to test."
    elif by["luck"] == "fail" or by["costs"] == "fail":
        verdict_ = "luck"
        bits = []
        if by["luck"] == "fail":
            bits.append("random wins and losses of the same sizes often did as well")
        if by["costs"] == "fail":
            bits.append("charges took the whole profit")
        summary_ = "Your trades made money overall, but " + " and ".join(bits) + ". The profit looks like it could be luck."
    elif by["luck"] == "pass" and by["sample"] == "pass" and by["shuffle"] != "fail" and by["costs"] == "pass":
        verdict_ = "edge"
        summary_ = ("Your trades made money after charges, did better than random wins and losses of the same sizes, and "
                    "would still be in profit with charges doubled.")
    else:
        verdict_ = "mixed"
        summary_ = "Some checks pass and some don't. Treat it as a maybe: more trades will tell."
    return {"verdict": verdict_, "headline": V.HEADLINES[verdict_], "summary": summary_,
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "total": sum(1 for c in checks if c["status"] != "skip"), "checks": checks}


# ---------- paper trading beside real ----------
def paper_trades(row: dict) -> list[dict]:
    """A paper session's closed trades as {net, entry_t, exit_t}: single, group and option sessions."""
    st = row.get("state") if isinstance(row.get("state"), dict) else {}
    raw = list(st.get("trades") or [])
    for m in (st.get("members") or {}).values() if isinstance(st.get("members"), dict) else ():
        if isinstance(m, dict):
            raw += m.get("trades") or []
    out = []
    for t in raw:
        if not isinstance(t, dict) or _num(t.get("pnl"), -1e12, 1e12) is None:
            continue
        e, x = str(t.get("entry_t") or t.get("opened") or ""), str(t.get("exit_t") or t.get("closed") or "")
        out.append({"net": float(t["pnl"]), "gross": float(t["pnl"]) + float(_num(t.get("costs"), 0) or 0),
                    "charges": float(_num(t.get("costs"), 0) or 0), "entry_t": e[:19], "exit_t": x[:19], "hold_days": 0, "hold_s": None})
    for t in out:
        try:
            a, b = datetime.fromisoformat(t["entry_t"]), datetime.fromisoformat(t["exit_t"])
            t["hold_s"], t["hold_days"] = max(0.0, (b - a).total_seconds()), (b.date() - a.date()).days
        except ValueError:
            pass
    out.sort(key=lambda t: t["exit_t"])
    return out


def compare(real: list[dict], paper: list[dict]) -> dict:
    """The same per-trade facts for the real trades of one setup and a paper session, side by side. Sizes differ, so
    rates and per-trade figures compare better than rupee totals."""
    keys = ("n", "win_rate", "avg_win", "avg_loss", "expectancy", "profit_factor", "net", "charges", "max_dd", "avg_hold_days")

    def pick(ts):
        s = summary(ts)
        return {**{k: s[k] for k in keys}, "equity": s["equity"]}
    return {"real": pick(real), "paper": pick(paper)}


def new_id() -> str:
    return "m" + secrets.token_hex(5)
