"""Long daily histories kept as one small value each: JSON, deflated, as text (the settings table holds text). A year of an
ETF's closes and NAVs is about 6 KB this way, and a week's margin-funding points for every stock about 4 KB."""
import base64
import json
import zlib


def pack(obj) -> str:
    return base64.b64encode(zlib.compress(json.dumps(obj, separators=(",", ":")).encode(), 6)).decode()


def unpack(raw) -> dict:
    """The value `pack` made; {} for nothing stored, or text that is damaged."""
    try:
        got = json.loads(zlib.decompress(base64.b64decode(str(raw))))
        return got if isinstance(got, dict) else {}
    except (ValueError, zlib.error, TypeError):
        return {}
