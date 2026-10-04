"""The API's answers, shared by every router: errors as {code, message} with provider names reworded, and JSON with
NaN and infinity sent as null (JSON has no way to write them)."""
import math
from typing import Any, NoReturn

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .branding import public_text


def err(status: int, code: str, message: str) -> NoReturn:
    """Stop the request with `status` and a {code, message} body."""
    raise HTTPException(status, {"code": code, "message": public_text(message)})


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
