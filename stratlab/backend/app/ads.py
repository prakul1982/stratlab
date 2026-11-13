"""Google AdSense on the pages the server draws (the public company pages; the blog calls the same helper), ADS-1.

Off by default: `ad_slot_html()` returns "" until ADS_ENABLED=true AND the slot's ID are set (ADSENSE_CLIENT, ca-pub-…, already holds the owner's ID), so
nothing on a page changes until the owner switches ads on (docs/ADMIN.md). What it returns is plain HTML: a labelled box that
already holds its height (so the page doesn't jump when the ad arrives) and the one script tag for /ads.js. That file (the
frontend's public/ads.js) asks the visitor first ("Allow ads" / "No thanks", DPDP Act) and loads Google's script only after
"Allow", so an ad cookie is never set before consent. The app's own React slot (frontend/src/components/AdUnit.tsx) shares the
visitor's answer through the same localStorage key.

Never call it from a page that shows someone's own money or account, or from an email: those carry personal financial data.
How to use it from another server-rendered page: `html = ads.add_to_page(html, "blog")` puts the ad above `</main>` and the
script before `</body>`, or place `ads.ad_slot_html("blog", page=html)` by hand, once per page, below the fold and away from
buttons. Either way the page must have enough original content (MIN_ORIGINAL_WORDS) or it gets no ad."""
import re
from html.parser import HTMLParser

from .config import settings

CLIENT = re.compile(r"^ca-pub-\d{10,20}$")        # the publisher ID as Google writes it; anything else switches ads off
SLOT = re.compile(r"^\d{6,20}$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,20}$")

# self-contained (a blog page has other colour names than a company page, so every var has a fallback) and drawn with the
# site's own tokens in both themes. The box holds 280px before the ad arrives: the page does not jump (CLS). No border, no card
# colour: an ad must not look like StratLab's own content.
STYLE = (".ad{margin:40px 0 8px;padding-top:8px;border-top:1px solid var(--line,#E2DAC8);clear:both}"
         ".ad-label{margin:0 0 6px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted,#5C574D)}"
         ".ad-box{min-height:280px;display:block;overflow:hidden}"
         ".ad-ask{display:flex;flex-direction:column;gap:10px;align-items:flex-start;max-width:520px;font-size:14px;line-height:1.5;color:var(--ink-2,#2E2B25)}"
         ".ad-ask p{margin:0}.ad-ask .ad-btns{display:flex;flex-wrap:wrap;gap:10px}"
         ".ad-ask button{min-height:44px;padding:0 18px;border-radius:10px;border:1px solid var(--ink,#1D1B17);font:inherit;font-weight:600;cursor:pointer;"
         "background:var(--ink,#1D1B17);color:var(--on-ink,#F5F1E8)}"
         ".ad-ask button.ad-no{background:transparent;color:var(--ink,#1D1B17)}"
         ".ad-ask button{min-width:112px}")       # the two answers, one width (VR4-015)


# AdSense allows no ad on auto-generated pages or pages with little to no original content. A page carries the ad only when its
# main content holds at least MIN_ORIGINAL_WORDS words of its own text (original_words): the words in <main> outside navigation,
# header and footer, forms, tables, charts, buttons and link text, and outside any element marked data-shared (wording that is
# the same on every page of its kind, or a template's sentences filled in with figures the page already shows). A word has a
# letter in it, so a number or a date is not one. docs/ADMIN.md has the rule.
MIN_ORIGINAL_WORDS = 300
_SKIP = {"script", "style", "noscript", "template", "nav", "header", "footer", "form", "table", "svg", "button", "select", "a", "aside"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_WORD = re.compile(r"\S*[^\W\d_]\S*")


class _Words(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_main = 0
        self.skip: list[str] = []          # the open tags being left out, innermost last
        self.words = 0

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        if tag == "main":
            self.in_main += 1
        if self.skip:
            self.skip.append(tag)
        elif self.in_main and (tag in _SKIP or any(k in ("data-shared", "hidden") for k, _ in attrs) or ("aria-hidden", "true") in attrs):
            self.skip.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self.skip and tag in self.skip:
            while self.skip and self.skip.pop() != tag:
                pass
        if tag == "main" and self.in_main:
            self.in_main -= 1

    def handle_data(self, data):
        if self.in_main and not self.skip:
            self.words += len(_WORD.findall(data))


def original_words(page: str) -> int:
    """How many words of the page's own text its <main> holds (see MIN_ORIGINAL_WORDS)."""
    p = _Words()
    try:
        p.feed(page or "")
        p.close()
    except Exception:                      # a page the parser can't read carries no ad
        return 0
    return p.words


def enough_content(page: str) -> bool:
    """The page has enough original content to carry an ad (AdSense: no ads on pages with little to no original content)."""
    return original_words(page) >= MIN_ORIGINAL_WORDS


def client() -> str:
    """The publisher ID, or "" when it isn't a ca-pub-… ID (a pasted mistake must never reach a page's HTML)."""
    c = (settings.ADSENSE_CLIENT or "").strip()
    return c if CLIENT.match(c) else ""


def slot_id(slot_name: str = "public") -> str:
    """The ad unit's ID for a page kind. Only ADSENSE_SLOT_PUBLIC is set today; a page kind with its own ID
    (ADSENSE_SLOT_<NAME>) would use it, any other shares the public one."""
    own = getattr(settings, f"ADSENSE_SLOT_{slot_name.upper()}", "") if NAME.match(slot_name or "") else ""
    s = (own or settings.ADSENSE_SLOT_PUBLIC or "").strip()
    return s if SLOT.match(s) else ""


def enabled(slot_name: str = "public") -> bool:
    """Ads draw only with the switch on, a valid publisher ID and a valid slot ID."""
    return bool(settings.ADS_ENABLED and client() and slot_id(slot_name))


def ad_slot_html(slot_name: str = "public", page: str | None = None) -> str:
    """The labelled ad box and the script that fills it, for the finished `page` it goes on. "" when ads are off, and when the page
    is not given or has too little original content (enough_content). Once per page."""
    if not enabled(slot_name) or page is None or not enough_content(page):
        return ""
    name = slot_name if NAME.match(slot_name or "") else "public"
    return (f"<style>{STYLE}</style>"
            f'<section class="ad" data-ads data-client="{client()}" data-slot="{slot_id(slot_name)}" data-name="{name}" aria-label="Advertisement">'
            '<p class="ad-label">Advertisement</p><div class="ad-box"></div></section>'
            '<script src="/ads.js" defer></script>')


def add_to_page(page: str, slot_name: str = "public") -> str:
    """A finished page with its ad added at the end of the main content (below the fold, clear of the page's buttons), or the
    page unchanged when ads are off, the page has no `</main>` or too little original content (enough_content). Done as the page is sent, never stored with it: the stored copy
    never carries an ad, and switching ads on or off shows on the next request the API answers. The site's cache keeps a company
    or blog page up to a day (stock_pages.CACHE_CONTROL), so a copy it holds changes within that day (RC4-010)."""
    i = page.rfind("</main>")
    block = ad_slot_html(slot_name, page) if i >= 0 else ""
    return page if not block else page[:i] + block + page[i:]

