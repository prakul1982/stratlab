"""The small pages that links in emails open (unsubscribe, confirm an address), in the site's own look (R7M-004: they
were plain unstyled HTML). They are served by the API under stratlab.studio's address (the site forwards /unsubscribe and
/email/confirm to it), so the styles and the logo are inline and the fonts are the site's own files on the same host.
No script runs on them (guard.HTML_CSP)."""
from html import escape as e

from .config import settings

MANAGE_PATH = "/settings#notifications"          # Settings → Notifications: each email's choices


def _style() -> str:
    from .stock_pages import STYLE
    return STYLE + """
main.mail{max-width:34rem;margin:0 auto;padding:40px 16px 56px}
.mail .card{padding:24px}.mail h1{font-size:clamp(24px,5vw,32px);margin:0 0 12px}.mail p{margin:0 0 14px}
.mail form{margin:18px 0 6px}.mail button.btn{cursor:pointer;font:inherit;font-weight:600}
.mail .links2{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:6px}
"""


def page(title: str, body_html: str) -> str:
    """A whole page: the site's header with the logo, one card with `body_html` (already escaped), the small print."""
    from .stock_pages import LOGO
    site = settings.PUBLIC_SITE_URL.rstrip("/")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><meta name="robots" content="noindex,nofollow">'
            f'<title>{e(title)} · StratLab</title><link rel="icon" href="{e(site)}/favicon.svg" type="image/svg+xml">'
            f"<style>{_style()}</style></head><body>"
            f'<header class="nav"><a class="brand" href="{e(site)}/" aria-label="StratLab home">{LOGO}'
            f'<span class="word"><b>Strat</b>Lab</span></a></header>'
            f'<main class="mail" id="main"><div class="card">{body_html}</div>'
            f'<p class="muted small">Emails from StratLab are research and education only: facts from reported data, never investment advice.</p></main>'
            f"</body></html>")


def manage_link(site: str | None = None, label: str = "Change which emails you get in Settings → Notifications") -> str:
    base = (site or settings.PUBLIC_SITE_URL).rstrip("/")
    return f'<p><a href="{e(base)}{MANAGE_PATH}">{e(label)}</a></p>'


def notice(title: str, text: str) -> str:
    """The result or explanation page (unsubscribed, link doesn't work, preview)."""
    return page(title, f"<h1>{e(title)}</h1><p>{e(text)}</p>" + manage_link())


def ask(title: str, post_to: str, button: str, small: str = "", manage: bool = True) -> str:
    """A page with one button that posts (mail scanners open every link in an email, so nothing happens on opening)."""
    return page(title, f"<h1>{e(title)}</h1>" + (f"<p>{e(small)}</p>" if small else "")
                + f'<form method=post action="{e(post_to)}"><button class="btn" type="submit">{e(button)}</button></form>'
                + (manage_link() if manage else ""))
