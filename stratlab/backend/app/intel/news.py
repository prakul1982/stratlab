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


# ---------- headlines a page may carry (R7O-005) ----------
# a third party's own trades or picks, worded as advice to whoever reads them: "We're adding to our position in a
# hard-hit stock", "We're buying the dip in a stock…", "What … means for our AI chip stocks", "Which bank stock wins
# the race? Target price", "ICICI Bank prediction for tomorrow"
ADVICE_TITLE = re.compile(
    r"\b(we're|we are|we've|we have|i'm|i am|we)\s+(buying|selling|adding|trimming|starting|initiating|taking|booking|loading|"
    r"doubling|exiting|cutting|dumping|scooping)\b|\bour (position|portfolio|holdings?|stake|club)\b|\bour\b[^.]{0,30}\bstocks?\b"
    r"|\b(buy|sell|accumulate) (the dip|now|these|this|it)\b|\bstocks? to (buy|sell|avoid|accumulate|own)\b|\btop picks?\b"
    r"|\bshould you (buy|sell|hold)\b|\b(buy|sell|hold)\?|\bwhich\b[^?]{0,60}\bwins?\b|\btarget price\b|\bprice target\b"
    r"|\bprediction for (tomorrow|today|next)\b|\bprice prediction\b|\bmultibagger\b|\bbuy or sell\b|\bstock recommendations?\b"
    r"|\btrading (calls?|ideas?|picks?)\b|\bbrokerages? (recommend|suggest)\b"
    # R8O-010: a broker's call with its target ("Buy Tata Consultancy Services; target of Rs 2390: Prabhudas Lilladher"),
    # a question put to the reader ("Should you book profit or invest more?"), upside sold as a bet ("Up to 52% upside …
    # biggest bets for investors"), and a fund putting its own cash to work ("We're putting some of our large cash pile to
    # work in a beaten-down consumer name")
    r"|(^|[:;|]\s*)(buy|sell|accumulate|add|reduce)\b[^.]{0,100}\btarget\b|\btarget (of|at)\s*(rs\.?|₹|\$|inr|usd)"
    r"|\b(maintains?|reiterates?|retains?|upgrades?|downgrades?)\b[^.]{0,40}\b(to |a |an )?['\"]?(buy|sell|accumulate|outperform|underperform|overweight|underweight)\b"
    r"|\bshould you\b|\bbook (some )?profits?\b|\b\d+(\.\d+)?\s?% upside\b|\bupside (of|potential|ahead)\b|\bbiggest bets?\b|\bbets? for investors\b"
    r"|\b(we're|we are|we've|we have|i'm|i am)\s+(putting|deploying|parking|betting|investing)\b|\bputting\b[^.]{0,60}\b(cash|money|capital)\b[^.]{0,40}\bto work\b"
    r"|\b(stocks?|shares?) (that )?(could|can|may) (rally|surge|jump|double|zoom|soar|gain)\b"
    # R8B-012: a question put to the holders ("What should RIL investors do?"), a price move sold as a reason to own it
    # ("What Could Drive Reliance Industries Stock Higher by 15%"), a cheaper way in ("may be a cheaper way to buy Jio
    # Platforms"), brokers' targets in the plural ("Check Goldman Sachs, Morgan Stanley Target Prices") and "What
    # Investors Should Know"
    r"|\bwhat (should|must|can|do)\b[^?.]{0,60}\b(investors?|shareholders?|holders?|traders?|you)\b[^?.]{0,20}\bdo\b"
    r"|\bwhat (could|can|will|might|would|may) (drive|push|take|send|lift|power|fuel)\b[^.]{0,80}\b(higher|up|lower|down|rally|gains?)\b"
    r"|\bcheaper way (to|of) (buy|own|invest|get|play)\w*\b|\btarget prices\b|\bprice targets\b"
    r"|\bwhat (investors?|you|shareholders?|traders?) (should|need to|must|ought to) know\b", re.I)
# a website's own name for itself, not a story ("NSE - National Stock Exchange of India Ltd: Live Share/Stock Market
# News & Updates, Quotes- Nseindia.com")
SITE_TITLE = re.compile(r"\b(live share|stock market news & updates|quotes?\s*-\s*\w+\.(com|in))\b|\.(com|in|org|net)\s*$"
                        r"|^\s*(nse|bse)\s*-\s*(national|bombay) stock exchange\b|\bofficial (website|site)\b|\bhome\s*page\b", re.I)


def plain_headline(title: str | None) -> bool:
    """A headline a page may show: a story, not a site's name for itself, and not a third party's buying or selling
    worded as advice."""
    # typographic apostrophes as plain ones: "We’re adding to our position…" (R7T-009, CNBC's own curly quote) is the
    # same advice-worded title as "We're adding…"
    t = " ".join(str(title or "").replace("’", "'").replace("‘", "'").replace("ʼ", "'").split())
    return bool(t) and not ADVICE_TITLE.search(t) and not SITE_TITLE.search(t)


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
