"""Reading a company page's key figures in tests (PUB-2): a figure is a tile whose title is its full wording ("Net profit, last
12 months (₹ crore)"), so a test names the figure by that wording and reads its value; the price is the header's, the range is
a row of its own, and a figure that is n/a has no tile (`stat` is None)."""
import re
from html import escape, unescape


def stat(page: str, label: str) -> str | None:
    """The value of the key figure whose full wording is `label`; amounts without their symbol and unit ("₹74,736 cr" is "74,736"), so
    the checks on the numbers read as before. None when the page has no such figure."""
    if label.startswith(("Last close", "Last price")):
        m = re.search(r"<b data-price>([^<]*)</b>", page)
        return unescape(m.group(1)) if m else None
    if label.startswith(("1-year range", "Range since")):
        m = re.search(r'<p class="range-ends"><span><small>Low</small> <b>([^<]*)</b></span><span><small>High</small> <b>([^<]*)</b>', page)
        return f"{unescape(m.group(1))} to {unescape(m.group(2))}" if m else None
    m = re.search(rf'<div class="stat[^"]*" title="{re.escape(escape(label))}"><span>[^<]*</span><b>([^<]*)</b>', page)
    if not m:
        return None
    v = unescape(m.group(1))
    if label.startswith(("Net profit", "Profit to")):
        v = re.sub(r"^([-−]?)(?:[₹$]|[A-Z]{3} )", r"\1", v)
        v = re.sub(r"( cr|[MB])$", "", v)
    return v
