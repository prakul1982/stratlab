"""Recognise option-structure strategies (straddles, strangles, condors...) and translate them for the options builder."""
import json
import math
import re

from pydantic import ValidationError

from ..models import OptionStrategy

STRONG = re.compile(r"short[_ -]straddle|long[_ -]straddle|short[_ -]strangle|long[_ -]strangle|iron[_ -](?:fly|butterfly|condor)"
                    r"|butterfly|calendar spread|ratio spread|bull (?:call|put) spread|bear (?:call|put) spread|hedge_legs"
                    r"|short_legs|\"legs\"\s*:|atm (?:ce|pe|call|put)|recent(?:er|re)|0?\.\d+[ -]delta (?:strangle|straddle|call|put|ce|pe)"
                    r"|(?:closest|nearest) (?:premium|delta)|atm straddle premium", re.I)


def is_options(text: str, fmt: str) -> bool:
    hits = {m.group(0).lower().replace("_", " ").replace("-", " ") for m in STRONG.finditer(text[:60000])}
    return len(hits) >= 2 or (len(hits) >= 1 and fmt == "text")      # plain words, as importer.detect names them


SYSTEM = """You translate an options trading strategy (a config file, code or a description) into JSON for a paper-trading engine that trades option structures on live NSE, BSE and MCX quotes. Reply with ONLY the JSON object, no prose.

Schema:
{
 "name": str,
 "structure": one of "short_straddle","short_strangle","iron_fly","iron_condor","long_straddle","long_strangle","bull_call_spread","bear_put_spread","sell_call","sell_put","buy_call","buy_put","custom",
 "exchange": "NFO" (NSE options: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, stock options) | "BFO" (BSE: SENSEX, BANKEX) | "MCX" (CRUDEOIL, NATURALGAS, GOLDM, SILVERM...) | "CDS" (NSE currency options: USDINR, EURINR, GBPINR, JPYINR),
 "underlying": the option's underlying name as the exchange lists it, e.g. "NIFTY", "BANKNIFTY", "SENSEX", "CRUDEOIL", "RELIANCE",
 "expiry": "current" (nearest), "next", or "month",
 "offsetUnit": "strikes" or "points",
 "legs": [{"side": "sell"|"buy", "opt": "CE"|"PE", "offset": distance from the at-the-money strike, positive = out of the money (calls up, puts down), "lots": lots of this leg per unit,
           "pick": how the strike is chosen: "offset" (the distance above; the default), "delta" (the strike whose delta is nearest "delta", e.g. 0.2), "delta_range" (delta between "delta" and "deltaTo"), "premium" (premium nearest "premium" in rupees; "premiumOp": "near" | "gte" (at or above) | "lte" (at or below)), "straddle_pct" (premium nearest "pct" % of the at-the-money straddle),
           "delta": 0.01-0.99 (always positive, for calls and puts alike), "deltaTo": 0.01-0.99, "premium": rupees, "premiumOp": "near"|"gte"|"lte", "pct": 1-200}],
 "timing": {"entry": "HH:MM", "lastEntry": "HH:MM", "squareoff": "HH:MM", "maxEntries": int, "cooldown": minutes},
 "risk": {"stopType": "none"|"amount"|"credit_pct", "stop": number, "tgtType": "none"|"amount"|"credit_pct", "tgt": number,
          "trailAfter": money, "trailBy": money, "legStopPct": % rise in a sold leg's premium that closes it (0 = off), "dailyLoss": money (0 = off)},
 "recenter": {"enabled": bool, "every": minutes between checks, "threshold": strikes moved before rolling, "roll": "shorts"|"all"},
 "sizing": {"mode": "lots"|"margin", "lots": units of the structure, "capital": money, "safety": 0.5-1},
 "costs": {"brokerage": per order, "slippageTicks": int, "freeze": most units per order (0 = exchange default)},
 "vix": {"min": lowest India VIX to enter at (0 = none), "max": highest (0 = none)} or omit,
 "notes": short plain-English list of anything in the source this engine can't do (e.g. entry signals from indicators, SL-limit order mechanics, broker login details)
}
Rules: "sell the 0.2 delta strangle" = two sold legs with pick "delta", delta 0.2; "strike with delta between 0.15 and 0.25" = pick "delta_range"; "sell the strike nearest ₹50 premium" / "closest premium 50" = pick "premium", premium 50; "premium at least 40" = premiumOp "gte"; "30% of the ATM straddle" = pick "straddle_pct", pct 30. Only set pick when the source picks strikes that way. If the source filters entries on India VIX ("enter only if VIX is between 11 and 18", "no trade when VIX > 20"), set "vix": {"min": lowest or 0, "max": highest or 0}.
Amounts are in the account currency (rupees). A "stop of 50,000 per trade" is stopType "amount", stop 50000. A "30% SL on premium" is credit_pct 30. Iron fly = sell ATM CE and PE (offset 0) and buy wings; if the source searches a range of wing distances, pick the middle of the range in points. If the source sizes to a margin cap, use sizing mode "margin" with that capital and safety. Recentering check times every 30 minutes -> every 30. Ignore anything about logins, tokens, dashboards and schedulers."""


def from_json(text: str) -> OptionStrategy | None:
    """A StratLab options export loads exactly; one with values out of range is repaired (from_export says how)."""
    got = from_export(text)
    return got[0] if got else None


def from_export(text: str) -> tuple[OptionStrategy, list[str]] | None:
    """(the strategy, what was changed) for a StratLab options export. A value that doesn't fit is clamped or set to its
    default and said in plain words, never dropped: the export is read here, not by the AI (DB-002: a condor whose one
    leg had 100,000 lots went to the AI, which dropped the leg and turned it into another structure). None when the text
    isn't an options export."""
    try:
        d = json.loads(text)
    except ValueError:
        return None
    if not (isinstance(d, dict) and d.get("stratlab") == "options" and isinstance(d.get("strategy"), dict)):
        return None
    try:
        got = OptionStrategy(**d["strategy"]), []
    except ValidationError:
        try:
            got = repair(d["strategy"])
        except ValueError:
            return None
    return checked(*got)


def checked(s: OptionStrategy, notes: list[str]) -> tuple[OptionStrategy, list[str]]:
    """What a valid strategy can still get wrong, said (DB-003): an expiry date already past is the nearest expiry, and a
    stop of more than the whole premium is pointed out."""
    from datetime import date
    from ..kite_service import ist_date
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s.expiry):
        try:
            past = date.fromisoformat(s.expiry) < ist_date()
        except ValueError:
            past = True
        if past:
            notes.append(f"The expiry {s.expiry} has passed, so the nearest expiry is used.")
            s = s.model_copy(update={"expiry": "current"})
    r = s.risk
    if r.stopType == "credit_pct" and r.stop > 100:
        notes.append(f"The stop is {_shown(r.stop)}% of the premium: the loss can reach {r.stop / 100:,.3g} times the premium "
                     "before it exits. Check that's what you meant.")
    return s, notes


# ---------- repairing what doesn't fit (DB-002, DB-003) ----------
# each setting as the builder names it, for the notes
LABELS = {
    "lots": "lots", "offset": "the distance from the money", "delta": "the delta", "deltaTo": "the high end of the delta range",
    "premium": "the premium", "pct": "the share of the straddle", "pick": "how the strike is picked", "premiumOp": "the premium match",
    "entry": "Entry time", "lastEntry": "Last entry time", "squareoff": "Square-off time", "maxEntries": "Entries a day",
    "cooldown": "Wait after a trade (minutes)", "stopType": "The stop's type", "stop": "The stop", "tgtType": "The target's type",
    "tgt": "The target", "trailAfter": "Trail once up", "trailBy": "Giving back", "legStopPct": "The sold-leg stop",
    "dailyLoss": "The daily loss cap", "enabled": "Re-centring", "every": "The re-centring check (minutes)",
    "threshold": "The re-centring distance (strikes)", "roll": "What rolls", "mode": "Sizing", "capital": "Paper capital",
    "safety": "The margin safety share", "brokerage": "Brokerage per order", "slippageTicks": "Extra slippage (ticks)",
    "freeze": "The freeze limit", "min": "The lowest India VIX", "max": "The highest India VIX",
}


# each section in words, for the AI path's notes ("Used defaults for timing" was the field's name)
SECTIONS = {"timing": "timing (entry, last entry and square-off times)", "risk": "stop and target settings",
            "recenter": "re-centring settings", "sizing": "sizing", "costs": "costs (brokerage, slippage, freeze limit)",
            "vix": "India VIX filter (the lowest has to be below the highest)", "expiry": "expiry", "name": "name",
            "structure": "structure", "exchange": "exchange", "offsetUnit": "distance unit"}


def _shown(v) -> str:
    """A value from the file as a person reads it: 100,000, −3, "25:99"."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return f'"{str(v)[:30]}"'
    s = f"{abs(v):,.0f}" if float(v).is_integer() else f"{abs(v):,.4g}"
    return ("−" if v < 0 else "") + s


def _bounds(f) -> tuple[float | None, float | None, bool]:
    """(lowest, highest, whether both ends can be reached) of a numeric field."""
    lo = hi = None
    closed = True
    for m in f.metadata:
        for attr, is_lo, inclusive in (("ge", True, True), ("gt", True, False), ("le", False, True), ("lt", False, False)):
            v = getattr(m, attr, None)
            if v is not None:
                lo, hi = (v, hi) if is_lo else (lo, v)
                closed = closed and inclusive
    return lo, hi, closed


def _range(lo, hi) -> str:
    if hi is None or hi >= 1e9:
        return f"{_shown(lo)} or more"
    return f"between {_shown(lo)} and {_shown(hi)}" if lo < 0 else f"{_shown(lo)}–{_shown(hi)}"


def _fix(M, raw: dict, where: str, notes: list[str]) -> dict:
    """The fields of `raw` that model M can take: a number out of range clamped into it, a whole-number field rounded, and
    anything else that doesn't fit left to its default. Each change is a note in plain words."""
    from pydantic import TypeAdapter
    from typing import Annotated
    out = {}
    for name, f in M.model_fields.items():
        if name not in raw:
            continue
        v = raw[name]
        check = TypeAdapter(Annotated[f.annotation, *f.metadata] if f.metadata else f.annotation)
        try:
            out[name] = check.validate_python(v)
            continue
        except ValidationError:
            pass
        label = LABELS.get(name, name)
        lo, hi, closed = _bounds(f)
        num = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        if num and lo is not None and closed:
            new = min(max(v, lo), hi if hi is not None else v)
            if f.annotation is int:
                new = int(math.floor(new + 0.5))
            out[name] = new
            if lo <= v <= (hi if hi is not None else v):
                notes.append(f"{where}{label} must be a whole number; {_shown(v)} was set to {_shown(new)}.")
            else:
                notes.append(f"{where}{label} must be {_range(lo, hi)}; {_shown(v)} was set to {_shown(new)}.")
        elif f.default is not None and str(f.default) != "PydanticUndefined":
            d = f.default
            notes.append(f"{where}{label} couldn't be read ({_shown(v)}), so it is {_shown(d) if not isinstance(d, str) else d}, the default.")
    return out


def repair(s: dict) -> tuple[OptionStrategy, list[str]]:
    """An options strategy with every value made to fit, and the notes that say what changed. Legs are kept (clamped),
    never dropped, unless a leg's side or type can't be read. Raises ValueError when there's no leg or underlying."""
    from ..models import OptCosts, OptLeg, OptRecenter, OptRisk, OptSignal, OptSizing, OptTiming, OptVix
    notes: list[str] = []
    out = {k: s[k] for k in ("name", "structure", "exchange", "underlying", "offsetUnit") if k in s}
    if out.get("exchange") not in ("NFO", "BFO", "MCX", "CDS"):
        out.pop("exchange", None)
    if out.get("offsetUnit") not in ("strikes", "points"):
        out.pop("offsetUnit", None)
    if not isinstance(out.get("name"), str) or not out["name"].strip():
        out.pop("name", None)
    else:
        out["name"] = out["name"][:80]
    e = s.get("expiry", "current")
    if not isinstance(e, str) or not re.fullmatch(r"current|next|month|\d{4}-\d{2}-\d{2}", e):
        notes.append(f"The expiry {_shown(e)} couldn't be read, so the nearest expiry is used.")
        e = "current"
    out["expiry"] = e
    raw_legs = [l for l in s.get("legs") or [] if isinstance(l, dict)]
    if len(raw_legs) > 8:
        notes.append(f"A structure has at most 8 legs, so the first 8 of the {len(raw_legs)} were kept.")
    legs, changed = [], len(raw_legs) > 8
    for i, l in enumerate(raw_legs[:8], 1):
        if l.get("side") not in ("buy", "sell") or l.get("opt") not in ("CE", "PE"):
            notes.append(f"Left out leg {i}: its side has to be buy or sell and its type CE (call) or PE (put).")
            changed = True
            continue
        before = len(notes)
        got = _fix(OptLeg, l, f"Leg {i}: ", notes)
        try:
            legs.append(OptLeg(**got))
        except ValidationError:                     # a delta range the wrong way round
            got.pop("delta", None), got.pop("deltaTo", None)
            notes.append(f"Leg {i}: the delta range's low end has to be below its high end, so 0.20 to 0.30 is used.")
            legs.append(OptLeg(**got))
        changed = changed or len(notes) > before
    if not legs or not isinstance(out.get("underlying"), str) or not out["underlying"].strip():
        raise ValueError("No option legs or underlying could be found in that.")
    out["legs"] = legs
    # a structure whose legs changed is no longer the named one: the page then shows "Custom legs", not the condor's card
    if changed and out.get("structure") not in (None, "custom"):
        out["structure"] = "custom"
    raw = dict(s["risk"]) if isinstance(s.get("risk"), dict) else None
    if raw:
        # a stop or target that can't be read is off, not a number made up for it (DB-003: "−50" became a 50% stop and a
        # non-numeric target a 30% one)
        for kind, val, word in (("stopType", "stop", "stop"), ("tgtType", "tgt", "target")):
            v = raw.get(val)
            if val in raw and not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0):
                raw.pop(val)
                if raw.get(kind, OptRisk.model_fields[kind].default) != "none":
                    raw[kind] = "none"
                    notes.append(f"The {word} in the file ({_shown(v)}) isn't an amount of 0 or more, so there's no {word}. "
                                 "Set one before you start if you want it.")
    for k, M in (("timing", OptTiming), ("risk", OptRisk), ("recenter", OptRecenter), ("sizing", OptSizing), ("costs", OptCosts)):
        part = raw if k == "risk" else s.get(k)
        if isinstance(part, dict):
            out[k] = M(**_fix(M, part, "", notes))
    if isinstance(s.get("notes"), str):
        out["notes"] = s["notes"][:2000]
    if isinstance(s.get("signal"), dict):
        try:
            out["signal"] = OptSignal(**s["signal"])
        except ValidationError:
            notes.append("The notebook rules it entered on couldn't be read, so it enters at a set time. Pick the rules again if you want them.")
    if isinstance(s.get("vix"), dict):
        try:
            out["vix"] = OptVix(**_fix(OptVix, s["vix"], "", notes))
        except ValidationError:
            notes.append("The India VIX filter's band couldn't be used (the lowest has to be below the highest), so it is off.")
    try:
        return OptionStrategy(**out), notes
    except ValidationError:
        out["timing"] = OptTiming()
        notes.append("The times in the file put entries after the square-off, so the default times are used: enter at 09:30, "
                     "no later than 14:45, square off at 15:15.")
        return OptionStrategy(**out), notes


def leg_text(l: dict) -> str:
    """A leg from a source as a person reads it: "sell 4 OTM CE, 100,000 lots"."""
    side = l.get("side") if l.get("side") in ("buy", "sell") else "?"
    opt = l.get("opt") if l.get("opt") in ("CE", "PE") else "?"
    bits = [f"{side} {opt}"]
    if "offset" in l:
        bits.append(f"distance {_shown(l['offset'])}")
    if "lots" in l:
        bits.append(f"{_shown(l['lots'])} lots")
    return ", ".join(bits)


def parse_ai(data: dict) -> tuple[OptionStrategy, list[str]]:
    """Validate the AI's answer, dropping anything malformed rather than failing the whole import."""
    notes = data.pop("notes", "")
    notes = [notes] if isinstance(notes, str) and notes else [str(n) for n in notes] if isinstance(notes, list) else []
    legs = [l for l in data.get("legs") or [] if isinstance(l, dict)]
    base = {k: data[k] for k in ("name", "structure", "exchange", "underlying", "expiry", "offsetUnit") if k in data}
    base["legs"] = legs[:8]
    for k in ("timing", "risk", "recenter", "sizing", "costs", "vix"):
        if isinstance(data.get(k), dict):
            base[k] = data[k]
    try:
        return OptionStrategy(**base), notes
    except ValidationError:
        pass
    # keep what validates, section by section
    from ..models import OptCosts, OptLeg, OptRecenter, OptRisk, OptSizing, OptTiming, OptVix
    fixed = {k: base[k] for k in ("name", "structure", "exchange", "underlying", "expiry", "offsetUnit") if k in base}
    good = []
    for i, l in enumerate(legs, 1):
        try:
            good.append(OptLeg(**l))
        except ValidationError:
            # what the leg was and why, in words, not the raw dict (DB-002); a leg with a readable side and type is kept,
            # its numbers clamped, and the structure becomes custom legs
            if l.get("side") in ("buy", "sell") and l.get("opt") in ("CE", "PE"):
                try:
                    good.append(OptLeg(**_fix(OptLeg, l, f"Leg {i} ({leg_text(l)}): ", notes)))
                    fixed["structure"] = "custom"
                    continue
                except ValidationError:
                    pass
            notes.append(f"Left out leg {i} ({leg_text(l)}): its side has to be buy or sell and its type CE (call) or PE (put).")
            fixed["structure"] = "custom"
    fixed["legs"] = good
    for k, M in (("timing", OptTiming), ("risk", OptRisk), ("recenter", OptRecenter), ("sizing", OptSizing), ("costs", OptCosts),
                 ("vix", OptVix)):
        if k in base:
            try:
                fixed[k] = M(**base[k])
            except ValidationError:
                notes.append(f"The source's {SECTIONS[k]} didn't fit, so the defaults are used for them. Check them before you start.")
    if not good or not fixed.get("underlying"):
        raise ValueError("No option legs or underlying could be found in that.")
    for _ in range(8):
        try:
            return OptionStrategy(**fixed), notes
        except ValidationError as e:
            bad = {str(x["loc"][0]) if x.get("loc") else "timing" for x in e.errors()}
            if bad & {"legs", "underlying"} or not bad & set(fixed):
                raise ValueError("That options strategy couldn't be read.")
            for k in bad:
                fixed.pop(k, None)
                notes.append(f"Used the defaults for {SECTIONS.get(k, k)}. Check them before you start.")
    raise ValueError("That options strategy couldn't be read.")
