"""Google AdSense on the pages the server draws (the public company pages; the blog calls the same helper), ADS-1.

Off by default: `ad_slot_html()` returns "" until ADS_ENABLED=true AND the slot's ID are set (ADSENSE_CLIENT, ca-pub-…, already holds the owner's ID), so
nothing on a page changes until the owner switches ads on (docs/ADMIN.md). What it returns is plain HTML: a labelled box that
already holds its height (so the page doesn't jump when the ad arrives) and the one script tag for /ads.js. That file (the
frontend's public/ads.js) asks the visitor first ("Allow ads" / "No thanks", DPDP Act) and loads Google's script only after
"Allow", so an ad cookie is never set before consent. The app's own React slot (frontend/src/components/AdUnit.tsx) shares the
visitor's answer through the same localStorage key.

Never call it from a page that shows someone's own money or account, or from an email: those carry personal financial data.
How to use it from another server-rendered page: `html = ads.add_to_page(html, "blog")` puts the ad above `</main>` and the
script before `</body>`, or place `ads.ad_slot_html("blog")` by hand, once per page, below the fold and away from buttons."""
import re

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
         ".ad-ask button.ad-no{background:transparent;color:var(--ink,#1D1B17)}")


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


def ad_slot_html(slot_name: str = "public") -> str:
    """The labelled ad box and the script that fills it, or "" when ads are off. Once per page."""
    if not enabled(slot_name):
        return ""
    name = slot_name if NAME.match(slot_name or "") else "public"
    return (f"<style>{STYLE}</style>"
            f'<section class="ad" data-ads data-client="{client()}" data-slot="{slot_id(slot_name)}" data-name="{name}" aria-label="Advertisement">'
            '<p class="ad-label">Advertisement</p><div class="ad-box"></div></section>'
            '<script src="/ads.js" defer></script>')


def add_to_page(page: str, slot_name: str = "public") -> str:
    """A finished page with its ad added at the end of the main content (below the fold, clear of the page's buttons), or the
    page unchanged when ads are off or the page has no `</main>`. Done as the page is sent, never stored with it: switching ads
    on or off then shows on the next request, and the stored copy never carries an ad."""
    block = ad_slot_html(slot_name)
    i = page.rfind("</main>")
    return page if not block or i < 0 else page[:i] + block + page[i:]

