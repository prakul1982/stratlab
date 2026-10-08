"""Zerodha login for one user (Kite Connect's redirect flow), separate from the app's own data login in kite_service.py.

The user taps "Connect Zerodha", logs in at Zerodha, and Zerodha sends them back with a request token; we swap it (with the
api secret, server side) for an access token, keep it sealed (vault.py), and read their holdings and positions into My
Holdings. Zerodha ends every access token at about 6 am the next morning, so this is "log in once a day": a tap on Refresh
re-reads while the token lives, and after 6 am the same button logs in again.

Off until the owner says Zerodha has approved the multi-user Kite app (KITE_MULTIUSER_APPROVED=true). Until then only the
admin's own account can connect. The redirect URL set in the Kite app is {PUBLIC_API_URL}/connect/kite/callback, or the
existing /admin/kite/callback, which hands user logins here by their state."""
from datetime import datetime
from typing import Callable
from urllib.parse import quote

from .. import admin, mail_tokens
from ..config import settings
from ..kite_service import IST, token_valid, today_ist
from . import state, sync, vault

STATE_PREFIX = "u1."
PURPOSE = "kite-login"


def api_key() -> str:
    return settings.KITE_CONNECT_API_KEY or settings.KITE_API_KEY


def api_secret() -> str:
    return settings.KITE_CONNECT_API_SECRET or settings.KITE_API_SECRET


def make_kite(key: str):
    """The Kite Connect client (replaced by a fake in tests)."""
    from kiteconnect import KiteConnect
    return KiteConnect(api_key=key)


factory: Callable = make_kite


def configured() -> bool:
    return bool(api_key() and api_secret() and vault.ready())


def allowed(profile: dict) -> bool:
    """Everyone once Zerodha has approved the multi-user app; until then only the admin."""
    return configured() and (settings.KITE_MULTIUSER_APPROVED or admin.is_admin(profile))


def login_url(uid: str, profile: dict | None = None) -> str:
    """Where to log in. The state says who is logging in and whether they were let in as the admin (before approval)."""
    kite = factory(api_key())
    st = STATE_PREFIX + mail_tokens.make(uid, PURPOSE, "admin" if profile and admin.is_admin(profile) else "")
    return kite.login_url() + "&redirect_params=" + quote(f"state={st}")


class KiteConnectError(Exception):
    def __init__(self, message: str, expired: bool = False):
        super().__init__(message)
        self.message, self.expired = message, expired


def read_state(st: str) -> tuple[str, str] | None:
    if not st.startswith(STATE_PREFIX):
        return None
    return mail_tokens.read(st[len(STATE_PREFIX):], PURPOSE)


def uid_from_state(st: str) -> str | None:
    got = read_state(st)
    return got[0] if got else None


def complete(request_token: str, st: str) -> dict:
    """Finish a login: swap the request token, keep the access token, read holdings. Raises KiteConnectError."""
    got = read_state(st)
    if not got:
        raise KiteConnectError("This login link has expired. Start again from Settings.")
    uid, via = got
    profile = sync.profile_for(uid)
    if not profile or not configured() or not (settings.KITE_MULTIUSER_APPROVED or via == "admin"):
        raise KiteConnectError("Zerodha login isn't open for this account yet.")
    kite = factory(api_key())
    try:
        data = kite.generate_session(request_token, api_secret=api_secret())
        token = data["access_token"]
    except Exception as e:
        raise KiteConnectError("Zerodha didn't accept that login. Try again.") from None
    state.update(uid, "kite", token=vault.seal(token), kite_user=str(data.get("user_id") or "")[:20], day=today_ist(),
                 status="ok", detail=None, connected_at=state.now())
    return refresh(uid)


def rows_from(holdings: list[dict], positions: list[dict]) -> list[dict]:
    """Kite's holdings and today's equity positions as rows for My Holdings."""
    rows, have = [], set()
    for h in holdings or []:
        qty = float(h.get("quantity") or 0) + float(h.get("t1_quantity") or 0) + float(h.get("collateral_quantity") or 0)
        sym = str(h.get("tradingsymbol") or "")
        if qty <= 0 or not sym:
            continue
        have.add(sym)
        rows.append({"symbol": sym, "isin": h.get("isin") or None, "name": sym, "qty": qty, "avg": float(h.get("average_price") or 0) or None})
    for p in positions or []:
        sym = str(p.get("tradingsymbol") or "")
        if (p.get("product") == "CNC" and p.get("exchange") in ("NSE", "BSE") and float(p.get("quantity") or 0) > 0
                and sym and sym not in have):
            have.add(sym)
            rows.append({"symbol": sym, "isin": None, "name": sym, "qty": float(p["quantity"]),
                         "avg": float(p.get("average_price") or 0) or None})
    return rows


def shared_token(box: dict) -> str | None:
    """Today's token of the app's own data login, when the user's connected Zerodha account is that same account through
    the same Kite app (the owner's). Zerodha keeps one live session per account and app: a second login for My Holdings
    would cancel the data login's token, and the data login logs in again each morning, which ended the owner's holdings
    login every day ("Today's login has ended · last refreshed yesterday") (R5O-031). That account reuses the data
    login's token instead. None for anyone else."""
    if not settings.KITE_USER_ID or api_key() != settings.KITE_API_KEY:
        return None
    if str(box.get("kite_user") or "").upper() != settings.KITE_USER_ID.strip().upper():
        return None
    from .. import db
    tok, day = db.get_setting("kite_access_token"), db.get_setting("kite_token_day")
    return tok if tok and token_valid(day) else None


def refresh(uid: str) -> dict:
    """Re-read holdings and positions with today's token. Raises KiteConnectError(expired=True) when it needs a login."""
    box = state.section(uid, "kite")
    token = vault.unseal(box.get("token"))
    if not token:
        raise KiteConnectError("Connect Zerodha first.", expired=True)
    if not token_valid(box.get("day")):
        shared = shared_token(box)
        if not shared:
            state.update(uid, "kite", status="expired")
            raise KiteConnectError("Today's Zerodha login has ended. Log in again.", expired=True)
        token = shared                   # the same account's data login, already logged in today
        state.update(uid, "kite", token=vault.seal(token), day=today_ist(), shared=True)
    profile = sync.profile_for(uid)
    kite = factory(api_key())
    kite.set_access_token(token)
    try:
        holdings = kite.holdings()
        positions = (kite.positions() or {}).get("net") or []
    except Exception as e:
        if type(e).__name__ == "TokenException":
            state.update(uid, "kite", status="expired")
            raise KiteConnectError("Today's Zerodha login has ended. Log in again.", expired=True) from None
        state.update(uid, "kite", status="error", detail="Zerodha didn't answer. Try again in a few minutes.")
        raise KiteConnectError("Zerodha didn't answer. Try again in a few minutes.") from None
    got = sync.sync_holdings(profile, rows_from(holdings, positions), "kite", "Zerodha Kite")
    state.update(uid, "kite", refreshed_at=state.now(), status="ok", detail=None, count=got["count"])
    return {"count": got["count"], "unmatched": got["unmatched_count"], "added": got["added"], "changed": got["changed"]}


def status(uid: str, profile: dict) -> dict:
    box = state.section(uid, "kite")
    live = bool(box.get("token")) and (token_valid(box.get("day")) or bool(shared_token(box)))
    return {"available": allowed(profile), "configured": configured(), "connected": bool(box.get("token")), "live": live,
            "expired": bool(box.get("token")) and not live, "refreshed_at": box.get("refreshed_at"), "count": box.get("count"),
            "detail": box.get("detail"), "kite_user": box.get("kite_user")}


def disconnect(uid: str) -> None:
    """Forget the connection: the stored token is deleted (and ended at Zerodha when it still lives)."""
    box = state.section(uid, "kite")
    token = vault.unseal(box.get("token"))
    if token and token_valid(box.get("day")) and configured():
        try:
            k = factory(api_key())
            k.invalidate_access_token(token)
        except Exception:
            pass
    state.drop(uid, "kite")


def link_shared(uid: str, profile: dict) -> dict | None:
    """The owner connecting Zerodha when the data login is their own account through the same Kite app: link My Holdings
    to the data login's token instead of a second Zerodha login, which would cancel it. None when that doesn't apply."""
    if not admin.is_admin(profile) or not settings.KITE_USER_ID or api_key() != settings.KITE_API_KEY:
        return None
    if not shared_token({"kite_user": settings.KITE_USER_ID}):
        return None
    tok = shared_token({"kite_user": settings.KITE_USER_ID})
    state.update(uid, "kite", token=vault.seal(tok), kite_user=settings.KITE_USER_ID.strip().upper()[:20], day=today_ist(),
                 status="ok", detail=None, connected_at=state.now(), shared=True)
    return refresh(uid)


REFRESH_FROM = "09:20"          # after the data login (automatic from about 8:30 IST) and the market's open


def run_daily(now: datetime | None = None) -> int:
    """Once a trading morning, re-read My Holdings for an account that shares the data login's token (the owner's), so
    its holdings follow Zerodha without a login each day. How many were read."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if now.strftime("%H:%M") < REFRESH_FROM:
        return 0
    day, done = now.date().isoformat(), 0
    for uid, rec in state.everyone():
        box = rec.get("kite") or {}
        last = box.get("refreshed_at")
        read_today = bool(last) and datetime.fromisoformat(last).astimezone(IST).date().isoformat() == day
        if not box.get("token") or read_today or not shared_token(box):
            continue
        try:
            refresh(uid)
            done += 1
        except KiteConnectError as e:
            print("zerodha daily holdings:", e.message)
    return done


def when_label(iso: str | None) -> str | None:
    """"today 09:12" or "yesterday 09:12" in India time."""
    if not iso:
        return None
    t = datetime.fromisoformat(iso).astimezone(IST)
    days = (datetime.now(IST).date() - t.date()).days
    return f"{'today' if days == 0 else 'yesterday' if days == 1 else t.strftime('%d %b')} {t.strftime('%H:%M')}"
