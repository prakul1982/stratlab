"""The idea's own words, read without the AI, for the phrasings people write most (57.1, the PARSER lane).

The AI builder misread plain English and nothing said so: "Buy when the 20 EMA crosses above the 50 EMA, sell when it
crosses back below" came back as "Price crosses EMA 20 and Price crosses EMA 50" with "Price below EMA 20 or EMA 50" as the
way out, and with an index named, the way out was "EMA 50 crosses below Price": the lines the other way round, a different
strategy. The cause is the model's (the same answer was then served from the cache every time), so the check is ours.

`read` takes a sentence apart clause by clause and turns each buy or sell clause into rules, but only when every word of the
clause is understood: averages (EMA, SMA, DMA, "the 20-day average"), RSI, the price, the 52-week high or low, plain numbers,
crossing ("crosses above", "goes under", "breaks out above") and state ("is above", "closes under") wording, a stop or target in
%, and the pronoun ways out ("sell when it crosses back below", "when it closes back under it", "when it gets back above 70").
A side (buy or sell) whose clauses aren't all understood is not read at all, and the AI's reading stands for it. A pronoun
in a sell clause is kept as a placeholder and resolved by `resolve_exit` against the buy rules that end up being used, so "it
crosses back below" after "X crosses above Y" is "X crosses below Y": the same two lines, in the same order."""
import re

FLIP = {"gt": "lt", "lt": "gt", "xa": "xb", "xb": "xa", "eq": "eq"}
IT = {"t": "it"}            # a pronoun: the line the buy rule used, resolved once the buy rules are known
_NUM = r"\d+(?:\.\d+)?"

# instruments named in the words: never part of a rule ("NIFTY 50" holds a 50 that is not a 50-day anything)
_INDEX = re.compile(r"(?:\b(?:on|in|for)\s+)?\b(?:nifty\s*(?:50|bank|it|next\s*50|midcap\s*\d*|smallcap\s*\d*|fin\s*service|financial services)?|bank\s*nifty|"
                    r"finnifty|sensex|s&p\s*500|nasdaq(?:\s*100)?|dow(?:\s*jones)?)\b")
# a candle size is the strategy's timeframe, which the AI's reply already holds: not part of a rule either
_TF = re.compile(r"\b(?:on|using|with|in)?\s*(?:the\s+)?(?:daily|weekly|hourly|1[- ]?day|1[- ]?hour|\d+[- ]?min(?:ute)?s?)\s*"
                 r"(?:candles?|bars?|charts?|time ?frames?)\b|\bon\s+(?:the\s+)?(?:daily|hourly)\b")
_STOP = r"(?:stop[- ]?loss(?:es)?|stop|sl)"
_TGT = r"(?:target|take[- ]?profit|profit target|tp)"
_RISK = [
    ("sl", re.compile(rf"(?:\b(?:with|and)\s+)?(?:\ban?\s+)?(?:({_NUM})\s?%\s*(?:{_STOP})\b|\b{_STOP}(?:\s+(?:of|at|=|:))?\s*({_NUM})\s?%)")),
    ("tgt", re.compile(rf"(?:\b(?:with|and)\s+)?(?:\ban?\s+)?(?:({_NUM})\s?%\s*(?:{_TGT})\b|\b{_TGT}(?:\s+(?:of|at|=|:))?\s*({_NUM})\s?%)")),
]
_NO_RISK = re.compile(rf"(?:\b(?:with|and)\s+)?\b(?:no|without(?:\s+an?|\s+any)?)\s+(?:{_STOP}|{_TGT})s?\b")
# a short side is the AI's to read: the check below is for long ideas (buy, then sell) only
_SHORT = re.compile(r"\b(?:short|shorts|shorting|both ways|both directions)\b(?![- ]?term)")
_BUY = r"(?:buy|buys|buying|go long|going long|enter long|enter|long)"
_SELL = r"(?:sell|sells|selling|exit|exits|close(?:\s+(?:it|the trade|the position))?(?!\s*(?:is|was)?\s*(?:above|below|over|under|back))|" \
        r"get out|square off|book (?:the )?profits?)"
_LEAD = re.compile(rf"^(?:and\s+|then\s+)?(?:(?:i\s+)?(?:want to|would|will)\s+)?({_BUY}|{_SELL})\b")
_WHEN = re.compile(r"\b(?:when(?:ever)?|if|once|as soon as)\b")
_BREAK = re.compile(r"\bon\s+(?:an?\s+|the\s+)?(?=break)")
# a crossing happens on one candle; a state holds on every candle it stays true (the AI's prompt makes the same split)
_OP = re.compile(
    r"\bcross(?:es|ed|ing)?\s+(?P<xb>back\s+)?(?P<x1>above|over|below|under)\b"
    r"|\bcross(?:es|ed)?\s+back\b(?!\s+(?:above|over|below|under))(?P<xback>)"
    r"|\b(?:breaks?(?:\s+out)?|breakout|break-out|breaking(?:\s+out)?)\s+(?P<bb>back\s+)?(?P<x2>above|over|below|under)\b"
    r"|\b(?:goes|go|moves?|rises?|climbs?|jumps?|gets?|falls?|drops?|dips?|slips?|sinks?|declines?|comes?|turns?)\s+(?P<mb>back\s+)?"
    r"(?:up\s+|down\s+)?(?P<x3>above|over|below|under)\b"
    r"|(?:\b(?:is|are|was|stays?|remains?|trades?|closes?|closed|closing|holds?)\s+)?(?P<sb>back\s+)?(?P<s>above|over|below|under)\b")
_PCT_MOVE = re.compile(rf"^(?:it\s+|the\s+price\s+|price\s+)?(?:(?P<dn>falls?|drops?|declines?|loses?|is down|goes down)|"
                       rf"(?P<up>rises?|gains?|is up|goes up|climbs?))\s+(?:by\s+)?(?P<v>{_NUM})\s?%(?:\s+from\s+(?:the\s+)?(?:entry|buy)(?:\s+price)?)?$")

_KIND = (("ema", r"ema|exponential moving average|exponential average"),
         ("sma", r"sma|dma|simple moving average|simple average"),
         ("avg", r"moving average|day moving average|average|avg|ma"))
_KINDS = "|".join(p for _, p in _KIND)
_MA_N_FIRST = re.compile(rf"^(?P<n>\d{{1,3}})\s*[- ]?\s*(?P<u>(?:day|week|period|bar|candle)s?|d(?![a-z])|w(?![a-z]))?\s*[- ]?\s*(?P<k>{_KINDS})$")
_MA_N_AFTER = re.compile(rf"^(?P<k>ema|sma|dma|ma)\s*\(?\s*(?P<n>\d{{1,3}})\s*\)?$")
_RSI = re.compile(r"^(?:(?P<a>\d{1,3})\s*[- ]?\s*(?:day|period|bar|candle)?s?\s*[- ]?\s*)?rsi(?:\s*\(?\s*(?P<b>\d{1,3})\s*\)?)?$")
_W52 = re.compile(r"^(?:52|fifty[- ]?two)\s*[- ]?\s*(?:weeks?|wks?|w)\s*[- ]?\s*(?P<w>high|low)s?$|^(?:one|1)[- ]?year\s*[- ]?\s*(?P<y>high|low)s?$")
_PRICE = re.compile(r"^(?:price|close|closing price|the close|share price|stock|stock price|candle|ltp)$")
_FILL = re.compile(r"\b(?:the|its|a|an|new|their|current|daily)\b")


def _kind(word: str) -> str:
    return next(k for k, p in _KIND if re.fullmatch(p, word))


def _ref(s: str, assumed: list[str]) -> dict | None:
    """One side of a rule, from words that must say nothing else: None when they do."""
    s = re.sub(r"\s+", " ", _FILL.sub(" ", s)).strip(" ,")
    if s in ("", "it", "it's", "its", "this", "that"):
        return IT
    if m := _W52.match(s):
        return {"t": "dc_upper" if (m["w"] or m["y"]) == "high" else "dc_lower", "p": 252}
    m = _MA_N_FIRST.match(s) or _MA_N_AFTER.match(s)
    if m:
        kind, n = _kind(m["k"]), int(m["n"])
        if not 1 <= n <= 500:
            return None
        # LIVE3-004: a length said in days or weeks is kept in its unit (`u`), and turned into what runs once the candles are known
        # (on_timeframe): "200 day moving average" on 15-minute candles had become a 200-candle average while this line said 200-day
        u = (m.groupdict().get("u") or "").rstrip("s")
        unit = "day" if m["k"] == "dma" or u in ("day", "d") else "week" if u in ("week", "w") else None
        length = f"{n}-{unit}" if unit else f"{n}-candle"
        if m["k"] == "dma":
            # "DMA" in Indian usage is the plain (simple) daily average; said, as it is a reading
            assumed.append(f"\"{n} DMA\" is read as the {n}-day simple moving average (SMA).")
        if kind == "avg":
            # "the 20-day average" names no kind: the simple one, said under "We assumed"
            assumed.append(f"\"{s}\" is read as the {length} simple moving average (SMA): your words don't say simple or exponential.")
            kind = "sma"
        return {"t": kind, "p": n, **({"u": unit} if unit else {})}
    if m := _RSI.match(s):
        n = m["a"] or m["b"]
        if n:
            return {"t": "rsi", "p": int(n)} if 1 <= int(n) <= 500 else None
        assumed.append("RSI is read over 14 candles, its usual length: your words give none.")
        return {"t": "rsi", "p": 14}
    if _PRICE.match(s):
        return {"t": "price"}
    if re.fullmatch(_NUM, s):
        return {"t": "num", "v": float(s)}
    return None


def _clauses(t: str) -> list[str]:
    return [c.strip(" ,") for c in re.split(
        r"[.;!?](?=\s|$)|,\s*(?:and\s+|then\s+)?(?=(?:sell|exit|close|buy|go long|enter|get out|square off|book)\b)"
        r"|\s+(?:and|then)\s+(?=(?:sell|exit|close|buy|go long|enter|get out|square off|book)\b)|,\s*then\s+", t) if c and c.strip(" ,")]


def _cond(part: str, side: str, assumed: list[str]) -> tuple[str, object] | None:
    """One condition: ("rule", {l, op, r}), ("sl"/"tgt", value) for "exit if it falls 8%", or None when it isn't understood."""
    part = part.strip(" ,")
    if side == "exit" and (m := _PCT_MOVE.match(part)):
        v = float(m["v"])
        if not 0 < v < 100:
            return None
        k = "sl" if m["dn"] else "tgt"
        assumed.append(f"\"{part}\" is read as a {'stop loss' if k == 'sl' else 'target'} {v:g}% "
                       f"{'under' if k == 'sl' else 'over'} the price the trade was bought at.")
        return k, v
    m = _OP.search(part)
    if not m:
        return None
    left, right = part[:m.start()], part[m.end():]
    word = m["x1"] or m["x2"] or m["x3"] or m["s"]
    back = m["xback"] is not None
    if back:
        op = "back"                         # "crosses back": the other way from the buy rule's crossing, decided on resolving
    else:
        crossing = bool(m["x1"] or m["x2"] or m["x3"])
        up = word in ("above", "over")
        op = ("xa" if up else "xb") if crossing else ("gt" if up else "lt")
    if re.search(r"\b(?:or|either|not)\b", part):
        return None                         # "or" and "not" are the AI's to read
    L, R = _ref(left, assumed), _ref(right, assumed)
    if L is None or R is None:
        return None
    if L.get("t") == "num" or (L is IT and R is IT and side == "entry"):
        return None
    # "falls below", "goes back above": a move across, read as a crossing (as the AI is told), though "is below" reads the
    # same way out; marked, so an AI answer that took it as a state on the same two lines is not overruled for it
    return "rule", {"l": L, "op": op, "r": R, **({"soft": True} if m["x3"] else {})}


def read(text: str) -> dict | None:
    """The buy and sell rules the words state, side by side: {"entry": [...] | None, "exit": [...] | None, "risk": {...},
    "assumed": [...], "named": bool, "said_exit": bool}. A side is None when its words aren't all understood (the AI's reading
    stands for it); sell rules may hold IT, filled by `resolve_exit`. "named": words were passed over as a name (an instrument,
    "Buy RELIANCE when"). None for a short idea, a clause that is neither a buy nor a sell one, or no buy rule read."""
    t = " " + re.sub(r"\s+", " ", (text or "").lower().replace("\u2019", "'")).strip() + " "
    if _SHORT.search(t):
        return None
    named = bool(_INDEX.search(t))
    tf = words_tf(_INDEX.sub(" ", t))
    t = _TF.sub(" ", _INDEX.sub(" ", t))
    risk: dict = {}
    for k, pat in _RISK:
        for m in pat.finditer(t):
            risk.setdefault(k, float(m.group(1) or m.group(2)))
        t = pat.sub(" ", t)
    t = _NO_RISK.sub(" ", t)
    # "risk 1% of capital", "with 5 lakh capital": the money side, read by the AI and the checks after it
    t = re.sub(r"\s+", " ", re.sub(r"(?:\b(?:with|and)\s+)?\b(?:risk(?:ing)?|capital|position size)\b[^.;,]*", " ", t))
    sides: dict[str, list | None] = {"entry": [], "exit": []}
    assumed: list[str] = []
    side = None
    said_exit = False
    for clause in _clauses(t):
        # "on RELIANCE, buy when…", "…crosses back below on NIFTY": a name, not a rule
        bare = re.sub(r"^on\s+(?!an?\b|the\b|its?\b|break)[a-z][\w&.\-]*(?:\s+\d+)?\s*,?\s*", "", clause)
        bare = re.sub(r"\s+(?:on|in|for)\s+(?!an?\b|the\b|its?\b)[a-z][\w&.\-]*(?:\s+\d+)?\s*$", "", bare).strip(" ,")
        named |= bare != clause.strip(" ,")
        if not bare or re.fullmatch(r"(?:with|and|then)", bare):
            continue
        lead = _LEAD.match(bare)
        if lead:
            side = "entry" if re.fullmatch(_BUY, lead.group(1)) else "exit"
            rest = bare[lead.end():]
        elif side and _WHEN.match(bare):
            rest = bare
        else:
            return None                     # a clause that is neither a buy nor a sell one: the AI's reading stands
        said_exit |= side == "exit"
        if sides[side] is None:
            continue
        w = _WHEN.search(rest) or _BREAK.search(rest)
        between = rest[:w.start()].strip() if w else ""
        if not w or _OP.search(between) or re.search(r"\d|\b(?:rsi|ema|sma|dma|average)\b", between):
            sides[side] = None
            continue
        # "Buy RELIANCE when…": a name between the verb and "when" (never a word a rule uses)
        named |= bool(between) and not re.fullmatch(r"(?:it|this|the stock|the index|stock|shares|the shares)", between)
        got = [_cond(part, side, assumed) for part in re.split(r"\s+(?:and|&)\s+", rest[w.end():])]
        if any(c is None for c in got):
            sides[side] = None
            continue
        for kind, v in got:
            if kind == "rule":
                sides[side].append(v)
            else:
                risk.setdefault(kind, v)
    if sides["entry"] == [] or sides["entry"] is None and sides["exit"] is None:
        return None
    # a pronoun left of a buy rule is the price, or the line the buy clause was already about
    subject = None
    for c in sides["entry"] or []:
        if c["l"] is IT:
            c["l"] = subject or {"t": "price"}
        if c["r"] is IT or c["op"] == "back":
            return None
        subject = c["l"]
    return {"entry": sides["entry"], "exit": sides["exit"], "risk": risk, "assumed": list(dict.fromkeys(assumed)),
            "named": named, "said_exit": said_exit, "tf": tf}


_TF_OF = (("1d", r"daily|1[- ]?day"), ("1h", r"hourly|1[- ]?hour|60[- ]?min(?:ute)?s?"), ("15m", r"15[- ]?min(?:ute)?s?"), ("5m", r"5[- ]?min(?:ute)?s?"))
TF_WORDS = {"1d": "daily", "1h": "1-hour", "15m": "15-minute", "5m": "5-minute"}
WEEK_DAYS = 5                 # trading days in a week, for a length said in weeks
MAX_LENGTH = 500              # the longest average the app works out (models.Ref.p)


def words_tf(t: str) -> str | None:
    """The candles the words name ("15 minute candles", "on the daily chart"), one the app runs, else None."""
    m = _TF.search(t or "")
    if not m:
        return None
    return next((tf for tf, p in _TF_OF if re.search(rf"\b(?:{p})\b", m.group(0))), None)


def on_timeframe(got: dict, tf: str | None) -> list[str] | None:
    """The rules' lengths said in days or weeks made what runs on the strategy's candles (LIVE3-004), in place; the lines that say
    so for "We assumed". A day length on intraday candles is worked out on daily candles (the rule's own "tf": "1d"); a week length
    is that many trading days (x5), on daily candles. None when a length can't be run as said (more than MAX_LENGTH days): the side
    is then not read from the words, and the app asks."""
    said = []
    intraday = tf in ("1h", "15m", "5m")
    for side in ("entry", "exit"):
        for c in got.get(side) or []:
            for key in ("l", "r"):
                ref = c.get(key)
                if not isinstance(ref, dict) or "u" not in ref:
                    continue
                unit, n = ref.pop("u"), int(ref["p"])
                days = n * WEEK_DAYS if unit == "week" else n
                if days > MAX_LENGTH:
                    return None
                name = f"{n}-{unit} {ref['t'].upper()}"
                if unit == "week":
                    ref["p"] = days
                    said.append(f"The {name} is worked out as the {days}-day {ref['t'].upper()} ({n} weeks of {WEEK_DAYS} trading days).")
                if intraday:
                    ref["tf"] = "1d"
                    said.append(f"The {days}-day {ref['t'].upper()} is worked out on daily candles (each completed day's close); "
                                f"the trades are on {TF_WORDS[tf]} candles.")
    return list(dict.fromkeys(said))


def resolve_exit(exit_rules: list[dict], entry: list[dict]) -> list[dict] | None:
    """Sell rules with their pronouns filled from the buy rules: "it crosses back below" after "X crosses above Y" is "X crosses
    below Y". The buy rule it refers to is the one that looked the other way (for "below", one that was "above" or crossed
    above); a number on the right keeps the buy rule's subject ("it gets back above 70" after "RSI goes under 30" is "RSI
    crosses above 70"). None when the words could mean more than one buy rule, or none: then nobody guesses, the app asks."""
    out = []
    for c in exit_rules:
        l, op, r = c["l"], c["op"], c["r"]
        if l is not IT and r is not IT and op != "back":
            out.append(c)
            continue
        if op == "back":
            pool = [e for e in entry if e["op"] in ("xa", "xb", "gt", "lt") and e["r"].get("t") != "num"] if r is IT else \
                   [e for e in entry if e["op"] in ("xa", "xb", "gt", "lt")]
        else:
            facing = ("gt", "xa") if op in ("lt", "xb") else ("lt", "xb")
            pool = [e for e in entry if e["op"] in facing and (r is not IT or e["r"].get("t") != "num")]
        if len(pool) != 1:
            return None
        e = pool[0]
        if op == "back":
            op = "xb" if e["op"] in ("xa", "gt") else "xa"
        out.append({"l": dict(e["l"]) if l is IT else l, "op": op, "r": dict(e["r"]) if r is IT else r, **({"soft": True} if c.get("soft") else {})})
    return out
