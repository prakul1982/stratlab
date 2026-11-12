"""Business groups (groups.py): made out of the promoters each company names in its shareholding filing, by one rule for
every company (no hand list), with the government and lone shared personal names left out; their figures from the stored
daily rows; the plan gate on the figures; and the promoter group's total read from the filing (shareholders.parse_xbrl)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, groups as G, heatmap, main, shareholders as S

FIX = Path(__file__).parent / "fixtures" / "shareholding"


def co(name, promoters, q="2026-09-30", ppct=None):
    """A stored company: promoters as (name, kind, pct)."""
    row = {"filed": "2026-10-15T10:00", "url": "https://nsearchives.nseindia.com/x.xml",
           "rows": [[n, k, "promoter", 1000, p] for n, k, p in promoters] + [["Some Mutual Fund", "Mutual fund", "public", 10, 2.0]]}
    if ppct is not None:
        row["ppct"] = ppct
    return {"name": name, "q": {q: row}}


ENT, IND, GOV = "Company", "Individual or HUF", "Government"


def world():
    return {
        # three companies naming one promoter company: a group named by the word their names share
        "ALSTEEL": co("Alpha Steel Limited", [("Alpha Sons Private Limited", ENT, 31.8), ("Ravi Alphawala", IND, 1.2)], ppct=33.2),
        "ALPOWER": co("Alpha Power Company Limited", [("ALPHA SONS PVT LTD", ENT, 45.0)], ppct=46.9),
        "ALMOTOR": co("Alpha Motors Limited", [("Alpha Sons Private Limited", ENT, 42.6)]),
        # tied by two promoter individuals, and one is a promoter of a third (a listed company named as promoter)
        "KAPPA": co("Kappa Chemicals Limited", [("Meera Shah", IND, 10.0), ("Nikhil Shah", IND, 8.0)]),
        "LAMBDA": co("Lambda Pharma Limited", [("Meera Shah", IND, 12.0), ("Nikhil Shah", IND, 6.0)]),
        "MU": co("Mu Surfactants Limited", [("Kappa Chemicals Limited", ENT, 51.0)]),
        # one shared personal name is not a tie
        "ONE": co("One Textiles Limited", [("Vijay Kumar", IND, 20.0)]),
        "TWO": co("Two Foods Limited", [("Vijay Kumar", IND, 15.0)]),
        "THREE": co("Three Paper Limited", [("Vijay Kumar", IND, 5.0)]),
        # the government is not a business group
        "PSU1": co("Psu One Limited", [("President of India", GOV, 60.0)]),
        "PSU2": co("Psu Two Limited", [("President of India", GOV, 55.0)]),
        "PSU3": co("Psu Three Limited", [("THE PRESIDENT OF INDIA", "Company", 52.0)]),
    }


def test_the_rule_makes_out_groups_from_shared_promoters_only():
    got = G.build(world())
    by = {g["name"]: g for g in got["groups"]}
    assert set(by) == {"Alpha", "Meera Shah"}            # no word most of its names share: named by its anchor promoter
    alpha = by["Alpha"]
    assert [m["symbol"] for m in alpha["members"]] == ["ALMOTOR", "ALPOWER", "ALSTEEL"]
    assert alpha["named_by"] == "company names" and alpha["confidence"] == "high" and alpha["anchor_count"] == 3
    assert next(m for m in alpha["members"] if m["symbol"] == "ALSTEEL")["promoter_pct"] == 33.2
    assert next(m for m in alpha["members"] if m["symbol"] == "ALSTEEL")["ties"] == ["Alpha Sons Private Limited"]
    other = next(g for g in got["groups"] if g["name"] != "Alpha")
    assert [m["symbol"] for m in other["members"]] == ["KAPPA", "LAMBDA", "MU"] and other["confidence"] == "medium"
    assert got["companies"] == 12 and got["left_out"] == []
    every = {m["symbol"] for g in got["groups"] for m in g["members"]}
    assert not every & {"ONE", "TWO", "THREE", "PSU1", "PSU2", "PSU3"}
    assert len({g["slug"] for g in got["groups"]}) == len(got["groups"])


def test_a_joint_venture_partner_and_a_public_sector_parent_tie_nothing():
    w = {
        # a listed company holding a minority promoter stake in three ventures, each led by another promoter
        "PARTNER": co("Partner Motors Limited", [("Overseas Parent Corporation", "Foreign company", 56.0)]),
        "JV1": co("Jv One Glass Limited", [("Glass Holdings Corporation", "Foreign company", 21.0), ("Partner Motors Limited", ENT, 10.6)]),
        "JV2": co("Jv Two Seats Limited", [("Seat Family Trust", "Trust", 30.0), ("Partner Motors Limited", ENT, 14.8)]),
        "JV3": co("Jv Three Steering Limited", [("Steering Corporation", "Foreign company", 66.0), ("Partner Motors Limited", ENT, 5.4)]),
        # a public-sector company and the companies it promotes
        "PSUA": co("Psu Alpha Limited", [("President of India", GOV, 58.9)]),
        "SUB1": co("Sub One Limited", [("Psu Alpha Limited", ENT, 54.9)]),
        "SUB2": co("Sub Two Limited", [("Psu Alpha Limited", ENT, 71.6), ("Sub One Limited", ENT, 16.9)]),
        "SUB3": co("Sub Three Limited", [("Psu Alpha Limited", ENT, 51.0)]),
        "STATE1": co("State Fert Limited", [("Some State Investments Limited", ENT, 38.0)]),
        "STATE2": co("State Chem Limited", [("Some State Investments Limited", ENT, 41.0)]),
        "STATE3": co("State Power Limited", [("Some State Investments Limited", ENT, 30.0)]),
    }
    assert G.build(w)["groups"] == []


def test_a_chain_too_long_to_be_one_group_is_left_out(monkeypatch):
    monkeypatch.setattr(G, "MAX_MEMBERS", 4)
    chain = {f"C{i}": co(f"Chain {i} Limited", [(f"Link {i} Private Limited", ENT, 10.0), (f"Link {i + 1} Private Limited", ENT, 10.0),
                                                 (f"Link {i + 2} Private Limited", ENT, 10.0)]) for i in range(6)}
    got = G.build(chain)
    assert got["groups"] == [] and got["left_out"][0]["companies"] == 6


def test_the_promoter_groups_total_is_read_from_the_filing():
    text = (FIX / "SAFARI_2026-06-30.xml").read_text()
    assert S.parse_xbrl(text)["promoter_pct"] is None                       # the trimmed sample has no category line
    total = ('<xbrli:context id="ShareholdingOfPromoterAndPromoterGroup_ContextI"><xbrli:entity><xbrli:identifier scheme="x">523025'
             '</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario>'
             '<xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:ShareholdingOfPromoterAndPromoterGroupMember'
             '</xbrldi:explicitMember></xbrli:scenario></xbrli:context><in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares '
             'contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI" decimals="INF" unitRef="pure">0.4471</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>')
    got = S.parse_xbrl(text.replace("</xbrli:xbrl>", total + "</xbrli:xbrl>"))
    assert got["promoter_pct"] == 44.71
    assert sum(h["pct"] for h in got["holders"] if h["group"] == "promoter") < 44.71     # the named members above 1% add up to less
    assert S.PARSER == 3                                                     # stored quarters are read again for it


@pytest.fixture
def mem(monkeypatch):
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(S, "_index", lambda: world())
    monkeypatch.setattr(heatmap, "_facts", lambda region: ({s: {"name": w["name"], "market_cap": cap} for (s, w), cap in
                                                            zip(world().items(), [210000, 130000, 340000, 9000, 8000, 3000, 1, 1, 1, 1, 1, 1])}, {}))
    store[heatmap.KEY + "IN"] = json.dumps({"day": "2026-11-12", "stocks": {
        "ALSTEEL": [150.0, 1.2, 2.0, 5.0, 8.0, 10.0, 20.0, 1e6, 9e5], "ALPOWER": [400.0, 2.6, 1.0, -3.0, 4.0, 5.0, -10.0, 1e6, 9e5],
        "ALMOTOR": [900.0, -0.8, 0.5, 1.0, 2.0, 3.0, 4.0, 1e6, 9e5]}})
    heatmap.clear()
    G.forget()
    yield store
    G.forget()


def test_index_and_group_pages_add_up_the_members_and_hold_back_the_figures_without_the_plan(mem):
    idx = G.index_view()
    alpha = next(g for g in idx["groups"] if g["name"] == "Alpha")
    assert alpha["cap"] == 680000 and alpha["companies"] == 3 and alpha["largest"][0]["symbol"] == "ALMOTOR"
    before = 210000 / 1.012 + 130000 / 1.026 + 340000 / 0.992
    assert alpha["change"]["1d"] == round((680000 / before - 1) * 100, 2)
    page = G.group_view(alpha["slug"])
    assert [r["symbol"] for r in page["companies"]] == ["ALMOTOR", "ALSTEEL", "ALPOWER"]
    s = next(r for r in page["companies"] if r["symbol"] == "ALSTEEL")
    assert (s["close"], s["change"]["1d"], s["change"]["1m"], s["change"]["1y"], s["promoter_pct"]) == (150.0, 1.2, 5.0, 20.0, 33.2)
    assert len(page["tiles"]) == 3 and page["rule"] and "Not advice" in page["note"]
    teaser = G.group_view(alpha["slug"], full=False)
    t = next(r for r in teaser["companies"] if r["symbol"] == "ALSTEEL")
    assert t["change"]["1d"] == 1.2 and t["change"]["1m"] is None and t["change"]["1y"] is None and t["promoter_pct"] is None
    assert teaser["tiles"] == [] and teaser["cap"] == 680000
    assert G.index_view(full=False)["groups"][0]["change"]["1y"] is None
    assert G.group_of("ALPOWER")["slug"] == alpha["slug"] and G.group_of("ONE") is None


@pytest.fixture
def client(mem):
    who = {"p": {"id": "u1", "plan": "basic", "_plan": "basic"}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["p"]
    c = TestClient(main.app)
    c.who = who
    yield c
    main.app.dependency_overrides.clear()


def test_the_group_routes_and_their_plan_gate(client):
    idx = client.get("/invest/groups").json()
    slug = next(g["slug"] for g in idx["groups"] if g["name"] == "Alpha")
    page = client.get(f"/invest/groups/{slug}").json()
    assert page["full"] is True and page["companies"][0]["change"]["1y"] == 4.0 and page["plan_needed"] is None
    assert client.get("/invest/groups/no-such-group").status_code == 404
    assert client.get("/invest/groups/of/ALSTEEL").json()["group"]["slug"] == slug
    client.who["p"] = {"id": "u1", "plan": "free", "_plan": "free"}
    page = client.get(f"/invest/groups/{slug}").json()
    assert page["full"] is False and page["plan_needed"] == "Basic" and page["companies"][0]["change"]["1y"] is None and page["tiles"] == []
    assert page["companies"][0]["change"]["1d"] == -0.8 and page["companies"][0]["cap"] == 340000
