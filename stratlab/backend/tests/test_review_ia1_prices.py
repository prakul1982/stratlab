"""Item 34 (owner, 29 Oct): every price reads rupees first, the charged currency, with the dollar figure beside it
("₹699 a month (about $8)"), worked out from the USD/INR rate the app already reads daily, with a safe fixed rate when
none has been read. /pricing says which rate, and whether it is the fixed one."""
import json

import pytest

from app import pricing


@pytest.fixture
def store(monkeypatch):
    saved = {}
    pricing.forget()
    monkeypatch.setattr(pricing, "_rates_cache", [0.0, {}])          # the ten-minute cache of the daily read starts empty
    monkeypatch.setattr(pricing.db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(pricing.db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    return saved


def test_the_dollar_rate_is_the_daily_read(store):
    store[pricing.RATES] = json.dumps({"at": "2026-10-29T03:00:00+00:00", "rates": {"USD": 95.21, "EUR": 103.4}})
    assert pricing.usd_inr() == {"rate": 95.21, "fallback": False}
    pub = pricing.public()
    assert pub["usd_inr"] == {"rate": 95.21, "fallback": False}
    # the rupee prices the "about $" is worked out from are the plans' own, unchanged
    assert (pub["currencies"]["INR"]["basic"], pub["currencies"]["INR"]["pro"]) == (699, 1999)
    assert round(699 / pub["usd_inr"]["rate"]) == 7


def test_no_read_yet_gives_the_fixed_rate_marked_so(store):
    assert pricing.usd_inr() == {"rate": pricing.USD_INR_FALLBACK, "fallback": True}
    assert pricing.public()["usd_inr"]["fallback"] is True
    assert round(699 / pricing.USD_INR_FALLBACK) == 8                    # "about $8", never a blank


@pytest.mark.parametrize("bad", [0, -1, None, "95", 5000])
def test_a_nonsense_rate_is_not_used(store, bad):
    store[pricing.RATES] = json.dumps({"rates": {"USD": bad}})
    assert pricing.usd_inr() == {"rate": pricing.USD_INR_FALLBACK, "fallback": True}


def test_checkout_still_charges_the_rupee_plan(store):
    # the page now always asks for rupees: the rupee plan is the one charged, as today (Razorpay untouched)
    t = pricing.table()
    assert t["INR"]["charged_in"] == "INR" and t["USD"]["charged_in"] == "INR"
