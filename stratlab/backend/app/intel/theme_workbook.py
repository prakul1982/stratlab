"""A theme as an Excel workbook (GET /research/theme-dive/workbook): one sheet for each table the theme's page and deck show, worked out
from the same stored dive (theme_routes.dive_of), so a number in the workbook is the number on the page.

Sheets: Companies (each with its layer, market value and latest-year figures), Layer medians, Peers, Valuation, Operating figures (the
figures banks, insurers and US companies file, where the theme has them), What changed (theme_changes.py) and Sources and method (the
columns, the price and figure dates, how a median is built). Numbers are numbers with a format: percentages as Excel percentages, a
multiple with its "x", dates as dates, money in the theme's unit with Indian grouping (1,23,456) for rupees as the decks print it.
Nothing here reads a source or asks the AI."""
from datetime import date

from .. import xlsx_write
from ..xlsx_write import Num

PCT = "0.0%"
TIMES = '0.0"x"'
DAY = "d mmm yyyy"
USD = "#,##0"
PLAIN = "0.00"
MONEY_UNIT = {"IN": "₹ crore", "US": "$ million"}
CAUSE_WORDS = {"rules": "Re-checked under new placement rules", "map": "New map of the theme", "refresh": "Refresh",
               "figures": "Companies' figures updated"}
LAYER_WORDS = {"renamed": "Layer renamed", "split": "Layer split", "merged": "Layers merged", "added": "Layer added", "removed": "Layer removed"}


def _money_fmt(region: str) -> str:
    from ..deck import INDIAN_FORMAT            # the decks' own Indian grouping (DD-053)
    return INDIAN_FORMAT if region == "IN" else USD


def _n(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _pct(v):
    """A figure in percentage points (12.5) as Excel holds a percentage (0.125)."""
    x = _n(v)
    return None if x is None else round(x / 100, 6)


def _day(v):
    """An ISO day as Excel's date number (days since 30 Dec 1899), so it sorts and formats as a date."""
    try:
        d = date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None
    return (d - date(1899, 12, 30)).days


def _sheet(name: str, head: list[str], rows: list[list], fmts: dict[int, str]) -> tuple:
    return (name, [head] + rows, {0}, fmts)


def _in_figures(c: dict) -> str:
    from .theme_data import calc_of
    rec = calc_of(c)
    return "Yes" if rec["in"] else f"No: {rec['why']}" if rec.get("why") else "No"


def companies(dive: dict, region: str) -> tuple:
    unit, cap_unit = dive.get("unit") or MONEY_UNIT.get(region, ""), MONEY_UNIT.get(region, "")
    head = ["Company", "Symbol", "Layer", "In the layer's figures", f"Market value ({cap_unit})", "Year of the figures", f"Revenue ({unit})",
            "EBITDA margin", "Net margin", "ROCE", "ROE", "P/E", "P/B", "EV/EBITDA", "Revenue growth, 1 year", "Revenue growth, 3 years a year",
            "Debt to equity", "Price", "Price date"]
    rows, seen = [], set()
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            if c.get("symbol") in seen:
                continue
            seen.add(c.get("symbol"))
            rows.append([c.get("name"), c.get("symbol"), b.get("layer"), _in_figures(c), _n(c.get("cap")), c.get("year"), _n(c.get("revenue")),
                         _pct(c.get("ebitda")), _pct(c.get("net")), _pct(c.get("roce")), _pct(c.get("roe")), _n(c.get("pe")), _n(c.get("pb")),
                         _n(c.get("ev_ebitda")), _pct(c.get("sales_1y")), _pct(c.get("sales_3y")), _n(c.get("debt_equity")), _n(c.get("price")),
                         _day(c.get("price_at"))])
    m = _money_fmt(region)
    return _sheet("Companies", head, rows, {4: m, 6: m, 7: PCT, 8: PCT, 9: PCT, 10: PCT, 11: TIMES, 12: TIMES, 13: TIMES, 14: PCT, 15: PCT,
                                            16: PLAIN, 17: "#,##0.00", 18: DAY})


def _med(st):
    return (st or {}).get("median")


def layer_medians(dive: dict, region: str) -> tuple:
    unit = dive.get("unit") or MONEY_UNIT.get(region, "")
    head = ["Layer", "Companies listed", "In its figures", f"Revenue, total ({unit})", "EBITDA margin, median", "EBITDA margin, lowest",
            "EBITDA margin, highest", "EBITDA margins counted", "Net margin, median", "ROCE, median", "ROE, median", "P/E, median", "P/B, median",
            "EV/EBITDA, median"]
    sec = dive.get("sections") or {}
    val = sec.get("valuation") or {}
    by_val = {x.get("layer"): x for x in val.get("by_layer") or []}
    rows = []
    for b in dive.get("layers") or []:
        st, v = b.get("stats") or {}, by_val.get(b.get("layer")) or {}
        e = st.get("ebitda") or {}
        rows.append([b.get("layer"), b.get("listed", len(b.get("companies") or [])), b.get("n"), _n(b.get("revenue")), _pct(e.get("median")),
                     _pct(e.get("min")), _pct(e.get("max")), e.get("n"), _pct(_med(st.get("net"))), _pct(_med(st.get("roce"))),
                     _pct(_med(st.get("roe"))), _n(_med(v.get("pe"))), _n(_med(v.get("pb"))), _n(_med(v.get("ev_ebitda")))])
    med = sec.get("medians") or {}
    e = med.get("ebitda") or {}
    rows.append(["The whole theme", sum(len(b.get("companies") or []) for b in dive.get("layers") or []), dive.get("members"),
                 sum(_n(b.get("revenue")) or 0 for b in dive.get("layers") or []) or None, _pct(e.get("median")), _pct(e.get("min")),
                 _pct(e.get("max")), e.get("n"), _pct(_med(med.get("net"))), _pct(_med(med.get("roce"))), _pct(_med(med.get("roe"))),
                 _n(_med(val.get("pe"))), _n(_med(val.get("pb"))), _n(_med(val.get("ev_ebitda")))])
    m = _money_fmt(region)
    return _sheet("Layer medians", head, rows, {3: m, 4: PCT, 5: PCT, 6: PCT, 8: PCT, 9: PCT, 10: PCT, 11: TIMES, 12: TIMES, 13: TIMES})


PEER_WORDS = {"pe": ("P/E", TIMES), "sales_3y": ("Revenue growth, 3 years a year", PCT), "roce": ("ROCE", PCT)}


def peers(dive: dict) -> tuple:
    head = ["Measure", "The theme's median company", "Its comparable peers' median", "Companies compared", "Companies with no comparable peer set",
            "Most peers of the company's own industry", "Theme median against peers' median", "Peers most used", "Prices to"]
    pp = (((dive.get("sections") or {}).get("valuation") or {}).get("peers")) or {}
    rows = []
    for k, (label, fmt) in PEER_WORDS.items():
        p = pp.get(k)
        if not isinstance(p, dict):
            continue
        conv = (lambda v: Num(_pct(v), fmt)) if k != "pe" else (lambda v: Num(_n(v), fmt))      # noqa: E731  (each row in its own unit)
        like = p.get("like")
        rows.append([label, conv(p.get("theme")), conv(p.get("peers")), p.get("n"), p.get("none"),
                     None if like is None else "Yes" if like else "No",
                     _pct(p.get("premium")) if k == "pe" and like is not False else None,
                     ", ".join(p.get("names") or []) or None, _day(p.get("as_of"))])
    return _sheet("Peers", head, rows, {6: PCT, 8: DAY})


def valuation(dive: dict) -> tuple:
    val = (dive.get("sections") or {}).get("valuation") or {}
    head = ["Measure", "Group", "Median", "Lowest", "Highest", "Companies counted", "Date"]
    rows = []
    for k, label in (("pe", "P/E"), ("pb", "P/B"), ("ev_ebitda", "EV/EBITDA")):
        st = val.get(k)
        if isinstance(st, dict):
            rows.append([label, "The theme", _n(st.get("median")), _n(st.get("min")), _n(st.get("max")), st.get("n"), _day(dive.get("as_of"))])
    for k, label in (("market_pe", "P/E"), ("market_pb", "P/B")):
        st = val.get(k)
        if isinstance(st, dict):
            rows.append([label, "The whole market", _n(st.get("median")), _n(st.get("min")), _n(st.get("max")), st.get("n"), _day(dive.get("as_of"))])
    for x in val.get("by_layer") or []:
        for k, label in (("pe", "P/E"), ("pb", "P/B"), ("ev_ebitda", "EV/EBITDA")):
            st = x.get(k)
            if isinstance(st, dict):
                rows.append([label, f"Layer: {x.get('layer')}", _n(st.get("median")), _n(st.get("min")), _n(st.get("max")), st.get("n"),
                             _day(dive.get("as_of"))])
    for p in val.get("history") or []:
        if _n(p.get("pe")) is not None:
            rows.append(["P/E", "The theme, kept earlier", _n(p.get("pe")), None, None, p.get("n"), _day(p.get("d"))])
    return _sheet("Valuation", head, rows, {2: TIMES, 3: TIMES, 4: TIMES, 6: DAY})


def operating(dive: dict, region: str) -> tuple:
    from .sector_metrics import BY_KEY
    fams = ((dive.get("sections") or {}).get("sector")) or {}
    keys = list(dict.fromkeys(k for f in fams.values() if isinstance(f, dict) for k in f.get("keys") or []))
    head = ["Company", "Symbol", "Layer", "Kind", "Period to"] + [BY_KEY[k][1] if k in BY_KEY else k for k in keys]
    rows = []
    kind = {"bank": "Bank or lender", "insurer": "Insurer", "us": "US company"}
    for fam, f in fams.items():
        if not isinstance(f, dict):
            continue
        for r in f.get("rows") or []:
            rows.append([r.get("name"), r.get("symbol"), r.get("layer"), kind.get(fam, fam), _day(r.get("as_of"))]
                        + [(_pct(r.get(k)) if BY_KEY.get(k, ("", "", "", "pct"))[3] in ("pct", "chg") else _n(r.get(k))) if k in (f.get("keys") or []) else None
                           for k in keys])
    unit_fmt = {"pct": PCT, "chg": PCT, "x": TIMES, "amt": _money_fmt(region), "days": "0"}
    fmts = {4: DAY, **{5 + i: unit_fmt.get(BY_KEY[k][3], PLAIN) for i, k in enumerate(keys) if k in BY_KEY}}
    return _sheet("Operating figures", head, rows, fmts)


def changes(log: dict, region: str) -> tuple:
    unit = MONEY_UNIT.get(region, "")
    head = ["Date", "Why the read was stored again", "Change", "Company", "Symbol", "From", "To", "Reason or detail", "Year",
            f"Revenue before ({unit})", f"Revenue after ({unit})", "Margin before", "Margin after"]
    rows = []
    for e in (log or {}).get("entries") or []:
        d, why = _day(e.get("d")), CAUSE_WORDS.get(e.get("cause"), e.get("cause") or "")
        for c in e.get("removed") or []:
            rows.append([d, why, "Company removed", c.get("name"), c.get("symbol"), c.get("layer"), None, c.get("why")])
        for c in e.get("added") or []:
            rows.append([d, why, "Company added", c.get("name"), c.get("symbol"), None, c.get("layer")])
        for c in e.get("moved") or []:
            rows.append([d, why, "Company moved", c.get("name"), c.get("symbol"), c.get("from"), c.get("to")])
        for x in e.get("layers") or []:
            rows.append([d, why, LAYER_WORDS.get(x.get("kind"), x.get("kind")), None, None, " + ".join(x.get("from") or []) or None,
                         " + ".join(x.get("to") or []) or None, f"{x.get('n')} companies" if x.get("n") is not None else None])
        for c in e.get("restated") or []:
            rev, mar = c.get("revenue") or [None, None], c.get("margin") or [None, None]
            rows.append([d, why, "Figures restated", c.get("name"), c.get("symbol"), None, None,
                         " and ".join("Revenue" if w == "revenue" else c.get("measure") or "Margin" for w in c.get("what") or []) or None,
                         c.get("year"), _n(rev[0]), _n(rev[1]), _pct(mar[0]), _pct(mar[1])])
    m = _money_fmt(region)
    return _sheet("What changed", head, rows, {0: DAY, 9: m, 10: m, 11: PCT, 12: PCT})


def method(dive: dict, region: str, theme: str, made: date, log: dict) -> tuple:
    unit = dive.get("unit") or MONEY_UNIT.get(region, "")
    years = sorted({c.get("year") for b in dive.get("layers") or [] for c in b.get("companies") or [] if c.get("year")})
    rows = [
        ["Theme", theme],
        ["Market", "India" if region == "IN" else "US"],
        ["Workbook made", _day(made.isoformat())],
        ["Prices to the close of", _day(dive.get("as_of"))],
        ["Companies at an earlier close", f"{dive.get('as_of_older') or 0} of the theme's companies"],
        ["Years of the figures", ", ".join(years) or None],
        ["Figures", dive.get("basis") or ""],
        ["Money", f"Revenue and totals in {unit}; market values in {MONEY_UNIT.get(region, '')}."
                  + (" Rupee amounts are grouped the Indian way (1,23,456)." if region == "IN" else "")],
        ["Percentages", "Margins, returns and growth are Excel percentages (0.125 shows as 12.5%)."],
        ["How a layer's median is built", "Over the companies in the layer's figures: confirmed members whose way of earning is of the layer's "
                                          "kind and that have the figure. A company that runs other businesses too (its figures are the whole "
                                          "company's) is left out of the median when the layer has companies that are their own; a net margin "
                                          "with a one-off gain in it is left out of the net margin's median. \"In the layer's figures\" on the "
                                          "Companies sheet says which companies are in, and why each other one is not."],
        ["The whole theme's medians", "Over every confirmed company with figures, each company once, the companies whose figures are the "
                                      "whole company's left out when there are others."],
        ["Valuation", "P/E, P/B and EV/EBITDA medians over the companies that have one (a loss-maker has no P/E); the whole market's "
                      "median is over every listed company the site covers in that market."],
        ["Peers", "Each company against comparable listed companies outside the theme (its own sector first, then similar market value); "
                  "the gap against peers is given only when most of the peers are of the companies' own official industry."],
        ["Operating figures", "Figures filed by banks, lenders and insurers with the exchange, and by US companies with the SEC, each with "
                              "its period."],
        ["What changed", "Each time the theme's figures are stored again, set against the read before it: companies added or removed "
                         "(with the stated reason), moved between layers, layers renamed, split or merged, and latest-year revenue moved by "
                         "more than 2% or a margin by more than one point for the same year."
                         + (f" Kept since {log.get('since')}." if (log or {}).get("since") else "")],
        ["Sources", "The companies' own reported annual figures as stored on their StratLab pages, the exchanges' and the SEC's filings, and "
                    "the daily closes. The text that describes a layer is written by AI from general knowledge; no figure is."],
        ["Note", "Facts from reported numbers, not advice."],
    ]
    return ("Sources and method", [["Item", "Detail"]] + rows, {0}, {1: DAY})


def build(dive: dict, region: str, theme: str, log: dict, made: date) -> bytes:
    """The workbook's bytes."""
    sheets = [companies(dive, region), layer_medians(dive, region), peers(dive), valuation(dive), operating(dive, region), changes(log, region),
              method(dive, region, theme, made, log)]
    return xlsx_write.workbook(sheets)
