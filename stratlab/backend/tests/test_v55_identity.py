"""Lane v55 (Release 55, the owner's review of the live R54 decks): company identity, theme membership, business stage and fallback layers,
proven on exact replays of the live R54 placement inputs (GET /research/theme-dive/placement-inputs, read 14 Nov 2026 under RULES 53:
tests/fixtures/themes_live/inputs_r54/<theme>.json, each with the moves its stored change log records, `moved_before`).

1 P0 identity before exclusion: a listing line names its issuer only once its own words are taken off ("Adyen Nv-Unspon ADR" is Adyen); a
  company the map named whose check gave no answer is not checked yet, never "own words describe other work"; one whose principal business,
  in its own words, fits the theme is in it (a payments platform in a payments theme).
2 P0 membership before layer: a company whose principal business is a kind of product the theme's definition doesn't include is screened
  out with its reason, never parked in "Other" (Indo National, batteries and torches, in FMCG).
3 P0 business stage: a commercial-stage company is displayed in the map's commercial layer, never in a layer named by a development stage
  (Merck and Novartis out of "Pipeline-stage and royalty-funded drug developers"), by its own words or its stored revenue.
4 P1 fallback layers: contract manufacturers of the theme's products left in "Other" go to a layer of their kind (UFP Technologies and
  Integer Holdings in Medical devices), one alone is said to be one (Hindustan Foods in FMCG).
5 P1 the membership check's progress is said apart from the companies with figures.
"""
import json
import pathlib
import sys
import types
from datetime import date, datetime, timezone

import pytest

from app import deck as DK
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_routes as TR
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r54"
ORIGIN = {"payments": {"FLYW": "Card networks"}}     # the map layer the one map pick the split moved was named in (test_exact_replay's way)
STALE = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit", "sold_by")
PIPELINE, LARGE = "Pipeline-stage and royalty-funded drug developers", "Large pharma and biotech portfolios"
_CACHE: dict = {}

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check as DC  # noqa: E402


def inputs(key: str) -> dict:
    if key not in _CACHE:
        d = json.loads((LIVE / f"{key}.json").read_text())
        d = d.get("data", d)
        for v in d["value_chain"]:
            v["companies"] = [{k: x for k, x in c.items() if k not in STALE} for c in v["companies"]]
        _CACHE[key] = d
    return json.loads(json.dumps(_CACHE[key]))


def replay(key: str, **kw) -> dict:
    """The live R54 placement placed again from its live inputs, as theme_routes.placed feeds it (no AI)."""
    d = inputs(key)
    m = X.pre_map(d, ORIGIN.get(key, {}), {})
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d["previous"], off_before=d.get("off_before") or {},
                          moved_before=d.get("moved_before") or {}, **kw)
    return out


def layers(vc) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"])) for v in vc for c in v["companies"]}


def row(out, sym):
    return next(c for v in out["value_chain"] for c in v["companies"] if c["ticker"] == sym)


def deck(key: str, out: dict | None = None):
    from tests.test_export import texts
    from tests.test_r18_deck import deck_of
    from tests.test_r48_reconcile import co
    d = inputs(key)
    out = out or replay(key)
    f = {}
    for li, v in enumerate(out["value_chain"]):
        base = 6.0 + 3.3 * (li % 7)
        for i, c in enumerate(v["companies"]):
            sales = 1000.0 + 37 * i
            f[c["ticker"]] = co(c["ticker"], c.get("name") or c["ticker"], sales, base + (i % 3) - 1, sales * (base - 4) / 100)
    v, slides = deck_of(d["region"], {**out, "sector": d["theme"], "sub_themes": out.get("sub_themes") or []}, f, theme=d["theme"],
                        about=d["evidence"].get)
    return v, "\f".join(texts([s]) for s in DK.with_held(slides))          # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)


# ---------- 1 P0 identity before exclusion ----------
def test_a_listing_line_is_looked_up_under_the_issuer_it_stands_for():
    """Fails before: the encyclopedia was asked for "Adyen Nv-Unspon ADR", which names no company, so no description of Adyen was ever read."""
    assert B.issuer_name("Adyen Nv-Unspon ADR") == "Adyen" and TR.plain_name("Adyen Nv-Unspon ADR") == "Adyen"
    assert B.issuer_name("Toyota Motor Corp ADR (each repr 10 ord)") == "Toyota Motor"
    assert B.listing_line("Adyen Nv-Unspon ADR") == "listed as an unsponsored depositary receipt of Adyen"
    assert B.listing_line("Infosys Ltd ADR") == "listed as a depositary receipt of Infosys" and B.listing_line("Visa Inc.") == ""
    # ordinary share lines as before
    assert TR.plain_name("Qnity Electronics, Inc.") == "Qnity Electronics" and TR.plain_name("Bharti Airtel Ltd") == "Bharti Airtel"


ADYEN = ("Adyen N.V. is a Dutch payment company with the status of an acquiring bank. It provides an end-to-end payments platform that lets "
         "businesses accept e-commerce, mobile and point-of-sale payments, and it processes the payments of merchants worldwide.")


@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    monkeypatch.setattr(TR, "filing_reads", TR.Window())
    monkeypatch.setattr(TR, "_business_read", lambda sym: "")
    TR.EVIDENCE_CACHE.clear()
    yield kept
    TR.EVIDENCE_CACHE.clear()


def test_a_depositary_receipt_found_with_no_description_is_read_again_under_its_issuer(store, monkeypatch):
    """Fails before: the stored "none found" of "Adyen Nv-Unspon ADR" stood, and a new read asked for the listed name again."""
    asked = []
    hub = types.SimpleNamespace(wiki=types.SimpleNamespace(company=lambda name: asked.append(name) or ({"title": "Adyen", "extract": ADYEN}
                                                                                                         if name == "Adyen" else None)))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store["theme:evidence:US:ADYEY"] = json.dumps({"at": now, "about": "", "industry": "", "v": TR.ABOUT_V})
    got, pending = TR.evidence_reader("US", {"ADYEY": "Adyen Nv-Unspon ADR"})(["ADYEY"])
    assert asked == ["Adyen"] and not pending and got["ADYEY"]["about"].startswith("Adyen N.V. is a Dutch payment company")
    rec = json.loads(store["theme:evidence:US:ADYEY"])
    assert rec["issuer"] == "Adyen"
    # once looked up under its issuer, a "none found" is not read again each pass; an ordinary share line's never was
    assert not TR.thin_about({**rec, "about": ""}, "US", "Adyen Nv-Unspon ADR")
    assert not TR.thin_about({"at": now, "about": "", "v": TR.ABOUT_V}, "US", "Visa Inc.")


def test_adyen_with_no_words_is_not_checked_yet_never_a_company_whose_words_describe_other_work_on_the_live_r54_inputs():
    """Fails before: the live R54 Payments deck listed "Adyen Nv-Unspon ADR" (and WISeQey) among the "companies with figures whose own words
    describe other work", though no word of Adyen's was ever read (evidence_state "not_confirmed" for every unanswered map pick)."""
    d = inputs("payments")
    ady = row({"value_chain": d["value_chain"]}, "ADYEY")
    assert d["evidence"]["ADYEY"] is None and ady["verified"] is False and not ady["base"]
    words = D.theme_words({"value_chain": d["value_chain"]}, d["theme"])
    status = D.membership(ady, words, None)
    assert status == "unverified" and D.evidence_state(ady, words, None, None, status) == "membership_unverified"
    rec = D.theme_record(ady, status, None)
    assert "listed as an unsponsored depositary receipt of Adyen; no description of Adyen is stored yet" in rec["why"]
    v, text = deck("payments", out=inputs("payments"))          # the map as served (the replay's map makes every placed company a base one)
    assert not any(x["name"].startswith("Adyen") for x in v["checks"]["unverified"])
    assert any(x["name"].startswith("Adyen") and "unsponsored depositary receipt of Adyen" in x["why"] for x in v["checks"]["unchecked"])
    flat = " ".join(text.split())
    assert "whose membership is not checked yet: " in flat and "(not checked yet): Adyen Nv-Unspon ADR, listed as an unsponsored" in flat
    assert DC.check_text(text)["counts"]["identity unresolved"] == 0


def test_a_payments_platform_whose_own_words_fit_is_in_a_payments_theme_when_its_check_gave_no_answer():
    """Fails before: with the check unanswered, any company the map named from another industry was "unverified", whatever its words."""
    d = inputs("payments")
    words = D.theme_words({"value_chain": d["value_chain"]}, d["theme"])
    named = D.name_words({"value_chain": d["value_chain"]}, d["theme"])
    ady = {**row({"value_chain": d["value_chain"]}, "ADYEY"), "what": ""}
    status = D.membership(ady, words, ADYEN, named=named)
    assert status == "exposure" and D.evidence_state(ady, words, ADYEN, None, status) == "description_verified"
    assert D.membership(ady, words, ADYEN) == "unverified"            # (a caller that gives no theme names: as before)
    assert D.theme_record(ady, status, ADYEN)["why"].endswith("its principal business, in its own words, is of the theme's work")
    # words of another business still leave it unconfirmed (not checked yet: no answer), never in the theme by them
    other = "Acme Corp. is an American company that operates hotels and restaurants across the Midwest."
    assert D.membership(ady, words, other, named=named) == "unverified"


# ---------- 2 P0 membership before layer ----------
def test_indo_national_is_screened_out_of_fmcg_never_parked_in_other_on_the_live_r54_inputs():
    """Fails before: Indo National (batteries, torches, electrical accessories), taken out of "Branded packaged foods manufacturing", stayed
    a member in "Other FMCG companies". Now its principal business is checked against the theme's definition before any layer."""
    out = replay("fmcg")
    assert "NIPPOBATRY" not in layers(out["value_chain"])
    off = next(x for x in out["placements"]["off_industry"] if x["ticker"] == "NIPPOBATRY")
    assert off["scope"] == "batteries, torches and electrical goods" and "which the theme's definition doesn't include" in off["why"]
    assert DK.off_industry_line({"placements": out["placements"]}) == (
        "Outside the theme's definition: High Energy Batteries (India) Ltd (filed under Household Products; no description of its own; its "
        "name names batteries, torches and electrical goods); Indo National Ltd (filed under Household Products; its principal business is of "
        # r67e (P0-1, updated on purpose): the words of its own sentence that name the kind quoted beside it
        "batteries, torches and electrical goods: its own words, “manufactures and markets batteries”).")
    # every other company keeps its live layer (the one other difference is the replay's own, before this change too)
    live = layers(inputs("fmcg")["value_chain"])
    assert {s for s, x in layers(out["value_chain"]).items() if live.get(s) != x} == {"GPAPL"}
    assert set(live) - set(layers(out["value_chain"])) == {"NIPPOBATRY", "HIGHENE"}


def test_a_battery_maker_with_no_description_cant_stay_in_fmcg_through_other_on_the_live_r54_inputs():
    """The owner's acceptance test, "a battery maker can't remain in FMCG solely through Other". Fails before: High Energy Batteries (India),
    no description of its own stored, stayed in "Other FMCG companies" as not checked yet. With no words of its own, its official industry,
    else its listed name, is read against the theme's definition. (Panasonic Energy India, also with none, stays: neither its industry,
    Household Products, nor its name names a kind of product outside the theme.)"""
    out = replay("fmcg")
    got = layers(out["value_chain"])
    assert "HIGHENE" not in got and got["PANAENERG"] == "Other"
    off = next(x for x in out["placements"]["off_industry"] if x["ticker"] == "HIGHENE")
    assert off["scope_where"] == "name" and off["why"] == ("filed under Household products; no description of its own is stored, and its name "
                                                           "(“High Energy Batteries (India)”) names batteries, torches and electrical goods "
                                                           "(“Batteries”); outside the theme's definition")
    fmcg = B.scope_text("FMCG", "", [v for v in inputs("fmcg")["value_chain"] if not v.get("official")])
    by_ind = C.off_scope_listed("Acme Ltd", "Electrical Equipment > Batteries", fmcg)
    assert by_ind["where"] == "industry" and by_ind["kind"] == "batteries, torches and electrical goods"
    assert C.off_scope_listed("Acme Ltd", "Household Products", fmcg) is None
    assert C.off_scope_listed("Hindustan Foods Ltd", "Diversified FMCG", fmcg) is None
    # in a theme whose definition names the kind, a battery maker is the theme's
    assert C.off_scope_listed("High Energy Batteries (India) Ltd", "", "Automotive Auto components and batteries") is None


def test_the_out_of_scope_catalogue_reads_each_kind_of_product_only_outside_themes_of_its_scope():
    fmcg = "FMCG Branded packaged foods manufacturing Branded home, personal care and FMCG Beverages, coffee and mixed consumer foods"
    said = {k: C.off_scope(t, fmcg, "Acme Ltd") for k, t in (
        ("cables", "Acme manufactures power cables and wires for utilities."),
        ("steel", "Acme manufactures stainless steel pipes and alloy steel bars."),
        ("cement", "Acme manufactures cement and clinker in two plants."),
        ("tyres", "Acme manufactures tyres for trucks and buses."),
        ("fertilisers", "Acme manufactures fertilisers and pesticides for farmers."))}
    assert {k: (x or {}).get("kind") for k, x in said.items()} == {"cables": "cables, wires and electrical equipment", "steel": "steel and metal products",
                                                                   "cement": "cement and building materials", "tyres": "tyres and vehicle parts",
                                                                   "fertilisers": "fertilisers and crop protection"}
    assert C.off_scope("Acme manufactures cement and clinker.", "Cement Cement makers Building materials", "Acme Ltd") is None
    assert C.off_scope("Acme manufactures tyres for trucks.", "Automotive Tyre makers", "Acme Ltd") is None
    # a kind said of its parent or group is not its own (a subsidiary of a conglomerate "with interest in ... cement")
    assert C.off_scope("Acme Life Sciences, a subsidiary of Big Group Ltd, a conglomerate with interest in consumer products, cement and "
                       "drugs, makes active ingredients.", fmcg, "Acme Life Sciences Ltd") is None


def test_no_other_company_of_any_stored_theme_input_is_outside_its_themes_definition():
    """The scope check moves no company of the 14 benchmark themes or any other stored live input: only the two battery makers in FMCG."""
    found = set()
    for p in sorted((LIVE.parent).glob("inputs_r*/*.json")):
        if p.name in ("recovered.json", "moved.json"):
            continue
        d = json.loads(p.read_text())
        d = d.get("data", d)
        text = B.scope_text(d["theme"], "", [v for v in d["value_chain"] if not v.get("official")])
        for v in d["value_chain"]:
            for c in v["companies"]:
                if (c.get("base") or c.get("placed")) and C.off_scope(d["evidence"].get(c["ticker"]) or c.get("what"), text, c.get("name") or ""):
                    found.add((d["theme"], c["ticker"]))
                elif (c.get("base") or c.get("placed")) and not d["evidence"].get(c["ticker"]) and not c.get("what") and C.off_scope_listed(
                        c.get("name") or "", c.get("industry") or ((d.get("facts") or {}).get(c["ticker"]) or {}).get("industry") or "", text):
                    found.add((d["theme"], c["ticker"]))
    # v55 follow-up: with the catalogue widened (cables, steel and metal products, cement, tyres, fertilisers) and companies with no words of
    # their own read on their industry or name, still only the two battery makers in FMCG
    # r60 (updated on purpose: an independent review of the live R59 Defence deck): a ship breaker filed under shipbuilding, in its own words
    assert found <= {("FMCG", "NIPPOBATRY"), ("FMCG", "HIGHENE"), ("Defence", "HRYNSHP"), ("Logistics", "VMS")}
    assert {("FMCG", "NIPPOBATRY"), ("FMCG", "HIGHENE"), ("Defence", "HRYNSHP")} <= found


def test_a_kind_of_product_of_the_themes_scope_or_named_after_the_themes_own_product_stays():
    auto = "Automotive Two-wheelers Auto components and batteries Makers of vehicle parts"
    assert C.off_scope("Exide Industries manufactures storage batteries for vehicles and inverters.", auto, "Exide Industries Ltd") is None
    fmcg = "FMCG Branded personal care Hair oils, soaps and razors"
    assert C.off_scope("Acme makes razors, blades and batteries for shavers.", fmcg, "Acme Ltd") is None     # the theme's own product first
    assert C.off_scope("Acme makes dry cell batteries and torches.", fmcg, "Acme Ltd")["said"] == "dry cell"
    assert C.off_scope("", fmcg) is None                                                                     # no words: no finding


# ---------- 3 P0 business stage ----------
def test_merck_and_novartis_are_displayed_in_the_commercial_layer_on_the_live_r54_biotech_inputs():
    """Fails before: Merck & Co (about $65 bn of sales) and Novartis shown under "Pipeline-stage and royalty-funded drug developers" (left out
    of its figures, but displayed there). Their own words state revenue businesses: they are displayed in "Large pharma and biotech
    portfolios", with why; no other company moves."""
    out = replay("biotech")
    got, live = layers(out["value_chain"]), layers(inputs("biotech")["value_chain"])
    assert {s: (live[s], got[s]) for s in got if live[s] != got[s]} == {"MRK": (PIPELINE, LARGE), "NVS": (PIPELINE, LARGE)}
    r = row(out, "MRK")["refit"]
    assert r["from"] == PIPELINE and r["to"] == LARGE and r["stage"] == "commercial"
    assert r["why"].startswith("it is a commercial-stage company, a revenue business with products on sale (its own words: “largest biomedical "
                               "companies by revenue”)") and out["placements"]["stage_moved"] == 2
    # a layer whose name states both stages holds both (the map's "Commercial specialty biotechs", now "Specialty and clinical-stage")
    assert got["AMGN"] == live["AMGN"] == "Specialty and clinical-stage biotechs"


def test_a_company_is_staged_by_its_stored_revenue_when_its_words_dont_say_and_a_royalty_firm_stays_in_a_royalty_layer():
    vc = [{"layer": "Clinical-stage developers", "companies": [
              {"ticker": "DEV1", "name": "Dev One", "what": "We develop gene therapies."},
              {"ticker": "DEV2", "name": "Dev Two", "what": "We develop antibodies."},
              {"ticker": "BIG", "name": "Big Pharma", "what": "Big Pharma produces drugs to treat many diseases.", "cap": 500.0}]},
          {"layer": "Large commercial drug makers", "companies": [{"ticker": "OLD", "name": "Old Co", "what": "Old Co makes medicines.", "cap": 900.0},
                                                               {"ticker": "CAND", "name": "Cand Bio", "what": "We are a clinical-stage company."}]}]
    figs = {"DEV1": {"revenue": 10.0, "ebitda": -300.0}, "DEV2": {"revenue": 20.0, "ebitda": -80.0}, "BIG": {"revenue": 5000.0, "ebitda": 30.0}}
    out, n = B.stage_moves(vc, lambda s: "", "Biotech", lambda s: figs.get(s) or {})
    got = layers(out)
    assert n == 2 and got["BIG"] == "Large commercial drug makers" and got["CAND"] == "Clinical-stage developers" and got["DEV1"] == "Clinical-stage developers"
    assert "revenue 10 times the layer's median developer's or more" in row({"value_chain": out}, "BIG")["refit"]["why"]
    # no layer of its stage: "Other", said so
    out, _ = B.stage_moves(vc[:1], lambda s: "", "Biotech", lambda s: figs.get(s) or {})
    assert layers(out)["BIG"] == "Other" and row({"value_chain": out}, "BIG")["refit"]["why"].endswith("no layer of the map is of its stage")
    assert B.layer_stage({"layer": "Specialty and clinical-stage biotechs", "was": "Commercial specialty biotechs"}) == ""


# ---------- 4 P1 fallback layers ----------
def test_ufp_and_integer_go_to_a_medical_device_contract_manufacturers_layer_on_the_live_r54_inputs():
    """Fails before: UFP Technologies (a custom manufacturer for medical devices), out of "Surgical robotics systems", sat in an unexplained
    "Other medical device companies", with Integer Holdings (a medical device contract development and manufacturing organisation)."""
    out = replay("meddev")
    got, live = layers(out["value_chain"]), layers(inputs("meddev")["value_chain"])
    assert {s: (live[s], got[s]) for s in got if live[s] != got[s]} == {"UFPT": ("Other", "Medical device contract manufacturers"),
                                                                        "ITGR": ("Other", "Medical device contract manufacturers")}
    lay = next(v for v in out["value_chain"] if v["layer"] == "Medical device contract manufacturers")
    assert lay["by_place"] and lay["fallback"] == ["contract"]
    assert row(out, "UFPT")["refit"] == {"from": "Surgical robotics systems", "to": "Medical device contract manufacturers", "fallback": "contract",
                                         "why": "its own words make it one of the theme's contract manufacturers, an adjacent kind of business no "
                                                "layer of the map names"}


def test_one_contract_manufacturer_alone_stays_in_other_with_that_said_on_the_live_r54_fmcg_inputs():
    out = replay("fmcg")
    assert layers(out["value_chain"])["HNDFDS"] == "Other"
    assert row(out, "HNDFDS")["fallback"].startswith("its own words make it one of the theme's contract manufacturers, an adjacent kind of "
                                                     "business; too few such companies (1) for a layer of their own")
    # a map that has a layer of that kind already makes none
    vc = [{"layer": "Contract manufacturers", "companies": []},
          {"layer": "Other medical device companies", "official": True, "basis": "rest",
           "companies": [{"ticker": "A", "what": "A is a contract manufacturer of medical devices."},
                         {"ticker": "B", "what": "B is a custom manufacturer of medical devices."}]}]
    assert B.fallback_layer(vc, lambda s: "", "Medical devices") == (vc, None)


# ---------- 5 P1 coverage ----------
def test_the_membership_checks_progress_is_said_apart_from_the_companies_with_figures():
    v = {"membership_evidence": {"description_verified": 60, "industry_code_supported": 40},
         "membership_check": {"outside": {f"S{i}": "industry_code_supported" for i in range(60)},
                              "history": [["2026-11-07", 100, 820, 60], ["2026-11-14", 160, 820, 60]]},     # h56: the tally's points (updated on purpose)
         "figures": {"of": 820, "shown": 100}}
    r = DK.progress_row(v, {"total": 820, "n": 98})
    assert r[1] == "160 of 820 (20%)" and "Checked share after each stored version: 12% (07 Nov 2026) → 20% (14 Nov 2026)" in r[2]
    assert r[2].endswith("Membership checks only: figures are worked out for 100 of the 820 companies (98 with figures), a count of its own "
                         "that the checks don't change.")
    assert DC.check_text("Membership checked 160 of 820 " + r[2])["counts"]["coverage blur"] == 0


# ---------- deck_check ----------
def test_deck_check_finds_exclusions_on_unread_words_out_of_scope_others_stage_mismatches_and_blurred_coverage():
    t = ("Membership 2 companies with figures whose own words describe other work: WISeQey Corp., Adyen Nv-Unspon ADR. Listed.\n"
         "WISeQey Corp. (Data processing): membership: the theme's map names it, from another industry; its own words are not confirmed to show "
         "the theme's work yet.")
    assert DC.check_text(t)["counts"]["identity unresolved"] == 2
    head = "US · THEME DEEP DIVE\n\n\n\nFMCG\n\f"
    other = "Every company's figures\n Indo Batteries Ltd     Other FMCG companies     ₹236 cr     ₹452 cr     −3.2%     −3.9%     −6.0%\n"
    assert DC.check_text(head + other)["counts"]["out of scope in Other"] == 1
    said = head + "Companies that fit none of the map's layers; 1 of them not checked yet (Indo Batteries): no description.\f" + other
    assert DC.check_text(said)["counts"]["out of scope in Other"] == 0
    cables = "Every company's figures\n Acme Cables Ltd     Other {} companies     ₹236 cr     ₹452 cr     −3.2%     −3.9%     −6.0%\n"
    assert DC.check_text(head + cables.format("FMCG"))["counts"]["out of scope in Other"] == 1
    assert DC.check_text("US · THEME DEEP DIVE\n\n\n\nCapital goods\n\f" + cables.format("capital goods"))["counts"]["out of scope in Other"] == 0
    bio = ("US · THEME DEEP DIVE\n\n\n\nBiotech\n\fEvery company's figures\n"
           " Merck & Co., Inc.     Pipeline-stage and royalty-funded drug developers     $364.3 bn     $65 bn     +1.3%     39.2%     28.1%\n"
           " Eli Lilly & Co        Specialty and clinical-stage biotechs                 $1,358 bn     $65.2 bn   +44.7%    43.9%     31.7%\n"
           " Royalty Pharma plc    Pipeline-stage and royalty-funded drug developers     $31.1 bn      $2.3 bn    +5.0%     90.0%     40.0%\n")
    got = DC.check_text(bio)
    assert got["counts"]["stage mismatch"] == 1 and "Merck" in next(f["text"] for f in got["findings"] if f["kind"] == "stage mismatch")
    blur = "Membership checked 160 of 820 (20%) 100 confirmed. Checked share after each stored version: 12% (07 Nov 2026) → 20% (14 Nov 2026)."
    assert DC.check_text(blur)["counts"]["coverage blur"] == 1


def test_deck_check_fails_the_live_r54_payments_biotech_and_fmcg_texts_on_the_new_rules():
    """The live R54 decks' own lines (pdftotext -layout), as the owner read them."""
    pay = ("                              2 companies with figures whose own words describe other work: WISeQey Corp., Adyen               Listed as not confirmed; left out of every median\n"
           " Membership\n                              Nv-Unspon ADR.                                                                                   and total.\n")
    assert DC.check_text(pay)["counts"]["identity unresolved"] >= 1
    bio = ("US · THEME DEEP DIVE\n\n\n\nBiotech\n\f Merck & Co., Inc.                   Pipeline-stage and royalty-funded drug developers      $364.3 bn     $65 bn     "
           "+1.3%     39.2%    28.1%     22.0%      150.7x        6.9x\n")
    assert DC.check_text(bio)["counts"]["stage mismatch"] == 1


def test_the_replayed_decks_pass_the_new_rules():
    for key in ("payments", "biotech", "meddev", "fmcg"):
        _, text = deck(key)
        got = DC.check_text(text)["counts"]
        assert got["identity unresolved"] == got["stage mismatch"] == got["out of scope in Other"] == got["coverage blur"] == 0, key
