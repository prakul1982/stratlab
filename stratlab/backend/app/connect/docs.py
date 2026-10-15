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
    """The passbook's closing balances: "Closing Balance as on dd/mm/yyyy <employee> <employer> <pension>", the latest
    one of each member id (a passbook of two years has a closing line for each year: the later one is the balance), added
    up over the member ids. The balance is the employee and employer shares (the pension scheme isn't a provident fund
    balance)."""
    members = [(m.start(), m.group(1)) for m in re.finditer(r"(?i)member\s*id\s*[:\-]?\s*([A-Z0-9][A-Z0-9/]*)", text)]
    latest: dict = {}                          # member id (None before any) -> (day, balance)
    for m in re.finditer(r"(?i)closing\s+balance\s+as\s+on\s+(\d{2}[/-]\d{2}[/-]\d{4})\s+" + NUM + r"\s+" + NUM, text):
        ee, er = _money(m.group(2)), _money(m.group(3))
        if ee is None or er is None:
            continue
        who = next((mid for at, mid in reversed(members) if at < m.start()), None)
        d = _date(m.group(1)) or ""
        if who not in latest or d >= latest[who][0]:
            latest[who] = (d, ee + er)
    found = len(latest)
    as_of = max((d for d, _ in latest.values()), default="")
    return {"balance": round(sum(b for _, b in latest.values()), 2) if found else None, "as_of": as_of or None, "passbooks": found}


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
    """The financial year's first year from a value like "2025-26", "2025-2026" or "FY 2025-26" (the year of a pair of
    consecutive years, which an ISO date like 2025-03-15 never is) or a whole year like 2025, or from an assessment year,
    which starts a year after its financial year."""
    if isinstance(v, int) and not isinstance(v, bool) and 2000 <= v <= 2100:
        return v - (1 if assessment else 0)
    m = re.fullmatch(r"\s*(?:[FA]\.?\s?Y\.?\s*:?\s*)?(20\d\d)\s*[-–/]\s*(?:20)?(\d\d)\s*", str(v), re.I) if isinstance(v, str) else None
    if not m or int(m.group(2)) != (int(m.group(1)) + 1) % 100:
        return None
    return int(m.group(1)) - (1 if assessment else 0)


PAIR = r"(20\d\d)\s*[-–]\s*(\d\d)\b(?![-–/]?\d)"


def _year_in(text: str) -> int | None:
    """The financial year from some text: the one it names as the financial year ("FY 2024-25"), else the one before
    the assessment year it names ("AY 2025-26"), else the first pair of consecutive years like "2025-26" (an ISO date like
    2025-03-15 isn't one)."""
    for words, back in ((r"F\.?\s?Y\.?|financial\s+year", 0), (r"A\.?\s?Y\.?|assessment\s+year", 1), (None, 0)):
        rx = (r"(?i)\b(?:" + words + r")\s*[:\-–]?\s*" + PAIR) if words else r"\b" + PAIR
        for m in re.finditer(rx, text):
            if int(m.group(2)) == (int(m.group(1)) + 1) % 100:
                return int(m.group(1)) - back
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


def _kind(label: str) -> str | None:
    return "dividend" if "dividend" in label else "interest" if "interest" in label else None


def read_ais_json(data: bytes) -> dict:
    """Entries that say dividend, interest or TDS (any nesting) added up, and dividend lines that carry a date. Only the
    entries at the bottom are added: one that holds dividend or interest entries with amounts (a section, or a payer, with
    its total) is not, or the figures would count twice; an entry with no description of its own takes its section's, and
    one with no payer or date of its own takes those of the dividend or interest entry it sits in. Two payments are one
    only when their date, payer and amount are all the same. The year from the financial or assessment year the file
    names."""
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (ValueError, RecursionError):                # a broken file, or one nested too deep (UnicodeDecodeError is a ValueError)
        raise DocError("unreadable", "This file isn't an AIS JSON file.") from None
    found = _nodes(doc)
    fy = _filing_year(n for n, _ in found) or _year_in(data.decode("utf-8", "ignore"))
    labels, names, dates = [], [], []
    for i, (n, parent) in enumerate(found):
        own = " ".join(str(n.get(k)) for k in INFO_KEYS if isinstance(n.get(k), (str, int))).lower()
        labels.append(own or (labels[parent] if parent >= 0 else ""))
        up = parent >= 0 and _kind(labels[parent]) is not None             # a payer's entry, its payments listed below it
        names.append(_first(n, NAME_KEYS) or (names[parent] if up else None))
        dates.append(_first(n, DATE_KEYS) or (dates[parent] if up else None))
    kinds = [_kind(x) for x in labels]
    amounts = [(_money(_first(n, AMOUNT_KEYS)) or 0) > 0 for n, _ in found]
    tdses = [bool(_money(_first(n, TDS_KEYS))) and ("tds" in x or k is not None) for (n, _), x, k in zip(found, labels, kinds)]
    held_amt, held_tds = [False] * len(found), [False] * len(found)
    for i in range(len(found) - 1, -1, -1):             # children come after their parents
        parent = found[i][1]
        if parent >= 0:
            # an entry is "held" (its figure is the total of those below it) when one below it is counted itself: a
            # dividend or interest entry with an amount; a detail like who reported it is not
            held_amt[parent] |= kinds[parent] is not None and kinds[i] is not None and (amounts[i] or held_amt[i])
            held_tds[parent] |= tdses[i] or held_tds[i]
    div = intr = tds = 0.0
    lines, seen = [], set()
    for i, (n, _) in enumerate(found):
        amt = _money(_first(n, AMOUNT_KEYS))
        t = _money(_first(n, TDS_KEYS))
        if t and tdses[i] and not held_tds[i]:
            tds += t
        if not amt or amt <= 0 or held_amt[i]:
            continue
        if kinds[i] == "dividend":
            name, d = names[i], dates[i]
            key = (str(d), str(name), amt)
            if key in seen:
                continue
            seen.add(key)
            div += amt
            day = _date(str(d)) or (str(d)[:10] if re.match(r"\d{4}-\d{2}-\d{2}", str(d or "")) else None)
            if day:
                lines.append({"d": day, "sym": str(name or "AIS")[:20].upper(), "name": str(name or "")[:60],
                              "amount": round(amt, 2), "tds": round(t, 2) if t else None, "cur": "INR", "src": "AIS", "isin": ""})
        elif kinds[i] == "interest":
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
        note = _save_entry(uid, "epf", {"balance": bal}, asof, profile["_plan"])
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


def _save_entry(uid: str, kind: str, fields: dict, asof: str | None, plan: str | None = None) -> str:
    """The balance as a Net worth entry marked as read from a passbook: the one read before is updated; a new one is
    added only within the plan's limit, as a typed one would be. Returns why it wasn't saved, or ""."""
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
        full = money_networth.over_limit(items, plan) if plan else None
        if full:
            why.append(f"The {kind.upper()} balance was not added. {full}")
            return None
        entry["id"] = secrets.token_hex(4)
        return items + [entry]
    money_networth.update(uid, put)
    return why[0] if why else ""
