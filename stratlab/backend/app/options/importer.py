"""Recognise option-structure strategies (straddles, strangles, condors...) and translate them for the Options tab."""
import json
import re

from pydantic import ValidationError

from ..models import OptionStrategy

STRONG = re.compile(r"short[_ -]straddle|long[_ -]straddle|short[_ -]strangle|long[_ -]strangle|iron[_ -](?:fly|butterfly|condor)"
                    r"|butterfly|calendar spread|ratio spread|bull (?:call|put) spread|bear (?:call|put) spread|hedge_legs"
                    r"|short_legs|\"legs\"\s*:|atm (?:ce|pe|call|put)|recent(?:er|re)", re.I)


def is_options(text: str, fmt: str) -> bool:
    hits = {m.group(0).lower().replace("_", " ").replace("-", " ") for m in STRONG.finditer(text[:60000])}
    return len(hits) >= 2 or (len(hits) >= 1 and fmt == "words")


SYSTEM = """You translate an options trading strategy (a config file, code or a description) into JSON for a paper-trading engine that trades option structures on live NSE, BSE and MCX quotes. Reply with ONLY the JSON object, no prose.

Schema:
{
 "name": str,
 "structure": one of "short_straddle","short_strangle","iron_fly","iron_condor","long_straddle","long_strangle","bull_call_spread","bear_put_spread","sell_call","sell_put","buy_call","buy_put","custom",
 "exchange": "NFO" (NSE options: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, stock options) | "BFO" (BSE: SENSEX, BANKEX) | "MCX" (CRUDEOIL, NATURALGAS, GOLDM, SILVERM...),
 "underlying": the option's underlying name as the exchange lists it, e.g. "NIFTY", "BANKNIFTY", "SENSEX", "CRUDEOIL", "RELIANCE",
 "expiry": "current" (nearest), "next", or "month",
 "offsetUnit": "strikes" or "points",
 "legs": [{"side": "sell"|"buy", "opt": "CE"|"PE", "offset": distance from the at-the-money strike, positive = out of the money (calls up, puts down), "lots": lots of this leg per unit}],
 "timing": {"entry": "HH:MM", "lastEntry": "HH:MM", "squareoff": "HH:MM", "maxEntries": int, "cooldown": minutes},
 "risk": {"stopType": "none"|"amount"|"credit_pct", "stop": number, "tgtType": "none"|"amount"|"credit_pct", "tgt": number,
          "trailAfter": money, "trailBy": money, "legStopPct": % rise in a sold leg's premium that closes it (0 = off), "dailyLoss": money (0 = off)},
 "recenter": {"enabled": bool, "every": minutes between checks, "threshold": strikes moved before rolling, "roll": "shorts"|"all"},
 "sizing": {"mode": "lots"|"margin", "lots": units of the structure, "capital": money, "safety": 0.5-1},
 "costs": {"brokerage": per order, "slippageTicks": int, "freeze": most units per order (0 = exchange default)},
 "notes": short plain-English list of anything in the source this engine can't do (e.g. entry signals from indicators, SL-limit order mechanics, broker login details)
}
Rules: amounts are in the account currency (rupees). A "stop of 50,000 per trade" is stopType "amount", stop 50000. A "30% SL on premium" is credit_pct 30. Iron fly = sell ATM CE and PE (offset 0) and buy wings; if the source searches a range of wing distances, pick the middle of the range in points. If the source sizes to a margin cap, use sizing mode "margin" with that capital and safety. Recentering check times every 30 minutes -> every 30. Ignore anything about logins, tokens, dashboards and schedulers."""


def from_json(text: str) -> OptionStrategy | None:
    """A StratLab options export loads exactly."""
    try:
        d = json.loads(text)
    except ValueError:
        return None
    if isinstance(d, dict) and d.get("stratlab") == "options" and isinstance(d.get("strategy"), dict):
        try:
            return OptionStrategy(**d["strategy"])
        except ValidationError:
            return None
    return None


def parse_ai(data: dict) -> tuple[OptionStrategy, list[str]]:
    """Validate the AI's answer, dropping anything malformed rather than failing the whole import."""
    notes = data.pop("notes", "")
    notes = [notes] if isinstance(notes, str) and notes else [str(n) for n in notes] if isinstance(notes, list) else []
    legs = [l for l in data.get("legs") or [] if isinstance(l, dict)]
    base = {k: data[k] for k in ("name", "structure", "exchange", "underlying", "expiry", "offsetUnit") if k in data}
    base["legs"] = legs[:8]
    for k in ("timing", "risk", "recenter", "sizing", "costs"):
        if isinstance(data.get(k), dict):
            base[k] = data[k]
    try:
        return OptionStrategy(**base), notes
    except ValidationError:
        pass
    # keep what validates, section by section
    from ..models import OptCosts, OptLeg, OptRecenter, OptRisk, OptSizing, OptTiming
    fixed = {k: base[k] for k in ("name", "structure", "exchange", "underlying", "expiry", "offsetUnit") if k in base}
    good = []
    for l in legs:
        try:
            good.append(OptLeg(**l))
        except ValidationError:
            notes.append(f"Couldn't read a leg: {l}")
    fixed["legs"] = good
    for k, M in (("timing", OptTiming), ("risk", OptRisk), ("recenter", OptRecenter), ("sizing", OptSizing), ("costs", OptCosts)):
        if k in base:
            try:
                fixed[k] = M(**base[k])
            except ValidationError:
                notes.append(f"Used defaults for {k}; the source's values didn't fit.")
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
                notes.append(f"Used the default for {k}.")
    raise ValueError("That options strategy couldn't be read.")
