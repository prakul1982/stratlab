"""Import a strategy someone already has: a StratLab export, TradingView Pine Script, Python,
MetaTrader, AmiBroker, or plain words.

StratLab's own export is read directly. Everything else is translated by the AI builder, told
what language it's reading. When the AI is unavailable, common Pine Script patterns (moving
averages and RSI, crossovers and comparisons, entries, exits and percentage stops) are read by
a small built-in parser, so the most common import still works offline."""
import json
import re

from pydantic import ValidationError

from .models import Cond, GroupReq, Strategy

FORMATS = {
    "stratlab": "StratLab export",
    "json": "a JSON strategy config",
    "pine": "TradingView Pine Script",
    "python": "Python",
    "mql": "MetaTrader (MQL)",
    "afl": "AmiBroker (AFL)",
    "text": "plain words",
}
MAX_CHARS = 20000


def detect(text: str, filename: str = "") -> str:
    name = (filename or "").lower()
    t = text.strip()
    if t.startswith("{"):
        try:
            obj = json.loads(t)
        except ValueError:
            return "text"
        return "stratlab" if isinstance(obj, dict) and (obj.get("format", "").startswith("stratlab") or "strategy" in obj) else "json"
    if name.endswith(".pine") or re.search(r"//@version|\bstrategy\s*\(|\bta\.\w+\(|\bindicator\s*\(|\bstudy\s*\(", t):
        return "pine"
    if name.endswith((".mq4", ".mq5")) or re.search(r"\bOnTick\s*\(|\biMA\s*\(|\bOrderSend\s*\(", t):
        return "mql"
    if name.endswith(".afl") or re.search(r"^\s*(Buy|Sell|Short|Cover)\s*=", t, re.M):
        return "afl"
    if name.endswith(".py") or re.search(r"^\s*(import|from)\s+\w+|^\s*def\s+\w+\(|^\s*class\s+\w+\(", t, re.M):
        return "python"
    return "text"


def from_json(text: str) -> dict:
    """A StratLab export, or a bare strategy object. Raises ValueError with a plain message."""
    obj = json.loads(text)
    raw = obj.get("strategy", obj) if isinstance(obj, dict) else None
    if not isinstance(raw, dict):
        raise ValueError("That JSON doesn't hold a strategy.")
    try:
        s = Strategy(**raw)
    except ValidationError as e:
        raise ValueError(f"That JSON isn't a valid StratLab strategy ({e.errors()[0]['msg']}).") from None
    if not s.entry:
        raise ValueError("That strategy has no entry rules.")
    inst = obj.get("instrument") if isinstance(obj.get("instrument"), dict) else None
    group, notes = None, []
    if isinstance(obj.get("group"), dict):
        try:
            g = GroupReq(**obj["group"])
            group = {"id": g.id, "name": g.name, "market": g.market.upper(), "maxOpen": min(g.maxOpen, len(g.members)),
                     "members": [m.model_dump(exclude_none=True) for m in g.members]}
        except ValidationError:
            notes.append("The group in the file couldn't be read, so pick what to test it on.")
    # an export holds every setting: the timeframe, the sell rule, the stop, the target and the risk per trade are all
    # given, so none of them is asked again (R11C-013: the import asked the risk per trade the file holds)
    given = ["tf", "exit", "sl", "tgt", "trail", "maxBars", "riskPct", "capital"] + (["instrument"] if inst or group else [])
    return {"strategy": s.model_dump(), "instrument_id": None if group else (inst or {}).get("id"), "group": group,
            "mentioned": given, "notes": notes}


def ai_prompt(fmt: str, text: str) -> str:
    """What the AI builder is given: the language, what to extract, and the code itself."""
    if fmt == "text":
        return text
    return (f"The user imported an existing trading strategy written in {FORMATS[fmt]}. Translate what the code does "
            "into the schema: its buy (or short) conditions, its sell or cover conditions, any stop loss, target, "
            "trailing stop or time limit in percent, the timeframe and the instrument if the code names them. Use the "
            "default lengths from inputs. Don't invent rules that aren't in the code; list anything you couldn't "
            "express (other indicators, position sizing, pyramiding, filters on time or volume) in notes.\n\n"
            f"--- {FORMATS[fmt]} ---\n{text[:MAX_CHARS]}")


# ---------- a small Pine Script reader, for when the AI is unavailable ----------
_TA = r"(?:ta\.)?(sma|ema|rsi)\(\s*([\w.]+)\s*,\s*([\w.]+)\s*\)"


def pine(code: str) -> dict:
    notes: list[str] = []
    code = re.sub(r"//.*", "", code)
    consts: dict[str, float] = {}
    for m in re.finditer(r"^\s*(?:(?:int|float|var)\s+)?(\w+)\s*=\s*input(?:\.int|\.float)?\(\s*(?:defval\s*=\s*)?(-?[\d.]+)", code, re.M):
        consts[m.group(1)] = float(m.group(2))
    for m in re.finditer(r"^\s*(?:(?:int|float)\s+)?(\w+)\s*=\s*(-?[\d.]+)\s*$", code, re.M):
        consts.setdefault(m.group(1), float(m.group(2)))
    refs: dict[str, dict] = {}
    for m in re.finditer(r"^\s*(?:float\s+)?(\w+)\s*=\s*" + _TA + r"\s*$", code, re.M):
        ref = _ta_ref(m.group(2), m.group(3), m.group(4), consts)
        if ref:
            refs[m.group(1)] = ref
    cond_vars = {m.group(1): m.group(2).strip() for m in re.finditer(r"^\s*(?:bool\s+)?(\w+)\s*=\s*(.*(?:cross|[<>]).*)$", code, re.M)
                 if m.group(1) not in refs}

    def operand(tok: str):
        tok = _unwrap(tok)
        if tok == "close":
            return {"t": "price"}
        if re.fullmatch(r"-?[\d.]+", tok):
            return {"t": "num", "v": float(tok)}
        if tok in consts:
            return {"t": "num", "v": consts[tok]}
        if tok in refs:
            return refs[tok]
        m = re.fullmatch(_TA, tok)
        return _ta_ref(m.group(1), m.group(2), m.group(3), consts) if m else None

    def conds(expr: str, depth: int = 0) -> tuple[list[dict], str]:
        expr = _unwrap(expr)
        if expr in cond_vars and depth < 4:
            return conds(cond_vars[expr], depth + 1)
        join = "any" if re.search(r"\bor\b", expr) else "all"
        out = []
        for atom in re.split(r"\band\b|\bor\b", expr):
            atom = _unwrap(atom)
            if not atom:
                continue
            if atom in cond_vars and depth < 4:
                out += conds(atom, depth + 1)[0]
                continue
            m = re.fullmatch(r"(?:ta\.)?cross(over|under)\(\s*(.+?)\s*,\s*(.+)\s*\)", atom)
            if m:
                l, r, op = operand(m.group(2)), operand(m.group(3)), "xa" if m.group(1) == "over" else "xb"
            else:
                m = re.fullmatch(r"(.+?)\s*(>=|<=|>|<)\s*(.+)", atom)
                l, r, op = (operand(m.group(1)), operand(m.group(3)), "gt" if m.group(2).startswith(">") else "lt") if m else (None, None, None)
            if l and r and op:
                try:
                    out.append(Cond(l=l, op=op, r=r).model_dump(exclude_none=True))
                    continue
                except ValidationError:
                    pass
            notes.append(f"Couldn't translate \"{atom[:80]}\", so it was left out.")
        return out, join

    entries = {"long": [], "short": []}
    exits = {"long": [], "short": []}
    lines = code.splitlines()
    for i, line in enumerate(lines):
        call = re.search(r"strategy\.(entry|close|close_all)\s*\((.*)\)", line)
        if not call:
            continue
        args = call.group(2)
        when = re.search(r"when\s*=\s*(.+?)\s*(?:,\s*\w+\s*=|$)", args)
        cond = when.group(1) if when else None
        if cond is None:
            same = re.match(r"\s*if\s+(.+?)\s+strategy\.", line)
            prev = next((lines[j] for j in range(i - 1, -1, -1) if lines[j].strip()), "")
            m = same or re.match(r"\s*if\s+(.+?)\s*$", prev)
            cond = m.group(1) if m else None
        if not cond:
            continue
        if call.group(1) == "entry":
            side = "short" if re.search(r"strategy\.short|direction\s*=\s*strategy\.direction\.short", args) else "long"
            entries[side].append(cond)
        else:
            exits["long"].append(cond)
            exits["short"].append(cond)

    side = "long" if entries["long"] or not entries["short"] else "short"
    other = "short" if side == "long" else "long"
    entry, join = [], "all"
    for c in entries[side]:
        got, join = conds(c)
        entry += got
    exit_ = []
    for c in exits[side]:
        exit_ += conds(c)[0]
    if entries[other]:
        # a long-and-short script flips on the opposite signal: here that signal closes the trade
        for c in entries[other]:
            exit_ += conds(c)[0]
        notes.append(f"The script also trades {other}. StratLab tests one direction at a time, so the {other} signal is used as the exit.")

    risk = {}
    for key, pat in (("sl", r"stop\s*=\s*[^,)]*?\(\s*1\s*-\s*([\w.]+)\s*(/\s*100)?\s*\)"),
                     ("tgt", r"limit\s*=\s*[^,)]*?\(\s*1\s*\+\s*([\w.]+)\s*(/\s*100)?\s*\)")):
        m = re.search(pat, code)
        if m:
            v = consts.get(m.group(1)) if m.group(1) in consts else _num(m.group(1))
            if v is not None:
                pct = v if m.group(2) else v * 100 if v < 1 else v
                if 0 < pct < 100:
                    risk[key] = round(pct, 2)
    if re.search(r"strategy\.exit\([^)]*\b(loss|profit|trail_points|trail_offset)\s*=", code):
        notes.append("Stops or targets set in ticks or points couldn't be converted to percent. Set them in the rules.")
    name = re.search(r"strategy\s*\(\s*(?:title\s*=\s*)?[\"']([^\"']+)", code)
    return {"entry": entry[:10], "exit": exit_[:10], "entryJoin": join, "side": side, "tf": None,
            "name": name.group(1)[:80] if name else None, "instrument": None, "market": None,
            "risk": risk, "mentioned": sorted({*risk, *(["exit"] if exit_ else [])}), "notes": list(dict.fromkeys(notes))}


def _unwrap(s: str) -> str:
    """Drop brackets that wrap the whole expression, and only those: "(a > b)" -> "a > b", "f(a)" stays."""
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        for i, ch in enumerate(s):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(s) - 1:
                return s
        s = s[1:-1].strip()
    return s


def _num(s: str):
    try:
        return float(s)
    except ValueError:
        return None


def _ta_ref(kind: str, src: str, length: str, consts: dict) -> dict | None:
    n = consts.get(length) if length in consts else _num(length)
    if n is None or src not in ("close", "src"):
        return None
    return {"t": kind, "p": int(n)}
