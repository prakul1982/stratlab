"""The site's own public pages (the landing page and the policies), for the sitemap: each address and the day its words
last changed. The same list is in the web app's frontend/src/content/seo.ts (the pages marked index: true);
frontend/unit/seo.test.mjs fails when the two differ, so a page can't be added to one and forgotten in the other.
Change a date when the page's words change."""
from . import library

# (address, day the page's words last changed)
PAGES = [
    ("/", "2026-10-08"),
    ("/pricing", "2026-10-08"),
    ("/faq", "2026-10-08"),
    ("/library", "2026-10-08"),
    ("/terms", "2026-09-26"),
    ("/privacy", "2026-10-08"),
    ("/refunds", "2026-09-26"),
    ("/contact", "2026-09-26"),
]


def library_pages() -> list[tuple[str, str | None]]:
    """StratLab's own library strategies that visitors can open (/library/<id>), with the day each was published."""
    out = []
    for e in library.all_entries():
        if library.is_public(e) and library.ID.match(e.get("id") or ""):
            out.append((f"/library/{e['id']}", str(e.get("published_at") or "")[:10] or None))
    return sorted(out)
