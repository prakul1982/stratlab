"""Lane fix19 (owner, 18 Nov): every browser tab's title is "Page · StratLab", one part then the brand, written in one place
(app/titles.py; the app writes the same from frontend/src/content/seo.ts)."""
import re
from pathlib import Path

from app import company_cards, invoices, mail_pages, public, titles
from tests.test_invoices import PAY, SELLER, store  # noqa: F401  (fixture)

ONE = re.compile(r"^[^·]+ · StratLab$")
APP = Path(__file__).resolve().parent.parent / "app"


def _title(page: str) -> str:
    return re.search(r"<title>([^<]*)</title>", page).group(1).replace("&#x27;", "'").replace("&amp;", "&")


def test_one_pattern_helper():
    assert titles.page_title("Data status") == "Data status · StratLab"
    assert titles.page_title() == "StratLab" and titles.page_title("") == "StratLab"


def test_no_server_page_writes_its_own_brand_suffix():
    # the deck (PDF metadata) and the helper itself aside, no module spells " · StratLab" into a title
    for f in sorted(APP.rglob("*.py")):
        if f.name in ("titles.py", "deck.py"):
            continue
        code = "\n".join(line for line in f.read_text().splitlines() if not line.lstrip().startswith("#"))
        assert not re.search(r"· StratLab[\"'<]", code), f.name


def test_server_pages_titles_follow_the_pattern(store):  # noqa: F811
    assert ONE.match(_title(public.gone_html()))
    snap = {"verdict": {"headline": "Probably luck", "summary": "x"}, "name": "EMA cross", "instrument": {"symbol": "RELIANCE"}}
    assert ONE.match(_title(public.preview_html("t", snap, False)))
    card = {"symbol": "RELIANCE", "name": "Reliance Industries", "region": "IN"}
    assert _title(company_cards.preview_html("t", card, False)) == "Reliance Industries (RELIANCE): the facts · StratLab"
    assert _title(mail_pages.notice("That link isn't available", "x")) == "That link isn't available · StratLab"
    invoices.save_seller(SELLER)
    inv = invoices.make(PAY, {"id": "u1"}, "basic", "month")
    t = _title(invoices.html(inv))
    assert ONE.match(t) and t.startswith("Tax invoice "), t
