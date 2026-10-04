"""The long-term gains exemption on listed shares (section 112A): how much of this financial year's ₹1.25 lakh has
been used by the long-term gains already realised, what is left, the unrealised long-term gain on each open lot at the
latest price, and the open lots that turn long-term in the next 30, 60 or 90 days.

Worked out from the same open lots and realised sales as the tax report (tax_lots.compute), with grandfathering for
shares held on 31 Jan 2018. Arithmetic only: "if sold today, the gain would be…", never a view on selling."""
from datetime import date

from . import tax_lots as T

WINDOWS = (30, 60, 90)
MAX_ROWS = 200
FACTS = [
    "The exemption is per financial year, on long-term gains on listed shares and equity funds left after set-off. "
    "An unused part doesn't carry forward to the next year.",
    "Long-term gains above it are taxed at 12.5% (sales from 23 July 2024), plus 4% cess and any surcharge.",
    "Losses are set off first: short-term losses against short-term gains and then long-term ones, long-term losses "
    "only against long-term gains. A loss realised in the same year reduces the gains the exemption is used against.",
    "Shares sold and bought again start a new holding period from the new purchase, at its price as the cost.",
    "A sale is long-term when the shares were held for more than 12 months: from the day after the first anniversary "
    "of the purchase.",
]


def _r(v, dp=2):
    return None if v is None else round(v, dp)


def _gain(lot: dict, price: float) -> tuple[float, float, bool]:
    """(cost for tax, gain if sold at `price`, grandfathered): a lot held on 31 Jan 2018 costs at least its value that
    day, but not more than the sale value."""
    value = lot["qty"] * price
    cost = lot["cost"]
    gf = False
    if lot["d"] <= T.GF_DATE and lot.get("fmv"):
        new = max(cost, min(lot["fmv"], value))
        gf = new > cost + 0.005
        cost = new
    return cost, value - cost, gf


def tracker(c: dict, quotes: dict[str, dict], today: str, full: bool = True) -> dict:
    """This year's exemption used and left, open long-term lots with their gain at today's price, and lots turning
    long-term soon. `c` is tax_lots.compute's output."""
    fy = T.fy_of(today)
    y = T.year(fy, c["realised"], c["intraday"], limit=0)
    long_rows, soon, unpriced = [], [], 0
    t = date.fromisoformat(today)
    for lot in c["open"]:
        price = (quotes.get(lot["key"]) or {}).get("price")
        lt = T.long_term(lot["d"], today)
        start = T.long_from(lot["d"])
        days_left = (date.fromisoformat(start) - t).days
        if not lt and days_left > WINDOWS[-1]:
            continue
        if not price:
            unpriced += 1
            continue
        cost, gain, gf = _gain(lot, price)
        row = {"key": lot["key"], "bought": lot["d"], "qty": round(lot["qty"], 4), "cost": _r(cost), "price": _r(price),
               "value": _r(lot["qty"] * price), "gain": _r(gain), "grandfathered": gf, "bonus": lot.get("bonus", False)}
        if lt:
            row["text"] = f"If sold today, the long-term {'gain' if gain >= 0 else 'loss'} would be {T.money(abs(gain))}."
            long_rows.append(row)
        else:
            window = next(w for w in WINDOWS if days_left <= w)
            soon.append({**row, "long_from": start, "days_left": days_left, "window": window,
                         "text": (f"Long-term from {date.fromisoformat(start).strftime('%-d %b %Y')}. At today's price the "
                                  f"{'gain' if gain >= 0 else 'loss'} is {T.money(abs(gain))}, which would be short-term if sold before then.")})
    long_rows.sort(key=lambda r: -r["gain"])
    soon.sort(key=lambda r: r["long_from"])
    gains = [r["gain"] for r in long_rows if r["gain"] > 0]
    losses = [r["gain"] for r in long_rows if r["gain"] < 0]
    ex = y["exemption"]
    return {"fy": fy, "label": y["label"], "as_of": today,
            "exemption": {"limit": ex["limit"], "used": ex["used"], "left": ex["left"],
                          "realised_lt_net": y["ltcg"]["net"], "realised_st_net": y["stcg"]["net"]},
            "open_lt": {"lots": len(long_rows), "gains": _r(sum(gains)), "losses": _r(sum(losses)),
                        "with_gain": len(gains)},
            "soon_counts": {str(w): sum(1 for r in soon if r["window"] <= w) for w in WINDOWS},
            "long": long_rows[:MAX_ROWS] if full else [], "soon": soon[:MAX_ROWS] if full else [],
            "unpriced": unpriced, "facts": FACTS, "locked": not full}
