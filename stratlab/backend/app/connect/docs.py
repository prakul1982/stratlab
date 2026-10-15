"""Uploads for the figures no statement email carries: the EPF passbook (PDF), an NPS statement (PDF) and the AIS (annual
information statement, JSON or PDF).

Reading is a first step that saves nothing: read_doc() looks for the figures in the file and returns them, with whether
each was found, and the file is dropped. The user checks or types them, and confirm() saves what they confirmed:

  EPF   balance -> a Net worth EPF entry (marked as read from a passbook; one typed in by hand is left alone)
  NPS   Tier I and II values -> a Net worth NPS entry, the same way
  AIS   dividends and interest received, TDS -> kept with the year; the TDS can be set as the year's TDS in Tax tools
        (advance tax), and dividend lines with a date and an amount go to the dividends the tax report uses

Passbook and statement layouts change; whatever isn't found is left for the user to type, never guessed."""
import io
import json
import math
import re
import secrets

from .. import money_dividends as divs, money_networth, money_advance_tax as adv
from . import state, statements

MAX_FILE = 5 * 1024 * 1024
KINDS = ("epf", "nps", "ais")
NUM = r"([\d,]+(?:\.\d{1,2})?)"


class DocError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _money(s: str | None) -> float | None:
    try:
        x = float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def pdf_text(data: bytes, password: str = "") -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        r = PdfReader(io.BytesIO(data))
        if r.is_encrypted and not r.decrypt(password or ""):
            raise DocError("wrong_password", "That password didn't open the PDF.")
        return "\n".join((p.extract_text() or "") for p in r.pages[:40])
    except DocError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError):
        raise DocError("unreadable", "This PDF couldn't be read.") from None
    except Exception:
        raise DocError("unreadable", "This PDF couldn't be read.") from None


def _date(s: str) -> str | None:
    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


# ---------- EPF ----------
def read_epf(text: str) -> dict:
    """The passbook's closing balances: "Closing Balance as on dd/mm/yyyy <employee> <employer> <pension>", one per member id.
    The balance is the employee and employer shares (the pension scheme isn't a provident fund balance)."""
    total, found, as_of = 0.0, 0, None
    for m in re.finditer(r"(?i)closing\s+balance\s+as\s+on\s+(\d{2}[/-]\d{2}[/-]\d{4})\s+" + NUM + r"\s+" + NUM, text):
        ee, er = _money(m.group(2)), _money(m.group(3))
        if ee is None or er is None:
            continue
        total += ee + er
        found += 1
        d = _date(m.group(1))
        as_of = max(as_of or "", d or "")
    return {"balance": round(total, 2) if found else None, "as_of": as_of or None, "passbooks": found}


# ---------- NPS ----------
def read_nps(text: str) -> dict:
    """Tier I and Tier II values: the line that names the tier, then a value on it or the lines that follow."""
    out: dict = {"tier1": None, "tier2": None, "as_of": None}
    for key, rx in (("tier1", r"(?i)tier\s*(?:-|\s)?\s*I\b(?!I)[^\n]{0,80}?(?:value|balance|corpus)[^\d\n]{0,30}" + NUM),
                    ("tier2", r"(?i)tier\s*(?:-|\s)?\s*II\b[^\n]{0,80}?(?:value|balance|corpus)[^\d\n]{0,30}" + NUM)):
        m = re.search(rx, text)
        if m:
            out[key] = _money(m.group(1))
    m = re.search(r"(?i)(?:as\s+on|as\s+of|up\s*to)\s+(\d{2}[/-]\d{2}[/-]\d{4})", text)
    out["as_of"] = _date(m.group(1)) if m else None
    return out


# ---------- AIS ----------
INFO_KEYS = ("informationDescription", "infoDescription", "informationCode", "description", "category", "informationCategory", "head", "type")
AMOUNT_KEYS = ("amount", "amountPaid", "reportedAmount", "grossAmount", "amountReported", "value")
DATE_KEYS = ("dateOfPayment", "transactionDate", "paymentDate", "date", "dateOfCredit")
NAME_KEYS = ("sourceName", "payerName", "name", "deductorName", "informationSource")
TDS_KEYS = ("tdsDeducted", "tds", "taxDeducted", "amountOfTaxDeducted", "tdsAmount")


def _first(d: dict, keys) -> object:
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def _nodes(doc) -> list[list]:
    """Every object in the document, parents before their children, in file order: [object, index of the object it sits
    in (-1 for the top)]. A loop, not a recursion, so a deeply nested file can't run out of stack."""
    out, stack = [], [(doc, -1)]
    while stack:
        n, parent = stack.pop()
        if isinstance(n, dict):
            out.append([n, parent])
            parent = len(out) - 1
            kids = list(n.values())
        elif isinstance(n, list):
            kids = n
        else:
            continue
        stack.extend((v, parent) for v in reversed(kids) if isinstance(v, (dict, list)))
    return out


def _year_of(v, assessment: bool) -> int | None:
    """The financial year's first year from a value like "2025-26" or "2025-2026" (the year of a pair of consecutive years,
    which an ISO date like 2025-03-15 never is), or from an assessment year, which starts a year after its financial year."""
    m = re.fullmatch(r"\s*(20\d\d)\s*[-–/]\s*(?:20)?(\d\d)\s*", str(v)) if isinstance(v, str) else None
    if not m or int(m.group(2)) != (int(m.group(1)) + 1) % 100:
        return None
    return int(m.group(1)) - (1 if assessment else 0)


def _year_in(text: str) -> int | None:
    """The first pair of consecutive years like "2025-26" in some text (an ISO date like 2025-03-15 isn't one)."""
    for m in re.finditer(r"\b(20\d\d)\s*[-–]\s*(\d\d)\b(?![-–/]?\d)", text):
        if int(m.group(2)) == (int(m.group(1)) + 1) % 100:
            return int(m.group(1))
    return None


def _filing_year(objects) -> int | None:
    """The year from the keys that name it (financialYear, assessmentYear, FY, AY and the like), never from a date."""
    for n in objects:
        for k, v in n.items():
            name = re.sub(r"[^a-z]", "", str(k).lower())
            if name in ("fy", "ay") or "financialyear" in name or "assessmentyear" in name or "finyear" in name or "fiscalyear" in name:
                got = _year_of(v, assessment=name == "ay" or "assessment" in name)
                if got:
                    return got
    return None


def read_ais_json(data: bytes) -> dict:
    """Entries that say dividend, interest or TDS (any nesting) added up, and dividend lines that carry a date. Only the
    entries at the bottom are added: one that holds others (a section with its total) is not, or the figures would count
    twice; an entry with no description of its own takes its section's. The year from the financial or assessment year the
    file names."""
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (ValueError, RecursionError):                # a broken file, or one nested too deep (UnicodeDecodeError is a ValueError)
        raise DocError("unreadable", "This file isn't an AIS JSON file.") from None
    found = _nodes(doc)
    fy = _filing_year(n for n, _ in found) or _year_in(data.decode("utf-8", "ignore"))
    labels, held_amt, held_tds = [], [False] * len(found), [False] * len(found)
    for i, (n, parent) in enumerate(found):
        own = " ".join(str(n.get(k)) for k in INFO_KEYS if isinstance(n.get(k), (str, int))).lower()
        labels.append(own or (labels[parent] if parent >= 0 else ""))
    amounts = [(_money(_first(n, AMOUNT_KEYS)) or 0) > 0 for n, _ in found]
    tdses = [bool(_money(_first(n, TDS_KEYS))) for n, _ in found]
    for i in range(len(found) - 1, -1, -1):             # children come after their parents: an entry is "held" if anything below it has a figure
        parent = found[i][1]
        if parent >= 0:
            held_amt[parent] |= amounts[i] or held_amt[i]
            held_tds[parent] |= tdses[i] or held_tds[i]
    div = intr = tds = 0.0
    lines, seen = [], set()
    for i, (n, _) in enumerate(found):
        label = labels[i]
        amt = _money(_first(n, AMOUNT_KEYS))
        t = _money(_first(n, TDS_KEYS))
        if t and not held_tds[i] and ("tds" in label or "dividend" in label or "interest" in label):
            tds += t
        if not amt or amt <= 0 or held_amt[i]:
            continue
        if "dividend" in label:
            key = (str(_first(n, DATE_KEYS)), str(_first(n, NAME_KEYS)), amt)
            if key in seen:
                continue
            seen.add(key)
            div += amt
            d = _first(n, DATE_KEYS)
            day = _date(str(d)) or (str(d)[:10] if re.match(r"\d{4}-\d{2}-\d{2}", str(d or "")) else None)
            if day:
                lines.append({"d": day, "sym": str(_first(n, NAME_KEYS) or "AIS")[:20].upper(), "name": str(_first(n, NAME_KEYS) or "")[:60],
                              "amount": round(amt, 2), "tds": round(t, 2) if t else None, "cur": "INR", "src": "AIS", "isin": ""})
        elif "interest" in label:
            intr += amt
    return {"fy": fy, "dividend": round(div, 2) or None, "interest": round(intr, 2) or None, "tds": round(tds, 2) or None,
            "lines": lines[:500]}


# ---------- the two steps ----------
LABELS = {"epf": [("balance", "Your EPF balance", "₹"), ("as_of", "As of", "date")],
          "nps": [("tier1", "Tier I value", "₹"), ("tier2", "Tier II value", "₹"), ("as_of", "As of", "date")],
          "ais": [("fy", "Financial year (the year it starts, like 2025)", ""), ("dividend", "Dividends received", "₹"),
                  ("interest", "Interest received", "₹"), ("tds", "TDS deducted", "₹")]}


def read_doc(kind: str, data: bytes, filename: str = "", password: str = "") -> dict:
    """What the file says: {"kind", "figures": [{key, label, unit, value, found}], "lines": [dividend lines]}. Nothing is saved."""
    if kind not in KINDS:
        raise DocError("bad_kind", "Choose EPF, NPS or AIS.")
    if not data or len(data) > MAX_FILE:
        raise DocError("too_big", "That file is empty or larger than 5 MB.")
    lines: list = []
    if kind == "ais" and (data.lstrip()[:1] in (b"{", b"[") or filename.lower().endswith(".json")):
        got = read_ais_json(data)
        lines = got.pop("lines")
    else:
        if data[:5] != b"%PDF-":
            raise DocError("not_pdf", "That isn't a PDF" + (" or an AIS JSON file." if kind == "ais" else "."))
        text = pdf_text(data, password)
        if kind == "epf":
            got = read_epf(text)
        elif kind == "nps":
            got = read_nps(text)
        else:
            got = {"fy": _year_in(text), "dividend": None,
                   "interest": None, "tds": None}      # an AIS PDF's layout isn't read: the figures are typed
    figures = [{"key": k, "label": label, "unit": unit, "value": got.get(k), "found": got.get(k) is not None} for k, label, unit in LABELS[kind]]
    return {"kind": kind, "figures": figures, "lines": lines, "found": sum(f["found"] for f in figures)}


def _day(v) -> str | None:
    """A confirmed "as of" date as YYYY-MM-DD, or None: nothing else is stored."""
    return v if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None


def _num(v, lo=0.0, hi=1e12) -> float | None:
    x = _money(v) if not isinstance(v, (int, float)) else float(v)
    return x if x is not None and lo <= x <= hi else None


def _dividend_lines(lines) -> list[dict]:
    """The AIS dividend lines the page sends back, rebuilt from their checked fields: a date, an amount above zero and
    a TDS (if any) that are numbers, always INR and always marked as AIS lines. Raises DocError for a figure that isn't a number."""
    out = []
    for r in lines[:divs.MAX_ROWS] if isinstance(lines, list) else []:
        if not isinstance(r, dict) or _day(r.get("d")) is None:
            continue
        amount, tds = r.get("amount"), r.get("tds")
        amount = None if isinstance(amount, bool) else _num(amount, hi=divs.MAX_AMOUNT)
        has_tds = tds not in (None, "")
        tds = None if isinstance(tds, bool) or not has_tds else _num(tds, hi=divs.MAX_AMOUNT)
        if not amount or (has_tds and tds is None):
            raise DocError("bad_figure", f"The dividend on {r['d']} has an amount or TDS that isn't a number.")
        out.append({"d": r["d"], "sym": str(r.get("sym") or "AIS")[:20].upper(), "name": str(r.get("name") or "")[:60], "isin": "",
                    "amount": round(amount, 2), "tds": round(tds, 2) if tds else None, "cur": "INR", "src": divs.AIS})
    return out


def confirm(profile: dict, kind: str, figures: dict, apply_tds: bool = False, lines: list[dict] | None = None) -> dict:
    """Save what the user confirmed. Raises DocError for figures that can't be used."""
    uid = profile["id"]
    if kind not in KINDS:
        raise DocError("bad_kind", "Choose EPF, NPS or AIS.")
    now = state.now()
    docs = state.section(uid, "docs")
    if kind == "epf":
        bal = _num(figures.get("balance"))
        if bal is None:
            raise DocError("bad_figure", "Enter the balance as a number.")
        asof = _day(figures.get("as_of"))
        note = _save_entry(uid, "epf", {"balance": bal}, asof)
        docs["epf"] = {"balance": bal, "as_of": asof, "confirmed_at": now}
        out = {"detail": note or "EPF balance saved in Net worth."}
    elif kind == "nps":
        t1, t2 = _num(figures.get("tier1")), _num(figures.get("tier2"))
        if not (t1 or t2):
            raise DocError("bad_figure", "Enter the Tier I value as a number.")
        asof = _day(figures.get("as_of"))
        note = statements.save_nps(uid, {"tier1": t1 or 0.0, "tier2": t2 or 0.0}, asof, profile["_plan"], how="nps_statement")
        docs["nps"] = {"tier1": t1, "tier2": t2, "as_of": asof, "confirmed_at": now}
        out = {"detail": note or "NPS value saved in Net worth."}
    else:
        fy = figures.get("fy")
        fy = int(fy) if str(fy).isdigit() and 2018 <= int(fy) <= 2100 else None
        if fy is None:
            raise DocError("bad_figure", "Enter the financial year as the year it starts, like 2025.")
        vals = {k: _num(figures.get(k)) for k in ("dividend", "interest", "tds")}
        rows = _dividend_lines(lines) if lines else []         # checked before anything is saved
        notes = []
        ais = dict(docs.get("ais") or {})
        ais[str(fy)] = {**{k: v for k, v in vals.items() if v is not None}, "confirmed_at": now}
        docs["ais"] = ais
        if apply_tds and vals["tds"] is not None:
            saved = adv.load(uid)["years"].get(fy) or adv.clean_year({})
            adv.save_year(uid, fy, {"tds": vals["tds"], "paid": saved["paid"]})
            notes.append("TDS set in Tax tools.")
        if rows:
            added, _ = divs.add(uid, rows, "AIS", "statement")
            notes.append(f"{added} dividend lines added.")
        out = {"detail": " ".join(notes) or "Figures saved."}
    state.update(uid, "docs", **docs)
    return out


def _save_entry(uid: str, kind: str, fields: dict, asof: str | None) -> str:
    why = []

    def put(items):             # runs again on the newer entries if the user edits Net worth meanwhile
        why.clear()
        mine = [i for i in items if i["kind"] == kind and i.get("auto") == "passbook"]
        typed = [i for i in items if i["kind"] == kind and not i.get("auto")]
        if typed and not mine:
            why.append(f"You already have an {kind.upper()} entry in Net worth, so this balance was not added.")
            return None
        entry = money_networth.clean(money_networth.ItemReq(kind=kind, name=kind.upper(), as_of=asof, **fields))
        entry["auto"] = "passbook"
        if mine:
            entry["id"] = mine[0]["id"]
            return [entry if i["id"] == entry["id"] else i for i in items]
        entry["id"] = secrets.token_hex(4)
        return items + [entry]
    money_networth.update(uid, put)
    return why[0] if why else ""
