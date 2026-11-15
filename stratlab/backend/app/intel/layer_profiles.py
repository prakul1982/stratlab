"""Each layer on the measures that fit how its companies earn (m57, R57: the owner's review of the live R56 decks: "Airlines and travel: limited
airline/hotel operating measures; Cement: limited capacity, utilisation and volume statistics; Hospitals and Medical devices: sector operating
metrics; Renewable energy: generation, equipment and EPC businesses need distinct financial profiles; Payments: small sample").

Two profiles a layer is read on, both chosen by how its companies earn, never forced onto one comparison:
- its financial profile (FIN): the stored annual figures that fit its way of earning (theme_check.MODELS' family): a power producer on its EBITDA
  margin, debt over EBITDA and interest cover; a contractor on its margins and how much of its profit turns into cash; a lender on its return on
  equity, interest income over assets, bad loans and credit cost where stored; a payments processor on its margin and free cash flow. Each is a
  median over the layer's companies in its calculations, printed only where at least MIN_BASE companies and COVER of the layer have the figure,
  else its count; a figure the app stores for none of them is said (NOT_STORED, and each key with no value), never left as a gap.
- its sector operating profile (sector_ops.PROFILES): the measures its companies' own stored documents state (load factor, occupancy, capacity,
  orders...). A layer figure only where at least COVER of the layer's companies the profile fits state the measure ("passenger load factor 84%
  (3 of 4)"); fewer: the count only ("1 of 39 states it"); none: one line saying it isn't available in the documents the app holds.

Rankings stay inside a layer (its highest and lowest company on its lead measure, of MIN_BASE companies or more): layers that earn differently
are never ranked against each other here. Nothing is estimated: every value is a stored figure or a figure a company's own document states."""
from __future__ import annotations

from . import metric_registry as registry

MIN_BASE = 3                    # companies a median needs (theme_data.MIN_BASE)
COVER = 0.5                     # share of a layer's companies that must have a figure for a layer figure (theme_data.COVERAGE_MIN)

_POWER = ("ebitda", "debt_ebitda", "interest_cover", "roce")
_MAKING = ("ebitda", "roce", "sales_1y", "rd_share", "inventory_days")
_INSURER = ("roe", "solvency", "combined_ratio", "pb")
_SOFTWARE = ("sales_1y", "ebitda", "fcf_margin", "sbc_share", "rpo_growth")
_ASSETS = ("ebitda", "debt_ebitda", "roce", "sales_1y")
# a way of earning's (theme_check.MODELS family) own figures, the lead first (its ranking inside the layer)
FIN = {
    "generation": _POWER, "power_trading": _POWER, "utility": _POWER, "regulated_utility": ("ebitda", "debt_ebitda", "interest_cover", "roe"),
    "construction": ("ebitda", "net", "cfo_to_profit", "roce"),
    "making": _MAKING, "components": _MAKING, "contract_making": ("ebitda", "roce", "sales_1y", "inventory_days"),
    "lending": ("roe", "nii_assets", "gnpa", "credit_cost", "pb"),
    "underwriting": _INSURER, "life_insurance": ("roe", "solvency", "pb"), "general_insurance": _INSURER, "reinsurance": _INSURER,
    "payments": ("ebitda", "fcf_margin", "sales_1y", "roce"),
    "software": _SOFTWARE, "royalties": _SOFTWARE, "platform": ("sales_1y", "ebitda", "fcf_margin", "sbc_share"),
    "services": ("ebitda", "sales_1y", "roce", "net"), "bpo": ("ebitda", "sales_1y", "roce", "net"),
    "care": ("ebitda", "roce", "sales_1y", "debt_ebitda"),
    "transport": ("ebitda", "debt_ebitda", "interest_cover", "roce"), "consumer_services": _ASSETS,
    "capacity": ("ebitda", "debt_ebitda", "capex_share", "roce"), "telecom_services": ("ebitda", "debt_ebitda", "capex_share", "roce"),
    "resources": _ASSETS, "mining": _ASSETS, "metal_processing": ("ebitda", "roce", "sales_1y", "inventory_days"),
    "property": ("ebitda", "debt_ebitda", "interest_cover", "net"), "development": ("net", "roe", "sales_1y", "pb"),
    "resale": ("ebitda", "roce", "sales_1y", "inventory_days"), "media": ("ebitda", "sales_1y", "net", "roce"),
    "financial_fees": ("roe", "net", "sales_1y", "pb"),
}
# the figure a filing gives in place of the page's own (sector_metrics.REPLACES)
FILED = {"gnpa": "gnpa_f", "nii_assets": "nii_assets_f"}
# figures that fit a way of earning but that no source the app reads stores, said in the layer's row (never filled by a proxy)
NOT_STORED = {
    ("construction", "IN"): "working capital days (no receivables or payables lines are stored)",
    ("construction", "US"): "working capital days (no receivables or payables lines are stored)",
    ("lending", "IN"): "net interest margin (no element of the results format; NII over assets is shown instead)",
    ("lending", "US"): "net interest margin and credit cost (not in the figures the app stores for US lenders)",
}
# the sector operating profiles' amounts and counts: never a median across companies of different sizes, their range only
SIZES = ("ask", "rpk", "asm", "rpm", "beds_op", "beds_cap", "cem_capacity", "cem_volume", "mw_installed", "generation", "tpv", "txn", "rooms",
         "orders_held", "orders_won")
ORDER_KEYS = {"order_book": "orders_held", "order_inflow": "orders_won"}      # the business updates' order figures (deck.order_family)


def fin_keys(family: str | None, region: str) -> tuple:
    """A way of earning's own figures that apply in the region (an Indian bank's NPA, a US company's free cash flow)."""
    return tuple(k for k in FIN.get(family or "", ()) if region in registry.BY_ID[k].regions)


def _value(c: dict, k: str):
    v = c.get(FILED[k]) if k in FILED and c.get(FILED[k]) is not None else c.get(k)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def in_calc(c: dict) -> bool:
    """A company in its layer's calculations (theme_data's "calc"), confirmed and with figures."""
    return (c.get("calc") or {}).get("in", True) is not False and c.get("status") not in ("unverified", "unchecked") and not c.get("company_wide")


def _median(xs: list) -> float:
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def financial(layer: dict, region: str) -> dict | None:
    """The layer's financial profile: {"family", "keys", "figs": [{"key", "n", "of", "median"|None, "min", "max"}], "top": {...}|None,
    "not_stored": str}; None for a layer with no one way of earning (an "Other" group)."""
    fam = (layer.get("model") or {}).get("family") or ""
    keys = fin_keys(fam, region)
    if not keys:
        return None
    cos = [c for c in layer.get("companies") or [] if in_calc(c)]
    figs = []
    for k in keys:
        vals = [(c, _value(c, k)) for c in cos]
        vals = [(c, x) for c, x in vals if x is not None]
        xs = [x for _, x in vals]
        ok = len(xs) >= MIN_BASE and len(xs) >= COVER * len(cos)
        figs.append({"key": k, "n": len(xs), "of": len(cos), "median": round(_median(xs), 2) if ok else None,
                     "min": min(xs) if xs else None, "max": max(xs) if xs else None})
    top = None
    for f in figs:
        if f["median"] is None:
            continue
        vals = sorted(((_value(c, f["key"]), c.get("name") or c.get("symbol")) for c in cos if _value(c, f["key"]) is not None), key=lambda x: x[0])
        if len(vals) >= MIN_BASE and vals[-1][0] != vals[-2][0] and vals[0][0] != vals[1][0]:
            top = {"key": f["key"], "high": vals[-1], "low": vals[0], "n": len(vals)}
        break                       # the lead measure only: the first with a layer figure
    return {"family": fam, "keys": keys, "figs": figs, "top": top, "of": len(cos), "not_stored": NOT_STORED.get((fam, region), "")}


def ops_profile_of(layer: dict, fit_by_profile: dict) -> tuple[str | None, list]:
    """(the sector operating profile most of a layer's companies fit, those companies' symbols); (None, []) when fewer than half its companies
    fit any (sector_ops.profile_of decided each company's fit when the dive was built)."""
    syms = [c.get("symbol") for c in layer.get("companies") or [] if c.get("symbol")]
    best, got = None, []
    for pid, fit in fit_by_profile.items():
        mine = [s for s in syms if s in fit and fit[s] == layer.get("layer")]
        if len(mine) > len(got):
            best, got = pid, mine
    if not got or len(got) < COVER * len(syms):
        return None, []
    return best, got


def operating(layer: dict, pid: str, members: list, figs: dict, region: str) -> dict:
    """One layer's sector operating measures: {"profile", "of" (its companies the profile fits), "measures": [{"key", "n", "median"|None, "min",
    "max", "period", "size"}], "none": [measure ids none of them states]}. `figs`: {symbol: {measure: {"v", "period", ...}}}."""
    from . import sector_ops
    keys = [k for k in sector_ops.MEASURES.get(pid, ()) if region in registry.BY_ID[k].regions]
    out, none = [], []
    for k in keys:
        got = [(figs.get(s) or {}).get(k) for s in members]
        got = [g for g in got if g and g.get("v") is not None]
        if not got:
            none.append(k)
            continue
        xs = [g["v"] for g in got]
        size = k in SIZES or not registry.BY_ID[k].headline
        ok = len(xs) >= COVER * len(members)
        periods = sorted({g.get("as_of") or g.get("period") for g in got if g.get("as_of") or g.get("period")},
                         key=lambda p: registry.period_end(p) or registry.period_end("Jan 1900"))
        out.append({"key": k, "n": len(xs), "of": len(members), "size": size, "ok": ok,
                    "median": round(_median(xs), 2) if ok and not size and len(xs) >= MIN_BASE else None,
                    "min": min(xs), "max": max(xs), "period": periods[-1] if periods else ""})
    return {"profile": pid, "of": len(members), "measures": out, "none": none}


def rows(v: dict, ops_figs: dict | None = None) -> list[dict]:
    """Every layer of one way of earning with its financial profile and, where its companies fit one, its sector operating profile; layers of
    one family next to each other (in the order the deck lists them). `ops_figs`: {profile: {symbol: {measure: figure}}} as the deck has them
    (the dive's stored documents and, where the plan includes them, business updates)."""
    region = v.get("region") or "IN"
    profiles = (((v.get("sections") or {}).get("ops") or {}).get("profiles") or {})
    fit_by = {pid: {c["symbol"]: c.get("layer") for c in p.get("fit") or []} for pid, p in profiles.items()}
    adj = {x.get("symbol") for x in v.get("adjacent") or [] if x.get("symbol")}
    out = []
    for L in v.get("layers") or []:
        fin = financial(L, region)
        if fin is None:
            continue
        pid, members = ops_profile_of(L, fit_by)
        ops = operating(L, pid, members, (ops_figs or {}).get(pid) or {}, region) if pid else None
        cos = L.get("companies") or []
        out.append({"layer": L.get("layer"), "family": fin["family"], "model": L.get("model") or {}, "fin": fin, "ops": ops,
                    "adjacent": bool(L.get("adjacent")) or (bool(cos) and all(c.get("symbol") in adj for c in cos))})
    order = []
    for r in out:
        if r["family"] not in order:
            order.append(r["family"])
    return sorted(out, key=lambda r: order.index(r["family"]))


def figs_with_orders(ops_figs: dict, orders: dict | None) -> dict:
    """The contractors' profile's figures with the order book and inflow their business updates state (deck.order_family's rows), where a
    company's own document gave none."""
    if not orders:
        return ops_figs
    out = {pid: {s: dict(f) for s, f in figs.items()} for pid, figs in ops_figs.items()}
    epc = out.setdefault("epc", {})
    for r in orders.get("rows") or []:
        for k_from, k_to in ORDER_KEYS.items():
            if r.get(k_from) is None:
                continue
            have = epc.setdefault(r["symbol"], {})
            if k_to not in have:
                src = (r.get("src") or {}).get(k_from) or {}
                have[k_to] = {"v": r[k_from], "period": src.get("period") or r.get("as_of"), "as_of": src.get("period") or r.get("as_of"),
                              "source": src.get("source") or "Business update filed with the exchange"}
    return out


LARGEST = 10                    # the audit's acceptance (R57 RC12): of a theme's 10 largest companies a profile fits, how many state a measure


def largest_cover(v: dict, ops_figs: dict | None, k: int = LARGEST) -> tuple[int, int]:
    """(how many of the theme's `k` largest companies by market value that a sector operating profile fits state at least one of its measures,
    how many such companies there are, at most `k`), the figure each deck states so a reader sees how far the measures reach."""
    profiles = (((v.get("sections") or {}).get("ops") or {}).get("profiles") or {})
    pid_of = {c["symbol"]: pid for pid, p in profiles.items() for c in p.get("fit") or []}
    cos = {c["symbol"]: c for L in v.get("layers") or [] for c in L.get("companies") or [] if c.get("symbol") in pid_of}
    top = sorted(cos.values(), key=lambda c: -(c.get("cap") or 0))[:k]
    have = sum(1 for c in top if any(f and f.get("v") is not None for f in ((ops_figs or {}).get(pid_of[c["symbol"]]) or {}).get(c["symbol"], {}).values()))
    return have, len(top)
