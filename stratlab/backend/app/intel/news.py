"""Headlines from Google News RSS (India, and market-wide) and company facts from Wikipedia."""
import re
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

from .net import Source, SourceError


class GoogleNews(Source):
    name = "Google News"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://news.google.com", per_minute=30, burst=8, transport=transport)

    def search(self, query: str, region: str = "IN", limit: int = 10) -> list[dict]:
        gl, ceid = ("IN", "IN:en") if region == "IN" else ("US", "US:en")
        xml = self.fetch("/rss/search", {"q": query, "hl": f"en-{gl}", "gl": gl, "ceid": ceid}, ttl=1800, kind="text")
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError:
            raise SourceError(self.name, "Google News sent an unreadable feed.") from None
        out = []
        for item in root.iter("item"):
            title = unescape((item.findtext("title") or "").strip())
            source = unescape((item.findtext("source") or "").strip())
            if source and title.endswith(" - " + source):
                title = title[: -(len(source) + 3)]
            ts = None
            pub = item.findtext("pubDate")
            if pub:
                try:
                    ts = parsedate_to_datetime(pub).isoformat()
                except (TypeError, ValueError):
                    ts = None
            if title:
                out.append({"headline": title, "url": (item.findtext("link") or "").strip(),
                            "source": source or "Google News", "at": ts})
            if len(out) >= limit:
                break
        return out


_SUFFIX = re.compile(r"\s+(Inc|Corp|Corporation|Co|Company|Ltd|Limited|PLC|Group|Holdings?|SA|AG|NV|SE)\.?$", re.I)


class Wikipedia(Source):
    name = "Wikipedia"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://en.wikipedia.org", per_minute=60, burst=10, transport=transport)

    def _summary(self, title: str) -> dict | None:
        try:
            d = self.fetch(f"/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}", ttl=7 * 86400)
        except SourceError:
            return None
        if not d or not d.get("extract") or d.get("type") == "disambiguation":
            return None
        url = ((d.get("content_urls") or {}).get("desktop") or {}).get("page") or \
            f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
        return {"title": d.get("title"), "description": d.get("description"), "extract": d["extract"], "url": url}

    def company(self, name: str) -> dict | None:
        if not name:
            return None
        clean = _SUFFIX.sub("", name.strip()) or name
        try:
            s = self.fetch("/w/api.php", {"action": "query", "list": "search", "srsearch": f"{clean} company",
                                          "srlimit": 1, "format": "json"}, ttl=7 * 86400)
            hit = ((s or {}).get("query") or {}).get("search") or []
            if hit:
                r = self._summary(hit[0]["title"])
                if r:
                    return r
        except SourceError:
            pass
        return self._summary(clean)
