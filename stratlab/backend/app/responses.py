"""The API's answers, shared by every router: errors as {code, message} with provider names reworded, and JSON with
NaN and infinity sent as null (JSON has no way to write them)."""
import math
from typing import Any, NoReturn

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .branding import public_text


def err(status: int, code: str, message: str, fields: dict[str, str] | None = None) -> NoReturn:
    """Stop the request with `status` and a {code, message} body (`fields`: field -> what is wrong with it, for the page to say
    under that box, LIVE1B-003). A 402 (a plan's feature or limit) is worded through plans.upgrade_note, so every upgrade
    prompt is honest while paid plans can't be bought yet."""
    if status == 402:
        from .plans import named_plan, payments_live, upgrade_note
        # `plan`: the plan the words send the reader to, so the page adds its price in their currency (DP2-022, DP1-018)
        raise HTTPException(status, {"code": code, "message": public_text(upgrade_note(message)), "payments": payments_live(),
                                     "plan": named_plan(message)})
    raise HTTPException(status, {"code": code, "message": public_text(message),
                                 **({"fields": {k: public_text(v) for k, v in fields.items()}} if fields else {})})


def safe(obj: Any) -> Any:
    """`obj` with every NaN or infinite float, however deep, turned into None."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [safe(v) for v in obj]
    return obj


def ok(data: Any) -> JSONResponse:
    return JSONResponse(content=safe(data))
