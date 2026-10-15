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


EXTENSIONS = {".pine": "pine", ".mq4": "mql", ".mq5": "mql", ".afl": "afl", ".py": "python"}


def detect(text: str, filename: str = "") -> str:
    name = (filename or "").lower()
    t = text.strip()
    # the file's own extension first: a Python file that names a function strategy() or uses the ta library is Python
    ext = next((f for e, f in EXTENSIONS.items() if name.endswith(e)), None)
    if ext:
        return ext
    if t.startswith("{"):
        try:
            obj = json.loads(t)
        except ValueError:
            return "stratlab" if re.search(r'"format"\s*:\s*"stratlab', t[:400]) else "text"          # a cut or damaged export
        if not isinstance(obj, dict):
            return "json"
        fmt = obj.get("format")
        own = (isinstance(fmt, str) and fmt.startswith("stratlab")) or isinstance(obj.get("strategy"), dict)
        return "stratlab" if own else "json"
    if re.search(r"//@version|(?<!def )\bstrategy\s*\(|\bta\.\w+\(|\bindicator\s*\(|\bstudy\s*\(", t):
        return "pine"
    if re.search(r"\bOnTick\s*\(|\biMA\s*\(|\bOrderSend\s*\(", t):
        return "mql"
    if re.search(r"^\s*(Buy|Sell|Short|Cover)\s*=", t, re.M):
        return "afl"
    if re.search(r"^\s*(import|from)\s+\w+|^\s*def\s+\w+\(|^\s*class\s+\w+\(", t, re.M):
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
    inst_id = (inst or {}).get("id") if isinstance((inst or {}).get("id"), str) and (inst or {}).get("id") else None
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
    given = ["tf", "exit", "sl", "tgt", "trail", "maxBars", "riskPct", "capital"] + (["instrument"] if inst_id or group else [])
    return {"strategy": s.model_dump(), "instrument_id": None if group else inst_id, "group": group,
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

    def tree(expr: str, depth: int = 0):
        """An expression as an atom (a string) or (op, [parts]), parts joined by the same op merged into it."""
        expr = _unwrap(expr)
        if expr in cond_vars and depth < 4:
            return tree(cond_vars[expr], depth + 1)
        for op in ("or", "and"):                 # "or" binds loosest
            parts = _split_top(expr, rf"\b{op}\b")
            if len(parts) > 1:
                kids = []
                for k in (tree(x, depth + 1) for x in parts):
                    kids += k[1] if isinstance(k, tuple) and k[0] == op else [k]
                return op, kids
        return expr

    def flat(exprs: list[str]) -> tuple[str, list[str]] | None:
        """Conditions that must all hold (an `if` and the ones it sits in) as ("all" | "any", atoms), or None when and
        and or are mixed (StratLab's rules hold all of them, or any of them, not both)."""
        t = tree(" and ".join(f"({e})" for e in exprs))
        if isinstance(t, str):
            return "all", [t]
        op, kids = t
        if any(not isinstance(k, str) for k in kids):
            return None
        return ("any" if op == "or" else "all"), kids

    def cond(atom: str) -> dict | None:
        atom = _unwrap(atom)
        m = re.fullmatch(r"(?:ta\.)?cross(over|under)\((.*)\)", atom)
        args = _split_top(m.group(2), ",") if m else []
        if m and len(args) == 2:
            l, r, op = operand(args[0]), operand(args[1]), "xa" if m.group(1) == "over" else "xb"
        else:
            m = None if args else re.fullmatch(r"(.+?)\s*(>=|<=|>|<)\s*(.+)", atom)
            l, r, op = (operand(m.group(1)), operand(m.group(3)), "gt" if m.group(2).startswith(">") else "lt") if m else (None, None, None)
            if m and m.group(2) in (">=", "<="):
                word = "is above" if m.group(2) == ">=" else "is below"
                notes.append(f"\"{atom[:80]}\" was read as \"{word}\": StratLab's rules have no \"at or {word[3:]}\", so the two "
                             "differ only on a candle where both sides are exactly equal.")
        if l and r and op:
            try:
                return Cond(l=l, op=op, r=r).model_dump(exclude_none=True)
            except ValidationError:
                pass
        notes.append(f"Couldn't translate \"{atom[:80]}\", so it was left out.")
        return None

    def rules(atoms: list[str]) -> list[dict]:
        out = []
        for a in atoms:
            c = cond(a)
            if c and c not in out:
                out.append(c)
        return out

    # each strategy.entry / close call with the conditions it runs under: its when=, and every `if` it sits in (by
    # indentation: an `if` inside an `if` needs both); a call under an `else` can't be read (it runs when a condition is false)
    calls = []
    order = r"strategy\.(?:entry|close_all|close|exit|order)\s*\("     # a call; strategy.position_size and the like are values
    stack: list[tuple[int, str | None]] = []          # (indent, condition) of the open `if` blocks; None for an else
    for line in code.splitlines():
        if not line.strip():
            continue
        indent = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        head = re.match(r"\s*if\s+(.+?)\s*$", line)
        if re.match(r"\s*else\b", line):
            stack.append((indent, None))
            continue
        if head and not re.search(order, head.group(1)):   # `if x strategy.entry(...)` on one line is a call, not a block
            stack.append((indent, head.group(1)))
            continue
        call = re.search(r"strategy\.(entry|close_all|close)\s*\((.*)\)", line)
        if not call:
            continue
        args = call.group(2)
        when = re.search(r"when\s*=\s*(.+?)\s*(?:,\s*\w+\s*=|$)", args)
        same = re.match(r"\s*if\s+(.+?)\s+" + order, line)
        own = [c for _, c in stack] + [x.group(1) for x in (same, when) if x]
        cid = re.match(r"\s*[\"']([^\"']*)[\"']", args)
        side = "short" if re.search(r"strategy\.short|direction\s*=\s*strategy\.direction\.short", args) else "long"
        calls.append({"kind": call.group(1), "id": cid.group(1) if cid else None, "side": side, "conds": own,
                      "text": line.strip()[:80]})
    sides_of = {c["id"]: c["side"] for c in calls if c["kind"] == "entry" and c["id"] is not None}
    entries: dict[str, list] = {"long": [], "short": []}
    exits: dict[str, list] = {"long": [], "short": []}
    for c in calls:
        if not c["conds"]:                 # no condition: a close at the end of the script, an entry on every candle
            notes.append(f"\"{c['text']}\" runs without a condition, on every candle, which StratLab's rules can't express, "
                         "so it was left out.")
            continue
        if any(x is None for x in c["conds"]):
            notes.append(f"\"{c['text']}\" sits under an else, which StratLab's rules can't express, so it was left out.")
            continue
        if c["kind"] == "entry":
            entries[c["side"]].append(c)
        else:
            for sd in ([sides_of[c["id"]]] if c["kind"] == "close" and c["id"] in sides_of else ["long", "short"]):
                exits[sd].append(c)

    side = "long" if entries["long"] or not entries["short"] else "short"
    other = "short" if side == "long" else "long"
    # entries: each entry statement opens a trade on its own, so several are any-of; one statement keeps its own and/or
    entry, join = [], "all"
    read = []
    for c in entries[side]:                # the same conditions over several calls are one entry statement
        r = flat(c["conds"])
        if r is None or r not in read:
            read.append(r)
    if any(r is None for r in read):
        notes.append("The entry conditions mix and with or in a way StratLab's rules can't hold (all of the rules, or any "
                     "of them), so the entry rules were left out. Add them by hand.")
    elif len(read) == 1:
        join, atoms = read[0]
        entry = rules(atoms)
    elif read:
        if any(j == "all" and len(rules(a)) > 1 for j, a in read):   # what translates: a dropped atom isn't a condition
            notes.append(f"The script has {len(read)} entry statements (any one of them opens a trade) and at least one needs "
                         "several conditions together; StratLab's rules can't hold both, so the entry rules were left out. "
                         "Add them by hand.")
        else:
            join, entry = "any", rules([x for _, a in read for x in a])
    # exits close on any one rule: an exit that needs several conditions together can't be one, so it is left out whole.
    # Only what translates counts: a guard that can't be (strategy.position_size > 0) is left out with a note, not the exit
    exit_ = []
    flips = entries[other]
    for c in [*exits[side], *flips]:
        r = flat(c["conds"])
        got = rules(r[1]) if r else []
        if r is None or (r[0] == "all" and len(got) > 1):
            notes.append(f"An exit needs several conditions together (\"{' and '.join(c['conds'])[:80]}\"); StratLab's exit "
                         "rules close on any one of them, so that exit was left out. Add it by hand.")
            continue
        dropped = ", ".join(f'"{_unwrap(a)[:60]}"' for a in r[1] if cond(a) is None) if r[0] == "all" and got else ""
        if dropped:
            notes.append(f"The exit \"{' and '.join(c['conds'])[:80]}\" was imported without {dropped}, so it closes the "
                         "trade on the rest alone.")
        exit_ += [x for x in got if x not in exit_]
    if flips:
        # a long-and-short script flips on the opposite signal: here that signal closes the trade
        notes.append(f"The script also trades {other}. StratLab tests one direction at a time, so the {other} signal is used as the exit.")
    head = re.search(r"strategy\s*\((.*)\)", code)
    settings_ = head.group(1) if head else ""
    pyr = re.search(r"\bpyramiding\s*=\s*(\w+)", settings_)
    if pyr and pyr.group(1) not in ("0", "1"):
        notes.append(f"pyramiding = {pyr.group(1)} was not imported: StratLab holds one position at a time.")
    if re.search(r"\bprocess_orders_on_close\s*=\s*true", settings_):
        notes.append("process_orders_on_close was not imported: StratLab fills a rule's signal at the next candle's open.")
    if re.search(r"\bcommission_(?:value|type)\s*=", settings_):
        notes.append("The script's commission was not imported: the test uses StratLab's own brokerage and charges, set in the risk settings.")

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


def _split_top(s: str, sep: str) -> list[str]:
    """`s` split where `sep` (a pattern) matches outside brackets: "f(a, b), c" on "," is ["f(a, b)", "c"]."""
    out, depth, last, i = [], 0, 0, 0
    while i < len(s):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0:
            m = re.match(sep, s[i:])
            if m and m.end() > 0 and (i == 0 or not (sep[0:2] == r"\b" and (s[i - 1].isalnum() or s[i - 1] == "_"))):
                out.append(s[last:i].strip())
                i += m.end()
                last = i
                continue
        i += 1
    out.append(s[last:].strip())
    return out


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
