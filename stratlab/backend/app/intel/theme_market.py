"""site87 (owner: with India picked, "India defence" open, then "$ United States": the US mapped "India defence"): a theme whose name names
one market's country ("India defence", "Indian railways", "US shale", "American banks") is that market's own and is never mapped in the
other. The theme page clears or swaps the theme on a market switch; the API refuses it too, so no address or old link maps it."""
from __future__ import annotations

import re

from ..responses import err

_COUNTRY = {
    "IN": re.compile(r"\b(india|indian|indias|bharat|bharatiya)\b", re.I),
    "US": re.compile(r"\b(usa|u\.s\.a?\.?|united states|america|american|americas)(?=\W|$)|^us\b|\bus$", re.I),
}
_US_CASED = re.compile(r"\bUS\b")
NAMES = {"IN": "India", "US": "the US"}


def country_of(q: str) -> str | None:
    """The market whose country a theme's name names (IN or US), or None for a name that names neither (or both)."""
    s = " ".join(str(q or "").split())
    hits = {r for r, rx in _COUNTRY.items() if rx.search(s)}
    if _US_CASED.search(s):
        hits.add("US")
    return next(iter(hits)) if len(hits) == 1 else None


def foreign(q: str, region: str) -> str | None:
    """The other market a theme belongs to when it names that market's country, else None."""
    c = country_of(q)
    return c if c and c != region else None


def refuse_foreign(q: str, region: str) -> None:
    """Stop a request that would map one market's country-named theme in the other market (400 theme_other_market)."""
    c = foreign(q, region)
    if c:
        err(400, "theme_other_market",
            f"“{' '.join(str(q).split())[:80]}” is a theme of {NAMES[c]}, so it isn't mapped in {NAMES.get(region, region)}. Pick a theme of this market.")
