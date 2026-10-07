"""Reading a consolidated statement PDF (CAMS / KFintech / MF Central, NSDL, CDSL) and saving what it says.

casparser (MIT) opens the PDF in memory with the user's password: nothing is written to disk, so there is no file to
delete afterwards, and the bytes are dropped as soon as the read returns. The investor's name, PAN, address and phone number
on the statement are never copied out.

  mutual fund statement (detailed)  -> the Mutual funds store, through money_mf.apply_import (duplicates skipped, history kept)
  depository statement (NSDL, CDSL) -> My Holdings, through sync.sync_holdings; an NPS balance on it -> Net worth

Used by the inbox (inbound.py) and by the manual upload, so both do exactly the same."""
import io
import math
import re
from dataclasses import dataclass, field

from .. import money_mf, money_networth
from . import pdfsandbox, state, sync, vault

MAX_PDF = money_mf.MAX_PDF
ETF_RX = re.compile(r"(?i)\bETF\b|\bBeES\b|exchange traded")
STALE_NOTE = "This statement is older than one already read, so your holdings were left as they are."


class StatementError(Exception):
    """A statement that couldn't be read, with a code the page acts on and a message for the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Parsed:
    kind: str                                   # "mf" or "demat"
    asof: str | None = None                     # the statement's last day, YYYY-MM-DD
    mf: dict | None = None                      # money_mf's read of a detailed CAS
    rows: list[dict] = field(default_factory=list)   # demat equities: {symbol, isin, name, qty, avg}
    nps: dict | None = None                     # {"tier1", "tier2"} from the depository statement, if it carries NPS
    other: int = 0                              # demat funds and bonds, not copied to holdings


def _open(data: bytes, password: str):
    """The statement, read in a child process with a memory and time limit (pdfsandbox.py): a PDF made to unpack to
    gigabytes stops the child, not the server."""
    try:
        return pdfsandbox.read_cas(data, password or "")
    except pdfsandbox.SandboxError as e:
        if e.kind == "password":
            raise StatementError("wrong_password", "That password didn't open the statement.") from None
        if e.kind == "parse":
            raise StatementError("not_a_statement", "This PDF isn't a CAMS, KFintech, NSDL or CDSL statement.") from None
        if e.kind == "limit":
            raise StatementError("too_complex", "This PDF is too large or complex to read here.") from None
        raise StatementError("unreadable", "This PDF couldn't be read.") from None


def open_statement(data: bytes, passwords: list[str]):
    """The opened statement, trying each password (and its capital-letters form, as PAN-locked statements need)."""
    if data[:5] != b"%PDF-":
        raise StatementError("not_a_statement", "That file isn't a PDF.")
    if len(data) > MAX_PDF:
        raise StatementError("too_big", f"That PDF is larger than {MAX_PDF // (1024 * 1024)} MB.")
    tries: list[str] = []
    for p in passwords:
        for v in (p, p.upper()):
            if v not in tries:
                tries.append(v)
    if not tries:
        tries = [""]
    last = None
    for p in tries:
        try:
            return _open(data, p)
        except StatementError as e:
            if e.code != "wrong_password":
                raise
            last = e
    if not passwords:
        raise StatementError("no_password", "This statement is locked, and no statement password is set yet.")
    raise last or StatementError("wrong_password", "That password didn't open the statement.")


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _period_end(cas) -> str | None:
    p = getattr(cas, "statement_period", None)
    return money_mf._day(getattr(p, "to", "") or "") if p else None


def read(data: bytes, passwords: list[str]) -> Parsed:
    cas = open_statement(data, passwords)
    asof = _period_end(cas)
    if hasattr(cas, "folios"):
        try:
            got = money_mf.from_cas(cas)
        except money_mf.FileError as e:
            raise StatementError("summary_only", str(e)) from None
        return Parsed("mf", asof, mf={**got, "kind": "cas"})
    rows, other = [], 0
    for acct in getattr(cas, "accounts", None) or []:
        for eq in acct.equities or []:
            qty = _f(eq.num_shares)
            if qty and qty > 0:
                rows.append({"symbol": eq.symbol or "", "isin": eq.isin, "name": " ".join(str(eq.name or "").split())[:80], "qty": qty,
                             "avg": None})
        for mf in acct.mutual_funds or []:
            qty = _f(mf.balance)
            if qty and qty > 0 and ETF_RX.search(str(mf.name or "")):       # an exchange-traded fund is a share on My Holdings
                rows.append({"symbol": "", "isin": mf.isin, "name": " ".join(str(mf.name or "").split())[:80], "qty": qty, "avg": None})
            else:
                other += 1
        other += len(getattr(acct, "bonds", None) or [])
    nps = None
    n = getattr(cas, "nps", None)
    if n is not None:
        t1 = sum(_f(s.value) or 0 for s in n.schemes if str(s.tier or "I").strip().upper() in ("I", "1", "TIER I"))
        t2 = sum(_f(s.value) or 0 for s in n.schemes if str(s.tier or "").strip().upper() in ("II", "2", "TIER II"))
        total = _f(n.value)
        if not (t1 or t2) and total:
            t1 = total
        if t1 or t2:
            nps = {"tier1": round(t1, 2), "tier2": round(t2, 2)}
    if not rows and not nps and not other:
        raise StatementError("empty", "No holdings were found in this statement.")
    return Parsed("demat", asof, rows=rows, nps=nps, other=other)


# ---------- saving ----------
def save_nps(uid: str, figures: dict, asof: str | None, plan: str, how: str = "statement") -> str:
    """The NPS balance as a Net worth entry marked as read from a statement; one the user typed in is left alone."""
    items = money_networth.load(uid)["items"]
    mine = [i for i in items if i["kind"] == "nps" and i.get("auto") == how]
    typed = [i for i in items if i["kind"] == "nps" and not i.get("auto")]
    if typed and not mine:
        return "You already have an NPS entry in Net worth, so the statement's balance was not added."
    entry = money_networth.clean(money_networth.ItemReq(kind="nps", name="NPS", tier1=figures.get("tier1") or 0,
                                                        tier2=figures.get("tier2") or None, as_of=asof))
    entry["auto"] = how
    if mine:
        entry["id"] = mine[0]["id"]
        money_networth.save(uid, [entry if i["id"] == entry["id"] else i for i in items])
    else:
        import secrets
        entry["id"] = secrets.token_hex(4)
        money_networth.save(uid, items + [entry])
    return ""


def apply(profile: dict, parsed: Parsed, filename: str = "") -> dict:
    """Save a read statement with the user's data: {"kind", "detail", ...counts}."""
    uid = profile["id"]
    if parsed.kind == "mf":
        counts, _ = money_mf.apply_import(profile, parsed.mf, filename or "statement.pdf", "add")
        return {"kind": "mf", "schemes": counts["schemes"], "added": counts["added"], "duplicates": counts["duplicates"],
                "detail": (f"{counts['added']} new transactions in {counts['schemes']} funds."
                           if counts["added"] else "Nothing new: every transaction was already saved.")}
    box = state.section(uid, "inbox")
    out: dict = {"kind": "demat", "detail": ""}
    notes = []
    stale = bool(parsed.asof and box.get("cas_asof") and parsed.asof < box["cas_asof"])
    if parsed.rows and not stale:
        got = sync.sync_holdings(profile, parsed.rows, "cas", "Statement")
        out.update(stocks=got["count"], unmatched=got["unmatched_count"])
        notes.append(f"{got['count']} holdings read" + (f", {got['unmatched_count']} not matched to a listed company" if got["unmatched_count"] else "") + ".")
        if parsed.asof:
            state.update(uid, "inbox", cas_asof=parsed.asof)
    elif stale:
        notes.append(STALE_NOTE)
    if parsed.nps:
        why = save_nps(uid, parsed.nps, parsed.asof, profile["_plan"])
        notes.append(why or "NPS balance added to Net worth.")
    if parsed.other:
        notes.append(f"{parsed.other} funds and bonds held in your demat account were not copied (mutual funds come from the CAMS statement).")
    out["detail"] = " ".join(notes)
    return out


def process(uid: str, data: bytes, filename: str = "", passwords: list[str] | None = None, via: str = "email") -> dict:
    """Read and save one statement for a user; records the outcome on their inbox card. Never raises: {"ok", "status",
    "kind", "detail"}. `passwords` are tried first; the stored statement password after them."""
    profile = sync.profile_for(uid)
    result: dict
    try:
        if not profile:
            raise StatementError("unknown", "Account not found.")
        pws = list(passwords or [])
        stored = vault.unseal(state.section(uid, "inbox").get("pw"))
        if stored and stored not in pws:
            pws.append(stored)
        parsed = read(data, pws)
        got = apply(profile, parsed, filename)
        result = {"ok": True, "status": "ok", **got}
    except StatementError as e:
        result = {"ok": False, "status": e.code, "kind": None, "detail": e.message}
    except Exception:
        result = {"ok": False, "status": "unreadable", "kind": None, "detail": "Something went wrong reading this statement."}
    finally:
        data = b""                              # the statement's bytes are not kept anywhere
    state.update(uid, "inbox", last={"at": state.now(), "status": result["status"], "kind": result.get("kind"), "via": via,
                                     "detail": result.get("detail", "")[:300]})
    return result
