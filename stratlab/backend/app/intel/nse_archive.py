"""The exchange's file archive answers on more than one host, and one can turn this server away while another serves the
same file (fix98, 27 Nov 2026: production's address got 403 on nsearchives.nseindia.com for the list of companies every hour
from 26 Nov 19:51 UTC, while nsearchives.nseindia.in and archives.nseindia.com served the same CSV; release 93 had already
moved the insider-trading documents to the .in host for the same reason).

One rule for every archive file, rather than a patch per address: `mirrors(url)` is the same file on each archive host, the
.in host first (as R93), then .com, then the older archives host; `get(http, url)` asks them in that order and moves on only
when a host refuses (401/403) or can't be reached. Any other answer (the file, a 404, a 5xx) is the archive's answer and is
returned as it is, so a file that isn't published is asked for once, not three times. When every host refuses, the last
refusal is returned (or the last connection error raised), so callers see the failure they always did."""
from __future__ import annotations

import re

import httpx

# the hosts tried for a file, in order (the paths are the same on each: checked 27 Nov for the list of companies, the price-band,
# ban, index, lot-size and ETF files, the bhavcopies, participant files, combined OI and the SLB files)
MIRRORS = ("nsearchives.nseindia.in", "nsearchives.nseindia.com", "archives.nseindia.com")
# every host the exchange links its documents on (allow-lists of links and documents)
HOSTS = ("nsearchives.nseindia.com", "archives.nseindia.com", "nsearchives.nseindia.in", "archives.nseindia.in")
REFUSED = (401, 403)

_URL = re.compile(r"^(https?://)([^/:?#]+)(.*)$", re.S)


def is_archive(url) -> bool:
    """An https address on one of the archive's hosts."""
    m = _URL.match(str(url or ""))
    return bool(m) and m.group(1).lower() == "https://" and m.group(2).lower() in HOSTS and len(m.group(3)) > 1


def mirrors(url: str) -> list[str]:
    """The same file on each archive host, in the order to ask them; any other address as it is."""
    m = _URL.match(str(url or ""))
    if not m or m.group(2).lower() not in HOSTS:
        return [url]
    return [f"https://{h}{m.group(3)}" for h in MIRRORS]


def get(http: httpx.Client, url: str, **kw) -> httpx.Response:
    """GET one archive file through `http`, host after host until one doesn't refuse (see the module's note)."""
    urls = mirrors(url)
    last: httpx.Response | None = None
    for i, u in enumerate(urls):
        try:
            r = http.get(u, **kw)
        except httpx.HTTPError:
            if i == len(urls) - 1:
                if last is not None:
                    return last
                raise
            continue
        if r.status_code not in REFUSED:
            return r
        last = r
    return last


def after_refusal(url: str, tried) -> str | None:
    """For a document read by streaming (a filing's PDF, an offer document's zip) whose link was refused: the same file on the
    next archive host not yet `tried`, in MIRRORS order; None when there is none or the link isn't on the archive."""
    if not is_archive(url):
        return None
    return next((u for u in mirrors(url) if u not in tried), None)
