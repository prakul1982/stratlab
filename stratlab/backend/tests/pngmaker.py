"""Real PNG files for the share-card tests: a one-colour picture of any size, and its base64 form."""
import base64
import struct
import zlib


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def make_png(width: int = 2400, height: int = 1260) -> bytes:
    """A grey picture, compressed: a few kilobytes even at the share cards' 2400x1260."""
    rows = (b"\x00" + b"\x80" * width) * height
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(rows, 9)) + _chunk(b"IEND", b""))


def png_b64(width: int = 2400, height: int = 1260, data_url: bool = True) -> str:
    raw = base64.b64encode(make_png(width, height)).decode()
    return "data:image/png;base64," + raw if data_url else raw
