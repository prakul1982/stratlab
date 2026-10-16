"""The site's own public pages (the landing page and the policies), for the sitemap: each address and the day its words
last changed. The same list is in the web app's frontend/src/content/seo.ts (the pages marked index: true whose canonical address is their own: /pricing names / and is left out);
frontend/unit/seo.test.mjs fails when the two differ, so a page can't be added to one and forgotten in the other.
Change a date when the page's words change."""
from . import library, library_seed

# (address, day the page's words last changed)
PAGES = [
    ("/", "2026-10-17"),
    ("/faq", "2026-10-08"),
    ("/library", "2026-10-08"),
    ("/terms", "2026-10-16"),
    ("/privacy", "2026-10-15"),
    ("/refunds", "2026-09-26"),
    ("/contact", "2026-09-26"),
]


def library_pages() -> list[tuple[str, str | None]]:
    """StratLab's own library strategies that visitors can open (/library/<id>), with the day each was published. Only the seeded ones: the build writes a page
    for those alone (there's no /library rewrite to the app), so any other id would be a 404."""
    built = {library_seed.entry_id(slug, pid) for slug, s in library_seed.STRATEGIES.items() for _, pid in s["groups"]}
    out = []
    for e in library.public_entries():
        if e.get("id") in built and library.ID.match(e["id"]):
            out.append((f"/library/{e['id']}", str(e.get("published_at") or "")[:10] or None))
    return sorted(out)
