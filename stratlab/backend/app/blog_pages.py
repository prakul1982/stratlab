"""The blog's public pages and its admin routes (BLOG-1).

/blog (newest first, paged), /blog/briefs, /blog/research, /blog/<slug> and /blog/feed.xml are real HTML (and an Atom feed)
drawn here from the rows in app.blog_posts, so a crawler reads the words; the site's host forwards /blog* to the API
(frontend/vercel.json) the way it does /stocks. They wear the same header, footer, type and colours as the company pages
(stock_pages), and each post carries its title and description, the canonical address on the site, Open Graph and Twitter
tags, an Article in JSON-LD (headline, dates, author and publisher), a "facts, not advice" line, links to the company pages
and the app, and the posts before and after it. A post that is not indexable is served with noindex and left out of the
lists, the sitemap and the feed; a post an admin has hidden answers 404. Nothing is kept in memory: a page reads its rows.

The admin routes (/admin/blog...) list the posts, show or hide one, add posts for the stored daily briefs, and run the
research generator (blog_research.py) in the background."""
import json
import re
import threading
from datetime import datetime, timezone
from html import escape as e
from xml.sax.saxutils import escape as xml

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from . import admin, ads, blog, blog_research, stock_pages as sp
from .config import settings
from .responses import err, ok

router = APIRouter(tags=["blog"], include_in_schema=False)
admin_router = APIRouter(tags=["admin"])

# a post is fixed once published and a list grows by a post or two a day, so the host keeps a page a day (SEO-1: cold responses took
# 0.6 to 1.8 s, which Google counts against crawling a site); a post an admin hides is gone from the public within that day. The
# feed is read by programs that poll it, so it stays at ten minutes.
CACHE = sp.CACHE_CONTROL
FEED_CACHE = "public, max-age=300, s-maxage=600, stale-while-revalidate=600"
FACTS = "Facts, not advice. Data and method for research and education; not investment advice or a recommendation about any security."
KIND_NAME = {"brief": "Market brief", "research": "Research"}
TITLES = {None: ("StratLab blog: daily market briefs and research from market data",
                 "Daily India and US market briefs and research built from StratLab's own data: index closes, sector rotation, strategy tests, IPO "
                 "listings and SIPs. Facts and method, not advice."),
          "brief": ("Daily market briefs for India and the US · StratLab",
                    "Each trading day's India and US market brief: index closes, sector rotation and stocks newly matching a price rule, built after "
                    "the close from market data. Facts, not advice."),
          "research": ("Research from StratLab's own data · StratLab",
                       "Research posts built from StratLab's own data: classic strategies across markets after costs, IPO listing days and SIP against "
                       "lump sum, each with its data, period, method and limits.")}
PATHS = {None: "/blog", "brief": "/blog/briefs", "research": "/blog/research"}

STYLE = """
/* PUB-2: one content width for a post and a list (the page's own 960 px column, as a company page has), text and tables alike */
.blog-eyebrow{font-size:13px;color:var(--muted);margin:0 0 4px}.blog-eyebrow a{color:var(--muted)}
.byline{font-size:14px;color:var(--muted);margin:2px 0 4px}
.facts{font-size:13.5px;color:var(--muted);margin:0 0 22px}
article h2{margin-top:32px}article h3{font-family:var(--serif);font-weight:600;font-size:17px;margin:20px 0 6px}
article p,article li{max-width:none}article>p,article li{font-size:16px;line-height:1.6}article ul{padding-left:20px}article li{margin:5px 0}
.btbl{overflow-x:auto;margin:12px 0 18px;border:1px solid var(--line);border-radius:12px;background:var(--card)}
.btbl table{font-size:14px}.btbl caption{text-align:left;padding:10px 14px 2px;font-size:13px;color:var(--muted)}
.btbl th,.btbl td{text-align:right;white-space:nowrap;padding:9px 10px;vertical-align:middle}.btbl .l{text-align:left}
.btbl th[scope=row],.btbl thead th:first-child{text-align:left;position:static;background:transparent;min-width:0;white-space:nowrap}
.btbl thead th{font-weight:600;color:var(--ink-2);vertical-align:bottom}.btbl td small.sub,.btbl th small.sub{display:block;font-weight:400;font-size:12.5px;color:var(--muted)}
.btbl tr:last-child td,.btbl tr:last-child th{border-bottom:0}
.btbl.fx table{table-layout:fixed;min-width:880px}.btbl.fx td,.btbl.fx tbody th{overflow:hidden;text-overflow:ellipsis}
article ul.kpis{list-style:none;padding:0;margin:14px 0 8px;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.kpis li{margin:0;padding:12px 14px;background:var(--card);border:1px solid var(--line);border-radius:12px;display:grid;grid-template-rows:auto 1fr auto;gap:2px}
.kpis b{font-size:26px;line-height:1.2;font-weight:600;white-space:nowrap}.kpis span{font-size:14px;line-height:1.35;color:var(--ink-2)}
article .kpis small{font-size:12.5px;line-height:1.35;color:var(--muted)}
.hbars{margin:14px 0 18px;padding:14px 16px;background:var(--card);border:1px solid var(--line);border-radius:12px}.hbars figcaption{font-size:13px;color:var(--muted);margin:0 0 8px}
.hbars .key{display:flex;flex-wrap:wrap;gap:4px 18px;margin:0 0 10px;font-size:13px;color:var(--ink-2)}.hbars ul{list-style:none;margin:0;padding:0}
.hbars li{display:grid;grid-template-columns:minmax(84px,150px) 1fr auto;align-items:center;gap:12px;margin:0;padding:5px 0;font-size:14px}
.hbars .track{display:flex;gap:2px;height:14px}.hbars .seg{display:block;height:100%;min-width:3px;border-radius:3px}
.hbars .sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}.hbars .n{display:flex;gap:14px;font-variant-numeric:tabular-nums;min-width:96px;justify-content:flex-end}
.seg.one,.sw.one{background:var(--blue)}.seg.two,.sw.two{background:var(--orange)}.seg.none,.sw.none{background:repeating-linear-gradient(135deg,var(--line-2) 0 2px,var(--card) 2px 4px);box-shadow:inset 0 0 0 1px var(--line-2)}
article details.how{margin:22px 0 8px}article details.how ul{margin:4px 0 8px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.tabs a{display:inline-flex;align-items:center;min-height:44px;padding:4px 16px;border:1px solid var(--line);border-radius:999px;text-decoration:none;color:var(--ink-2);background:var(--card)}
.tabs a[aria-current=page]{background:var(--ink);color:var(--on-ink);border-color:var(--ink)}
ul.posts{list-style:none;padding:0;margin:0}ul.posts li{margin:12px 0}
ul.posts a.post{display:grid;gap:4px;text-decoration:none;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 18px}
ul.posts a.post:hover{border-color:var(--line-2)}ul.posts .kind{font-size:13px;color:var(--muted)}
ul.posts h2{font-size:19px;margin:0;color:var(--ink)}ul.posts p{margin:0;color:var(--ink-2);font-size:14px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pager{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:24px 0 8px}
.pager a{display:inline-flex;align-items:center;min-height:44px;padding:6px 14px;border:1px solid var(--line);border-radius:10px;text-decoration:none;background:var(--card)}
.more{margin-top:28px}.more ul{list-style:none;padding:0;margin:8px 0 0;display:flex;flex-wrap:wrap;gap:8px}
.more a{display:inline-flex;align-items:center;min-height:44px;padding:4px 14px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:var(--card);color:var(--ink-2)}
@media (max-width:640px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.kpis b{font-size:22px}.hbars li{grid-template-columns:1fr auto;gap:2px 10px}.hbars .k{grid-column:1/-1}.hbars{padding:12px}}
"""


def _site() -> str:
    return settings.PUBLIC_SITE_URL


def _shorten(text: str, n: int = 158) -> str:
    """A description for search results: at most `n` characters, cut at a word."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def _when(v) -> str:
    try:
        return blog.short_day(str(v)[:10])
    except ValueError:
        return ""


def _kind_line(p: dict) -> str:
    where = blog.MARKET_NAME.get(p.get("market") or "")
    return KIND_NAME.get(p["kind"], "Post") + (f" · {where}" if where else "")


def _feed_link() -> str:
    return f'<link rel="alternate" type="application/atom+xml" title="StratLab blog" href="{_site()}/blog/feed.xml">\n'


def _crumbs(*items: tuple[str, str]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": n, "name": name, "item": url} for n, (name, url) in enumerate([("StratLab", _site() + "/"), *items], 1)]}


def _html(body: str, status: int = 200, headers: dict | None = None) -> HTMLResponse:
    return HTMLResponse(body, status_code=status, headers=headers or {"Cache-Control": CACHE})


def _unavailable() -> HTMLResponse:
    """The posts can't be read right now: a page a visitor can read, never cached, and 503 so a crawler tries again."""
    body = sp._page(sp._head("The blog is busy · StratLab", "The blog can't be read right now.", _site() + "/blog", robots="noindex,follow"), None,
                    '<h1>The blog is busy</h1><p class="muted">Please try again in a minute.</p>')
    return HTMLResponse(body, status_code=503, headers={"Retry-After": "120", "Cache-Control": "no-store"})


def _not_found(what: str = "post") -> HTMLResponse:
    body = sp._page(sp._head("Page not found · StratLab", "That blog page doesn't exist.", _site() + "/blog", f"<style>{STYLE}</style>", robots="noindex,follow"), None,
                    f'<h1>That {e(what)} isn\'t here</h1><p class="muted">It may have been moved or taken down.</p>'
                    '<div class="ctas"><a class="btn" href="/blog">All blog posts</a><a class="btn ghost" href="/blog/briefs">Market briefs</a></div>')
    return HTMLResponse(body, status_code=404, headers={"Cache-Control": "public, max-age=60, s-maxage=60"})


# ---------- the lists ----------
def _page_no(raw) -> int:
    try:
        return max(1, min(blog.MAX_PAGE, int(str(raw or "1")[:4])))
    except ValueError:
        return 1


def _tabs(kind: str | None) -> str:
    return '<nav class="tabs" aria-label="Blog sections">' + "".join(
        f'<a href="{PATHS[k]}"' + (' aria-current="page"' if k == kind else "") + f">{label}</a>"
        for k, label in ((None, "All posts"), ("brief", "Market briefs"), ("research", "Research"))) + "</nav>"


def _card_text(r: dict) -> str:
    """A post's line on the list: the summary without what the card already says. A brief's title holds its day, and the page's own
    lead says "Facts, not advice", so the card kept neither "Tuesday 27 October 2026:" nor a "Facts, not advice." on every post
    (VR4-010). The summary itself, in full, stays the post's description and the feed's."""
    t = re.sub(r"\s*Facts, not advice\.$", "", str(r.get("summary") or ""))
    if r.get("kind") == "brief":
        t = re.sub(r"^[A-Z][a-z]+day \d{1,2} [A-Z][a-z]+ \d{4}: ", "", t)
    return t


def list_page(kind: str | None, page: int) -> HTMLResponse:
    site, path = _site(), PATHS[kind]
    rows, total = blog.listing(kind, None, page)
    pages = max(1, -(-total // blog.PER_PAGE))
    if page > pages or (page > 1 and not rows):
        return _not_found("page")
    canonical = site + path + (f"?page={page}" if page > 1 else "")
    title, desc = TITLES[kind]
    if page > 1:
        title, desc = title.replace(" · StratLab", "") + f" (page {page}) · StratLab", desc
    cards = "".join(
        f'<li><a class="post" href="/blog/{e(r["slug"])}"><span class="kind">{e(_kind_line(r))} · {e(_when(r["published_at"]))}</span>'
        f'<h2>{e(r["title"])}</h2><p>{e(_shorten(_card_text(r), 220))}</p></a></li>' for r in rows)
    pager = ""
    links = []
    if page > 1:
        links.append(f'<a rel="prev" href="{e(path + ("?page=%d" % (page - 1) if page > 2 else ""))}">Newer posts</a>')
    if page < pages:
        links.append(f'<a rel="next" href="{e(path)}?page={page + 1}">Older posts</a>')
    if links:
        pager = f'<nav class="pager" aria-label="Pages">{"".join(links)}</nav>'
    rel = (f'<link rel="prev" href="{site}{path}{"?page=%d" % (page - 1) if page > 2 else ""}">\n' if page > 1 else "") \
        + (f'<link rel="next" href="{site}{path}?page={page + 1}">\n' if page < pages else "")
    ld = sp._ld([{"@context": "https://schema.org", "@type": "Blog", "name": "StratLab blog", "url": site + "/blog", "inLanguage": "en",
                  "publisher": {"@type": "Organization", "name": "StratLab", "url": site + "/"}},
                 _crumbs(("Blog", site + "/blog"), *([(TITLES[kind][0].split(" · ")[0], site + path)] if kind else []))])
    intro = {None: "Daily market briefs and research built from StratLab's own data. Every post gives its data, its period and its method.",
             "brief": "Each trading day's India and US market brief, written after the close from market data.",
             "research": "Research built from StratLab's own data, each with its data source, period, method and limits."}[kind]
    body = (f'<h1>{"StratLab blog" if kind is None else KIND_NAME[kind] + "s" if kind == "brief" else "Research"}</h1><p class="muted">{e(intro)} Facts, not advice.</p>'
            + _tabs(kind) + (f'<ul class="posts">{cards}</ul>' if cards else '<p class="muted">No posts yet. The first market brief is written after the next close.</p>')
            + pager)
    head = sp._head(title, desc, canonical, f"{_feed_link()}{rel}{ld}<style>{STYLE}</style>")
    return _html(sp._page(head, None, body))


# ---------- one post ----------
def post_page(slug: str) -> HTMLResponse:
    post = blog.get(slug)
    if not post or not post.get("published"):
        return _not_found()
    site = _site()
    canonical = f"{site}/blog/{post['slug']}"
    indexable = bool(post.get("indexable"))
    before, after = blog.neighbours(post) if indexable else (None, None)
    published, modified = str(post["published_at"]), str(post["updated_at"])
    title = f"{post['title']} · StratLab"
    desc = _shorten(post["summary"])
    blocks = (post.get("body") or {}).get("blocks") or []
    art = {"@context": "https://schema.org", "@type": "Article", "headline": post["title"][:110], "description": desc,
           "datePublished": published, "dateModified": modified, "inLanguage": "en", "url": canonical,
           "mainEntityOfPage": {"@type": "WebPage", "@id": canonical}, "image": [site + "/og-image.png"],
           "author": {"@type": "Organization", "name": "StratLab", "url": site + "/"},
           "publisher": {"@type": "Organization", "name": "StratLab", "url": site + "/",
                         "logo": {"@type": "ImageObject", "url": site + "/icon-512.png"}}}
    crumbs = _crumbs(("Blog", site + "/blog"), (KIND_NAME[post["kind"]] + ("s" if post["kind"] == "brief" else ""), site + PATHS[post["kind"]]), (post["title"], canonical))
    extra = (_feed_link() + f'<meta property="article:published_time" content="{e(published)}">'
             f'<meta property="article:modified_time" content="{e(modified)}"><meta property="article:author" content="StratLab">\n'
             + sp._ld([art, crumbs]) + f"<style>{STYLE}</style>")
    robots = "index,follow" if indexable else "noindex,follow"
    changed = _when(modified) != _when(published)
    where = blog.MARKET_NAME.get(post.get("market") or "")
    more = [("/stocks", "Company pages"), ("/library", "Strategy library"), ("/new", "Test a trading idea on past prices")]
    if post["kind"] == "brief":
        more = [(blog.ROTATION_PATH.get(post["market"], "/research/rotation"), "Sector rotation chart"), ("/blog/briefs", "All market briefs")] + more
    else:
        more = [("/blog/research", "More research")] + more
    nav = ""
    if before or after:
        nav = ('<nav class="pager" aria-label="Earlier and later posts">'
               + (f'<a rel="prev" href="/blog/{e(before["slug"])}">&larr; {e(_shorten(before["title"], 70))}</a>' if before else "<span></span>")
               + (f'<a rel="next" href="/blog/{e(after["slug"])}">{e(_shorten(after["title"], 70))} &rarr;</a>' if after else "<span></span>") + "</nav>")
    body = (f'<article><p class="blog-eyebrow"><a href="/blog">Blog</a> · <a href="{PATHS[post["kind"]]}">{e(KIND_NAME[post["kind"]])}{"s" if post["kind"] == "brief" else ""}</a>'
            f'{" · " + e(where) if where else ""}</p><h1>{e(post["title"])}</h1>'
            f'<p class="byline">By StratLab · <time datetime="{e(published)}">Published {e(_when(published))}</time>'
            + (f' · <time datetime="{e(modified)}">Updated {e(_when(modified))}</time>' if changed else "") + "</p>"
            f'<p class="facts">{e(FACTS)}</p>' + blog.blocks_html(blocks)
            + '<section class="more" aria-label="More on StratLab"><h2>More on StratLab</h2><ul>'
            + "".join(f'<li><a href="{e(h)}">{e(t)}</a></li>' for h, t in more) + "</ul></section>" + nav + "</article>")
    head = sp._head(title, desc, canonical, extra, robots=robots, og_type="article")
    page = ads.add_to_page(sp._page(head, None, body), "blog")        # ADS-1: as the page is sent; unchanged while ads are off
    return _html(page, headers={"Cache-Control": CACHE, **({} if indexable else {"X-Robots-Tag": "noindex, follow"})})


# ---------- the feed ----------
def feed_xml() -> str:
    site = _site()
    rows = blog.feed_rows()
    updated = max((str(r["updated_at"]) for r in rows), default=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    items = "".join(
        f'<entry><title>{xml(r["title"])}</title><link href="{xml(site + "/blog/" + r["slug"])}" rel="alternate" type="text/html"/>'
        f'<id>{xml(site + "/blog/" + r["slug"])}</id><published>{xml(str(r["published_at"]))}</published><updated>{xml(str(r["updated_at"]))}</updated>'
        f'<summary type="text">{xml(r["summary"])}</summary><category term="{xml(r["kind"])}"/></entry>' for r in rows)
    return ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>StratLab blog</title>'
            "<subtitle>Daily market briefs and research from StratLab's own data. Facts, not advice.</subtitle>"
            f'<link href="{site}/blog/feed.xml" rel="self" type="application/atom+xml"/><link href="{site}/blog" rel="alternate" type="text/html"/>'
            f"<id>{site}/blog</id><updated>{xml(updated)}</updated><author><name>StratLab</name><uri>{site}/</uri></author>"
            f"<rights>StratLab. Facts, not advice.</rights>{items}</feed>\n")


# ---------- routes ----------
def _safely(fn, *a):
    try:
        return fn(*a)
    except Exception as ex:                 # the posts can't be read: said to the visitor, never a raw error
        print("blog page failed:", type(ex).__name__, str(ex)[:160])
        return _unavailable()


@router.get("/blog", response_class=HTMLResponse)
@router.get("/blog/", response_class=HTMLResponse)
def blog_index(page: str = "1"):
    return _safely(list_page, None, _page_no(page))


@router.get("/blog/briefs", response_class=HTMLResponse)
@router.get("/blog/briefs/", response_class=HTMLResponse)
def blog_briefs(page: str = "1"):
    return _safely(list_page, "brief", _page_no(page))


@router.get("/blog/research", response_class=HTMLResponse)
@router.get("/blog/research/", response_class=HTMLResponse)
def blog_research_list(page: str = "1"):
    return _safely(list_page, "research", _page_no(page))


@router.get("/blog/feed.xml")
def blog_feed():
    try:
        return Response(feed_xml(), media_type="application/atom+xml", headers={"Cache-Control": FEED_CACHE})
    except Exception as ex:
        print("blog feed failed:", type(ex).__name__, str(ex)[:160])
        return Response("The feed can't be read right now.", status_code=503, media_type="text/plain", headers={"Retry-After": "120", "Cache-Control": "no-store"})


@router.get("/blog/{slug}", response_class=HTMLResponse)
@router.get("/blog/{slug}/", response_class=HTMLResponse)
def blog_post(slug: str):
    if not blog.valid_slug(slug):
        return _not_found()
    return _safely(post_page, slug)


# ---------- admin ----------
@admin_router.get("/admin/blog")
def admin_blog(_=Depends(admin.admin_profile)):
    """The posts (newest first, without their words), the last research run and the month it next runs for."""
    rows = blog.admin_rows()
    return ok({"posts": rows, "run": blog_research.last_run(), "running": blog_research._lock.locked(), "site": _site(),
               "counts": {"posts": len(rows), "shown": sum(1 for r in rows if r.get("published") and r.get("indexable")),
                          "hidden": sum(1 for r in rows if not r.get("published")), "not_indexed": sum(1 for r in rows if not r.get("indexable"))}})


class Shown(BaseModel):
    published: bool


@admin_router.post("/admin/blog/posts/{slug}/published")
def admin_blog_show(slug: str, req: Shown, _=Depends(admin.admin_profile)):
    """Publish (true) or unpublish (false) a post. An unpublished post answers 404 and leaves the list, the sitemap and the feed."""
    row = blog.set_published(slug, req.published)
    if not row:
        err(404, "no_post", "That post isn't there.")
    return ok({"slug": slug, "published": bool(row["published"])})


@admin_router.post("/admin/blog/research")
def admin_blog_research(_=Depends(admin.admin_profile)):
    """Write the research posts from the app's data now, in the background (a minute or so)."""
    if blog_research._lock.locked():
        return ok({"started": False, "running": True})
    threading.Thread(target=blog_research.generate, daemon=True, name="blog-research").start()
    return ok({"started": True, "running": True})


@admin_router.post("/admin/blog/briefs")
def admin_blog_briefs(_=Depends(admin.admin_profile)):
    """Add posts for the daily Market Briefs already stored (the newest 60 of each market) that have none yet."""
    from .newsletter import job
    issues = [i for r in ("IN", "US") for i in job.recent("market", r, 60) if not i.get("weekly")]
    return ok(blog.backfill(issues))
