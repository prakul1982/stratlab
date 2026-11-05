"""Upstox, Angel One and Dhan logins (app/connect/brokers.py) against fake brokers (httpx.MockTransport): the login address,
the callback's state check, swapping the login for a token, the holdings each broker returns (odd fields too), when a
login ends, disconnecting, the admin-only gate and the *_FOR_ALL flags, "not set up yet", and that the server only ever
calls the brokers' read-only addresses and never logs or returns a token. Every account and token here is made up."""
import base64
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet

from app import db, holdings
from app.config import settings
from app.connect import brokers, redact, state, vault
from tests import world

PRO, BASIC, ADMIN = (world.headers(t) for t in ("pro-token", "basic-token", "admin-token"))
PRO_ID, BASIC_ID, ADMIN_ID = "u-pro", "u-basic", "u-admin"
SITE = "https://site.example"
API = "https://api.example"
IST = brokers.IST


def jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'HS256'})}.{enc(claims)}.c2lnbmF0dXJl"


UPSTOX_TOKEN = jwt({"sub": "UP1234", "exp": int(time.time()) + 3 * 86400})        # ends later than Upstox's own 03:30 rule
ANGEL_TOKEN = jwt({"username": "A123456", "exp": int(time.time()) + 3 * 86400})
DHAN_TOKEN = jwt({"dhanClientId": "1000000001"})


class Fake:
    """The three brokers' servers: what each read returns, and every request the server made."""

    def __init__(self):
        self.seen: list[httpx.Request] = []
        self.upstox_holdings = [
            {"isin": "INE009A01021", "company_name": "INFOSYS LIMITED", "quantity": 8, "t1_quantity": 2, "collateral_quantity": 0,
             "trading_symbol": "INFY", "tradingsymbol": "INFY", "average_price": 1400.0, "exchange": "NSE"},
            {"isin": "INE154A01025", "company_name": "ITC LTD", "quantity": "5", "t1_quantity": None, "collateral_quantity": 20,
             "tradingsymbol": "ITC", "average_price": "380.5", "exchange": "NSE"},
            {"isin": "", "company_name": "GONE", "quantity": 0, "trading_symbol": "GONE", "average_price": 10, "exchange": "NSE"}]
        self.upstox_status = 200
        self.angel_holdings: list | None = [
            {"tradingsymbol": "TATASTEEL-EQ", "exchange": "NSE", "isin": "INE081A01020", "t1quantity": 0, "realisedquantity": 2,
             "quantity": 2, "product": "DELIVERY", "collateralquantity": None, "averageprice": 111.87},
            {"tradingsymbol": "SBIN-BE", "exchange": "BSE", "isin": "INE062A01020", "t1quantity": 3, "realisedquantity": 5,
             "quantity": None, "averageprice": "573.1"},
            {"tradingsymbol": "SBIN-EQ", "exchange": "NSE", "isin": "INE062A01020", "t1quantity": 0, "realisedquantity": 0,
             "quantity": 2, "averageprice": 600}]
        self.angel_error = None
        self.dhan_holdings: list | dict = [
            {"exchange": "ALL", "tradingSymbol": "HDFCBANK", "securityId": "1333", "isin": "INE040A01034", "totalQty": 10, "dpQty": 10,
             "t1Qty": 0, "availableQty": 10, "collateralQty": 0, "avgCostPrice": 1500.0},
            {"exchange": "ALL", "tradingSymbol": "TCS", "isin": "INE467B01029", "totalQty": None, "dpQty": 3, "t1Qty": 1,
             "avgCostPrice": "NaN"}]
        self.dhan_status = 200
        self.dhan_client = "1000000001"
        self.dhan_expiry = (datetime.now(IST) + timedelta(hours=20)).replace(microsecond=0, tzinfo=None).isoformat()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.seen.append(req)
        u = str(req.url.copy_with(query=None))
        if u == brokers.UPSTOX_TOKEN:
            form = parse_qs(req.content.decode())
            if form.get("code") != ["good-code"]:
                return httpx.Response(400, json={"status": "error", "errors": [{"errorCode": "UDAPI100057"}]})
            return httpx.Response(200, json={"email": "x@example.com", "user_id": "UP1234", "access_token": UPSTOX_TOKEN, "extended_token": None})
        if u == brokers.UPSTOX_HOLDINGS:
            if self.upstox_status == 401:
                return httpx.Response(401, json={"status": "error", "errors": [{"errorCode": "UDAPI100050", "message": "Invalid token"}]})
            return httpx.Response(self.upstox_status, json={"status": "success", "data": self.upstox_holdings})
        if u == brokers.ANGEL_HOLDINGS:
            if self.angel_error:
                return httpx.Response(200, json={"status": False, "message": "Invalid Token", "errorcode": self.angel_error, "data": None})
            return httpx.Response(200, json={"status": True, "message": "SUCCESS", "errorcode": "",
                                             "data": {"holdings": self.angel_holdings, "totalholding": {"totalholdingvalue": 1}}})
        if u in (brokers.DHAN_CONSENT, brokers.DHAN_PARTNER_CONSENT):
            return httpx.Response(200, json={"consentAppId": "940b0ca1-consent", "consentId": "partner-consent", "consentAppStatus": "GENERATED", "status": "success"})
        if u in (brokers.DHAN_CONSUME, brokers.DHAN_PARTNER_CONSUME):
            if req.url.params.get("tokenId") != "good-token-id":
                return httpx.Response(400, json={"errorCode": "DH-905"})
            return httpx.Response(200, json={"dhanClientId": self.dhan_client, "dhanClientName": "MADE UP", "dhanClientUcc": "ABCD1234",
                                             "givenPowerOfAttorney": False, "accessToken": DHAN_TOKEN, "expiryTime": self.dhan_expiry})
        if u == brokers.DHAN_HOLDINGS:
            return httpx.Response(self.dhan_status, json=self.dhan_holdings)
        return httpx.Response(404)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(brokers, "transport", httpx.MockTransport(f))
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", Fernet.generate_key().decode())
    for k, v in {"UPSTOX_API_KEY": "up-key", "UPSTOX_API_SECRET": "up-secret-value", "ANGELONE_API_KEY": "angel-key",
                 "ANGELONE_API_SECRET": "angel-secret", "DHAN_APP_ID": "dhan-app", "DHAN_APP_SECRET": "dhan-secret-value",
                 "DHAN_CLIENT_ID": "1000000001", "DHAN_PARTNER_ID": "", "DHAN_PARTNER_SECRET": "", "UPSTOX_FOR_ALL": False,
                 "ANGELONE_FOR_ALL": False, "DHAN_FOR_ALL": False, "ADMIN_EMAILS": "owner@example.com",
                 "PUBLIC_SITE_URL": SITE, "PUBLIC_API_URL": API}.items():
        monkeypatch.setattr(settings, k, v)
    return f


def login(c, key, headers=ADMIN) -> tuple[str, dict]:
    r = c.get(f"/connect/{key}/login", headers=headers)
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    return url, {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def back(c, key, params) -> tuple[httpx.Response, dict]:
    r = c.get(f"/connect/{key}/callback", params=params, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith(f"{SITE}/settings?broker={key}&b=") and loc.endswith("#accounts")     # only ever back to the app's own page
    return r, {k: v[0] for k, v in parse_qs(urlparse(loc).query).items()}


def connect(c, key, headers=ADMIN, **extra):
    """The whole round trip as the Settings page does it: log in, come back, confirm."""
    _, q = login(c, key, headers)
    params = {"upstox": {"code": "good-code", "state": q.get("state", "")},
              "angelone": {"auth_token": ANGEL_TOKEN, "feed_token": "feed", "refresh_token": "refresh", "state": q.get("state", "")},
              "dhan": {"tokenId": "good-token-id"}}[key]
    _, got = back(c, key, {**params, **extra})
    assert got["b"] == "confirm", got
    return c.post(f"/connect/{key}/confirm", headers=headers, json={"ref": got["bs"], "claim": got["bc"]})


def card(c, key, headers=ADMIN) -> dict:
    return next(b for b in c.get("/connect", headers=headers).json()["brokers"] if b["key"] == key)


# ---------- set up, open, who ----------
def test_without_keys_every_card_says_not_set_up(w, fake, monkeypatch):
    for k in ("UPSTOX_API_KEY", "ANGELONE_API_KEY", "DHAN_APP_ID", "DHAN_PARTNER_ID"):
        monkeypatch.setattr(settings, k, "")
    c = w["client"]
    for key in brokers.ALL:
        v = card(c, key)
        assert v["configured"] is False and v["available"] is False and v["connected"] is False
        r = c.get(f"/connect/{key}/login", headers=ADMIN)
        assert r.status_code == 503 and r.json()["detail"]["message"] == "Not set up yet."
    assert not fake.seen


def test_the_encryption_key_is_needed_too(w, fake, monkeypatch):
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", "")
    assert all(not card(w["client"], k)["configured"] for k in brokers.ALL)


def test_each_broker_is_admin_only_until_its_flag(w, fake, monkeypatch):
    c = w["client"]
    for key in brokers.ALL:
        assert card(c, key)["available"] is True                                   # the owner can already use it
        assert card(c, key, PRO)["available"] is False
        assert c.get(f"/connect/{key}/login", headers=PRO).status_code == 403
        assert c.post(f"/connect/{key}/refresh", headers=PRO).status_code == 403
    monkeypatch.setattr(settings, "UPSTOX_FOR_ALL", True)
    monkeypatch.setattr(settings, "ANGELONE_FOR_ALL", True)
    monkeypatch.setattr(settings, "DHAN_FOR_ALL", True)
    # owner, 5 Nov (late): the flag opens Dhan too, partner credentials or not (a login Dhan refuses is said plainly)
    assert all(card(c, k, PRO)["available"] for k in brokers.ALL)


def test_a_flag_on_without_keys_still_says_not_set_up(w, fake, monkeypatch):
    for k in ("UPSTOX_FOR_ALL", "ANGELONE_FOR_ALL", "DHAN_FOR_ALL"):
        monkeypatch.setattr(settings, k, True)
    for k in ("UPSTOX_API_SECRET", "ANGELONE_API_KEY", "DHAN_APP_SECRET"):
        monkeypatch.setattr(settings, k, "")
    c = w["client"]
    for key in brokers.ALL:
        v = card(c, key, PRO)
        assert v["configured"] is False and v["available"] is False                  # never a Connect that can't work
        assert c.get(f"/connect/{key}/login", headers=PRO).json()["detail"]["message"] == "Not set up yet."


def test_dhan_refusing_someone_elses_login_ends_on_settings_in_plain_words(w, fake, monkeypatch, caplog):
    monkeypatch.setattr(settings, "DHAN_FOR_ALL", True)
    c = w["client"]
    fake.dhan_client = "2000000002"                                                 # not the app owner's account
    caplog.set_level(logging.WARNING)
    login(c, "dhan", PRO)
    r, got = back(c, "dhan", {"tokenId": "good-token-id"})
    assert got["b"] == "refused" and "bs" not in got
    assert "isn't the app owner's" in caplog.text and DHAN_TOKEN not in caplog.text
    assert not card(c, "dhan", PRO)["connected"]
    # Dhan refusing to make a token at all ends the same way
    caplog.clear()
    login(c, "dhan", PRO)
    assert back(c, "dhan", {"tokenId": "refused-token-id"})[1]["b"] == "refused"
    assert "consume answered 400" in caplog.text
    assert brokers.REFUSED == "Dhan didn't allow this login yet. Upload your holdings file or forward your statement instead."


def test_confirming_needs_signing_in_and_an_open_broker(w, fake):
    c = w["client"]
    for key in brokers.ALL:
        assert c.post(f"/connect/{key}/confirm", json={"ref": "x", "claim": "y"}).status_code == 401
    _, q = login(c, "upstox")
    _, got = back(c, "upstox", {"code": "good-code", "state": q["state"]})
    # a user the broker isn't open for can't attach it, even holding the claim
    assert c.post("/connect/upstox/confirm", headers=PRO, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400


# ---------- Upstox ----------
def test_upstox_login_address(w, fake):
    url, q = login(w["client"], "upstox")
    assert url.startswith(brokers.UPSTOX_DIALOG + "?")
    assert q["response_type"] == "code" and q["client_id"] == "up-key" and q["redirect_uri"] == f"{API}/connect/upstox/callback"
    assert brokers.read_state(q["state"]) == (ADMIN_ID, "upstox")
    assert "up-secret-value" not in url


def test_upstox_round_trip_reads_holdings_and_keeps_the_token_sealed(w, fake):
    c = w["client"]
    _, q = login(c, "upstox")
    r, got = back(c, "upstox", {"code": "good-code", "state": q["state"]})
    assert got["b"] == "confirm" and got["bs"] and got["bc"]
    assert not card(c, "upstox")["connected"]                                       # the callback alone links nothing
    swap = next(x for x in fake.seen if str(x.url) == brokers.UPSTOX_TOKEN)
    form = parse_qs(swap.content.decode())
    assert swap.method == "POST" and form == {"code": ["good-code"], "client_id": ["up-key"], "client_secret": ["up-secret-value"],
                                              "redirect_uri": [f"{API}/connect/upstox/callback"], "grant_type": ["authorization_code"]}
    done = c.post("/connect/upstox/confirm", headers=ADMIN, json={"ref": got["bs"], "claim": got["bc"]})
    assert done.status_code == 200, done.text
    assert done.json()["count"] == 2
    items = {i["symbol"]: i for i in holdings.load(ADMIN_ID)["items"]}
    assert items["INFY"]["qty"] == 10 and items["INFY"]["avg"] == 1400.0               # settled and T+1
    assert items["ITC"]["qty"] == 25 and items["ITC"]["avg"] == 380.5                  # "5" as text, plus pledged shares
    assert "GONE" not in items and all(i["via"] == "upstox" for i in items.values())
    assert holdings.load(ADMIN_ID)["source"] == "Upstox login"
    raw = json.dumps(db.get_setting(state.KEY + ADMIN_ID))
    assert UPSTOX_TOKEN not in raw and vault.unseal(state.section(ADMIN_ID, "upstox")["token"]) == UPSTOX_TOKEN
    view = c.get("/connect", headers=ADMIN).text
    assert UPSTOX_TOKEN not in view and "up-secret-value" not in view
    held = next(x for x in fake.seen if str(x.url) == brokers.UPSTOX_HOLDINGS)
    assert held.method == "GET" and held.headers["authorization"] == f"Bearer {UPSTOX_TOKEN}"
    v = card(c, "upstox")
    assert v["connected"] and v["live"] and not v["expired"] and v["refreshed_label"].startswith("today ") and v["account"] == "UP1234"
    # Upstox ends every login at 03:30 India time, before the token's own end
    ends = datetime.fromisoformat(v["ends_at"]).astimezone(IST)
    assert (ends.hour, ends.minute) == (3, 30) and timedelta(0) < ends - datetime.now(IST) <= timedelta(hours=24)


def test_upstox_callback_refuses_a_missing_forged_used_or_other_brokers_state(w, fake):
    c = w["client"]
    _, angel = login(c, "angelone")
    for params in ({"code": "good-code"}, {"code": "good-code", "state": "b1.forged.value"}, {"code": "good-code", "state": "plain"},
                   {"code": "good-code", "state": angel["state"]}):
        _, got = back(c, "upstox", params)
        assert got["b"] == "failed"
    _, got = back(c, "upstox", {"error": "access_denied"})
    assert got["b"] == "cancelled"
    assert not [x for x in fake.seen if str(x.url) == brokers.UPSTOX_TOKEN]           # no login was swapped
    _, q = login(c, "upstox")
    assert back(c, "upstox", {"code": "good-code", "state": q["state"]})[1]["b"] == "confirm"
    n = len(fake.seen)
    assert back(c, "upstox", {"code": "good-code", "state": q["state"]})[1]["b"] == "failed"   # a state works once
    assert len(fake.seen) == n
    _, q = login(c, "upstox")
    assert back(c, "upstox", {"code": "wrong-code", "state": q["state"]})[1]["b"] == "failed"  # the broker refused the code
    assert db.get_setting(state.KEY + ADMIN_ID) is None


def test_a_state_expires_and_is_for_one_user(w, fake, monkeypatch):
    c = w["client"]
    _, q = login(c, "upstox")
    real = time.time()
    monkeypatch.setattr(time, "time", lambda: real + brokers.START_TTL + 60)
    assert brokers.read_state(q["state"]) is None
    assert back(c, "upstox", {"code": "good-code", "state": q["state"]})[1]["b"] == "failed"


def test_a_staged_login_is_for_its_user_its_claim_once_and_expires(w, fake, monkeypatch):
    monkeypatch.setattr(settings, "UPSTOX_FOR_ALL", True)
    c = w["client"]
    _, q = login(c, "upstox", PRO)
    _, got = back(c, "upstox", {"code": "good-code", "state": q["state"]})
    assert c.post("/connect/upstox/confirm", headers=BASIC, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400
    assert c.post("/connect/upstox/confirm", headers=PRO, json={"ref": got["bs"], "claim": "guessed"}).status_code == 400
    assert c.post("/connect/upstox/confirm", headers=PRO, json={"ref": got["bs"], "claim": ""}).status_code == 400
    assert c.post("/connect/angelone/confirm", headers=ADMIN, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400  # another broker's route
    assert db.get_setting(state.KEY + BASIC_ID) is None
    assert c.post("/connect/upstox/confirm", headers=PRO, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 200
    assert c.post("/connect/upstox/confirm", headers=PRO, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400  # once
    _, q = login(c, "upstox", BASIC)
    _, got = back(c, "upstox", {"code": "good-code", "state": q["state"]})
    real = time.time()
    monkeypatch.setattr(time, "time", lambda: real + brokers.PENDING_TTL + 5)
    assert c.post("/connect/upstox/confirm", headers=BASIC, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400
    assert db.get_setting(state.KEY + BASIC_ID) is None


def test_upstox_login_ends_and_a_refused_token(w, fake, monkeypatch):
    c = w["client"]
    assert connect(c, "upstox").status_code == 200
    assert c.post("/connect/upstox/refresh", headers=ADMIN).status_code == 200
    later = datetime.now(timezone.utc) + timedelta(days=1, hours=1)                 # past 03:30 next morning
    monkeypatch.setattr(brokers, "_now", lambda: later)
    r = c.post("/connect/upstox/refresh", headers=ADMIN)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "login_needed"
    assert r.json()["detail"]["message"] == "Your Upstox login has ended. Log in again."
    v = card(c, "upstox")
    assert v["connected"] and v["expired"] and not v["live"] and v["ends_at"] is None


def test_upstox_refused_token_mid_day(w, fake):
    c = w["client"]
    connect(c, "upstox")
    fake.upstox_status = 401
    r = c.post("/connect/upstox/refresh", headers=ADMIN)
    assert r.status_code == 409 and state.section(ADMIN_ID, "upstox")["status"] == "expired"
    assert card(c, "upstox")["expired"] is True
    fake.upstox_status = 500
    connect(c, "upstox")
    r = c.post("/connect/upstox/refresh", headers=ADMIN)
    assert r.status_code == 502 and r.json()["detail"]["message"] == "Upstox didn't answer. Try again in a few minutes."


def test_an_empty_reply_keeps_what_was_read(w, fake):
    c = w["client"]
    connect(c, "upstox")
    fake.upstox_holdings = []
    assert c.post("/connect/upstox/refresh", headers=ADMIN).status_code == 200
    assert {i["symbol"] for i in holdings.load(ADMIN_ID)["items"]} == {"INFY", "ITC"}
    assert "returned no holdings" in card(c, "upstox")["detail"]


def test_a_sold_stock_leaves(w, fake):
    c = w["client"]
    connect(c, "upstox")
    fake.upstox_holdings = fake.upstox_holdings[:1]
    assert c.post("/connect/upstox/refresh", headers=ADMIN).status_code == 200
    assert {i["symbol"] for i in holdings.load(ADMIN_ID)["items"]} == {"INFY"}


# ---------- Angel One ----------
def test_angelone_login_address(w, fake):
    url, q = login(w["client"], "angelone")
    assert url.startswith(brokers.ANGEL_LOGIN + "?") and q["api_key"] == "angel-key"
    assert brokers.read_state(q["state"]) == (ADMIN_ID, "angelone")


def test_angelone_round_trip_and_its_headers(w, fake):
    c = w["client"]
    r = connect(c, "angelone")
    assert r.status_code == 200, r.text
    items = {i["symbol"]: i for i in holdings.load(ADMIN_ID)["items"]}
    assert set(items) == {"TATASTEEL", "SBIN"}                                       # "-EQ" and "-BE" aren't part of the symbol
    assert items["TATASTEEL"]["qty"] == 2 and items["TATASTEEL"]["avg"] == 111.87
    # SBIN on BSE (no total: settled 5 + T+1 3) and NSE (2) is one holding
    assert items["SBIN"]["qty"] == 10 and items["SBIN"]["avg"] == pytest.approx((573.1 * 8 + 600 * 2) / 10)
    assert all(i["via"] == "angelone" for i in items.values()) and holdings.load(ADMIN_ID)["source"] == "Angel One login"
    req = next(x for x in fake.seen if str(x.url) == brokers.ANGEL_HOLDINGS)
    h = req.headers
    assert req.method == "GET" and h["authorization"] == f"Bearer {ANGEL_TOKEN}" and h["x-privatekey"] == "angel-key"
    assert h["x-usertype"] == "USER" and h["x-sourceid"] == "WEB" and h["x-clientlocalip"] and h["x-clientpublicip"] and h["x-macaddress"].count(":") == 5
    v = card(c, "angelone")
    assert v["live"] and v["account"] == "A123456"
    ends = datetime.fromisoformat(v["ends_at"]).astimezone(IST)
    assert (ends.hour, ends.minute) == (0, 0)                                        # SmartAPI logins last until midnight
    raw = json.dumps(db.get_setting(state.KEY + ADMIN_ID))
    box = state.section(ADMIN_ID, "angelone")
    assert ANGEL_TOKEN not in raw and not {"feed_token", "refresh_token", "feed", "refresh"} & set(box)   # only the session token is kept


def test_angelone_without_a_returned_state_needs_the_users_own_tap(w, fake, monkeypatch):
    monkeypatch.setattr(settings, "ANGELONE_FOR_ALL", True)
    c = w["client"]
    login(c, "angelone", PRO)                                                        # PRO tapped Connect; BASIC didn't
    _, got = back(c, "angelone", {"auth_token": ANGEL_TOKEN})
    assert got["b"] == "confirm"
    assert c.post("/connect/angelone/confirm", headers=BASIC, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400
    assert c.post("/connect/angelone/confirm", headers=PRO, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 200
    # the tap works once
    _, got = back(c, "angelone", {"auth_token": ANGEL_TOKEN})
    assert c.post("/connect/angelone/confirm", headers=PRO, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400
    # an old tap doesn't count
    login(c, "angelone", BASIC)
    real = time.time()
    monkeypatch.setattr(time, "time", lambda: real + brokers.START_TTL + 30)
    _, got = back(c, "angelone", {"auth_token": ANGEL_TOKEN})
    assert c.post("/connect/angelone/confirm", headers=BASIC, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 400


def test_angelone_refuses_a_token_that_isnt_one_and_says_when_it_ended(w, fake):
    c = w["client"]
    _, q = login(c, "angelone")
    assert back(c, "angelone", {"auth_token": "not-a-jwt", "state": q["state"]})[1]["b"] == "failed"
    connect(c, "angelone")
    fake.angel_error = "AG8001"
    r = c.post("/connect/angelone/refresh", headers=ADMIN)
    assert r.status_code == 409 and r.json()["detail"]["message"] == "Your Angel One login has ended. Log in again."
    assert card(c, "angelone")["expired"]


def test_angelone_empty_holdings_keep_the_last_read(w, fake):
    c = w["client"]
    connect(c, "angelone")
    fake.angel_holdings = None
    assert c.post("/connect/angelone/refresh", headers=ADMIN).status_code == 200
    assert {i["symbol"] for i in holdings.load(ADMIN_ID)["items"]} == {"TATASTEEL", "SBIN"}


# ---------- Dhan ----------
def test_dhan_login_asks_for_a_consent_first(w, fake):
    url, q = login(w["client"], "dhan")
    assert url == f"{brokers.DHAN_LOGIN}?consentAppId=940b0ca1-consent"
    req = next(x for x in fake.seen if str(x.url.copy_with(query=None)) == brokers.DHAN_CONSENT)
    assert req.method == "POST" and req.url.params["client_id"] == "1000000001"
    assert req.headers["app_id"] == "dhan-app" and req.headers["app_secret"] == "dhan-secret-value"


def test_dhan_round_trip(w, fake):
    c = w["client"]
    r = connect(c, "dhan")
    assert r.status_code == 200, r.text
    consume = next(x for x in fake.seen if str(x.url.copy_with(query=None)) == brokers.DHAN_CONSUME)
    assert consume.method == "GET" and consume.url.params["tokenId"] == "good-token-id" and consume.headers["app_secret"] == "dhan-secret-value"
    items = {i["symbol"]: i for i in holdings.load(ADMIN_ID)["items"]}
    assert items["HDFCBANK"]["qty"] == 10 and items["HDFCBANK"]["avg"] == 1500.0
    assert items["TCS"]["qty"] == 4 and items["TCS"]["avg"] is None                  # no total: in demat + T+1; a NaN cost is no cost
    assert all(i["via"] == "dhan" for i in items.values()) and holdings.load(ADMIN_ID)["source"] == "Dhan login"
    req = next(x for x in fake.seen if str(x.url) == brokers.DHAN_HOLDINGS)
    assert req.method == "GET" and req.headers["access-token"] == DHAN_TOKEN and req.headers["client-id"] == "1000000001"
    v = card(c, "dhan")
    # Dhan says when the login ends (India time, with no zone)
    assert v["live"] and datetime.fromisoformat(v["ends_at"]).astimezone(IST).replace(tzinfo=None) == datetime.fromisoformat(fake.dhan_expiry).replace(second=0)
    assert DHAN_TOKEN not in json.dumps(db.get_setting(state.KEY + ADMIN_ID))


def test_dhan_individual_app_is_for_its_owners_account_only(w, fake):
    fake.dhan_client = "2000000002"
    c = w["client"]
    login(c, "dhan")
    assert back(c, "dhan", {"tokenId": "good-token-id"})[1]["b"] == "refused"
    assert back(c, "dhan", {})[1]["b"] == "cancelled"
    assert not card(c, "dhan")["connected"]


def test_dhan_partner_flow(w, fake, monkeypatch):
    monkeypatch.setattr(settings, "DHAN_PARTNER_ID", "partner")
    monkeypatch.setattr(settings, "DHAN_PARTNER_SECRET", "partner-secret")
    monkeypatch.setattr(settings, "DHAN_FOR_ALL", True)
    fake.dhan_client = "3000000003"                                                 # any account, through the partner app
    c = w["client"]
    url, _ = login(c, "dhan", PRO)
    assert url == f"{brokers.DHAN_PARTNER_LOGIN}?consentId=partner-consent"
    _, got = back(c, "dhan", {"tokenId": "good-token-id"})
    assert c.post("/connect/dhan/confirm", headers=PRO, json={"ref": got["bs"], "claim": got["bc"]}).status_code == 200
    req = next(x for x in fake.seen if str(x.url.copy_with(query=None)) == brokers.DHAN_PARTNER_CONSUME)
    assert req.headers["partner_id"] == "partner" and "app_id" not in req.headers


def test_dhan_ended_and_no_holdings(w, fake):
    c = w["client"]
    connect(c, "dhan")
    fake.dhan_status, fake.dhan_holdings = 400, {"errorType": "Holding_Error", "errorCode": "DH-1111", "errorMessage": "No holdings available"}
    assert c.post("/connect/dhan/refresh", headers=ADMIN).status_code == 200
    assert {i["symbol"] for i in holdings.load(ADMIN_ID)["items"]} == {"HDFCBANK", "TCS"}        # kept: an empty reply isn't "sold"
    fake.dhan_status, fake.dhan_holdings = 401, {"errorType": "Invalid_Authentication", "errorCode": "DH-901", "errorMessage": "expired"}
    r = c.post("/connect/dhan/refresh", headers=ADMIN)
    assert r.status_code == 409 and card(c, "dhan")["expired"]


def test_dhan_says_when_it_doesnt_answer(w, fake, monkeypatch):
    def down(req):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(brokers, "transport", httpx.MockTransport(down))
    r = w["client"].get("/connect/dhan/login", headers=ADMIN)
    assert r.status_code == 502 and r.json()["detail"]["message"] == "Dhan didn't answer. Try again in a few minutes."


# ---------- holdings from each broker, odd fields ----------
def test_rows_from_odd_fields():
    up = brokers.ALL["upstox"].rows([
        {"tradingsymbol": "infy", "isin": "ine009a01021", "quantity": "3", "t1_quantity": "x", "average_price": None},
        {"trading_symbol": "INFY", "isin": "INE009A01021", "exchange": "BSE", "quantity": 1, "average_price": 100},
        {"trading_symbol": "", "isin": "", "quantity": 5},
        {"trading_symbol": "NEG", "quantity": -4, "average_price": 10},
        {"trading_symbol": "INF", "quantity": float("inf")}])
    assert up == [{"symbol": "INFY", "isin": "INE009A01021", "name": "INFY", "qty": 4, "avg": None}]   # one cost unknown: no average
    angel = brokers.ALL["angelone"].rows([{"tradingsymbol": "BAJAJ-AUTO-EQ", "isin": "INE917I01010", "quantity": 1, "averageprice": "0"},
                                          {"tradingsymbol": "", "isin": "INE000X01010", "quantity": 2, "averageprice": 5}])
    assert angel == [{"symbol": "BAJAJ-AUTO", "isin": "INE917I01010", "name": "BAJAJ-AUTO", "qty": 1, "avg": None},
                     {"symbol": "INE000X01010", "isin": "INE000X01010", "name": "INE000X01010", "qty": 2, "avg": 5.0}]
    assert brokers.ALL["dhan"].rows([{"tradingSymbol": "X", "totalQty": 0, "dpQty": 0, "t1Qty": 0}]) == []


def test_reply_shapes_that_arent_lists(w, fake):
    up, angel, dhan = (brokers.ALL[k] for k in ("upstox", "angelone", "dhan"))
    fake.upstox_holdings = {"odd": True}
    assert up.fetch("t") == []
    fake.angel_holdings = [{"tradingsymbol": "A-EQ"}, "junk", 3]
    assert angel.fetch("t") == [{"tradingsymbol": "A-EQ"}]
    fake.dhan_holdings = {"errorCode": "DH-908", "errorMessage": "server"}
    with pytest.raises(brokers.BrokerError) as e:
        dhan.fetch("t")
    assert not e.value.expired


# ---------- read-only, secrets, disconnect ----------
def test_only_read_only_broker_addresses_are_called(w, fake):
    c = w["client"]
    for key in brokers.ALL:
        connect(c, key)
        c.post(f"/connect/{key}/refresh", headers=ADMIN)
        c.delete(f"/connect/{key}", headers=ADMIN)
    called = {str(x.url.copy_with(query=None)) for x in fake.seen}
    assert called and called <= brokers.READ_ONLY
    assert not any(w_ in u for u in called for w_ in ("order", "fund", "margin", "gtt", "convert", "edis", "payout"))
    with pytest.raises(RuntimeError):
        brokers._http("POST", "https://api.upstox.com/v2/order/place")
    with pytest.raises(RuntimeError):
        brokers._http("POST", "https://api.dhan.co/v2/orders")


def test_tokens_never_reach_the_logs(w, fake, caplog):
    caplog.set_level(logging.DEBUG)
    c = w["client"]
    for key in brokers.ALL:
        connect(c, key)
    for tok in (UPSTOX_TOKEN, ANGEL_TOKEN, DHAN_TOKEN, "good-code", "good-token-id"):
        assert tok not in caplog.text
    # an access log line of a callback is masked too
    line = redact.mask(f"GET /connect/angelone/callback?auth_token={ANGEL_TOKEN}&feed_token=feed1&refresh_token=ref1&state=b1.x")
    assert ANGEL_TOKEN not in line and "feed1" not in line and "ref1" not in line
    assert "good-token-id" not in redact.mask("GET /connect/dhan/callback?tokenId=good-token-id")
    assert "good-code" not in redact.mask("GET /connect/upstox/callback?code=good-code&state=b1.x")


def test_disconnecting_deletes_the_token_and_keeps_the_holdings(w, fake):
    c = w["client"]
    for key in brokers.ALL:
        connect(c, key)
        r = c.delete(f"/connect/{key}", headers=ADMIN)
        assert r.status_code == 200 and not next(b for b in r.json()["brokers"] if b["key"] == key)["connected"]
        assert state.section(ADMIN_ID, key) == {}
    items = holdings.load(ADMIN_ID)["items"]
    assert items and not any(i.get("via") for i in items)                         # what was read stays, no longer synced


def test_deleting_everything_deletes_waiting_logins(w, fake):
    c = w["client"]
    _, q = login(c, "upstox")
    back(c, "upstox", {"code": "good-code", "state": q["state"]})
    login(c, "dhan")
    assert db.all_settings_with_prefix(brokers.PENDING) and db.get_setting(f"{brokers.START}dhan:{ADMIN_ID}")
    c.delete("/connect", headers=ADMIN)
    assert not db.all_settings_with_prefix(brokers.PENDING) and not db.get_setting(f"{brokers.START}dhan:{ADMIN_ID}")


def test_my_holdings_names_the_brokers_that_can_connect(w, fake, monkeypatch):
    c = w["client"]
    connect(c, "upstox")
    h = c.get("/holdings", headers=ADMIN).json()
    assert {"Upstox", "Angel One", "Dhan"} <= set(h["brokers_open"])
    assert h["brokers"] == [{"key": "upstox", "name": "Upstox", "live": True, "count": 2, "read_at": h["brokers"][0]["read_at"]}]
    p = c.get("/holdings", headers=PRO).json()
    assert p["brokers_open"] == [] and p["brokers"] == []
    monkeypatch.setattr(settings, "ANGELONE_FOR_ALL", True)
    assert c.get("/holdings", headers=PRO).json()["brokers_open"] == ["Angel One"]


def test_a_broker_read_outranks_a_statement_like_zerodha(w, fake):
    from app.connect import sync
    assert sync.PRIORITY["upstox"] == sync.PRIORITY["kite"] > sync.PRIORITY["cas"]
    assert set(brokers.ALL) <= set(holdings.SYNCED) and holdings.VIA_NAMES["angelone"] == "Angel One"


def test_the_broker_picked_is_kept_on_the_account(w):
    c = w["client"]
    assert "broker" not in c.put("/me/prefs", headers=PRO, json={"level": "some"}).json()["prefs"]      # none picked yet
    assert c.put("/me/prefs", headers=PRO, json={"broker": "groww"}).json()["prefs"]["broker"] == "groww"
    assert c.put("/me/prefs", headers=PRO, json={"level": "pro"}).json()["prefs"]["broker"] == "groww"   # another change keeps it
    assert c.get("/me", headers=PRO).json()["prefs"]["broker"] == "groww"
    for bad in ("Groww!", "x", "a" * 30):
        assert c.put("/me/prefs", headers=PRO, json={"broker": bad}).status_code == 422
