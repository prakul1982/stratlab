"""Every Money page offers (and so opens on) the same financial year: the one being filed now, even with nothing in it."""
import pytest

from app import tax_lots
from app.money_routes import today
from tests import world

OWNER = world.headers("admin-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_the_tax_report_dividends_and_itr_list_the_year_being_filed(w):
    c = w["client"]
    filing = tax_lots.fy_of(today().isoformat()) - 1
    tax = c.get("/tax", headers=OWNER).json()
    assert filing in [y["fy"] for y in tax["years"]] and tax["current_fy"] == filing + 1
    divs = c.get("/money/dividends", headers=OWNER).json()
    assert filing in [y["fy"] for y in divs["years"]]
    itr = c.get("/money/itr", headers=OWNER).json()
    assert itr["fy"] == filing                                     # the ITR page's own default is the same year
