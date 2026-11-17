"""LIVE10B: the findings of the live end-to-end review of Release 60, each with the test that proves it. Plain asserts on the
existing fixtures and the `world` helpers."""
import base64
from pathlib import Path

import pytest

from app import holdings
from tests import world

FIX = Path(__file__).parent / "fixtures" / "holdings"
PRO = world.headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def file_upload(c, name: str, mode="replace", **extra):
    body = {"filename": name, "data": base64.b64encode((FIX / name).read_bytes()).decode(), "mode": mode, **extra}
    return c.post("/holdings/import", headers=PRO, json=body)


def qtys(body):
    return {x["symbol"]: x["qty"] for x in body["holdings"]["rows"]}


def test_live10b_024_a_file_of_stocks_already_held_is_never_added_silently(w):
    """Re-uploading the same Zerodha file (after an ICICI file was added) doubled every quantity."""
    c = w["client"]
    file_upload(c, "zerodha_kite_holdings.csv", "replace")
    merged = file_upload(c, "icici_direct_portfolio.csv", "add").json()
    assert merged["saved"] is False and merged["overlap"] == ["ICICIBANK", "SBIN"]   # held already: asked first
    assert qtys(merged)["SBIN"] == 60
    merged = file_upload(c, "icici_direct_portfolio.csv", "add", overlap_ok=True).json()
    assert merged["saved"] is True and qtys(merged)["SBIN"] == 140                   # the user's word: more shares
    again = file_upload(c, "zerodha_kite_holdings.csv", "add").json()
    assert again["saved"] is False and qtys(again)["SBIN"] == 140                   # the same file: not doubled


def test_live10b_024_the_same_holdings_in_a_file_not_remembered_count_as_the_same_file(w, monkeypatch):
    """Holdings imported before the file's fingerprint was kept: the same lines again are recognised by their content."""
    c = w["client"]
    file_upload(c, "zerodha_kite_holdings.csv", "replace")
    monkeypatch.setattr(holdings, "file_seen", lambda uid, digest: False)
    body = file_upload(c, "zerodha_kite_holdings.csv", "add").json()
    assert body["duplicate"] is True and body["saved"] is False and qtys(body)["SBIN"] == 60
