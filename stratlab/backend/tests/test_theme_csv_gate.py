"""Release 43: a theme's companies as a CSV is a download, so Basic and up (plans.py "theme_workbook", the theme's downloads), answered
by the server (GET /research/theme-dive/companies.csv) with a 402 for Free. Free still sees every company on the theme's page."""
import csv
import io

from tests.test_research_api import api  # noqa: F401  (the research API on the fake sources)

URL = "/research/theme-dive/companies.csv?q=AI%20data%20centers&region=US"


def test_free_gets_a_402_naming_basic_and_nothing_is_counted(api, monkeypatch):
    from app.intel import routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    r = api.get(URL)
    assert r.status_code == 402
    d = r.json()["detail"]
    assert d["code"] == "upgrade_required" and "Basic" in d["message"] and "CSV" in d["message"]
    assert api.usage == []


def test_basic_gets_every_company_of_the_page_with_its_figures_and_no_deck_is_counted(api, monkeypatch):
    from app import main
    from app.intel import routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "basic", "plan": "basic"}
    r = api.get(URL)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    disp = r.headers["content-disposition"]
    assert disp.startswith('attachment; filename="stratlab-theme-ai-data-centers-us-companies-') and disp.endswith('.csv"')
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["Company", "Symbol", "Layer", "Industry", "Market value ($ million)", rows[0][5], "EBITDA margin (%)", "Net margin (%)",
                       "ROCE (%)", "Year of the figures", "In the theme by", "What it does, in its own words"]
    assert rows[0][5].startswith("Revenue (")
    assert len(rows) > 1 and all(len(x) == 12 and x[0] and x[1] and x[2] for x in rows[1:])
    assert not any(u.startswith("deck") for u in api.usage)


def test_a_cell_that_starts_like_a_formula_is_written_as_text():
    from app.intel import theme_routes
    m = {"sector": "T", "value_chain": [{"layer": "L", "companies": [{"ticker": "AAA", "name": "=HYPERLINK(1)", "base": True}]}], "sub_themes": []}
    rows = list(csv.reader(io.StringIO(theme_routes.companies_csv(m, {"layers": [], "subs": []}, "US").decode("utf-8-sig"))))
    assert rows[1][0] == "'=HYPERLINK(1)" and rows[1][10] == "Official industry"
