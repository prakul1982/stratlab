"""R2 integration (SECMEM's new-listing fallback meeting REVIEW's LIVE2-021 market guess): a US page may stand on the quote
site's listing alone only when that listing is a US one. Swept over every Indian company in the fake world: none opens as
a US company, so a two-company link with no market falls through to India."""
import pytest

from app import main
from tests import fake_prices, world
from tests.world import headers


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_no_indian_company_opens_as_a_us_company(w):
    c, h = w["client"], headers("pro-token")
    india = sorted(s for s in fake_prices.COMPANIES if fake_prices.market_of(s) == "IN")
    assert len(india) > 10
    wrong = [s for s in india if c.get(f"/research/company/us/{s.lower()}", headers=h).status_code == 200]
    assert wrong == []
    # the pair from the link: not a US pair, an Indian one
    assert c.get("/research/compare?region=US&a=HDFCBANK&b=ICICIBANK", headers=h).status_code != 200
    got = c.get("/research/compare?region=IN&a=HDFCBANK&b=ICICIBANK", headers=h)
    assert got.status_code == 200 and got.json()["a"]["name"].startswith("HDFC Bank")


def test_a_us_listing_still_stands_on_its_own(monkeypatch):
    hub = main.research_hub
    for listing, ok in (({"name": "Apex Critical Metals Corp.", "currency": "USD", "tz": "America/New_York"}, True),
                        ({"name": "Apex Critical Metals Corp.", "currency": "USD"}, True),          # no clock given
                        ({"name": "HDFC Bank Ltd", "currency": "INR", "tz": "Asia/Kolkata"}, False),
                        ({"name": "Vodafone Group", "currency": "GBp", "tz": "Europe/London"}, False),
                        ({"name": "Odd one", "currency": "USD", "tz": "Asia/Tokyo"}, False),
                        ({}, False)):
        monkeypatch.setattr(hub, "_listing_or_none", lambda s, x=listing: x)
        assert (hub._us_listing("X") is not None) is ok, listing
