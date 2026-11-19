"""Every browser tab's title has one pattern (owner, 18 Nov): "Page · StratLab" ("Reliance Industries (RELIANCE) share
price, financials and filings · StratLab"), the brand alone where a page has no name of its own. This is the one place the
server writes it; the app writes the same from frontend/src/content/seo.ts (withBrand). A page's name is one part: a second
part goes after a colon, never after another " · "."""

BRAND = "StratLab"


def page_title(name: str | None = None) -> str:
    """'<name> · StratLab', or 'StratLab' for no name."""
    return f"{name} · {BRAND}" if name else BRAND
