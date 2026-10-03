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
MAX_BYTES = 30 * 1024 * 1024        # large investor decks run to 20 MB
MAX_PAGES = 80
_cache = TTLCache(max_items=300)


def _host_ok(host: str | None, extra_hosts: tuple[str, ...]) -> bool:
    if not host:
        return False
    return host in ALLOWED_HOSTS or any(host == h or host.endswith("." + h) for h in extra_hosts)


def allowed(url: str | None, extra_hosts: tuple[str, ...] = ()) -> bool:
    """An https PDF on the exchanges' document hosts, or on the company's own website when `extra_hosts` names it."""
    try:
        u = urlparse(url or "")
    except ValueError:
        return False
    return u.scheme == "https" and _host_ok(u.hostname, extra_hosts) and u.path.lower().endswith(".pdf")


def public_host(host: str) -> bool:
    """The name resolves only to public internet addresses (a company website, never this server's own network)."""
    import ipaddress
    import socket
    try:
        ipaddress.ip_address(host)
        return False                           # bare IP addresses aren't company websites
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    addrs = {i[4][0] for i in infos}
    return bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def site_domain(website: str | None) -> str | None:
    """'https://www.apollohospitals.com/' → 'apollohospitals.com'."""
    try:
        host = urlparse(website or "").hostname or ""
    except ValueError:
        return None
    host = host.lower()
    host = host[4:] if host.startswith("www.") else host
    return host if "." in host else None


PDF_LINK = re.compile(r"(?:https?://|www\.)[^\s\"'<>()\[\]]+?\.pdf\b", re.I)


def pdf_links(text: str) -> list[str]:
    """PDF links written in a filing (a cover letter often just points to the transcript on the company's website).
    Links broken across a line by the PDF are joined back first."""
    joined = re.sub(r"(https?://\S+|www\.\S+)\s*\n\s*(\S+)", lambda m: m.group(1) + m.group(2)
                    if not m.group(1).lower().endswith(".pdf") else m.group(0), text or "")
    out = []
    for m in PDF_LINK.finditer(joined):
        url = m.group(0)
        url = "https://" + url if url.lower().startswith("www.") else url.replace("http://", "https://", 1)
        if url not in out:
            out.append(url)
    return out


WEB_LINK = re.compile(r"(?:https?://|www\.)[^\s\"'<>()\[\]]+", re.I)


def web_links(text: str) -> list[str]:
    """Links to web pages (not PDFs) written in a filing, e.g. "available at www.company.com/investors"."""
    out = []
    def rejoin(m):                   # a link broken across lines: the host is cut short, or the next line goes on with a path
        url, nxt = m.group(1), m.group(2)
        host = re.sub(r"^https?://", "", url).split("/")[0]
        cut = not re.search(r"\.(com|in|co|net|org|bank|io)$", host) and "/" not in url[8:]
        return url + nxt if cut or nxt.startswith("/") or (url.endswith("/") and "/" in nxt) else m.group(0)
    joined = re.sub(r"(https?://\S+|www\.\S+)[ \t]*\n[ \t]*(\S+)", rejoin, text or "")
    for m in WEB_LINK.finditer(joined):
        url = m.group(0).rstrip(".,;:")
        if url.lower().endswith(".pdf") or "@" in url:
            continue
        url = "https://" + url if url.lower().startswith("www.") else url.replace("http://", "https://", 1)
        if url not in out:
            out.append(url)
    return out


def host_of(url: str) -> str | None:
    try:
        h = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    return h or None


HREF = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
KIND_WORDS = {"transcript": re.compile(r"transcript|con\.?\s?call|concall|earnings[\s_-]?call", re.I),
              "presentation": re.compile(r"presentation|investor[\s_-]?(?:deck|update)|earnings[\s_-]?update", re.I)}


def page_pdfs(html: str, base: str, kind: str | None = None) -> list[str]:
    """PDF links on an investor web page, the ones naming the wanted kind of document first (in page order)."""
    found = []
    for href, label in HREF.findall(html or ""):
        url = str(httpx.URL(base).join(href.strip()))
        if not urlparse(url).path.lower().endswith(".pdf") or not url.startswith("https://"):
            continue
        words = f"{url} {re.sub(r'<[^>]+>', ' ', label)}"
        score = 1 if kind and KIND_WORDS.get(kind, re.compile("$^")).search(words) else 0
        if url not in [u for _, u in found]:
            found.append((score, url))
    return [u for _, u in sorted(found, key=lambda x: -x[0])]


# Indian company PDFs often draw the rupee sign with a font that maps it to another character; the text then reads
# "¥186,630", "`1,200", "X 70,435" or "%640". Put the rupee sign back.
_YEN = re.compile(r"¥\s?(?=\d)")
_TICK = re.compile(r"`\s?(?=\d)")
_ODD = re.compile(r"(?<![A-Za-z0-9%])([X%])\s?(?=\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b|\d{2,}(?:\.\d+)?\b)")


def fix_rupee(text: str) -> str:
    text = _TICK.sub("₹", _YEN.sub("₹", text))
    # "X945" or "%640" (a percent sign BEFORE a number) only stand in for ₹ when the document does it repeatedly
    if len(_ODD.findall(text)) >= 3:
        text = _ODD.sub("₹", text)
    return text


SCANNED_CHARS = 150          # fewer text characters than this per page: the pages are pictures (a scan)


def scanned(text: str, pages: int) -> bool:
    return pages >= 1 and len(text.strip()) < SCANNED_CHARS * min(pages, 4)


def pdf_text_pages(data: bytes, max_pages: int = MAX_PAGES) -> tuple[str, int]:
    """The PDF's text and its page count."""
    from pypdf import PdfReader               # imported here: only these reads need it
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:                     # one bad page mustn't lose the document
            continue
    return _tidy("\n".join(parts)), len(reader.pages)


def _tidy(text: str) -> str:
    return fix_rupee(re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip())


class Docs:
    def __init__(self, http: httpx.Client | None = None, transport: httpx.BaseTransport | None = None, check_host=public_host,
                 ocr=None):
        self.http = http or httpx.Client(timeout=30, transport=transport, follow_redirects=False,
                                         headers={"User-Agent": BROWSER_UA, "Accept": "application/pdf,*/*",
                                                  "Referer": "https://www.nseindia.com/"})
        self.check_host = check_host
        self.ocr = ocr                          # reads scanned PDFs; None: the AI services' OCR when a key is set
        self.scans = 0                          # scanned PDFs read this way

    def _download(self, url: str, extra_hosts: tuple[str, ...], limit: int) -> bytes:
        """The body at `url`, following up to three redirects that stay on the allowed hosts, every host checked to be
        on the public internet."""
        target = url
        try:
            for _ in range(4):
                host = urlparse(target).hostname or ""
                if host not in ALLOWED_HOSTS and not self.check_host(host):
                    raise SourceError("the exchange", "That website isn't reachable from here.")
                with self.http.stream("GET", target) as r:
                    if 300 <= r.status_code < 400:
                        nxt = str(httpx.URL(target).join(r.headers.get("location", "")))
                        if not _host_ok(urlparse(nxt).hostname, extra_hosts) or urlparse(nxt).scheme != "https":
                            raise SourceError("the exchange", "The document moved off the company's site; it wasn't followed.")
                        target = nxt
                        continue
                    if r.status_code >= 400:
                        raise SourceError("the exchange", f"The document couldn't be downloaded ({r.status_code}).", busy=r.status_code >= 500)
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) > limit:
                            raise SourceError("the exchange", "The document is too large to read here.")
                    return bytes(buf)
            raise SourceError("the exchange", "The document moved too many times.")
        except httpx.HTTPError as e:
            raise SourceError("the exchange", f"Couldn't reach the document ({e.__class__.__name__}).", busy=True) from None

    def page(self, url: str, extra_hosts: tuple[str, ...] = ()) -> str:
        """An investor web page's HTML (up to 2 MB), on the hosts the company's filing named."""
        u = urlparse(url)
        if u.scheme != "https" or not _host_ok(u.hostname, extra_hosts):
            raise SourceError("the exchange", "That page isn't on a site the company's filing named.")
        hit = _cache.get(("page", url))
        if hit is not None:
            return hit
        html = self._download(url, extra_hosts, 2 * 1024 * 1024).decode("utf-8", "replace")
        _cache.set(("page", url), html, 86400)
        return html

    def _ocr(self, data: bytes) -> str:
        """A scanned PDF's text, read from the page images; '' when no OCR service is set up."""
        from . import ocr
        fn = self.ocr or (ocr.read_pdf if ocr.available() else None)
        if fn is None:
            return ""
        try:
            got = fn(data)
        except Exception as e:
            raise SourceError("the exchange", f"The PDF is a scan and couldn't be read ({str(e)[:80]}).", busy=True) from None
        if got and got.strip():
            self.scans += 1
            return _tidy(got)
        return ""

    def text(self, url: str, extra_hosts: tuple[str, ...] = ()) -> str:
        """The text of a PDF on the exchange's site, or on the company's own website (`extra_hosts`). Up to three
        redirects are followed, each one checked the same way."""
        if not allowed(url, extra_hosts):
            raise SourceError("the exchange", "That document isn't on the exchange's or the company's own site.")
        hit = _cache.get(url)
        if hit is not None:
            return hit
        buf = self._download(url, extra_hosts, MAX_BYTES)
        if not bytes(buf[:5]).startswith(b"%PDF"):
            raise SourceError("the exchange", "The link didn't return a PDF.")
        try:
            text, pages = pdf_text_pages(bytes(buf))
        except Exception as e:
            raise SourceError("the exchange", f"The PDF couldn't be read ({e.__class__.__name__}).") from None
        if scanned(text, pages):
            text = self._ocr(bytes(buf)) or text
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
