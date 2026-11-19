"""Lane ci60: where Release 60's lanes met (fix9's theme addresses beside B3's share teaser and blog2's theme posts, ...)."""
from app import main  # noqa: F401, I001


def _logistics(monkeypatch):
    from app import computed
    from app.intel import theme_base
    monkeypatch.setattr(computed, "index", lambda kind: {"entries": {"h1": {"region": "IN", "label": "Logistics", "at": 1,
                                                                            "meta": {"rules": theme_base.RULES, "q": "logistic", "aliases": []}}}})


# ---------- LIVE9A-029 beside B3 and blog2: every link to a stored theme's public page is its own address, not the old alias ----------
def test_a_shared_theme_and_a_theme_post_link_the_page_at_its_shown_name(monkeypatch):
    from app import blog_research, public_themes as pt, share
    _logistics(monkeypatch)
    snap = share.theme_snapshot("IN", {"name": "logistic", "entry": {"label": "Logistics"}, "at": 1,
                                       "payload": {"summary": "Moving goods.", "value_chain": []}})
    assert snap["page"] == "/themes/in/logistics" and snap["slug"] == "logistics"
    assert pt.page_path("IN", "logistic") == "/themes/in/logistics"
    assert blog_research.theme_page_path("logistic", "IN") == "/themes/in/logistics"
    # a theme with no stored entry keeps the name's own address (it finds the theme once stored, or says none is there)
    assert pt.page_path("IN", "Rail") == "/themes/in/rail"
