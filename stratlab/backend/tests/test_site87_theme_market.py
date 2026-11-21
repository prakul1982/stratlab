"""site87 (owner: with India picked, "India defence" open, then "$ United States": the US mapped "India defence"): a theme whose name names
one market's country is never mapped in the other market. The page clears or swaps it on a switch (e2e/site87.spec.ts); the API refuses it."""
from app.intel import theme_market as M
from tests.test_research_api import api  # noqa: F401  (the research pages' fake world, signed in)


def test_the_country_a_theme_names():
    for q in ("India defence", "Indian railways", "railways capex india", "Bharat electronics theme"):
        assert M.country_of(q) == "IN", q
    for q in ("US shale", "us defense", "American banks", "United States housing", "U.S. utilities", "defense us"):
        assert M.country_of(q) == "US", q
    for q in ("Defence", "Specialty chemicals", "Railways capex", "AI data centers", "Business services", "Bonus issues", "Industrials"):
        assert M.country_of(q) is None, q
    assert M.country_of("India and US trade") is None          # names both: neither market's own
    assert M.foreign("India defence", "US") == "IN" and M.foreign("India defence", "IN") is None
    assert M.foreign("US shale", "IN") == "US" and M.foreign("Defence", "US") is None


def test_the_api_refuses_a_theme_of_the_other_markets_country(api):  # noqa: F811
    for path in ("/research/sector", "/research/theme-dive", "/research/theme-dive/news", "/research/theme-dive/prices"):
        r = api.get(f"{path}?q=India%20defence&region=US")
        assert r.status_code == 400, (path, r.status_code)
        body = r.json()
        detail = body.get("detail", body)
        assert detail["code"] == "theme_other_market"
        assert "India" in detail["message"] and "the US" in detail["message"]
    r = api.get("/research/sector?q=US%20shale&region=IN")
    assert r.status_code == 400
    # the same theme in its own market is not refused here
    assert api.get("/research/sector?q=India%20defence&region=IN").status_code != 400
