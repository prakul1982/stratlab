"""The public blog (BLOG-1): daily market briefs and research posts, kept as small rows in Postgres (app.blog_posts) and
served as real HTML by blog_pages.py, so a search engine reads the words.

Two kinds of post. A brief is the day's Market Brief of one market (India after the close, the US after its close) written
as a post from the issue the newsletter job built: market-level facts only (index closes, sector rotation, stocks newly
matching a price rule), never anything from a user's own data (a My Stocks issue is refused). One per market per day: the
slug is `<market>-market-brief-<day>` and a second save of the same day changes nothing. A day with too little to say (a
holiday, no index figure) is stored with indexable=false, so it is kept out of the list, the sitemap and the feed and
carries a noindex tag. Research posts are made from StratLab's own data by blog_research.py, one row per post that is
updated in place.

A post's body is structured blocks (headings, paragraphs, lists, tables; a text can carry an internal link), written to
the row already cleaned and escaped again when drawn, so nothing a source returns can put markup or an outside link on a
page. Facts only, no advice wording, no data-vendor names. Nothing is held in memory: every page reads its rows."""
import re
from datetime import date, datetime, timezone

from . import db
from .branding import public_text

TABLE = "blog_posts"
KINDS = ("brief", "research")
MARKET_NAME = {"IN": "India", "US": "US"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,90}$")
RESERVED = {"briefs", "research", "feed", "feed-xml"}     # /blog/briefs and /blog/research are the lists
LIST_COLS = "slug,kind,market,title,summary,published_at,updated_at,indexable,published"
PER_PAGE = 20
MAX_PAGE = 50                           # a page past the 1,000th post isn't served: a read is never longer than that
FEED_ITEMS = 30
SITEMAP_ROWS = 5000
HREF = re.compile(r"^/(?!/)[A-Za-z0-9_\-./?=&%#:+]{0,200}$")      # an address on this site, never another host
MAX_TEXT = 3000
MAX_BLOCKS = 80
MAX_ROWS = 150

MINUS = "−"
MAIN_INDEX = {"IN": "NIFTY 50", "US": "S&P 500"}
# the rotation chart and the closing-price pages the posts point to (the app's own addresses)
ROTATION_PATH = {"IN": "/research/rotation?region=IN", "US": "/research/rotation?region=US"}


# ---------- rows ----------
def _t():
    return db.sb().table(TABLE)


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def valid_slug(slug: str) -> bool:
    return bool(SLUG.match(slug or "")) and slug not in RESERVED


def get(slug: str) -> dict | None:
    """One post with its body, or None."""
    if not valid_slug(slug):
        return None
    rows = _t().select("*").eq("slug", slug).limit(1).execute().data
    return rows[0] if rows else None


def listing(kind: str | None = None, market: str | None = None, page: int = 1) -> tuple[list[dict], int]:
    """(one page of posts without their bodies, newest first; how many posts in all) of the posts a visitor may see: published
    and indexable. The read is as long as the page number asks for, at most MAX_PAGE pages."""
    page = max(1, min(MAX_PAGE, int(page or 1)))
    q = _t().select(LIST_COLS, count="exact").eq("published", True).eq("indexable", True)
    if kind:
        q = q.eq("kind", kind)
    if market:
        q = q.eq("market", market)
    got = q.order("published_at", desc=True).limit(page * PER_PAGE).execute()
    return (got.data or [])[(page - 1) * PER_PAGE:page * PER_PAGE], got.count or 0


def neighbours(post: dict) -> tuple[dict | None, dict | None]:
    """(the post before this one, the post after it) in the same kind (and, for a brief, the same market): published and
    indexable ones only."""
    def base():
        q = _t().select("slug,title,published_at").eq("published", True).eq("indexable", True).eq("kind", post["kind"])
        return q.eq("market", post["market"]) if post.get("market") else q
    at = post["published_at"]
    before = base().lt("published_at", at).order("published_at", desc=True).limit(1).execute().data
    after = base().gt("published_at", at).order("published_at").limit(1).execute().data
    return (before[0] if before else None), (after[0] if after else None)


def feed_rows() -> list[dict]:
    got = (_t().select("slug,kind,market,title,summary,published_at,updated_at").eq("published", True).eq("indexable", True)
           .order("published_at", desc=True).limit(FEED_ITEMS).execute().data)
    return got or []


def sitemap_rows() -> list[dict]:
    got = (_t().select("slug,kind,updated_at").eq("published", True).eq("indexable", True).order("published_at", desc=True)
           .limit(SITEMAP_ROWS).execute().data)
    return got or []


def sitemap_urls(site: str) -> list[tuple[str, str | None]]:
    """The blog's addresses for its sitemap, each with the day it last changed: the three lists, then every visible post."""
    rows = sitemap_rows()
    day = lambda r: str(r["updated_at"])[:10]      # noqa: E731
    newest = lambda kind: max((day(r) for r in rows if kind is None or r["kind"] == kind), default=None)      # noqa: E731
    return ([(f"{site}/blog", newest(None)), (f"{site}/blog/briefs", newest("brief")), (f"{site}/blog/research", newest("research"))]
            + [(f"{site}/blog/{r['slug']}", day(r)) for r in rows])


def latest_day() -> str:
    """The day the newest visible post changed ("" when there is none), for the sitemap index."""
    got = (_t().select("updated_at").eq("published", True).eq("indexable", True).order("updated_at", desc=True).limit(1).execute().data)
    return str(got[0]["updated_at"])[:10] if got else ""


def admin_rows(limit: int = 200) -> list[dict]:
    return _t().select(LIST_COLS).order("published_at", desc=True).limit(limit).execute().data or []


def set_published(slug: str, on: bool, now: datetime | None = None) -> dict | None:
    """Show or hide a post (a hidden one answers 404 and leaves the list, the sitemap and the feed). The post is kept."""
    if not valid_slug(slug) or not get(slug):
        return None
    _t().update({"published": bool(on), "updated_at": now_iso(now)}).eq("slug", slug).execute()
    return get(slug)


def add_once(post: dict) -> bool:
    """Store a post unless its slug is taken. True when it was stored; a second call with the same slug changes nothing."""
    row = _row(post)
    got = _t().upsert(row, ignore_duplicates=True, on_conflict="slug").execute()
    return bool(got.data)


def upsert_research(post: dict, now: datetime | None = None) -> str:
    """Store a research post, or bring the stored one up to date. "new", "updated" or "same": a post whose words haven't
    changed keeps its date of last change, so a monthly run that finds the same data doesn't make it look new to a search
    engine. Its first date, and whether an admin hid it, stay."""
    row = _row(post)
    old = get(row["slug"])
    if not old:
        _t().upsert(row, ignore_duplicates=True, on_conflict="slug").execute()
        return "new"
    if all(old.get(k) == row[k] for k in ("title", "summary", "body")):
        return "same"
    _t().update({"title": row["title"], "summary": row["summary"], "body": row["body"], "market": row["market"],
                 "updated_at": row["updated_at"]}).eq("slug", row["slug"]).execute()
    return "updated"


def _row(post: dict) -> dict:
    """The row for a post dict: cleaned, with its dates. Raises ValueError on a post that can't be stored."""
    slug = str(post.get("slug") or "")
    if not valid_slug(slug):
        raise ValueError(f"not a post address: {slug!r}")
    if post.get("kind") not in KINDS:
        raise ValueError("a post is a brief or research")
    title, summary = clean_text(post.get("title"), 160), clean_text(post.get("summary"), 400)
    if not title or not summary:
        raise ValueError("a post needs a title and a summary")
    at = str(post.get("published_at") or now_iso())
    return {"slug": slug, "kind": post["kind"], "market": post.get("market") if post.get("market") in MARKET_NAME else None,
            "title": title, "summary": summary, "body": {"v": 1, "blocks": clean_blocks(post.get("blocks") or [])},
            "published_at": at, "updated_at": str(post.get("updated_at") or at), "indexable": bool(post.get("indexable", True)),
            "published": bool(post.get("published", True)), "day": post.get("day")}


# ---------- cleaning and drawing blocks ----------
def clean_text(v, limit: int = MAX_TEXT, edges: bool = True) -> str:
    """Plain text for a page: provider names replaced, runs of space and line breaks folded, cut at `limit`. `edges` False keeps
    one space at either end, for a piece of a sentence that sits beside a link."""
    s = re.sub(r"\s+", " ", str(public_text(v) if v is not None else ""))
    return (s.strip() if edges else s)[:limit]


def _inline(v):
    """A text: a string, or a list of strings and {"a": words, "href": a path on this site}."""
    if isinstance(v, list):
        out = []
        for x in v[:40]:
            if isinstance(x, dict):
                href = str(x.get("href") or "")
                text = clean_text(x.get("a"), 200)
                out.append({"a": text, "href": href} if text and HREF.match(href) else text)
            else:
                out.append(clean_text(x, edges=False))
        out = [x for x in out if x and x != " "]
        if out and isinstance(out[0], str):
            out[0] = out[0].lstrip()
        if out and isinstance(out[-1], str):
            out[-1] = out[-1].rstrip()
        return [x for x in out if x]
    if isinstance(v, dict):
        return _inline([v])
    return clean_text(v)


def clean_blocks(blocks: list) -> list[dict]:
    """The blocks of a post, with only the kinds drawn below and only text, short lists and addresses on this site."""
    out = []
    for b in blocks[:MAX_BLOCKS]:
        if not isinstance(b, dict):
            continue
        t = b.get("t")
        if t in ("h2", "h3"):
            text = clean_text(b.get("text"), 200)
            if text:
                out.append({"t": t, "text": text})
        elif t in ("p", "note"):
            text = _inline(b.get("text"))
            if text:
                out.append({"t": t, "text": text})
        elif t == "ul":
            items = [x for x in (_inline(i) for i in (b.get("items") or [])[:MAX_ROWS]) if x]
            if items:
                out.append({"t": "ul", "items": items})
        elif t == "table":
            head = [clean_text(h, 80) for h in (b.get("head") or [])[:10]]
            rows = [[_inline(c) for c in (r or [])[:len(head)]] for r in (b.get("rows") or [])[:MAX_ROWS] if isinstance(r, list)]
            if head and rows:
                out.append({"t": "table", "caption": clean_text(b.get("caption"), 200), "head": head, "rows": rows})
    return out


def _esc(s) -> str:
    from html import escape
    return escape(str(s), quote=True)


def inline_html(v) -> str:
    if isinstance(v, list):
        return "".join(inline_html(x) for x in v)
    if isinstance(v, dict):
        href = str(v.get("href") or "")
        return f'<a href="{_esc(href)}">{_esc(v.get("a"))}</a>' if HREF.match(href) else _esc(v.get("a"))
    return _esc(v)


def blocks_html(blocks: list) -> str:
    """A post's blocks as HTML (everything escaped; a link only to an address on this site). A table's first column is its
    row label, the others are figures."""
    out = []
    for b in clean_blocks(blocks):
        t = b["t"]
        if t in ("h2", "h3"):
            out.append(f"<{t}>{_esc(b['text'])}</{t}>")
        elif t == "p":
            out.append(f"<p>{inline_html(b['text'])}</p>")
        elif t == "note":
            out.append(f'<p class="note">{inline_html(b["text"])}</p>')
        elif t == "ul":
            out.append("<ul>" + "".join(f"<li>{inline_html(i)}</li>" for i in b["items"]) + "</ul>")
        elif t == "table":
            cap = f"<caption>{_esc(b['caption'])}</caption>" if b.get("caption") else ""
            head = "".join(f'<th scope="col">{_esc(h)}</th>' for h in b["head"])
            rows = "".join("<tr>" + "".join((f'<th scope="row">{inline_html(c)}</th>' if n == 0 else f"<td>{inline_html(c)}</td>")
                                            for n, c in enumerate(r)) + "</tr>" for r in b["rows"])
            out.append(f'<div class="btbl"><table>{cap}<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>')
    return "".join(out)


def plain_text(blocks: list) -> str:
    """All the words of a post's blocks, for a check that none of them is advice."""
    def flat(v):
        if isinstance(v, list):
            return " ".join(flat(x) for x in v)
        if isinstance(v, dict):
            return str(v.get("a") or "")
        return str(v)
    parts = []
    for b in blocks:
        for k in ("text", "caption"):
            if b.get(k):
                parts.append(flat(b[k]))
        parts += [flat(i) for i in b.get("items") or []] + [str(h) for h in b.get("head") or []]
        parts += [flat(c) for r in b.get("rows") or [] for c in r]
    return " ".join(parts)


# ---------- dates and figures ----------
def long_day(day: str | date) -> str:
    """Tuesday 27 October 2026."""
    d = date.fromisoformat(str(day)[:10])
    return f"{d:%A} {d.day} {d:%B %Y}"


def short_day(day: str | date) -> str:
    """27 Oct 2026."""
    d = date.fromisoformat(str(day)[:10])
    return f"{d.day} {d:%b %Y}"


def level(x, region: str) -> str:
    """An index level: 24,812.30 (Indian digit grouping in India)."""
    from . import email_kit as kit
    return kit.num(x) if region == "IN" else f"{float(x):,.2f}"


def pct(x, dp: int = 2) -> str:
    from . import email_kit as kit
    return kit.pct(x, dp)


def move_words(change) -> str:
    if change is None:
        return ""
    r = round(float(change), 2)
    if r == 0:
        return "unchanged from the previous close"
    return f"{abs(r):.2f}% {'higher' if r > 0 else 'lower'} than the previous close"


def company_path(region: str, symbol: str) -> str | None:
    """The public page of a listed company (/stocks/in/TCS), or None when the page doesn't exist (the symbol isn't listed)."""
    try:
        from . import stock_pages
        hit = stock_pages.find(region, symbol)
        return stock_pages.path(region, hit[0]) if hit else None
    except Exception:
        return None


# ---------- a brief as a post ----------
_SCAN_ITEM = re.compile(r"^([A-Z0-9][A-Z0-9&.\-]*) (matches|moved)\b")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]{0,19}$")


def brief_slug(region: str, day: str) -> str:
    return f"{'india' if region == 'IN' else 'us'}-market-brief-{day}"


def _section(issue: dict, start: str) -> dict | None:
    return next((s for s in issue.get("sections") or [] if isinstance(s, dict) and str(s.get("title") or "").startswith(start)), None)


def _stocks(region: str, sec: dict | None) -> list:
    """A scan section's stocks as lines: the symbol links to its company page when it has one."""
    out = []
    for it in (sec or {}).get("items") or []:
        m = _SCAN_ITEM.match(str((it or {}).get("text") or ""))
        if not m or not _SYMBOL.match(m.group(1)):
            continue
        sym = m.group(1)
        href = company_path(region, sym)
        # "(ST S2)" is the scan's own shorthand: a reader of the post is told the rule in words, just before (VR4-004)
        tail = str(it["text"])[len(sym):].replace(" (ST S2)", "")
        out.append([{"a": sym, "href": href} if href else sym, tail])
    return out


def _open_day(region: str, day: date) -> bool:
    try:
        from .data.calendar import is_trading_day
        return bool(is_trading_day(region, day))
    except Exception:
        return True


def _holiday(region: str, day: date) -> str | None:
    try:
        from .data.calendar import holiday_name
        return holiday_name(region, day)
    except Exception:
        return None


def brief_post(issue: dict, now: datetime | None = None) -> dict | None:
    """A daily Market Brief issue as a post, or None for anything else (a weekly issue, a My Stocks issue, a market that has
    no blog, a day that isn't a date). Only the issue's market-level fields are read: its day, the index closes, the sector
    rotation, the stocks the scan named and the market's closures. Nothing else of the issue is copied."""
    if not isinstance(issue, dict) or issue.get("kind") != "market" or issue.get("weekly") or "uid" in issue:
        return None
    region = issue.get("region")
    if region not in MARKET_NAME:
        return None
    try:
        day = date.fromisoformat(str(issue.get("day") or "")[:10])
    except ValueError:
        return None
    iso, name = day.isoformat(), MARKET_NAME[region]
    indices = [i for i in issue.get("indices") or [] if isinstance(i, dict) and isinstance(i.get("price"), (int, float)) and i.get("name")]
    moved = [i for i in indices if isinstance(i.get("change_pct"), (int, float))]
    open_day = _open_day(region, day)
    lead = next((i for i in moved if i["name"] == MAIN_INDEX[region]), moved[0] if moved else None)
    blocks: list[dict] = []
    if not open_day:
        why = _holiday(region, day)
        title = f"{name} market brief, {short_day(day)}: market closed"
        summary = f"The {name} market was closed on {long_day(day)}" + (f" ({why})" if why else "") + ", so there are no closing figures for the day."
        blocks.append({"t": "p", "text": summary})
    else:
        title = f"{name} market brief, {short_day(day)}" + (f": {lead['name']} {pct(lead['change_pct'])}" if lead else "")
        if lead:
            bits = [f"{i['name']} {'closed ' if n == 0 else ''}at {level(i['price'], region)} ({pct(i['change_pct'])})" for n, i in enumerate(moved[:2])]
            summary = f"{long_day(day)}: " + ", ".join(bits) + ". Facts, not advice."
        else:
            summary = f"The {name} market brief for {long_day(day)}."
        sentences = []
        for i in indices:
            s = f"The {i['name']} closed at {level(i['price'], region)}"
            if isinstance(i.get("change_pct"), (int, float)):
                s += f", {move_words(i['change_pct'])}"
            sentences.append(s + ".")
        blocks.append({"t": "p", "text": f"The {name} market on {long_day(day)}, from the day's closing figures. " + " ".join(sentences)
                       if sentences else f"The {name} market on {long_day(day)}."})
        if indices:
            blocks += [{"t": "h2", "text": "Index closes"},
                       {"t": "table", "caption": f"{name} index closes on {short_day(day)}", "head": ["Index", "Close", "Change on the day"],
                        "rows": [[i["name"], level(i["price"], region), pct(i["change_pct"]) if isinstance(i.get("change_pct"), (int, float)) else "–"]
                                 for i in indices]}]
        rot = _section(issue, "Sector rotation")
        if rot and rot.get("items"):
            blocks += [{"t": "h2", "text": "Sector rotation"},
                       {"t": "p", "text": "The rotation chart places each sector in one of four quadrants (leading, weakening, lagging, improving) "
                                          "from its strength against the market and the direction it is moving, on weekly candles. These sectors "
                                          "moved to another quadrant since the session before."},
                       {"t": "ul", "items": [str(it.get("text") or "") for it in rot["items"]]},
                       {"t": "p", "text": [{"a": "Open the rotation chart", "href": ROTATION_PATH[region]}, "."]}]
        both, only = _section(issue, "Newly matched Stage 2"), _section(issue, "Newly in Stage 2")
        if (both and both.get("items")) or (only and only.get("items")):
            group = re.search(r"\(([^)]+)\)\s*$", str((both or only).get("title") or ""))
            blocks += [{"t": "h2", "text": "Stocks newly matching a price rule"},
                       {"t": "p", "text": "A stock is in Stage 2 when its price is above a rising 150-day average. The Supertrend (10, 3) is a "
                                          "trend line built from the average true range. This is a screen of price history"
                                          + (f" over {group.group(1)}" if group else "")
                                          + ", not a view on any company."}]
            if both and both.get("items"):
                blocks += [{"t": "h3", "text": "Stage 2 with the price above its Supertrend, newly on the day"}, {"t": "ul", "items": _stocks(region, both)}]
            if only and only.get("items"):
                blocks += [{"t": "h3", "text": "Newly in Stage 2, Supertrend not up"}, {"t": "ul", "items": _stocks(region, only)}]
        shut = _section(issue, "Market holiday")
        if shut and shut.get("items"):
            blocks += [{"t": "h2", "text": "Market holiday ahead"}, {"t": "p", "text": str(shut["items"][0].get("text") or "")}]
    blocks += [{"t": "h2", "text": "How this brief is made"},
               {"t": "p", "text": f"It is built by StratLab's own jobs after the {name} close, from the exchange's daily closing figures. "
                                  "A change on the day is measured from the previous session's close. Sector rotation uses weekly candles; "
                                  "a stock is listed when it newly meets the stated price rule. Nothing here comes from any user's account, "
                                  "and nothing in it is a view on what prices will do."}]
    return {"slug": brief_slug(region, iso), "kind": "brief", "market": region, "title": title, "summary": summary, "blocks": blocks,
            "day": iso, "published_at": now_iso(now), "indexable": bool(open_day and lead)}


def backfill(issues: list[dict]) -> dict:
    """Posts for stored daily briefs that have none yet (the first run, when the blog opens): {"added", "skipped"}. A post is
    dated by when its issue was built."""
    added = skipped = 0
    for issue in issues:
        try:
            at = datetime.fromisoformat(str(issue.get("at"))) if issue.get("at") else None
        except ValueError:
            at = None
        if save_brief(issue, at):
            added += 1
        else:
            skipped += 1
    return {"added": added, "skipped": skipped}


def save_brief(issue: dict, now: datetime | None = None) -> bool:
    """Save the day's Market Brief as a post, once: True when a post was stored, False for an issue that isn't a daily
    market brief or a day that already has its post."""
    post = brief_post(issue, now)
    return add_once(post) if post else False
