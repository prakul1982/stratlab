"""The API for Settings -> Connected accounts: GET /connect (everything's state), the statement inbox, an upload that uses the
same reader, Zerodha login, Interactive Brokers (Flex) and the EPF / NPS / AIS uploads, plus the mail service's webhook.

Nothing secret ever leaves here: an address, dates, counts and plain-words statuses. Every route is for the signed-in user's
own data only (the user id comes from the sign-in, never from the request)."""
import base64
import binascii
import re

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field, field_validator

from ..auth import current_profile
from ..config import settings
from ..responses import err, ok
from . import docs, ibkr, inbound, kite_user, state, statements, vault

router = APIRouter(prefix="/connect", tags=["connect"])
hook_router = APIRouter(tags=["connect"])
_throttle = None


def setup(throttle) -> None:
    """The app's per-user action limit (main.py)."""
    global _throttle
    _throttle = throttle


def _limit(profile, what: str, times: int, message: str = "That's a lot of tries in an hour. Try again a little later."):
    if _throttle:
        _throttle(profile, what, times, 3600, message)


def _decode(data: str, limit: int) -> bytes:
    raw = re.sub(r"^data:[^,]{0,200},", "", data.strip())
    if len(raw) > limit * 4 // 3 + 16:
        err(413, "file_too_big", f"That file is larger than {limit // (1024 * 1024)} MB.")
    try:
        out = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        err(400, "bad_upload", "The file didn't arrive whole. Pick it again.")
    if not out:
        err(400, "bad_upload", "The file is empty.")
    return out


# ---------- state ----------
def view(profile: dict) -> dict:
    uid = profile["id"]
    box = state.section(uid, "inbox")
    address = inbound.address_of(box["local"]) if box.get("local") and inbound.configured() else None
    k = kite_user.status(uid, profile)
    k["refreshed_label"] = kite_user.when_label(k["refreshed_at"])
    confirm = box.get("confirm")
    return {
        "inbox": {"ready": inbound.configured(), "address": address, "has_password": bool(box.get("pw")), "last": box.get("last"),
                  "forwarding_code": confirm if confirm and (state.now() < _plus_days(confirm.get("at"), 3)) else None,
                  "created_at": box.get("created_at")},
        "kite": k,
        "ibkr": ibkr.status(uid),
        "docs": {kd: (state.section(uid, "docs").get(kd) or None) for kd in docs.KINDS},
        "storage_ready": vault.ready(),
    }


def _plus_days(iso: str | None, days: int) -> str:
    from datetime import datetime, timedelta
    try:
        return (datetime.fromisoformat(iso) + timedelta(days=days)).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return ""


@router.get("")
def connect_view(profile=Depends(current_profile)):
    """Where each connection stands: the statement inbox (address, last mail), Zerodha, Interactive Brokers, uploaded figures."""
    return ok(view(profile))


@router.delete("")
def connect_delete(profile=Depends(current_profile)):
    """Disconnect everything: the forwarding address, every stored password and token."""
    kite_user.disconnect(profile["id"])
    state.drop_all(profile["id"])
    return {"deleted": True}


# ---------- the statement inbox ----------
class PasswordReq(BaseModel):
    password: str = Field(..., min_length=1, max_length=64)


@router.post("/inbox")
def inbox_turn_on(profile=Depends(current_profile)):
    """Make the user's private forwarding address (the same one again if it already exists)."""
    _limit(profile, "connect_addr", 12)
    if not inbound.configured():
        err(503, "not_set_up", "Not set up yet.")
    inbound.ensure_address(profile["id"])
    return ok(view(profile))


@router.put("/inbox/password")
def inbox_password(req: PasswordReq, profile=Depends(current_profile)):
    """Keep the statement password (encrypted) so the inbox can open locked statements. Never shown again."""
    _limit(profile, "connect_pw", 20)
    if not vault.ready():
        err(503, "not_set_up", "Not set up yet.")
    pw = req.password.strip()
    if not pw or any(ord(c) < 32 for c in pw):
        err(400, "bad_password", "Enter the password as you use it to open the statement.")
    state.update(profile["id"], "inbox", pw=vault.seal(pw))
    return ok(view(profile))


@router.delete("/inbox/password")
def inbox_password_delete(profile=Depends(current_profile)):
    state.update(profile["id"], "inbox", pw=None)
    return ok(view(profile))


@router.post("/inbox/new-address")
def inbox_new_address(profile=Depends(current_profile)):
    """A new forwarding address; the old one stops working at once."""
    _limit(profile, "connect_addr", 6)
    if not inbound.configured():
        err(503, "not_set_up", "Not set up yet.")
    inbound.new_address(profile["id"])
    return ok(view(profile))


@router.delete("/inbox")
def inbox_delete(profile=Depends(current_profile)):
    """Turn the inbox off: the address stops working and the stored password is deleted."""
    state.drop(profile["id"], "inbox")
    return ok(view(profile))


class StatementReq(BaseModel):
    filename: str = Field("", max_length=200)
    data: str = Field(..., max_length=statements.MAX_PDF * 4 // 3 + 64)
    password: str = Field("", max_length=64)
    remember: bool = False


@router.post("/statement")
async def upload_statement(req: StatementReq, profile=Depends(current_profile)):
    """The fallback to the inbox: upload a CAMS, KFintech, NSDL or CDSL statement (PDF) by hand. Read by the same code."""
    _limit(profile, "connect_statement", 30, "That's a lot of uploads in an hour. Try again a little later.")
    data = _decode(req.data, statements.MAX_PDF)
    pw = req.password.strip()
    if pw and req.remember and vault.ready():
        await run_in_threadpool(state.update, profile["id"], "inbox", pw=vault.seal(pw))
    got = await run_in_threadpool(statements.process, profile["id"], data, req.filename, [pw] if pw else [], "upload")
    if not got["ok"]:
        code = "wrong_password" if got["status"] in ("wrong_password", "no_password") else "bad_file"
        err(400, code, got["detail"])
    return ok({**got, "connect": await run_in_threadpool(view, profile)})


# ---------- Zerodha ----------
@router.get("/kite/login")
def kite_login(profile=Depends(current_profile)):
    """The address to log in at Zerodha. Open only once Zerodha has approved the multi-user app (the owner can always)."""
    _limit(profile, "connect_kite", 30)
    if not kite_user.allowed(profile):
        err(403, "not_open", "Zerodha login isn't open yet.")
    try:
        # the owner's own account is already logged in for the market data: share that login (a second one would
        # cancel it), and come straight back to Settings (R5O-031)
        if kite_user.link_shared(profile["id"], profile) is not None:
            return ok({"url": settings.PUBLIC_SITE_URL + "/settings?kite=ok#accounts", "shared": True})
    except kite_user.KiteConnectError:
        pass
    return ok({"url": kite_user.login_url(profile["id"], profile)})


def _kite_done(request_token: str, status: str, st: str) -> RedirectResponse:
    where = settings.PUBLIC_SITE_URL + "/settings?kite={}#accounts"
    if status != "success" or not request_token:
        return RedirectResponse(where.format("cancelled"), status_code=303)
    try:
        kite_user.complete(request_token, st)
    except kite_user.KiteConnectError:
        return RedirectResponse(where.format("failed"), status_code=303)
    return RedirectResponse(where.format("ok"), status_code=303)


@router.get("/kite/callback")
def kite_callback(request_token: str = "", status: str = "", state: str = ""):
    """Where Zerodha sends the user back (set as the redirect address of the Kite app); no sign-in is needed, the signed
    state says who started the login and for how long."""
    return _kite_done(request_token, status, state)


@router.post("/kite/refresh")
async def kite_refresh(profile=Depends(current_profile)):
    """Read holdings and positions again. When today's login has ended, say so (with the login address)."""
    _limit(profile, "connect_kite_refresh", 30)
    if not kite_user.allowed(profile):
        err(403, "not_open", "Zerodha login isn't open yet.")
    try:
        got = await run_in_threadpool(kite_user.refresh, profile["id"])
    except kite_user.KiteConnectError as e:
        if e.expired:
            err(409, "login_needed", e.message)
        err(502, "broker_error", e.message)
    return ok({**got, "connect": await run_in_threadpool(view, profile)})


@router.delete("/kite")
def kite_delete(profile=Depends(current_profile)):
    """Disconnect Zerodha: the stored login is deleted. Holdings already read stay in My Holdings."""
    kite_user.disconnect(profile["id"])
    return ok(view(profile))


# ---------- Interactive Brokers ----------
class IbkrReq(BaseModel):
    token: str = Field(..., min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._~-]+$")
    query_id: str = Field(..., min_length=3, max_length=20, pattern=r"^\d+$")
    expires: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.put("/ibkr")
async def ibkr_connect(req: IbkrReq, profile=Depends(current_profile)):
    """Connect Interactive Brokers: the Flex token and query id are tried once, then kept (encrypted) for the daily read."""
    _limit(profile, "connect_ibkr", 12)
    if not vault.ready():
        err(503, "not_set_up", "Not set up yet.")
    try:
        got = await run_in_threadpool(ibkr.connect, profile["id"], req.token, req.query_id, req.expires)
    except ibkr.FlexError as e:
        err(400, e.code, e.message)
    return ok({**got, "connect": await run_in_threadpool(view, profile)})


@router.post("/ibkr/refresh")
async def ibkr_refresh(profile=Depends(current_profile)):
    _limit(profile, "connect_ibkr_refresh", 6)
    try:
        got = await run_in_threadpool(ibkr.sync_user, profile["id"])
    except ibkr.FlexError as e:
        err(400, e.code, e.message)
    return ok({**got, "connect": await run_in_threadpool(view, profile)})


@router.delete("/ibkr")
def ibkr_delete(profile=Depends(current_profile)):
    """Disconnect: the stored token and query id are deleted. Positions and trades already read stay."""
    ibkr.disconnect(profile["id"])
    return ok(view(profile))


# ---------- EPF, NPS, AIS ----------
class DocReadReq(BaseModel):
    kind: str = Field(..., pattern="^(epf|nps|ais)$")
    filename: str = Field("", max_length=200)
    data: str = Field(..., max_length=docs.MAX_FILE * 4 // 3 + 64)
    password: str = Field("", max_length=64)


@router.post("/docs/read")
async def docs_read(req: DocReadReq, profile=Depends(current_profile)):
    """Look in an uploaded file for the figures (nothing is saved, the file isn't kept): what was found, to check."""
    _limit(profile, "connect_docs", 60, "That's a lot of uploads in an hour. Try again a little later.")
    data = _decode(req.data, docs.MAX_FILE)
    try:
        return ok(await run_in_threadpool(docs.read_doc, req.kind, data, req.filename, req.password))
    except docs.DocError as e:
        err(400, e.code, e.message)


class DocConfirmReq(BaseModel):
    kind: str = Field(..., pattern="^(epf|nps|ais)$")
    figures: dict[str, str | float | int | None] = Field(..., max_length=12)
    apply_tds: bool = False
    lines: list[dict] = Field(default_factory=list, max_length=500)

    @field_validator("figures")
    @classmethod
    def _small_figures(cls, v: dict) -> dict:
        """Figures are a few numbers and dates: what is saved with the user's record stays small."""
        if any(len(k) > 30 or (isinstance(x, str) and len(x) > 40) for k, x in v.items()):
            raise ValueError("figures are short numbers and dates")
        return v

    @field_validator("lines")
    @classmethod
    def _small_lines(cls, v: list[dict]) -> list[dict]:
        for line in v:
            if len(line) > 12 or any(len(str(k)) > 20 or not (x is None or isinstance(x, (str, int, float, bool))) or (isinstance(x, str) and len(x) > 120)
                                     for k, x in line.items()):
                raise ValueError("a dividend line is a few short values")
        return v


@router.post("/docs/confirm")
def docs_confirm(req: DocConfirmReq, profile=Depends(current_profile)):
    """Save the figures the user checked: Net worth (EPF, NPS), Tax tools and dividends (AIS)."""
    _limit(profile, "connect_docs_confirm", 60)
    try:
        got = docs.confirm(profile, req.kind, req.figures, req.apply_tds, req.lines)
    except docs.DocError as e:
        err(400, e.code, e.message)
    return ok({**got, "connect": view(profile)})


# ---------- the mail service's webhook ----------
@hook_router.post("/inbound/email/{provider}")
async def inbound_email(provider: str, request: Request):
    """Incoming mail for a statement inbox. Signed or secret-carrying posts only; answers 200 whatever it did with the mail."""
    body = await request.body()
    status = await run_in_threadpool(inbound.receive, provider, dict(request.headers), dict(request.query_params), body)
    return Response(status_code=status)
