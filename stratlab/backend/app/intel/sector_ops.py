"""Each sector's own operating measures, as the companies state them (m53, R53: the owner's review of the live R52 decks, "new sectors need
operating metrics where source data supports them, never fabricated: Airlines PLF/ASK/RPK/yield; Hospitals occupancy, ARPOB, beds; Cement
capacity/utilisation/volumes/realisation; Renewables installed MW/generation/CUF; Payments TPV/transactions/take rate").

A sector profile (PROFILES) says which companies a set of measures fits: by the way of earning of the company's layer (theme_check.MODELS'
families) and the words of its official industry and of what it does (an airline, a hospital, a cement maker, a power producer, a payments
company). Each measure's definition, period, source and limitation are metric_registry's (group = the profile); how it is found is RULES'.

Where the figures come from, nothing read for them alone:
- the passages of the companies' own documents the filings index already holds (doc_store: Indian investor presentations, US earnings
  releases), one search a profile while a theme's dive is built (passages_reader), at most PASSAGES rows;
- the business updates already read and stored (biz_updates), for the companies whose layer the profile fits, at the deck (the plan's own
  gate: the deck has them only where the plan gives business updates).

Each figure is taken only as stated: the number right after its label (a period's own column where the table names it), in a unit the rule
knows, within a plausible range, never a figure of a plan, a target, a pipeline or an industry; a size (beds, capacity, volume) is the largest
stated for the latest period (a company's total, never one region's), a share (occupancy, load factor) the one beside that total, else the one
figure every passage agrees on. A passage two companies filed word for word (a group's document filed by each listed company) counts only for
the parent among them, else for neither. A measure no company states has no column (no "n/a" pages)."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from typing import NamedTuple

from . import metric_registry as registry

VERSION = 1
PASSAGES = 900                  # passages one profile's search reads at most (each at most doc_index.CHUNK_CHARS)
DOC_DAYS = 200                  # documents filed this recently are read (the latest quarter's, and the one before)
LAG_DAYS = 100                  # a document's own quarter: the latest quarter end at most this many days before it was filed
KINDS = {"IN": ("presentation",), "US": ("earnings_release",)}
SOURCE_WORD = {"presentation": "Investor presentation filed with the exchange", "earnings_release": "Earnings release filed with the SEC",
               "transcript": "Call transcript filed with the exchange", "annual_report": "Annual report filed with the SEC"}


class Profile(NamedTuple):
    id: str
    one: str                    # "airline"
    many: str                   # "airlines"
    models: frozenset           # layer model families it fits (theme_check.MODELS)
    words: str                  # words of a company's industry or work that make it one
    not_words: str              # ...and words that rule it out
    query: str                  # the filings index search (websearch syntax) that finds the passages


PROFILES = (
    Profile("airline", "airline", "airlines", frozenset({"transport", "consumer_services"}),
            r"\bairlines?\b|air transportation,? scheduled|scheduled (?:passenger )?air|passenger aviation|\bair carriers?\b",
            r"airport|air freight|cargo airline|aircraft (?:leasing|parts|maker|manufactur)|aerospace",
            '"load factor" or ASK or ASKs or RPK or RPKs or ASMs or RPMs or "seat miles" or "seat kilometres" or "passenger miles" or yield'),
    Profile("hospital", "hospital operator", "hospital operators", frozenset({"care"}),
            r"\bhospitals?\b|medical (?:&|and) surgical hospital|multi-?specialty|super-?specialty",
            r"hospitality|hospital (?:beds? |furniture|supplies|equipment)|medical (?:devices?|equipment|instruments|supplies)|diagnostic",
            'beds or occupancy or ARPOB'),
    Profile("cement", "cement maker", "cement makers", frozenset({"making", "resources", "components"}),
            r"\bcement\b", r"cement (?:machinery|equipment|plant equipment)|refractor",
            'MTPA or "capacity utilisation" or "capacity utilization" or volume or volumes or realisation or realization'),
    Profile("power", "power producer", "power producers", frozenset({"generation", "power_trading", "utility"}),
            r"power generation|electric services|integrated power|renewable energy|solar power|wind power|hydro ?power|hydro ?electric|"
            r"cogeneration|independent power|thermal power",
            r"equipment|modules?\b|cells?\b|turbines? mak|cables?|transformers?|inverters?",
            'MW or GW or megawatts or gigawatts or CUF or PLF or "load factor" or generation or "units generated" or "energy sold"'),
    Profile("payments", "payments company", "payments companies", frozenset({"payments"}),
            r"payment (?:processing|network|gateway|solutions|services)|card networks?|digital payments|transaction processing|"
            r"merchant acquir",
            r"payment (?:of|for) (?:dividend|interest)",
            '"payment volume" or "payments volume" or TPV or "dollar volume" or GMV or transactions or "take rate"'),
)
BY_PROFILE = {p.id: p for p in PROFILES}


class Rule(NamedTuple):
    label: str                  # the measure's label in a document (regex, case aside)
    kind: str                   # "pct" a share in %; "num" a count or price; "amt" money in the theme's unit
    units: tuple = ()           # ((unit regex, multiplier to the measure's unit), ...): the number's own unit, or its label's "(...)"
    default: float | None = 1.0  # multiplier when no unit is stated (None: a unit must be stated)
    lo: float = 0.0             # plausible range, in the measure's unit
    hi: float = 1e12
    size: bool = False          # a size: the company's total is the largest stated for the period
    flow: bool = False          # a quarter's flow (a quarter's column first), else a level at a date
    anchor: str | None = None   # a share: read beside this size's total
    before: str = ""            # a "number unit label" form ("113.5 MTPA cement capacity"), with the number as group 1 and the unit as group 2
    biz: str = ""               # a business update's measure name that is this measure
    biz_not: str = ""


_MILLIONS = ((r"\bbn\b|billions?", 1000.0), (r"\bmn\b|millions?|\bmio\b", 1.0))
_BILLIONS = ((r"\bbn\b|billions?", 1.0), (r"\bmn\b|millions?", 0.001), (r"\bcrores?\b|\bcr\b", 0.01), (r"\blakhs?\b", 0.0001))
_MW = ((r"\bGW\b|gigawatts?", 1000.0), (r"\bMW\b|megawatts?", 1.0))
_GWH = ((r"\bTWh\b|\bBUs?\b|billion units", 1000.0), (r"\bGWh\b|\bMUs?\b|million units", 1.0), (r"\bMWh\b", 0.001))
_PLAN = re.compile(r"target|planned|plan(?:s|ning)? to|post[- ]expansion|projected|pipeline|\bby (?:fy|20\d\d|end)|to be (?:commissioned|added|operational)|"
                   r"expected|under[- ]construction|under[- ]development|addition|added|adding|guidance|outlook|\baim|backlog|locked[- ]in|"
                   r"potential|\bup ?to\b|at the time of acquisition|contracted|awarded|signed|ppa|ppas|\bto add\b|\badd\b", re.I)
_SCOPE = re.compile(r"industry|market|country|nation|all[- ]india|india['’]s|sector|peers?|clinker|grinding|storage|bess|battery|transmission|"
                    r"manufacturing|module|cell|production line|same[- ]facility|same[- ]store|established units?|mature|emerging|new units?", re.I)
RULES = {
    "plf": Rule(r"passenger load factor|(?<!plant )(?<!plant)\bload factor\b|\bPLF\b(?! ?\()", "pct", lo=30, hi=100, anchor="ask|asm"),
    "ask": Rule(r"\bASKs?\b|available seat (?:kilometres|kilometers|kms?)\b", "num", _BILLIONS, None, 0.05, 2000, size=True, flow=True),
    "rpk": Rule(r"\bRPKs?\b|revenue passenger (?:kilometres|kilometers|kms?)\b", "num", _BILLIONS, None, 0.05, 2000, size=True, flow=True),
    "asm": Rule(r"\bASMs?\b(?! per)|available seat miles\b(?! per)", "num", _MILLIONS, None, 100, 1e6, size=True, flow=True),
    "rpm": Rule(r"\bRPMs?\b(?! per)|revenue passenger miles\b(?! per)", "num", _MILLIONS, None, 100, 1e6, size=True, flow=True),
    "yield_km": Rule(r"(?:passenger )?yield(?: per RPK)?", "num", ((r"₹|\brs\.?|\binr\b", 1.0),), None, 1, 30, anchor="ask"),
    "yield_mile": Rule(r"(?:average |passenger (?:mile |revenue )?)?yield(?: per RPM)?", "num", ((r"\bcents?\b|¢", 1.0),), None, 3, 80,
                       anchor="asm"),
    "beds_op": Rule(r"(?:weighted average |average )?beds in (?:operation|service)\b|operat(?:ing|ional) (?:census )?beds\b", "num", lo=10, hi=500000,
                    size=True),
    "beds_cap": Rule(r"(?:licensed|installed|capacity) beds\b|bed capacity\b", "num", lo=10, hi=500000, size=True,
                     before=r"(\d[\d,]*)()\s+(?:capacity|installed|licensed) beds\b"),
    "occupancy": Rule(r"(?:bed )?occupancy(?: rate)?", "pct", lo=10, hi=100, anchor="beds_op|beds_cap"),
    "arpob": Rule(r"\bARPOB\b|average revenue per occupied bed(?: per day)?", "num", ((r"₹|\brs\.?|\binr\b", 1.0),), 1.0, 3000, 1e6,
                  anchor="beds_op|beds_cap"),
    "cem_capacity": Rule(r"(?:installed |current |total |cement )*capacity", "num", ((r"\bMTPA\b|million tonnes? per annum|mn ?tpa", 1.0),), None,
                         0.3, 600, size=True,
                         before=r"(\d[\d,]*(?:\.\d+)?)\s*(MTPA|million tonnes? per annum|mn ?tpa)\s+(?:of\s+)?(?:current |installed |total |existing )*"
                                r"(?:cement )?capacity"),
    "cem_util": Rule(r"capacity utili[sz]ation|utili[sz]ation", "pct", lo=20, hi=130, anchor="cem_capacity|cem_volume"),
    "cem_volume": Rule(r"(?:cement |sales |despatch |dispatch |total )*(?:sales )?volumes?", "num",
                       ((r"\bmn ?t\b|\bmnt\b|million tonnes?|\bmmt\b|\bmt\b", 1.0),), None, 0.05, 80, size=True, flow=True),
    "cem_realisation": Rule(r"(?:net sales |blended |cement )?reali[sz]ations?|\bNSR\b", "num",
                            ((r"(?:₹|rs\.?|inr)\s*/\s*(?:t|tonne|ton|mt)\b|per (?:tonne|ton|mt)\b|\bpmt\b", 1.0),), None, 1500, 20000),
    "mw_installed": Rule(r"(?:total |gross |net )?(?:installed|operational|operating|commissioned|in[- ]operation)(?: portfolio| generation| power|"
                         r" renewable| renewable energy| re| generating)* capacity", "num", _MW, None, 1, 500000, size=True,
                         before=r"(\d[\d,]*(?:\.\d+)?)\s*(GW|MW)\s+(?:of\s+)?(?:operational|operating|installed|commissioned)\b",
                         biz=r"(?:installed|operational|operating|commissioned)\b.*capacity|capacity.*\b(?:installed|in operation)",
                         biz_not=r"add|under|pipeline|locked|plan|target|storage|bess|agreement|supply|contract|cell|module|production|award"),
    "generation": Rule(r"(?:gross |net |total )?(?:power |energy |electricity )?generation|units generated|energy sold", "num", _GWH, None, 1, 2e6,
                       size=True, flow=True, biz=r"generation|units generated|energy sold", biz_not=r"capacity|add|plan|target|annual energy"),
    "cuf": Rule(r"\bCUF\b|capacity utili[sz]ation factor|plant load factor|\bPLF\b", "pct", lo=5, hi=100, anchor="mw_installed"),
    "tpv": Rule(r"total payment volume|\bTPV\b|gross dollar volume|\bGDV\b|payments? volume|payments? GMV|\bGMV\b", "amt", (), None, 1, 1e12,
                size=True, flow=True),
    "txn": Rule(r"(?:payment|processed|switched) transactions|transactions processed", "num", _BILLIONS, None, 0.001, 2000, size=True, flow=True),
    "take_rate": Rule(r"(?:transaction )?take rate", "pct", lo=0.01, hi=10, anchor="tpv"),
}
MEASURES = {p.id: tuple(m.id for m in registry.METRICS if m.group == p.id) for p in PROFILES}
NOTE_CHECKED = {"IN": "the companies' investor presentations held in the app's filings index and, where the plan includes them, their business updates",
                "US": "the companies' earnings releases held in the app's filings index"}


# ---------- whom a profile fits ----------
def _text(row: dict) -> str:
    return " ".join(str(x) for x in [row.get("official_industry"), row.get("map_industry"), row.get("sector"), row.get("map_what"), row.get("name"),
                                     *(row.get("industry") or [])] if x)


def profile_of(row: dict, model_family: str | None = None, layer: str = "") -> str | None:
    """The sector profile a company's operating measures come from: its words (official industry, what it does) or its layer's name name the
    sector, none of its own words rules it out, and its layer's way of earning (when the layer has one) is one the profile fits. None for every
    other company (a bank, a maker of hospital equipment, an airport)."""
    text = _text(row)
    for p in PROFILES:
        said = re.search(p.words, text, re.I) or re.search(p.words, str(layer or ""), re.I)
        if said and not re.search(p.not_words, text, re.I) and (not model_family or model_family in p.models):
            return p.id
    return None


# ---------- periods ----------
_MON = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
PERIOD = re.compile(
    r"\b(?P<fy>[QH][1-4]|9M|H[12])\s?['’]?\s?FY\s?['’]?(?P<fyy>\d{2}(?:\d{2})?)\b"
    r"|\b(?P<qn>[1-4])Q\s?['’]?(?P<qy>(?:20)?\d{2})\b"
    r"|\bQ(?P<q2>[1-4])\s?['’]?(?P<q2y>20\d{2}|\d{2})\b(?!\s?FY)"
    r"|(?P<fisc>fiscal\s+)?\b(?P<ord>first|second|third|fourth|1st|2nd|3rd|4th)[- ]quarter\b[^.]{0,60}?\b(?P<ordy>20\d{2})\b"
    r"|\b(?P<ordy2>20\d{2})\s+(?P<ord2>first|second|third|fourth)[- ]quarter\b"
    r"|\b(?P<span>three|six|nine|twelve) months ended\b[^.]{0,60}?" + _MONTH.replace("(", "(?P<smon>", 1) + r"\s\d{1,2},?[^.]{0,30}?\b(?P<sy>20\d{2})\b"
    r"|\bquarter ended\s+" + _MONTH.replace("(", "(?P<qmon>", 1) + r"\s\d{1,2},?\s+(?P<qey>20\d{2})\b"
    r"|\b" + _MONTH.replace("(", "(?P<mon>", 1) + r"\s?['’]\s?(?P<my>\d{2})\b(?:\s?Q\b)?"
    r"|\b(?P<dm>\d{2})/(?P<dd>\d{2})/(?P<dy>\d{2}(?:\d{2})?)\b", re.I)


def _month_end(y: int, m: int) -> date:
    return date(y, m, 1)


def period_of(m: re.Match) -> tuple[date, str] | None:
    """A period token as (its last month, its span: "Q" a quarter, "H" six months, "9M", "Y" a year, "D" a date); None for a fiscal quarter
    of a company whose fiscal year isn't the calendar's or the Indian one (said by its filing's date instead)."""
    g = m.groupdict()
    if g.get("fy"):
        y = int(g["fyy"][-2:]) + 2000
        k = g["fy"].upper()
        if k in ("Q1", "Q2", "Q3", "Q4"):
            return _month_end(y if k == "Q4" else y - 1, {"Q1": 6, "Q2": 9, "Q3": 12, "Q4": 3}[k]), "Q"
        if k in ("H1", "H2"):
            return _month_end(y if k == "H2" else y - 1, 9 if k == "H1" else 3), "H"
        return _month_end(y - 1, 12), "9M"
    if g.get("qn") or g.get("q2"):
        q = int(g.get("qn") or g["q2"])
        y = int((g.get("qy") or g["q2y"])[-2:]) + 2000
        return _month_end(y, 3 * q), "Q"
    if g.get("ord") or g.get("ord2"):
        if g.get("fisc"):
            return None
        return _month_end(int(g.get("ordy") or g["ordy2"]), 3 * _ORD[(g.get("ord") or g["ord2"]).lower()]), "Q"
    if g.get("span"):
        return _month_end(int(g["sy"]), _MON[g["smon"][:3].lower()]), {"three": "Q", "six": "H", "nine": "9M", "twelve": "Y"}[g["span"].lower()]
    if g.get("qmon"):
        return _month_end(int(g["qey"]), _MON[g["qmon"][:3].lower()]), "Q"
    if g.get("mon"):
        return _month_end(2000 + int(g["my"]), _MON[g["mon"][:3].lower()]), "Q"
    if g.get("dm"):
        mo, y = int(g["dm"]), int(g["dy"][-2:]) + 2000
        return (_month_end(y, mo), "D") if 1 <= mo <= 12 else None
    return None


def doc_quarter(filed: str) -> date | None:
    """The quarter a document filed on `filed` reports: the latest quarter end at most LAG_DAYS before it."""
    try:
        d = date.fromisoformat(str(filed)[:10])
    except ValueError:
        return None
    q = date(d.year, ((d.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)       # the last quarter end before this month
    q = date(q.year, q.month, 1)
    if (d - date(q.year, q.month, 28)).days < 0:
        return None
    return q if (d - date(q.year, q.month, 28)).days <= LAG_DAYS else None


def period_words(end: date, span: str) -> str:
    mon = end.strftime("%b %Y")
    return {"Q": f"Quarter to {mon}", "H": f"Six months to {mon}", "9M": f"Nine months to {mon}", "Y": f"Year to {mon}"}.get(span, mon)


# ---------- reading a passage ----------
_NUM = r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_NUM_RX = re.compile(_NUM)
_CUR = r"(?:\$|US\$|USD|₹|Rs\.?|INR)"
_FILL = re.compile(r"\s*(?:\((?P<par>[^()\d]{1,32}|[a-z]|\d)\)|(?P<pcol>" + PERIOD.pattern.replace("(?P<", "(?P<f_") + r")\s?:|"
                   r"(?P<uw>mn ?t|mnt|mtpa|mw|gw|gwh|mus?|bus?|mn\.?|millions?|billions?|crores?|cents|(?:rs\.?|₹|inr) ?/ ?(?:t|tonne|km))(?![\w])|"
                   r"(?P<word>[:\-–—*^~#†]+|\d(?=\s)|approx(?:imately|\.)?|at (?:the )?end of (?:the )?period|at period end|"
                   r"consolidated|total|overall|system|portfolio|pan[- ]india|rate|ratio|%))", re.I)
_VALUE = re.compile(r"\s*(?P<cur>" + _CUR + r")?\s?(?P<n>" + _NUM[1:-1] + r")(?![\d,])\s?(?P<pct>%)?"
                    r"(?P<unit>\s?[A-Za-z₹$¢][A-Za-z₹$¢/.]*(?:\s?/\s?[A-Za-z]+)?(?![\w'’])(?:\s(?:crores?|cr|per annum|tonnes?|units|per (?:tonne|ton|mt)))?)?",
                    re.I)
_PROSE = re.compile(r"\b(?:increased|decreased|grew|growth|rose|fell|declined|up|down)\b[^.;]{0,60}?\bto\s+(?P<v>" + _CUR + r"?\s?" + _NUM +
                    r"(?:\s?(?:trillion|billion|million|crore|lakh crore|bn|mn|cr))*)|\b(?:was|were|stood at|totall?ed|reached|of)\s+(?P<w>" + _CUR +
                    r"\s?" + _NUM + r"(?:\s?(?:trillion|billion|million|crore|lakh crore|bn|mn|cr))*)", re.I)
_MONEY_UNIT = {"US": ((r"trillion", 1e6), (r"billion|\bbn\b", 1e3), (r"million|\bmn\b", 1.0)),
               "IN": ((r"lakh crore", 1e5), (r"crore|\bcr\b", 1.0), (r"billion|\bbn\b", 100.0), (r"million|\bmn\b", 0.1))}


def tidy(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')).strip()


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _mult(rule: Rule, unit_text: str) -> float | None:
    for rx, k in rule.units:
        if re.search(rx, unit_text or "", re.I):
            return k
    return None


def _money(region: str, text: str) -> float | None:
    """A payment volume in the theme's unit (USD million, ₹ crore), only in the theme's own currency."""
    cur = re.match(r"\s*(" + _CUR + r")", text or "", re.I)
    us = bool(cur and cur.group(1).upper().replace(".", "") in ("$", "US$", "USD"))
    if cur is None or us != (region == "US"):
        return None
    n = _NUM_RX.search(text)
    v = _num(n.group(1)) if n else None
    if v is None:
        return None
    rest = text[n.end():]
    for rx, k in _MONEY_UNIT[region]:
        if re.match(r"\s?(?:" + rx + r")", rest, re.I):
            return v * k
    return None


def _header(text: str, upto: int) -> list[tuple[date, str]]:
    """The run of period tokens nearest before `upto` (the column heads of the table a row is in), in order."""
    runs, last = [], None
    for m in PERIOD.finditer(text, 0, upto):
        p = period_of(m)
        if p is None:
            continue
        if last is None or m.start() - last > 40:
            runs.append([])
        runs[-1].append(p)
        last = m.end()
    return runs[-1] if runs else []


class Found(NamedTuple):
    value: float
    end: date | None
    span: str
    pos: int
    quote: str
    sure: bool = True           # the period is the figure's own (its column's, its colon's); else the document's quarter


def _raw(g: re.Match) -> str:
    return (g.group("cur") or "") + g.group("n") + (g.group("pct") or "") + (g.group("unit") or "")


def _latest_of(t: str, rule: Rule, region: str, got: re.Match, unit_par: str) -> tuple | None:
    """Numbers followed by their own periods ("16.6 17.1 16.5 Q2FY'26 Q1FY'27 Q2FY'27"): (the latest period's value, its period); None when
    the numbers aren't followed by as many periods."""
    nums, k = [got], got.end()
    while len(nums) < 5:
        nx = _VALUE.match(t, k)
        if not nx or not nx.group("n") or bool(nx.group("pct")) != (rule.kind == "pct") or nx.group("unit"):
            break
        nums.append(nx)
        k = nx.end()
    if len(nums) < 2:
        return None
    pers = []
    while len(pers) < len(nums):
        pm = PERIOD.match(t, k + len(re.match(r"\s*", t[k:]).group(0)))
        p = period_of(pm) if pm else None
        if p is None:
            break
        pers.append(p)
        k = pm.end()
    if len(pers) != len(nums):
        return None
    i = max(range(len(pers)), key=lambda x: (pers[x][0], pers[x][1] == "Q"))
    val = _value_of(rule, region, _raw(nums[i]), unit_par, bool(nums[i].group("pct")))
    return (val, pers[i], nums[i].end()) if val is not None else None


def find(text: str, rule: Rule, region: str = "IN", filed: str = "") -> list[Found]:
    """Every figure of one measure a passage states: the number right after its label (fillers aside: a unit in brackets, a footnote mark,
    a period with a colon), in the rule's unit and range, with the period its column or the passage's table heads give (the document's own
    quarter when neither does); never one of a plan, a target, an industry or a part (a region, a segment's column)."""
    t = tidy(text)
    out: list[Found] = []
    dq = doc_quarter(filed)
    own = (dq, "Q") if dq else None
    label = re.compile(rf"(?<![\w-])(?:{rule.label})(?:\d\b)?", re.I)
    for m in label.finditer(t):
        if _PLAN.search(t[max(0, m.start() - 40):m.start()]) or _SCOPE.search(t[max(0, m.start() - 25):m.end()]) or re.match(r"\s+per\b", t[m.end():]):
            continue
        j, unit_par, per = m.end(), "", None
        for _ in range(6):
            f = _FILL.match(t, j)
            if not f or f.end() == j or f.end() - m.end() > 70:
                break
            unit_par += " " + (f.group("par") or f.group("uw") or ("%" if (f.group("word") or "").strip() == "%" else ""))
            if f.group("pcol"):
                pm = PERIOD.match(t, f.start("pcol"))
                per = (period_of(pm) if pm else None) or per
            j = f.end()
        got = _VALUE.match(t, j)
        if got is None or (got.start("n") > 0 and t[got.start("n") - 1] in "+-−"):
            if rule.kind not in ("amt", "num") or got is not None:
                continue
            pr = _PROSE.search(t, m.end(), min(len(t), m.end() + 110))
            if pr is None:
                continue
            val = _value_of(rule, region, pr.group("v") or pr.group("w"), unit_par, False)
            if val is not None and (per or own):
                p = per or own
                out.append(Found(val, p[0], p[1], m.start(), t[m.start():pr.end()][:240], per is not None))
            continue
        val = _value_of(rule, region, _raw(got), unit_par, bool(got.group("pct")))
        if val is None:
            continue
        p, stop, sure = per, got.end(), True
        if p is None:
            latest = _latest_of(t, rule, region, got, unit_par)
            if latest:
                val, p, stop = latest
            else:
                head = _header(t, m.start())
                if head and head.count(head[0]) > 1:
                    continue            # the same period twice in the heads: columns of segments side by side, not the company's own
                if head and len(head) >= 2 and head[0][0] < max(h[0] for h in head):
                    continue            # heads oldest first: which number is the latest's isn't certain
                if not head and _VALUE.match(t, got.end()) and (_VALUE.match(t, got.end()).group("n") or "") and rule.size:
                    continue            # a row of several numbers with no heads (a table cut at a passage's start): whose column isn't known
                p, sure = (head[0], True) if head else (own, False)
        if p is None or (dq is not None and p[0] > dq + timedelta(days=95)):
            continue                    # no period, or one after the document's own quarter (a plan, not a figure)
        out.append(Found(val, p[0], p[1], m.start(), t[m.start():stop][:240], sure))
    if rule.before:
        for m in re.finditer(rule.before, t, re.I):
            if _PLAN.search(t[max(0, m.start() - 40):m.start()]) or t[max(0, m.start() - 1):m.start()] in "+":
                continue
            val = _value_of(rule, region, m.group(1) + " " + (m.group(2) or ""), "", False)
            head = _header(t, m.start())
            p = head[0] if head and head.count(head[0]) == 1 else own
            if val is not None and p is not None and not (dq is not None and p[0] > dq + timedelta(days=95)):
                out.append(Found(val, p[0], p[1], m.start(), m.group(0)[:240], p is not own))
    return out


def _value_of(rule: Rule, region: str, raw: str, unit_par: str, pct: bool) -> float | None:
    """A stated number in the measure's unit, or None when its unit or range doesn't fit the measure."""
    if rule.kind == "pct":
        if not pct and "%" not in unit_par:
            return None
        n = _NUM_RX.search(raw)
        v = _num(n.group(1)) if n else None
    elif rule.kind == "amt":
        v = _money(region, raw)
    else:
        if pct:
            return None
        n = _NUM_RX.search(raw)
        v = _num(n.group(1)) if n else None
        if v is None:
            return None
        if rule.units:
            k = _mult(rule, raw[n.end():]) or _mult(rule, unit_par)
            if k is None and re.match(r"\s?(?:" + _CUR + r")", raw, re.I):
                k = _mult(rule, raw[:n.start()])
            if k is None:
                if rule.default is None:
                    return None
                k = rule.default
            v *= k
        elif re.match(r"\s?[A-Za-z]{2,}", raw[n.end():]) and not re.match(r"\s?(?:beds?|nos?\.?)\b", raw[n.end():], re.I):
            return None             # a count stated in some other unit
    if v is None or not rule.lo <= v <= rule.hi:
        return None
    return round(v, 4)


# ---------- a company's figures from its documents ----------
def pick(rule: Rule, found: list[tuple[Found, int, bool]]) -> tuple[Found, int] | None:
    """One figure from a document's (figure, passage index, standalone passage) list: the latest period's (a flow's quarter first, figures
    whose own column names the period before those dated by the document); a size's largest (the company's total, never a region's or a
    standalone part's when a consolidated one is stated) unless they are a flow's figures dated only by the document and differ (a quarter's
    or the year to date's isn't known); else the one value they all agree on."""
    if not found:
        return None
    if any(not st for _, _, st in found):
        found = [x for x in found if not x[2]]
    dated = [x for x in found if x[0].end]
    if not dated:
        return None
    end = max(x[0].end for x in dated)
    at = [x for x in dated if x[0].end == end]
    if any(x[0].sure for x in at):
        at = [x for x in at if x[0].sure]
    if rule.flow and any(x[0].span == "Q" for x in at):
        at = [x for x in at if x[0].span == "Q"]
    vals = {round(x[0].value, 4) for x in at}
    if rule.size and not (rule.flow and len(vals) > 1 and not at[0][0].sure):
        best = max(at, key=lambda x: x[0].value)
        return best[0], best[1]
    if len(vals) == 1:
        return at[0][0], at[0][1]
    return None


def document_figures(passages: list[dict], region: str, measures: tuple) -> dict:
    """{measure: {"v", "period", "as_of", "source", "quote", "page", "url"}} from one document's passages (in page order): each size by pick();
    each share the first stated after its size's total, in the passage that states that total, else the one value every passage agrees on."""
    texts = [tidy(p.get("body")) for p in passages]
    stand = [bool(re.search(r"\bstandalone\b", t, re.I)) for t in texts]
    filed = str(passages[0].get("filed_at") or "")[:10] if passages else ""
    found = {k: [(f, i, stand[i]) for i, t in enumerate(texts) for f in find(t, RULES[k], region, filed)] for k in measures if k in RULES}
    for a in {a for k in measures if k in RULES and RULES[k].anchor for a in RULES[k].anchor.split("|")} - set(found):
        if region in registry.BY_ID[a].regions:
            found[a] = [(f, i, stand[i]) for i, t in enumerate(texts) for f in find(t, RULES[a], region, filed)]
    chosen = {}
    for k in found:
        if not RULES[k].anchor:
            got = pick(RULES[k], found[k])
            if got:
                chosen[k] = got
    for k in measures:
        rule = RULES.get(k)
        if rule is None or not rule.anchor:
            continue
        got = None
        for a in rule.anchor.split("|"):
            if a not in chosen:
                continue
            fa = chosen[a][0]
            for f0, i, _ in found[a]:
                if abs(f0.value - fa.value) > 1e-6 or f0.end != fa.end:
                    continue
                after = sorted((f for f, j, _ in found.get(k) or [] if j == i and 0 <= f.pos - f0.pos <= 400), key=lambda f: f.pos)
                if after:
                    got = (after[0], i)
                    break
            if got:
                break
        got = got or pick(rule._replace(size=False), found.get(k) or [])
        if got:
            chosen[k] = got
    out = {}
    for k, (f, i) in chosen.items():
        if k not in measures:
            continue
        p, rule = passages[i], RULES[k]
        span = f.span if (rule.flow or not rule.size) and f.span in ("Q", "H", "9M", "Y") else "D"
        out[k] = {"v": f.value, "period": period_words(f.end, span), "as_of": f.end.strftime("%b %Y"),
                  "source": SOURCE_WORD.get(p.get("kind"), "Document") + (f" on {filed}" if filed else "") + (f", page {p['page']}" if p.get("page") else ""),
                  "quote": f.quote, "page": p.get("page"), "url": p.get("link") or p.get("url")}
    return out


def company_figures(docs: list[list[dict]], region: str, measures: tuple) -> dict:
    """A company's figures from its documents, newest first: each measure from the newest document that states it."""
    out: dict = {}
    for d in docs:
        for k, fig in document_figures(d, region, tuple(m for m in measures if m not in out)).items():
            out.setdefault(k, fig)
    return out


def _digest(text: str) -> str:
    return hashlib.sha1(tidy(text).lower().encode("utf-8", "replace")).hexdigest()


def read_profile(pid: str, symbols: list[str], region: str, passages, parents: dict | None = None) -> tuple[dict, list[dict]]:
    """({symbol: {measure: figure}}, held) for one profile's companies from the passages `passages(symbols, query)` gives (each {"symbol",
    "doc_id", "n", "page", "kind", "filed_at", "body", "link"}). A passage that two of them filed word for word counts only for the parent of the
    others (`parents`: symbol -> its listed parent), else for none of them, and is said in `held`."""
    if not symbols:
        return {}, []
    try:
        rows = passages(list(symbols), BY_PROFILE[pid].query) or []
    except Exception as e:                  # the index unreachable: no figures from it, never a failed dive
        print("sector ops: passages not read:", pid, type(e).__name__, str(e)[:100])
        return {}, []
    parents = parents or {}
    owners: dict[str, set] = {}
    for r in rows:
        owners.setdefault(_digest(r.get("body") or ""), set()).add(r["symbol"])
    held: dict[str, set] = {}
    by_doc: dict = {}
    for r in rows:
        who = owners[_digest(r.get("body") or "")]
        if len(who) > 1 and not all(parents.get(o) == r["symbol"] for o in who - {r["symbol"]}):
            held.setdefault(r["symbol"], set()).update(who - {r["symbol"]})
            continue
        by_doc.setdefault(r["symbol"], {}).setdefault((str(r.get("filed_at") or ""), r.get("doc_id")), []).append(r)
    figs = {}
    for sym, docs in by_doc.items():
        ordered = [sorted(v, key=lambda x: (x.get("page") or 0, x.get("n") or 0)) for _, v in sorted(docs.items(), key=lambda kv: kv[0], reverse=True)]
        got = company_figures(ordered, region, tuple(k for k in MEASURES[pid] if region in registry.BY_ID[k].regions))
        if got:
            figs[sym] = got
    return figs, [{"symbol": s, "with": sorted(w)} for s, w in sorted(held.items()) if s not in figs]


def section(rows: list[dict], region: str, layer_of: dict, model_of: dict, passages, parents: dict | None = None, layer_names: dict | None = None) -> dict:
    """The dive's operating measures by sector profile: {"profiles": {id: {"fit": [{"symbol", "name", "layer"}], "figs": {symbol: {measure:
    figure}}, "held": [...]}}}, only profiles some company of the theme fits; {} when none does."""
    out = {}
    for p in PROFILES:
        fit = [r for r in rows if profile_of(r, model_of.get(r["symbol"]), (layer_names or {}).get(r["symbol"], "")) == p.id]
        if not fit:
            continue
        figs, held = read_profile(p.id, [r["symbol"] for r in fit], region, passages, parents)
        out[p.id] = {"fit": [{"symbol": r["symbol"], "name": r.get("name") or r["symbol"], "layer": layer_of.get(r["symbol"]),
                              "model": model_of.get(r["symbol"])} for r in fit], "figs": figs, "held": held}
    return {"profiles": out, "version": VERSION} if out else {}


def passages_reader(region: str, store=None, today: date | None = None):
    """(symbols, query) -> the passages of the companies' latest documents that match the profile's search, from the filings index; [] while
    the index isn't set up."""
    def read(symbols, q):
        from .. import doc_store
        s = store or doc_store.store()
        if s is None or not hasattr(s, "passages"):
            return []
        since = ((today or date.today()) - timedelta(days=DOC_DAYS)).isoformat()
        return s.passages(q, region, list(symbols), list(KINDS[region]), since, PASSAGES)
    return read


# ---------- business updates (the deck's, where the plan includes them) ----------
def from_business(business: dict | None, pid: str, region: str) -> dict:
    """{symbol: {measure: figure}} from the business updates the deck has (its "business" rows' measures, as biz_updates read and checked
    them), for the measures whose rule names a business update's measure, in their unit."""
    out: dict = {}
    if region != "IN":                  # business updates are Indian companies' exchange filings
        return out
    for grp in ((business or {}).get("layers") or []) + ((business or {}).get("subs") or []):
        for r in grp.get("rows") or []:
            for m in r.get("measures") or []:
                name = f"{m.get('metric') or ''} {m.get('segment') or ''}"
                for k in MEASURES.get(pid, ()):
                    rule = RULES.get(k)
                    if not rule or not rule.biz or region not in registry.BY_ID[k].regions or m.get("own") is False:
                        continue
                    if not re.search(rule.biz, name, re.I) or (rule.biz_not and re.search(rule.biz_not, name, re.I)) or m.get("segment"):
                        continue
                    mult = _mult(rule, str(m.get("unit") or ""))
                    v = m.get("value")
                    if mult is None or v is None or not m.get("period") or not rule.lo <= v * mult <= rule.hi:
                        continue
                    try:
                        end = datetime.strptime(str(m["period"])[:7], "%Y-%m").date()
                    except ValueError:
                        continue
                    have = out.setdefault(r["symbol"], {}).get(k)
                    if have and have["_end"] >= end:
                        continue
                    out[r["symbol"]][k] = {"v": round(v * mult, 4), "_end": end, "as_of": end.strftime("%b %Y"),
                                           "period": period_words(end, "Q" if rule.flow and m.get("span") == "quarter" else "D"),
                                           "source": "Business update filed with the exchange" + (f" on {m['filed']}" if m.get("filed") else ""),
                                           "quote": m.get("quote") or "", "page": m.get("page"), "url": m.get("url")}
    return out


def family(pid: str, prof: dict, region: str, stat, business: dict | None = None) -> dict | None:
    """One profile's page: each company's measures in their state (metric_registry), the measures some company states only (no column of
    "n/a"), the median of each share over the companies that state it with "N of M" those it applies to (sizes never: companies of different
    sizes), where each is from, and the measures none of them states. None when no company states any."""
    figs = {s: dict(f) for s, f in (prof.get("figs") or {}).items()}
    for s, f in from_business(business, pid, region).items():
        for k, fig in f.items():
            have = figs.setdefault(s, {}).get(k)
            if have is None or (registry.period_end(have.get("period")) or date.min) <= fig["_end"]:
                figs[s][k] = {x: y for x, y in fig.items() if x != "_end"}
    fit = [c for c in prof.get("fit") or []]
    names = {c["symbol"]: c for c in fit}
    tag = f"ops:{pid}"
    measures = [k for k in MEASURES[pid] if region in registry.BY_ID[k].regions]
    keys = [k for k in measures if any(k in figs.get(c["symbol"], {}) for c in fit)]
    if not keys:
        return None
    rows, tagsets = [], []
    for c in fit:
        f = figs.get(c["symbol"]) or {}
        if not any(k in f for k in keys):
            continue
        ends = [registry.period_end(f[k].get("period")) or registry.period_end(f[k].get("as_of")) for k in keys if k in f]
        as_of = max((e for e in ends if e), default=None)
        rows.append({"symbol": c["symbol"], "name": c["name"], "layer": c.get("layer"), "as_of": as_of.strftime("%b %Y") if as_of else None,
                     **{k: f[k]["v"] for k in keys if k in f},
                     "src": {k: {x: f[k][x] for x in ("period", "source", "quote", "page", "url") if f[k].get(x) not in (None, "")} for k in keys if k in f}})
        tagsets.append({tag})
    rest = [c for c in fit if c["symbol"] not in {r["symbol"] for r in rows}]
    sts = {k: registry.states(k, region, rows, tagsets) for k in keys}
    meds = {}
    for k in keys:
        if registry.BY_ID[k].headline:
            meds[k] = registry.coverage([r.get(k) for r in rows], sts[k], stat)
            meds[k]["of"] += len(rest)
    head = [k for k in keys if k in meds and registry.headline_ok(k, meds[k], True)]
    none = [registry.BY_ID[k].label for k in measures if k not in keys]
    held = [names[h["symbol"]]["name"] + " (the same document as " + ", ".join(names.get(w, {"name": w})["name"] for w in h["with"]) + ")"
            for h in prof.get("held") or [] if h["symbol"] in names]
    p = BY_PROFILE[pid]
    return {"keys": keys, "rows": rows, "n": len(rows), "of": len(fit), "pending": 0, "read": len(fit), "states": sts, "medians": meds,
            "headline": head, "extreme": [], "periods": sorted({x["period"] for r in rows for x in r["src"].values() if x.get("period")}),
            "checked": NOTE_CHECKED.get(region, NOTE_CHECKED["US"]), "profile": pid, "one": p.one, "many": p.many,
            "not_filed": "; ".join(x for x in [(", ".join(none) + ": stated in none of these companies' documents the app holds") if none else "",
                                               ("not taken: " + "; ".join(held)) if held else ""] if x)}
