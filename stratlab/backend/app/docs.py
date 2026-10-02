"""Company documents filed with the exchange (investor presentations, earnings-call transcripts): fetched, turned
into text, and cut down to the passages that matter, so a free AI model can read them.

Only the exchanges' own document hosts are fetched (the links come from a third-party feed), with a size and page
cap, and the text is cached for a week."""
import io
import re
from urllib.parse import urlparse

import httpx

from .intel.net import BROWSER_UA, SourceError, TTLCache

ALLOWED_HOSTS = {"nsearchives.nseindia.com", "archives.nseindia.com", "www.nseindia.com", "www.bseindia.com"}
MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 80
_cache = TTLCache(max_items=300)


def allowed(url: str | None) -> bool:
    try:
        u = urlparse(url or "")
    except ValueError:
        return False
    return u.scheme == "https" and u.hostname in ALLOWED_HOSTS and u.path.lower().endswith(".pdf")


def pdf_text(data: bytes, max_pages: int = MAX_PAGES) -> str:
    from pypdf import PdfReader               # imported here: only these reads need it
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:                     # one bad page mustn't lose the document
            continue
    text = "\n".join(parts)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


class Docs:
    def __init__(self, http: httpx.Client | None = None, transport: httpx.BaseTransport | None = None):
        self.http = http or httpx.Client(timeout=30, transport=transport, follow_redirects=False,
                                         headers={"User-Agent": BROWSER_UA, "Accept": "application/pdf,*/*",
                                                  "Referer": "https://www.nseindia.com/"})

    def text(self, url: str) -> str:
        if not allowed(url):
            raise SourceError("the exchange", "That document isn't on the exchange's own site.")
        hit = _cache.get(url)
        if hit is not None:
            return hit
        try:
            with self.http.stream("GET", url) as r:
                if r.status_code >= 400:
                    raise SourceError("the exchange", f"The document couldn't be downloaded ({r.status_code}).", busy=r.status_code >= 500)
                if 300 <= r.status_code < 400:
                    raise SourceError("the exchange", "The document moved; it wasn't followed.")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise SourceError("the exchange", "The document is too large to read here.")
        except httpx.HTTPError as e:
            raise SourceError("the exchange", f"Couldn't reach the document ({e.__class__.__name__}).", busy=True) from None
        if not bytes(buf[:5]).startswith(b"%PDF"):
            raise SourceError("the exchange", "The link didn't return a PDF.")
        try:
            text = pdf_text(bytes(buf))
        except Exception as e:
            raise SourceError("the exchange", f"The PDF couldn't be read ({e.__class__.__name__}).") from None
        _cache.set(url, text, 7 * 86400)
        return text


def windows(text: str, keywords: list[str], width: int = 700, limit: int = 12000) -> str:
    """The passages around each keyword, merged where they overlap, in document order, up to `limit` characters.
    Falls back to the start of the document when no keyword appears."""
    if not text:
        return ""
    spans = []
    for kw in keywords:
        for m in re.finditer(kw, text, re.I):
            spans.append((max(0, m.start() - width), min(len(text), m.end() + width)))
    if not spans:
        return text[:limit]
    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out, total = [], 0
    for a, b in merged:
        piece = text[a:b].strip()
        if total + len(piece) > limit:
            piece = piece[: max(0, limit - total)]
        if piece:
            out.append(piece)
            total += len(piece)
        if total >= limit:
            break
    return "\n…\n".join(out)


BOILERPLATE = re.compile(r"forward[- ]looking statement|safe harbou?r|actual results (?:may|could) differ|undue reliance|"
                         r"no obligation to (?:update|revise)|this transcript (?:has been|is) edited|disclaimer", re.I)


def ranked_windows(text: str, keywords: list[str], width: int = 600, limit: int = 16000) -> str:
    """Like `windows`, but the passages that pack the most different keywords (and numbers) win, legal boilerplate is
    left out, and the chosen passages are put back in document order. Keeps a long call transcript's guidance instead
    of whatever keyword match happens to come first."""
    if not text:
        return ""
    pats = [re.compile(k, re.I) for k in keywords]
    spans = []
    for p in pats:
        for m in p.finditer(text):
            spans.append((max(0, m.start() - width), min(len(text), m.end() + width)))
    if not spans:
        return text[:limit]
    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1] and b - merged[-1][0] <= 3 * width:      # keep passages short enough to rank
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    scored = []
    for a, b in merged:
        piece = text[a:b]
        if BOILERPLATE.search(piece):
            continue
        kinds = sum(1 for p in pats if p.search(piece))
        nums = len(re.findall(r"\d+(?:\.\d+)?\s*(?:%|per ?cent|crore|cr\b|bps|basis points)", piece, re.I))
        scored.append((kinds * 2 + min(nums, 6), a, b))
    picked, total = [], 0
    for score, a, b in sorted(scored, key=lambda x: (-x[0], x[1])):
        if total + (b - a) > limit:
            continue
        picked.append((a, b))
        total += b - a
    picked.sort()
    return "\n…\n".join(text[a:b].strip() for a, b in picked) or text[:limit]


FILLER = {"a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "will", "would", "we", "our",
          "that", "this", "it", "so", "as", "at", "by", "with", "about", "around", "approximately", "roughly", "some"}


def _words(s: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9%.]+", " ", (s or "").lower().replace("per cent", "%").replace("percent", "%")).split()
            if w not in FILLER and w != "."]


def quote_found(quote: str, text: str) -> bool:
    """Whether a quote the AI gave really is in the document. Small words, case and punctuation are ignored (the AI
    often trims or tidies a spoken sentence); then the whole quote, or most of its 3-word runs, must be there.
    A quote that fails this is treated as made up."""
    q, t = _words(quote), " ".join(_words(text))
    if len(q) < 2 or not t:
        return False
    if " ".join(q) in t:
        return True
    if len(q) < 4:
        return False
    runs = [" ".join(q[i:i + 3]) for i in range(len(q) - 2)]
    return sum(1 for r in runs if r in t) / len(runs) >= 0.6
