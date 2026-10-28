"""RC-5, the main review (the whole app, end to end, as a new visitor, a trader, an investor and a money user): what broke
in the flows, each with the test that proves it."""
import pytest

from app import main, suggest
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    main.suggester.clear()
    yield built
    main.suggester.clear()
    built["close"]()


PRO = world.headers("pro-token")


# ---------- RC5-003: a company whose own symbol has a dash ----------
def test_a_symbol_with_a_dash_is_kept_whole_and_only_a_series_suffix_comes_off():
    eq = [{"symbol": "BAJAJ-AUTO", "name": "BAJAJ AUTO", "exchange": "NSE"},
          {"symbol": "MCDOWELL-N", "name": "UNITED SPIRITS", "exchange": "NSE"},
          {"symbol": "SLOWCO-BE", "name": "SLOW CO", "exchange": "NSE"},
          {"symbol": "SMEHOUSE-SM", "name": "SME HOUSE", "exchange": "NSE"},
          {"symbol": "TCS", "name": "TATA CONSULTANCY", "exchange": "NSE"}]
    rows = {r["symbol"]: suggest.shown(r) for r in suggest.india_rows(eq)}
    assert set(rows) == {"BAJAJ-AUTO", "MCDOWELL-N", "SLOWCO", "SMEHOUSE", "TCS"}, "BAJAJ-AUTO was offered as BAJAJ, a symbol no page has"
    assert rows["BAJAJ-AUTO"]["id"] == "BAJAJ-AUTO" and rows["SLOWCO"]["id"] == "SLOWCO"


def test_picking_bajaj_auto_from_the_search_opens_its_page(w):
    c = w["client"]
    got = c.get("/suggest/companies", params={"q": "bajaj auto"}, headers=PRO).json()["rows"]
    pick = next(r for r in got if r["name"] == "Bajaj Auto")
    assert pick["id"] == "BAJAJ-AUTO"
    page = c.get(f"/research/company/IN/{pick['id']}", headers=PRO)
    assert page.status_code == 200 and page.json()["name"] == "Bajaj Auto"
