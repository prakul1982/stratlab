"""The one email design for everything StratLab sends: briefs, alerts, results, tax reminders, welcome and billing.

Every email is built from the same few pieces, so they all look alike and read well in Gmail, Outlook and Apple Mail,
on a phone and in dark mode:

    header (wordmark, type and date) -> title -> one-line summary -> number tiles, cards, rows, tables
    -> one primary button to a page on stratlab.studio -> footer (why you get it, how often, unsubscribe, manage).

The HTML is table-based with inline styles (plus a small <style> block for phones and dark mode, which clients that
ignore it simply skip). No images and no web fonts: Fraunces and IBM Plex Sans are named first, with Georgia and the
system sans as fallbacks. Every piece returns a Block holding its HTML and its plain-text twin, so each email has a
text version built from the same content. All text that is not ours (stock names, headlines, user names) goes
through escape(), and a link is only ever a web address.

Facts only: the kit has no place for advice wording, and colour is never the only signal (up and down carry ▲ and ▼).
The footer's unsubscribe link is the {unsubscribe_url} placeholder, which the sender fills per reader with `finish()`."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from .config import settings

UNSUBSCRIBE = "{unsubscribe_url}"          # the sender fills this in per reader (see finish)
SERIF = "Fraunces,Georgia,'Times New Roman',serif"
SANS = "'IBM Plex Sans',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MINUS = "−"
UP, DOWN = "▲", "▼"

# Light (the app's paper and ink) and dark values. Mid-tone accents, so the colours still read when a client inverts them.
L = dict(page="#F5F1E8", card="#FFFDF8", soft="#EFE9DC", line="#E2DAC8", ink="#1D1B17", ink2="#2E2B25", muted="#5C574D",
         up="#138A62", down="#B23B3B", blue="#1F4FB5", on_blue="#FFFFFF")
D = dict(page="#141311", card="#1F1D1A", soft="#2A2823", line="#34312A", ink="#EFE9DC", ink2="#D8D1C2", muted="#A39C8C",
         up="#3CC48F", down="#EE7B70", blue="#7EA0F0", on_blue="#0F1422")

STYLE = f"""
:root{{color-scheme:light dark;supported-color-schemes:light dark}}
a{{color:{L['blue']}}}
@media (max-width:480px){{
  .px{{padding-left:16px!important;padding-right:16px!important}}
  .stack{{display:block!important;width:100%!important;box-sizing:border-box}}
  .tile-gap{{padding:0 0 8px 0!important}}
  .h1{{font-size:23px!important;line-height:1.25!important}}
  .btn-t{{width:100%!important}}
  .btn-a{{display:block!important;text-align:center!important}}
  .meta{{text-align:left!important;display:block!important;width:100%!important;padding-top:4px!important}}
}}
@media (prefers-color-scheme:dark){{
  .bg-page{{background:{D['page']}!important}}
  .bg-card{{background:{D['card']}!important}}
  .bg-soft{{background:{D['soft']}!important}}
  .bd{{border-color:{D['line']}!important}}
  .c-ink{{color:{D['ink']}!important}}
  .c-ink2{{color:{D['ink2']}!important}}
  .c-muted{{color:{D['muted']}!important}}
  .c-up{{color:{D['up']}!important}}
  .c-down{{color:{D['down']}!important}}
  .c-blue,a{{color:{D['blue']}!important}}
  .btn-bg{{background:{D['blue']}!important}}
  .btn-a{{color:{D['on_blue']}!important;background:{D['blue']}!important}}
}}
"""


# ---------- numbers: Indian grouping, lakh and crore ----------
def indian(n: float | int, dp: int = 0) -> str:
    """1234567.5 -> 12,34,567.5 (Indian digit grouping), with a real minus sign."""
    neg = n < 0
    ip, _, fp = f"{abs(n):.{dp}f}".partition(".")
    if len(ip) > 3:
        head, tail, groups = ip[:-3], ip[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        ip = ",".join(groups + [tail])
    return (MINUS if neg else "") + ip + (f".{fp}" if fp else "")


def num(x, dp: int = 2) -> str:
    """A price or index level: 22,555.75; a missing value is a dash."""
    return "–" if x is None else indian(float(x), dp)


def inr(v, dp: int = 0) -> str:
    """Full rupees: ₹1,00,000 or, with dp=2, ₹1,849.30."""
    return "–" if v is None else ("−" if v < 0 else "") + "₹" + indian(abs(float(v)), dp)


def inr_compact(v) -> str:
    """Indian units: ₹925, ₹5.2 lakh, ₹3,472 cr, ₹1.51 lakh cr (the app's own style)."""
    if v is None:
        return "–"
    a, sign = abs(float(v)), ("−" if v < 0 else "")
    trim = lambda x: f"{x:.2f}".rstrip("0").rstrip(".")  # noqa: E731
    if a < 1e5:
        return f"{sign}₹{indian(a, 0)}"
    if a < 1e7:
        return f"{sign}₹{trim(a / 1e5)} lakh"
    if a < 1e12:
        return f"{sign}₹{indian(round(a / 1e7), 0)} cr"
    return f"{sign}₹{trim(a / 1e12)} lakh cr"


def pct(x, dp: int = 2) -> str:
    """Signed percent with a real minus: +0.60%, −1.25%."""
    return "–" if x is None else f"{'+' if x > 0 else MINUS if x < 0 else ''}{abs(x):.{dp}f}%"


def pct_plain(x, dp: int = 2) -> str:
    return "–" if x is None else f"{abs(x):.{dp}f}%"


def delta(x, dp: int = 2, tone: str = "updown") -> tuple[str, str, str]:
    """(html, text, direction) for a change: ▲ 0.60% in green, ▼ 1.25% in red. The arrow carries the meaning, the
    colour only backs it up. tone="neutral" (a market-wide figure where a rise is not good news, like the VIX) keeps
    the arrow and drops the colour."""
    if x is None:
        return "", "", ""
    if round(x, dp) == 0:
        txt, cls = f"– {pct_plain(0, dp)}", "c-muted"
    else:
        txt = f"{UP if x > 0 else DOWN} {pct_plain(x, dp)}"
        cls = "c-muted" if tone == "neutral" else ("c-up" if x > 0 else "c-down")
    col = {"c-up": L["up"], "c-down": L["down"], "c-muted": L["muted"]}[cls]
    return f'<span class="{cls}" style="color:{col};white-space:nowrap">{txt}</span>', txt, cls


# ---------- links ----------
def site(path: str = "/") -> str:
    """A page on the site: the path appended to the public address (an absolute web address is kept as it is)."""
    if path.lower().startswith(("https://", "http://")):
        return path
    return settings.PUBLIC_SITE_URL + (path if path.startswith("/") else "/" + path)


def manage_url() -> str:
    return site("/settings#notifications")


def safe_url(url) -> str | None:
    """Only a web address is ever a link: a feed's javascript: or data: address stays plain text."""
    return url if isinstance(url, str) and url.lower().startswith(("https://", "http://")) else None


def _a(url, text: str, cls: str = "c-blue", color: str = L["blue"], extra: str = "") -> str:
    u = safe_url(url)
    return (f'<a href="{escape(u)}" class="{cls}" style="color:{color};text-decoration:none;{extra}">{escape(text)}</a>'
            if u else escape(text))


def link(url, text: str) -> str:
    """A link in the kit's colours (or plain text when the address isn't a web address); text is escaped."""
    return _a(url, text)


# ---------- blocks ----------
@dataclass
class Block:
    html: str
    text: str


def _t(s: str) -> str:
    """Text for the plain version: one line, no markup."""
    return " ".join(str(s).split())


def para(text: str, muted: bool = False, size: int = 15) -> Block:
    cls, col = ("c-muted", L["muted"]) if muted else ("c-ink2", L["ink2"])
    return Block(f'<p class="{cls}" style="margin:0 0 14px;font:{size}px/1.55 {SANS};color:{col}">{escape(text)}</p>', text)


def note(text: str) -> Block:
    return Block(f'<p class="c-muted" style="margin:0 0 14px;font:13px/1.5 {SANS};color:{L["muted"]}">{escape(text)}</p>', text)


def heading(text: str) -> Block:
    """A small uppercase section label between blocks."""
    return Block(f'<p class="c-muted" style="margin:18px 0 8px;font:600 12px/1.2 {SANS};letter-spacing:.08em;'
                 f'text-transform:uppercase;color:{L["muted"]}">{escape(text)}</p>', f"\n{text.upper()}")


@dataclass
class Tile:
    label: str
    value: str
    change: float | None = None          # shown as ▲ / ▼
    sub: str | None = None               # a line under it ("of 2,180")
    tone: str = "updown"                 # "neutral": the arrow without red or green


def _tile_html(t: Tile) -> str:
    d_html = delta(t.change, tone=t.tone)[0] if t.change is not None else ""
    sub = f'<div class="c-muted" style="font:13px/1.4 {SANS};color:{L["muted"]}">{escape(t.sub)}</div>' if t.sub else ""
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="bg-soft" bgcolor="{L["soft"]}" '
            f'style="background:{L["soft"]};border-radius:10px"><tr><td style="padding:12px 14px">'
            f'<div class="c-muted" style="font:13px/1.4 {SANS};color:{L["muted"]}">{escape(t.label)}</div>'
            f'<div class="c-ink" style="font:600 22px/1.3 {SANS};color:{L["ink"]}">{escape(t.value)}</div>'
            f'<div style="font:600 13px/1.4 {SANS}">{d_html}</div>{sub}</td></tr></table>')


def tiles(items: list[Tile]) -> Block:
    """Number tiles, 2 or 3 to a row (4 make two pairs), one under another on a phone."""
    if not items:
        return Block("", "")
    per = 1 if len(items) == 1 else 2 if len(items) in (2, 4) else 3
    rows, text = [], []
    for i in range(0, len(items), per):
        chunk = items[i:i + per]
        cells = "".join(
            f'<td class="stack tile-gap" width="{100 // per}%" valign="top" style="padding:0 {0 if j == len(chunk) - 1 else 8}px 8px 0">'
            f'{_tile_html(t)}</td>' for j, t in enumerate(chunk))
        cells += "".join(f'<td class="stack" width="{100 // per}%"></td>' for _ in range(per - len(chunk)))
        rows.append(f'<tr>{cells}</tr>')
    for t in items:
        d = delta(t.change, tone=t.tone)[1] if t.change is not None else ""
        text.append(f"{t.label}: {t.value}" + (f" {d}" if d else "") + (f" ({t.sub})" if t.sub else ""))
    return Block('<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 6px">'
                 + "".join(rows) + "</table>", "\n".join(text))


@dataclass
class Row:
    title: str                           # "TATAMOTORS"
    value: str | None = None             # right-hand side: "₹925" or "results Thu 8 Oct"
    change: float | None = None          # ▲ / ▼ beside the value
    sub: str | None = None               # small line under the title
    url: str | None = None               # makes the title a link
    lines: tuple = ()                    # more small lines: strings or (text, url)
    tone: str = "updown"
    since: str | None = None             # "since Mon 05 Oct", after the change


def _line(item) -> tuple[str, str | None]:
    return (item, None) if isinstance(item, str) else (item[0], item[1] if len(item) > 1 else None)


def _row_html(r: Row, first: bool) -> str:
    top = "" if first else f"border-top:1px solid {L['line']};"
    d_html = delta(r.change, tone=r.tone)[0] if r.change is not None else ""
    since = f'<div class="c-muted" style="font:13px/1.4 {SANS};color:{L["muted"]}">{escape(r.since)}</div>' if r.since and d_html else ""
    right = ""
    if r.value or d_html:
        right = (f'<td class="c-ink" align="right" valign="top" nowrap style="padding:10px 0 0 12px;font:600 15px/1.4 {SANS};'
                 f'color:{L["ink"]};text-align:right;white-space:nowrap">{escape(r.value) if r.value else ""}'
                 + (f'<div style="font:600 13px/1.4 {SANS}">{d_html}</div>' if d_html else "") + since + "</td>")
    subs = ""
    for item in ([r.sub] if r.sub else []) + list(r.lines):
        text, url = _line(item)
        subs += f'<div class="c-muted" style="font:13px/1.45 {SANS};color:{L["muted"]};padding-top:2px">{_a(url, text)}</div>'
    weight = 600 if (r.value or r.change is not None) else 500
    return (f'<tr><td class="bd" style="{top}padding:0"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
            f'<td valign="top" style="padding:10px 0 0"><div class="c-ink" style="font:{weight} 15px/1.4 {SANS};color:{L["ink"]}">'
            f'{_a(r.url, r.title, "c-ink", L["ink"])}</div></td>{right}</tr>'
            f'<tr><td colspan="2" style="padding:0 0 10px">{subs}</td></tr></table></td></tr>')


def card(title: str | None, rows: list[Row], foot: str | None = None) -> Block:
    """A bordered box with a small heading and rows (a stock and its change, an event and its date)."""
    if not rows and not foot:
        return Block("", "")
    head = (f'<div class="c-muted" style="font:600 12px/1.2 {SANS};letter-spacing:.08em;text-transform:uppercase;'
            f'color:{L["muted"]};padding-bottom:4px">{escape(title)}</div>') if title else ""
    body = "".join(_row_html(r, i == 0) for i, r in enumerate(rows))
    foot_html = f'<div class="c-muted" style="font:13px/1.5 {SANS};color:{L["muted"]};padding-top:8px">{escape(foot)}</div>' if foot else ""
    html = (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="bg-card bd" bgcolor="{L["card"]}" '
            f'style="margin:0 0 14px;background:{L["card"]};border:1px solid {L["line"]};border-radius:12px"><tr>'
            f'<td style="padding:14px 16px">{head}<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{body}</table>'
            f'{foot_html}</td></tr></table>')
    text = [f"\n{title.upper()}"] if title else []
    for r in rows:
        right = " ".join(x for x in (r.value or "", delta(r.change, tone=r.tone)[1] if r.change is not None else "", r.since or "") if x)
        text.append(f"- {_t(r.title)}" + (f"  {_t(right)}" if right else "") + (f" ({r.url})" if safe_url(r.url) else ""))
        for item in ([r.sub] if r.sub else []) + list(r.lines):
            t, u = _line(item)
            text.append(f"    {_t(t)}" + (f" ({u})" if safe_url(u) else ""))
    if foot:
        text.append(foot)
    return Block(html, "\n".join(text))


def table(headers: list[str], rows: list[list[str]], right: tuple[int, ...] = (), title: str | None = None) -> Block:
    """A plain table (an invoice's lines, a list of instalments). `right` lists the columns that are numbers."""
    th = "".join(f'<td class="c-muted" align="{"right" if i in right else "left"}" style="padding:6px 0;font:600 12px/1.3 {SANS};'
                 f'letter-spacing:.06em;text-transform:uppercase;color:{L["muted"]};border-bottom:1px solid {L["line"]}">{escape(h)}</td>'
                 for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(
        f'<td class="c-ink bd" align="{"right" if i in right else "left"}" valign="top" style="padding:8px 0;font:15px/1.4 {SANS};'
        f'color:{L["ink"]};border-bottom:1px solid {L["line"]}">{escape(str(c))}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    head = (f'<div class="c-muted" style="font:600 12px/1.2 {SANS};letter-spacing:.08em;text-transform:uppercase;'
            f'color:{L["muted"]};padding-bottom:4px">{escape(title)}</div>') if title else ""
    html = (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="bg-card bd" bgcolor="{L["card"]}" '
            f'style="margin:0 0 14px;background:{L["card"]};border:1px solid {L["line"]};border-radius:12px"><tr><td style="padding:14px 16px">'
            f'{head}<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>{th}</tr>{body}</table></td></tr></table>')
    text = ([f"\n{title.upper()}"] if title else []) + ["  ".join(headers)] + ["  ".join(_t(c) for c in r) for r in rows]
    return Block(html, "\n".join(text))


def bullets(items: list) -> Block:
    """A short list: strings, or (title, line, url) with the title in bold and a link."""
    li, text = [], []
    for it in items:
        title, line, url = (it, None, None) if isinstance(it, str) else (tuple(it) + (None, None))[:3]
        li.append(f'<li class="c-ink2" style="margin:0 0 8px;color:{L["ink2"]}">'
                  f'<b class="c-ink" style="color:{L["ink"]}">{_a(url, title, "c-ink", L["ink"], "font-weight:600;")}</b>'
                  + (f" – {escape(line)}" if line else "") + "</li>")
        text.append(f"- {title}" + (f": {line}" if line else "") + (f" ({url})" if safe_url(url) else ""))
    if not li:
        return Block("", "")
    return Block(f'<ul style="margin:0 0 14px;padding-left:20px;font:15px/1.5 {SANS}">' + "".join(li) + "</ul>", "\n".join(text))


def button(label: str, url: str) -> Block:
    """The one primary button: a link to the right page on the site (a bulletproof table button, for Outlook too)."""
    url = site(url)
    html = (f'<table role="presentation" class="btn-t" cellspacing="0" cellpadding="0" style="margin:10px 0 6px"><tr>'
            f'<td class="btn-bg" align="center" bgcolor="{L["blue"]}" style="border-radius:10px;background:{L["blue"]}">'
            f'<a href="{escape(url)}" class="btn-a" style="display:inline-block;padding:13px 26px;font:600 15px/1.2 {SANS};'
            f'color:{L["on_blue"]};text-decoration:none;border-radius:10px;background:{L["blue"]}">{escape(label)}</a></td></tr></table>')
    return Block(html, f"\n{label}: {url}")


# ---------- the footer ----------
@dataclass
class Footer:
    why: str                                          # "You get this because you chose the daily India brief."
    frequency: tuple[str, str] | None = None          # ("Switch to weekly", path): the newsletters' frequency
    unsubscribe: str | None = None                    # "Unsubscribe from India briefs": the one-click link for this type
    transactional: str | None = None                  # why it can't be turned off ("about your account")
    legal: str | None = None                          # the facts-not-advice line


def _footer(f: Footer) -> Block:
    links, text = [], [f.why]
    if f.transactional:
        text.append(f.transactional)
    if f.frequency:
        links.append(_a(site(f.frequency[1]), f.frequency[0], "c-muted", L["muted"], "text-decoration:underline;"))
        text.append(f"{f.frequency[0]}: {site(f.frequency[1])}")
    if f.unsubscribe:
        links.append(_a_raw(UNSUBSCRIBE, f.unsubscribe))
        text.append(f"{f.unsubscribe}: {UNSUBSCRIBE}")
    links.append(_a(manage_url(), "Manage emails", "c-muted", L["muted"], "text-decoration:underline;"))
    text.append(f"Manage emails: {manage_url()}")
    if f.legal:
        text.append(f.legal)
    sep = f' <span style="color:{L["line"]}">&middot;</span> '
    html = (f'<p class="c-muted" style="margin:0 0 8px;font:13px/1.55 {SANS};color:{L["muted"]}">{escape(f.why)}'
            + (f" {escape(f.transactional)}" if f.transactional else "") + "</p>"
            f'<p class="c-muted" style="margin:0 0 8px;font:13px/1.8 {SANS};color:{L["muted"]}">{sep.join(links)}</p>'
            + (f'<p class="c-muted" style="margin:0;font:12px/1.5 {SANS};color:{L["muted"]}">{escape(f.legal)}</p>' if f.legal else ""))
    return Block(html, "\n".join(["", "--"] + text))


def _a_raw(url: str, text: str) -> str:
    """The unsubscribe link: its address is the placeholder the sender fills in, so it isn't checked as a web address."""
    return (f'<a href="{url}" class="c-muted" style="color:{L["muted"]};text-decoration:underline">{escape(text)}</a>')


# ---------- the whole email ----------
def render(title: str, blocks: list[Block], footer: Footer, *, label: str = "", date: str = "", summary: str | None = None,
           cta: tuple[str, str] | None = None, subject: str | None = None, preheader: str | None = None) -> tuple[str, str]:
    """(html, text) for one email. `label` and `date` fill the header's type line ("Market brief · India", "Tue 6 Oct"),
    `cta` is (button label, page path or address)."""
    pre = preheader if preheader is not None else (summary or title)
    meta = " · ".join(x for x in (label, date) if x)
    parts = list(blocks) + ([button(*cta)] if cta else [])
    fb = _footer(footer)
    body = "".join(b.html for b in parts)
    summary_html = (f'<p class="c-ink2" style="margin:0 0 18px;font:16px/1.55 {SANS};color:{L["ink2"]}">{escape(summary)}</p>'
                    if summary else "")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">'
        '<meta http-equiv="X-UA-Compatible" content="IE=edge">'
        f'<title>{escape(subject or title)}</title><style>{STYLE}</style></head>'
        f'<body class="bg-page" bgcolor="{L["page"]}" style="margin:0;padding:0;background:{L["page"]};-webkit-text-size-adjust:100%">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;font-size:1px;line-height:1px;color:{L["page"]}">{escape(pre[:140])}</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="bg-page" bgcolor="{L["page"]}" style="background:{L["page"]}">'
        '<tr><td align="center" style="padding:20px 12px">'
        '<!--[if mso]><table role="presentation" width="600" align="center" cellspacing="0" cellpadding="0"><tr><td><![endif]-->'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px">'
        # header
        f'<tr><td class="bg-soft bd px" bgcolor="{L["soft"]}" style="background:{L["soft"]};padding:16px 24px;border:1px solid {L["line"]};'
        f'border-bottom:0;border-radius:16px 16px 0 0"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td class="c-ink" style="font:600 21px/1.2 {SERIF};letter-spacing:-.01em;color:{L["ink"]}">StratLab</td>'
        f'<td class="meta c-muted" align="right" style="font:13px/1.4 {SANS};color:{L["muted"]};text-align:right">{escape(meta)}</td>'
        '</tr></table></td></tr>'
        # body
        f'<tr><td class="bg-card bd px" bgcolor="{L["card"]}" style="background:{L["card"]};padding:26px 24px 16px;'
        f'border:1px solid {L["line"]};border-top:1px solid {L["line"]};border-bottom:0">'
        f'<h1 class="h1 c-ink" style="margin:0 0 8px;font:600 27px/1.2 {SERIF};letter-spacing:-.01em;color:{L["ink"]}">{escape(title)}</h1>'
        f'{summary_html}{body}</td></tr>'
        # footer
        f'<tr><td class="bg-card bd px" bgcolor="{L["card"]}" style="background:{L["card"]};padding:14px 24px 20px;border:1px solid {L["line"]};'
        f'border-top:1px solid {L["line"]};border-radius:0 0 16px 16px">{fb.html}</td></tr>'
        '</table><!--[if mso]></td></tr></table><![endif]-->'
        '</td></tr></table></body></html>')
    head = [f"STRATLAB" + (f" | {meta}" if meta else ""), "", title, "=" * min(len(title), 60)]
    text = head + ([summary] if summary else []) + [""] + [b.text for b in parts if b.text] + [fb.text]
    return html, "\n".join(text).replace("\n\n\n", "\n\n").strip() + "\n"


def today_label() -> str:
    """Today's India date for a header: Tue 6 Oct."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    d = datetime.now(ZoneInfo("Asia/Kolkata"))
    return f"{d:%a} {d.day} {d:%b}"


# ---------- finishing: fill the unsubscribe link and the headers ----------
def finish(html: str, text: str, uid: str | None, what: str | None) -> tuple[str, str, dict | None]:
    """Fill the footer's {unsubscribe_url} for this reader and give the List-Unsubscribe headers (None when the email
    has no unsubscribe, like a receipt)."""
    if not what or not uid:
        return html, text, None
    from . import alerts
    unsub = alerts.unsubscribe_url(uid, what)
    return html.replace(UNSUBSCRIBE, escape(unsub)), text.replace(UNSUBSCRIBE, unsub), alerts.list_unsubscribe_headers(uid, what)


def preview_links(html: str, text: str) -> tuple[str, str]:
    """For previews: the unsubscribe link just opens Manage emails."""
    return html.replace(UNSUBSCRIBE, manage_url()), text.replace(UNSUBSCRIBE, manage_url())


# ---------- a message from plain lines: alerts, reminders, admin notes ----------
BUTTONS = {"/alerts": "Open your alerts", "/trade/events": "See every event", "/trade/fo-changes": "See every change",
           "/paper": "Open paper trading", "/admin": "Open Admin", "/money/calendar": "Open your money calendar",
           "/account": "Open your account", "/research/screens": "Open your screens", "/research/filings": "Open filings",
           "/money/tax-tools?tab=advance": "Open your advance tax figures", "/account#invite": "See your invites"}
_ADVICE_TAIL = ("not advice", "not investment advice", "not tax advice", "facts, not")


def _is_footnote(line: str) -> bool:
    low = line.lower()
    return any(k in low for k in _ADVICE_TAIL)


def message(subject: str, text: str, path: str, label: str, why: str, *, summary: str | None = None, button_label: str | None = None,
            date: str = "", footer: Footer | None = None) -> tuple[str, str]:
    """(html, text) for an alert, reminder or note given as a subject and plain lines: a line starting "- " is a row,
    a line ending in ":" heads the rows after it, the rest are paragraphs, and a closing "facts, not advice" line
    becomes the small print. The deep link is the one button."""
    title = subject.removeprefix("StratLab alert: ").removeprefix("StratLab: ").removeprefix("StratLab ").strip() or subject
    title = title[:1].upper() + title[1:]
    blocks: list[Block] = []
    rows: list[Row] = []
    head: str | None = None
    legal = None
    first_para = summary

    def flush():
        nonlocal rows, head
        if rows:
            blocks.append(card(head, rows))
        rows, head = [], None
    for raw in [ln.strip() for ln in text.splitlines() if ln.strip()]:
        if raw.startswith("- "):
            rows.append(Row(raw[2:]))
        elif _is_footnote(raw):
            legal = raw
        elif raw.endswith(":") and not rows:
            head = raw[:-1]
        else:
            flush()
            if first_para is None and not blocks:
                first_para = raw
            else:
                blocks.append(para(raw))
    flush()
    if head and not blocks:
        first_para = first_para or head
    f = footer or Footer(why=why, legal=legal or "Facts, not advice.")
    if legal and not f.legal:
        f.legal = legal
    return render(title, blocks, f, label=label, date=date, summary=first_para, subject=subject,
                  cta=(button_label or BUTTONS.get(path, "Open StratLab"), path))
