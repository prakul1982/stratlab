"""US stocks from Interactive Brokers through its Flex Web Service: connect once with a Flex token and a query id, then a
daily job reads open positions into My Holdings (US) and closed trades into the trade journal (US).

The user makes a Flex Query in IBKR's Client Portal (Performance & Reports -> Flex Queries) with the Open Positions and
Trades sections in XML, and a Flex Web Service token (valid for up to a year, they choose). Both are kept sealed. The token
travels in the request's URL, as IBKR's service requires, so errors from the HTTP layer are never shown or logged as they
are: they carry that URL."""
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

from .. import journal
from . import state, sync, vault
from .redact import mask

BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
MAX_XML = 8 * 1024 * 1024
IST = ZoneInfo("Asia/Kolkata")
SYNC_AFTER = "07:00"         # IST: the US day's statement is ready by then

ERRORS = {"1012": ("token_expired", "Your Flex token has expired. Make a new one in IBKR and paste it here."),
          "1015": ("token_invalid", "IBKR doesn't recognise that token. Check you copied all of it."),
          "1014": ("query_invalid", "IBKR doesn't recognise that query id."),
          "1003": ("not_available", "IBKR's statement isn't available yet. It will be tried again tomorrow."),
          "1018": ("busy", "IBKR asked us to slow down. It will be tried again later."),
          "1020": ("token_invalid", "IBKR refused the request. Check the token and that its IP restriction (if any) allows StratLab.")}


class FlexError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


transport: httpx.BaseTransport | None = None        # tests swap in a fake
sleep: Callable[[float], None] = time.sleep


def _get(path: str, params: dict) -> str:
    try:
        with httpx.Client(transport=transport, timeout=60, follow_redirects=False) as c:
            r = c.get(f"{BASE}/{path}", params=params, headers={"User-Agent": "StratLab"})
    except httpx.HTTPError as e:
        raise FlexError("unreachable", "IBKR didn't answer. It will be tried again later.") from None
    if r.status_code != 200 or len(r.content) > MAX_XML:
        raise FlexError("unreachable", "IBKR didn't answer. It will be tried again later.")
    return r.text


def _xml(text: str) -> ET.Element:
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise FlexError("bad_reply", "IBKR's reply wasn't what was expected.")
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        raise FlexError("bad_reply", "IBKR's reply wasn't what was expected.") from None


def _fail(root: ET.Element) -> FlexError:
    code = (root.findtext("ErrorCode") or "").strip()
    known = ERRORS.get(code)
    return FlexError(known[0] if known else "failed", known[1] if known else "IBKR couldn't make the statement. Check the query and try again.")


def fetch(token: str, query: str, tries: int = 6) -> ET.Element:
    """The Flex statement for a query, as XML: ask for it, then fetch it when it's ready."""
    root = _xml(_get("SendRequest", {"t": token, "q": query, "v": "3"}))
    if (root.findtext("Status") or "").strip() != "Success":
        raise _fail(root)
    ref = (root.findtext("ReferenceCode") or "").strip()
    if not ref:
        raise FlexError("bad_reply", "IBKR's reply wasn't what was expected.")
    for n in range(tries):
        got = _xml(_get("GetStatement", {"t": token, "q": ref, "v": "3"}))
        if got.tag == "FlexQueryResponse":
            return got
        if (got.findtext("ErrorCode") or "").strip() == "1019":       # still being made
            sleep(5 * (n + 1))
            continue
        raise _fail(got)
    raise FlexError("not_available", "IBKR's statement isn't ready yet. It will be tried again tomorrow.")


# ---------- reading ----------
def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _day(v: str) -> str | None:
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", v or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _clock(v: str) -> str | None:
    m = re.search(r"[;T ,](\d{2}):?(\d{2}):?(\d{2})", v or "")
    return f"{m.group(1)}:{m.group(2)}:{m.group(3)}" if m else None


def positions(root: ET.Element) -> tuple[list[dict], int]:
    """(US stock rows for My Holdings, positions left out: other kinds or currencies). A query that lists each lot as well
    as the position (levelOfDetail LOT beside SUMMARY) is counted once: by its SUMMARY rows, or by its LOT rows when it has
    no SUMMARY rows."""
    rows, left = [], 0
    by = {}
    levels = {(p.get("levelOfDetail") or "").upper() for p in root.iter("OpenPosition")}
    use = ("", "SUMMARY") if levels & {"", "SUMMARY"} else ("LOT",)
    for p in root.iter("OpenPosition"):
        a = p.attrib
        if (a.get("levelOfDetail") or "").upper() not in use:
            continue
        qty = _num(a.get("position"))
        sym = (a.get("symbol") or "").strip().upper().replace(" ", "-")
        if a.get("assetCategory") != "STK" or a.get("currency") != "USD" or not qty or qty <= 0 or not sym:
            left += 1
            continue
        cur = by.setdefault(sym, {"qty": 0.0, "cost": 0.0, "name": a.get("description") or sym, "isin": a.get("isin") or None})
        cur["qty"] += qty
        cur["cost"] += qty * (_num(a.get("costBasisPrice")) or 0)
    for sym, v in by.items():
        rows.append({"symbol": sym, "isin": None, "name": v["name"][:80], "qty": round(v["qty"], 4),
                     "avg": round(v["cost"] / v["qty"], 4) if v["cost"] else None, "market": "US"})
    return rows, left


def fills(root: ET.Element) -> list[dict]:
    """Stock trades in dollars, oldest first: {id, sym, side "B"/"S", qty, price, d, t, fee, oc}. `oc` is IBKR's
    openCloseIndicator ("O" opens a position, "C" closes one). Only the executions: a query that lists the order or the
    closed lots beside them (other levels of detail) would count each trade again."""
    out = []
    for t in root.iter("Trade"):
        a = t.attrib
        if (a.get("levelOfDetail") or "").upper() not in ("", "EXECUTION"):
            continue
        qty, price = _num(a.get("quantity")), _num(a.get("tradePrice"))
        d = _day(a.get("tradeDate") or a.get("dateTime") or "")
        sym = (a.get("symbol") or "").strip().upper().replace(" ", "-")
        if a.get("assetCategory") != "STK" or a.get("currency") != "USD" or not qty or price is None or not d or not sym:
            continue
        side = "B" if (a.get("buySell") or "").upper().startswith("B") else "S"
        out.append({"id": a.get("tradeID") or hashlib.sha1(repr(sorted(a.items())).encode()).hexdigest()[:12], "sym": sym, "side": side,
                    "qty": abs(qty), "price": price, "d": d, "t": _clock(a.get("dateTime") or "") or "",
                    "fee": abs(_num(a.get("ibCommission")) or 0.0), "oc": (a.get("openCloseIndicator") or "").strip().upper()})
    return sorted(out, key=lambda f: (f["d"], f["t"], f["id"]))


def splits(root: ET.Element) -> dict[str, list[tuple[str, float]]]:
    """{symbol: [(the first day it counts, shares after per share before)]} from the statement's Corporate Actions
    section, when the query has one: a forward or reverse split described as "SPLIT 4 FOR 1". IBKR books a split the
    evening before (dateTime "20260210;202500") and reports it the day it takes effect (reportDate "20260211"): the
    report date when there is one, else the day after the booking, so the booking day's own fills keep the old shares."""
    out: dict[str, list[tuple[str, float]]] = {}
    for c in root.iter("CorporateAction"):
        a = c.attrib
        m = re.search(r"\bSPLIT\s+(\d+(?:\.\d+)?)\s+FOR\s+(\d+(?:\.\d+)?)", a.get("actionDescription") or "", re.I)
        d = _day(a.get("reportDate") or "")
        booked = _day(a.get("dateTime") or "")
        if not d and booked:
            try:
                d = (date.fromisoformat(booked) + timedelta(days=1)).isoformat()
            except ValueError:
                d = None
        sym = (a.get("symbol") or "").strip().upper().replace(" ", "-")
        if a.get("assetCategory") not in (None, "STK") or not m or not d or not sym or float(m.group(2)) <= 0 or float(m.group(1)) <= 0:
            continue
        out.setdefault(sym, []).append((d, float(m.group(1)) / float(m.group(2))))
    return {k: sorted(set(v)) for k, v in out.items()}


def closed_trades(fs: list[dict], split: dict[str, list[tuple[str, float]]] | None = None,
                  done: dict[str, list[tuple[str | None, float]]] | None = None) -> list[dict]:
    """Round trips by first in, first out per stock, as the journal's added-by-hand trades (segment "us"), each with the
    ids of its entry and exit fills (`ef`, `xf`). A sale with no purchase before it in the data (bought before the query's
    period) is left out, never guessed: when IBKR marks each fill (openCloseIndicator), a sale opens a short position only
    when marked as opening one ("O") and a purchase marked as closing one ("C") opens nothing; a query without the mark
    lets either side open a position. `split` (splits): the shares bought before a split count as the shares after it, at
    the price of each after it, from the split's first day on. `done` (paired): {exit fill id: [(entry fill id, qty)]} of
    the trades read before. A query over the last 365 days sees a different window each day: the part of an exit that was
    paired with a fill no longer in the data is taken off it, so the rest pairs as it did when that fill was there."""
    out = []
    book: dict[str, list[list]] = {}                  # symbol -> open lots [side, qty left, fill, fee left]
    ahead = {k: list(v) for k, v in (split or {}).items()}
    here = {f["id"] for f in fs}
    for f in fs:
        lots = book.setdefault(f["sym"], [])
        while ahead.get(f["sym"]) and ahead[f["sym"]][0][0] <= f["d"]:
            k = ahead[f["sym"]].pop(0)[1]
            for lot in lots:
                lot[1] *= k
                lot[2] = {**lot[2], "price": lot[2]["price"] / k}
        total = f["qty"]
        gone = sum(q for e, q in (done or {}).get(f["id"], ()) if e not in here)      # paired before, with a fill now out of the data
        q = max(total - gone, 0.0)
        fee = f["fee"] * q / total
        while q > 1e-9 and lots and lots[0][0] != f["side"]:
            lot = lots[0]
            c = min(q, lot[1])
            fee_part = f["fee"] * c / total
            lot_fee = lot[3] * c / lot[1]
            e, x = lot[2], f
            long = lot[0] == "B"
            ident = hashlib.sha1(f"{e['id']}|{x['id']}|{round(c, 4)}".encode()).hexdigest()[:10]
            out.append({"id": "ib" + ident, "sym": f["sym"], "segment": "us", "side": "long" if long else "short",
                        "ed": e["d"], "et": e["t"] or None, "xd": x["d"], "xt": x["t"] or None, "qty": round(c, 6),
                        "entry": e["price"], "exit": x["price"], "charges": round(fee_part + lot_fee, 4), "via": "ibkr",
                        "ef": e["id"], "xf": x["id"]})
            lot[1] -= c
            lot[3] -= lot_fee
            q -= c
            fee -= fee_part
            if lot[1] <= 1e-9:
                lots.pop(0)
        oc = (f.get("oc") or "").split(";")
        opens = "O" in oc if f.get("oc") else True
        if q > 1e-9 and opens:
            lots.append([f["side"], q, f, fee])
    return [t for t in out if t["xd"] >= t["ed"]]


def _sig(m: dict) -> tuple:
    return (m["sym"], m["ed"], m["xd"], round(float(m["qty"]), 4), round(float(m["entry"]), 4), round(float(m["exit"]), 4))


def _legacy_id(e: dict, x: dict, qty) -> str:
    return "ib" + hashlib.sha1(f"{e['id']}|{x['id']}|{round(float(qty), 4)}".encode()).hexdigest()[:10]


def _backfill(manual: list[dict], fs: list[dict]) -> bool:
    """Gives the trades read from IBKR before fill ids were kept (no `xf`) the ids of their fills, when the fills are in
    this statement: the exit by its stock, day, time, side and price, the entry by its stock, day, time and side (a split
    changes its price), the pair the trade's id was made from first. True when one was given."""
    by: dict[tuple, list[dict]] = {}
    for f in fs:
        by.setdefault((f["sym"], f["d"], f["t"], f["side"]), []).append(f)
    changed = False
    for m in manual:
        if m.get("via") != "ibkr" or m.get("xf"):
            continue
        long = m.get("side") == "long"
        xs = [f for f in by.get((m["sym"], m["xd"], m.get("xt") or "", "S" if long else "B"), [])
              if abs(f["price"] - float(m["exit"])) <= 1e-6 * max(1.0, abs(f["price"]))]
        es = by.get((m["sym"], m["ed"], m.get("et") or "", "B" if long else "S"), [])
        pair = next(((e, x) for x in xs for e in es if _legacy_id(e, x, m["qty"]) == m["id"]), None)
        x = pair[1] if pair else xs[0] if xs else None
        e = pair[0] if pair else es[0] if es else None
        if x:
            m["xf"] = x["id"]
            changed = True
            if e:
                m["ef"] = e["id"]
    return changed


def paired(manual: list[dict]) -> dict[str, list[tuple[str | None, float]]]:
    """{exit fill id: [(entry fill id or None, qty)]} of the trades read from IBKR before (for closed_trades' `done`)."""
    out: dict[str, list[tuple[str | None, float]]] = {}
    for m in manual:
        if m.get("via") == "ibkr" and m.get("xf"):
            out.setdefault(m["xf"], []).append((m.get("ef"), float(m["qty"])))
    return out


def _redo(fs: list[dict], split: dict[str, list[tuple[str, float]]]) -> dict[str, set[str]]:
    """{symbol: the ids of its fills in the statement} for each stock with a split in the statement. A trade read from
    IBKR before, from these same fills, may have counted the split differently: a different quantity, so a different id."""
    out: dict[str, set[str]] = {}
    for f in fs:
        if f["sym"] in split:
            out.setdefault(f["sym"], set()).add(f["id"])
    return out


def save_trades(uid: str, trades: list[dict], redo: dict[str, set[str]] | None = None, fs: list[dict] | None = None) -> int:
    """New closed trades into the journal: how many added. Those already there are skipped: by id, by the same trade, or
    by their exit fill, as an exit paired in an earlier read is not paired again from a later window. `redo` (_redo):
    in a stock with a split in the statement, the trades read before whose exit and entry fills are both in it, and whose
    exit is among `trades`, are recomputed: those not among `trades` are taken out first, so a statement read again after
    a split has each trade once, as it is read now. `fs` (the statement's fills) gives trades saved before fill ids were
    kept the ids of theirs."""
    j = journal.load(uid)
    before = len(j["manual"])
    dirty = _backfill(j["manual"], fs) if fs else False
    now = {t["id"] for t in trades}
    exits = {t["xf"] for t in trades if t.get("xf")}
    saved: dict[str, list[dict]] = {}
    for m in j["manual"]:
        if m.get("via") == "ibkr" and m.get("xf"):
            saved.setdefault(m["xf"], []).append(m)
    redone: set[str] = set()                                # exit fills whose trades are recomputed from this statement
    for sym, ids in (redo or {}).items():
        for xf, ms in saved.items():
            if xf in ids and xf in exits and all(m["sym"] == sym and m.get("ef") in ids for m in ms):
                redone.add(xf)
    if redone:
        j["manual"] = [m for m in j["manual"] if not (m.get("via") == "ibkr" and m.get("xf") in redone and m["id"] not in now)]
    dropped = len(j["manual"]) != before
    have_ids = {m["id"] for m in j["manual"]}
    have_sig = {_sig(m) for m in j["manual"]}
    added = 0
    for t in trades:
        if (t["id"] in have_ids or _sig(t) in have_sig or (t.get("xf") in saved and t["xf"] not in redone)
                or len(j["manual"]) >= journal.MAX_MANUAL):
            continue
        j["manual"].append({k: v for k, v in t.items() if v is not None})
        have_ids.add(t["id"])
        have_sig.add(_sig(t))
        added += 1
    if added or dropped or dirty:
        journal.save(uid, j)
    return added


def read_trades(uid: str, fs: list[dict], sp: dict[str, list[tuple[str, float]]]) -> int:
    """The statement's closed trades into the journal, paired with what was read from IBKR before: how many added."""
    manual = [dict(m) for m in journal.load(uid)["manual"]]
    _backfill(manual, fs)
    return save_trades(uid, closed_trades(fs, sp, paired(manual)), _redo(fs, sp), fs)


# ---------- the connection ----------
def connect(uid: str, token: str, query: str, expires: str | None = None) -> dict:
    """Check the token and query by pulling once, keep them sealed, and read. Raises FlexError (nothing kept)."""
    token, query = token.strip(), query.strip()
    root = fetch(token, query)
    state.update(uid, "ibkr", token=vault.seal(token), query=query, expires=expires, connected_at=state.now(), status="ok", detail=None)
    return ingest(uid, root)


def ingest(uid: str, root: ET.Element) -> dict:
    profile = sync.profile_for(uid)
    rows, left = positions(root)
    got = sync.sync_holdings(profile, rows, "ibkr", "Interactive Brokers") if rows or _had_ibkr(uid) else {"count": 0, "unmatched_count": 0}
    fs, sp = fills(root), splits(root)
    n = read_trades(uid, fs, sp)
    why = sync.note(got, "Interactive Brokers")      # an empty statement or an unmatched line keeps the US holdings read before
    state.update(uid, "ibkr", synced_at=state.now(), status="partial" if why else "ok", detail=why, positions=got["count"], trades=n)
    return {"positions": got["count"], "unmatched": got["unmatched_count"], "left_out": left, "trades_added": n}


def _had_ibkr(uid: str) -> bool:
    from .. import holdings
    return any(i.get("via") == "ibkr" for i in holdings.load(uid)["items"])


def sync_user(uid: str) -> dict:
    """One daily pull. Records the outcome on the connection; raises FlexError."""
    box = state.section(uid, "ibkr")
    token = vault.unseal(box.get("token"))
    if not token or not box.get("query"):
        raise FlexError("not_connected", "Connect Interactive Brokers first.")
    try:
        return ingest(uid, fetch(token, box["query"]))
    except FlexError as e:
        state.update(uid, "ibkr", status=e.code, detail=e.message, tried_at=state.now())
        raise
    except Exception as e:
        # anything else (a storage error while saving, say) is a failed try as well: without it the day's try wasn't
        # recorded, and the job read the statement from IBKR again every half hour all day
        print("IBKR daily read failed:", mask(type(e).__name__))
        msg = "Something went wrong saving the statement. It will be tried again tomorrow."
        state.update(uid, "ibkr", status="failed", detail=msg, tried_at=state.now())
        raise FlexError("failed", msg) from None


def due(box: dict, now: datetime) -> bool:
    """A connected user whose last good read is from before today (India time), after the morning start."""
    if not box.get("token") or not box.get("query"):
        return False
    local = now.astimezone(IST)
    if local.strftime("%H:%M") < SYNC_AFTER:
        return False
    for key in ("synced_at", "tried_at"):
        at = box.get(key)
        if at and datetime.fromisoformat(at).astimezone(IST).date() == local.date() and (key == "synced_at" or box.get("status") != "ok"):
            return False
    return True


def run_daily(now: datetime | None = None) -> dict:
    """Every due user, one at a time (IBKR limits requests). {"users", "ok", "failed"}."""
    now = now or datetime.now(IST)
    users = ok = failed = 0
    for uid, rec in state.everyone():
        box = rec.get("ibkr") or {}
        if not due(box, now):
            continue
        users += 1
        try:
            sync_user(uid)
            ok += 1
        except FlexError:
            failed += 1
        except Exception as e:
            failed += 1
            print("IBKR daily read failed:", mask(type(e).__name__))
    return {"users": users, "ok": ok, "failed": failed}


def status(uid: str) -> dict:
    box = state.section(uid, "ibkr")
    return {"connected": bool(box.get("token")), "synced_at": box.get("synced_at"), "status": box.get("status"), "detail": box.get("detail"),
            "positions": box.get("positions"), "trades": box.get("trades"), "expires": box.get("expires"), "query": box.get("query")}


def disconnect(uid: str) -> None:
    state.drop(uid, "ibkr")
