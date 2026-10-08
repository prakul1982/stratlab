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
        if "<!DOCTYPE" in xml[:2000].upper() or "<!ENTITY" in xml.upper():
            # a news feed never needs a DTD; refusing one rules out entity-expansion tricks
            raise SourceError(self.name, "Google News sent an unexpected feed.")
        try:
            root = ElementTree.fromstring(xml)   # nosec B314: a feed with a DTD is refused above
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
        """The company's own article, or None. A search's top hit (or a page under the name) that isn't about this
        company (another of the group's companies, a person, a place) is never shown as its description."""
        if not name:
            return None
        clean = _SUFFIX.sub("", name.strip()) or name
        try:
            s = self.fetch("/w/api.php", {"action": "query", "list": "search", "srsearch": f"{clean} company",
                                          "srlimit": 1, "format": "json"}, ttl=7 * 86400)
            hit = ((s or {}).get("query") or {}).get("search") or []
            if hit and is_about(clean, hit[0].get("title") or ""):
                r = self._summary(hit[0]["title"])
                if r and is_about(clean, r.get("title") or hit[0]["title"]):
                    return r
        except SourceError:
            pass
        r = self._summary(clean)
        return r if r and is_about(clean, r.get("title") or clean) else None


# words that name no company on their own: a match on these alone could be any company of a group or a country
_GENERIC = {"the", "of", "and", "&", "india", "indian", "limited", "ltd", "company", "co", "corporation", "corp", "inc",
            "group", "holdings", "holding", "plc", "sa", "ag", "nv", "se"}
# group names many listed companies share ("Tata Steel" and "Tata Consultancy Services")
_GROUPS = {"tata", "adani", "bajaj", "birla", "mahindra", "hindustan", "bharat", "state", "national", "jsw", "hdfc",
           "icici", "kotak", "godrej", "jindal", "aditya", "bank", "power", "steel", "oil", "coal"}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", unescape(text).lower().replace("&", " and "))]


def is_about(name: str, title: str) -> bool:
    """Whether an article or headline titled `title` names the company `name`: every distinctive word of the name in
    it ("Tata Consultancy Services" for "Tata Consultancy Services Limited"), not just a group's or country's name."""
    want = [w for w in _words(_SUFFIX.sub("", name.strip()) or name) if w not in _GENERIC]
    if not want:
        return False
    have = set(_words(title))
    return all(w in have for w in want)


def mentions(name: str, symbol: str, headline: str) -> bool:
    """Whether a headline is about the company: its full name, its symbol as a word ("TCS shares..."), or the name's
    first word where that word is its own ("Infosys", "Reliance"), never a group's shared name alone ("Tata")."""
    if is_about(name, headline):
        return True
    words = _words(headline)
    sym = (symbol or "").lower()
    if len(sym) >= 3 and sym.isalpha() and sym in words and re.search(rf"\b{re.escape(symbol.upper())}\b", headline):
        return True
    own = [w for w in _words(_SUFFIX.sub("", name.strip()) or name) if w not in _GENERIC]
    return bool(own) and len(own[0]) >= 4 and own[0] not in _GROUPS and own[0] in words
