"""The server runs on UTC; India's date is already the next day from 18:30 UTC. "Today" in India's money pages (the
financial year, a deposit's days to maturity, the loan check) must be India's date, not the server's."""
from datetime import date, datetime, timezone

import pytest

from app import fixed_income, loan_check, tax_lots

# 31 Mar 2027, 19:00 UTC = 1 Apr 2027, 00:30 IST: the first minutes of a new financial year
INSTANT = datetime(2027, 3, 31, 19, 0, tzinfo=timezone.utc)


def _freeze(monkeypatch, module):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return INSTANT.astimezone(tz) if tz else INSTANT.replace(tzinfo=None)

        @classmethod
        def today(cls):
            return INSTANT.replace(tzinfo=None)
    monkeypatch.setattr(module, "datetime", Frozen)


@pytest.mark.parametrize("module", [fixed_income, loan_check])
def test_today_is_the_indian_date(monkeypatch, module):
    _freeze(monkeypatch, module)
    assert module.today() == date(2027, 4, 1)


def test_the_financial_year_turns_at_midnight_india_time(monkeypatch):
    _freeze(monkeypatch, fixed_income)
    fy = fixed_income.tax_basis({"id": "u", "_plan": "free"}, None, False)[3]
    assert fy == tax_lots.fy_of("2027-04-01") != tax_lots.fy_of("2027-03-31")
