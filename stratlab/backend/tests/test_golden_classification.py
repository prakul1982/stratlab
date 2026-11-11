"""Golden classification check (R36 lane r1, the owner: "every fix breaks another sector"). Every company of the 14 benchmark themes' live
maps (11 Nov 2026, Release 35: tests/fixtures/themes_live/golden_r36.json, India and US) goes through the same path the dive gives a kept
placement's models (theme_base.refine_kept: theme_check.refine_model and model_confidence) and the placement rule that keeps a company of
another business out of a layer's figures (theme_check.off_industry, by_model), and is compared with its approved way of earning: the live
result, with the corrections below. A rule change that moves any company in any theme fails here; such a change is made on purpose by
editing APPROVED (with its reason), never by loosening the check. Fast: the classification functions only, no network, no AI."""
import json
import pathlib

from app.intel import theme_base as B
from app.intel import theme_check as C

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
GOLDEN = json.loads((LIVE / "golden_r36.json").read_text())

# Corrections to the live R35 result, approved on purpose: "theme:symbol" -> (model, how it counts: "" in the layer's figures, "low" left out
# as weakly shown, "other" left out as another business). Each with its reason.
APPROVED = {
    # R36 fix 1: an IDM ("It manufactures a wide range of microelectronics, including the widely used STM8 and STM32 microcontrollers"),
    # whatever "contract manufacturing" its encyclopedia line says
    "semis:STM": ("manufacturing", ""),
    # R36 fix 2: a specialty foundry ("manufactures integrated circuits using specialty process technologies")
    "semis:TSEM": ("contract_manufacturing", ""),
    # R36 fix 3: solar module, tracker and inverter makers filed as semiconductors are another business
    "semis:TE": ("manufacturing", "other"),
    "semis:FTCI": ("manufacturing", "other"),
    "semis:TYGO": ("manufacturing", "other"),
    "semis:MAXNQ": ("manufacturing", "other"),
    "semis:ASTI": ("manufacturing", "other"),
    # R36 fix 4: Amazon sells goods it owns ("products to be sold by us and by third parties"): a retailer with a marketplace beside it
    "retail:AMZN": ("retail", ""),
}
# Where the fixture's one-line description gives less than the words the live read had (its stored description, segments and filings), the
# same path gives these from the one line; kept apart from APPROVED so neither hides the other
ONE_LINE = {
    "semis:NLST": ("fabless", ""),          # "designs and sells": the live read also had its own making words
    "semis:UCTT": ("fabless", ""),          # live unknown; its one line ("developer and supplier of critical subsystems") reads as a designer
    "retail:JL": ("retail", ""),            # live "low"; its one line's own words show the family
    "retail:DBGI": ("retail", ""),
}


def evidence(c) -> str:
    """A fixture company's evidence as the dive builds it (theme_check.model_evidence): its official industry, then its own words (the
    encyclopedia summary where the fixture keeps it, and its stored one-line description)."""
    return C.model_evidence(c["i"], " ".join(x for x in (c.get("a"), c["w"]) if x))


def classify(c) -> tuple[str, str]:
    """(model, how it counts) for a fixture company by the dive's path for a kept placement."""
    ev = evidence(c)
    models, conf = B.refine_kept({c["s"]: c["m"]} if c["m"] else {}, {c["s"]: c["c"]} if c["c"] else {}, lambda s_: ev, [c["s"]])
    model, level = (models or {}).get(c["s"]) or "unknown", (conf or {}).get(c["s"], "")
    if model == "unknown":
        return "unknown", ""
    if C.off_industry(ev):
        return model, "other"
    return model, "low" if level == "low" else ""


def expected(theme: str, c) -> tuple[str, str]:
    k = f"{theme}:{c['s']}"
    if k in APPROVED:
        return APPROVED[k]
    if k in ONE_LINE:
        return ONE_LINE[k]
    return c["m"] or "unknown", "low" if c["c"] == "low" else ""


def company(theme: str, sym: str) -> dict:
    t = next(t for t in GOLDEN["themes"] if t["key"] == theme)
    return next(c for c in t["companies"] if c["s"] == sym)


# ---------- every company of every benchmark theme ----------
def test_golden_covers_the_fourteen_benchmark_themes():
    keys = {t["key"]: t["region"] for t in GOLDEN["themes"]}
    assert keys == {"auto": "IN", "bank": "IN", "semis": "US", "it": "IN", "pharma": "IN", "insurance": "IN", "defence": "IN", "cyber": "US",
                    "chem": "IN", "realty": "IN", "telecom": "IN", "retail": "US", "utilities": "IN", "metals": "IN"}
    n = sum(len(t["companies"]) for t in GOLDEN["themes"])
    assert n >= 1300
    assert sum(1 for t in GOLDEN["themes"] for c in t["companies"] if c["m"]) >= 1050


def test_no_company_in_any_theme_changes_its_way_of_earning_unless_approved():
    moved = []
    for t in GOLDEN["themes"]:
        for c in t["companies"]:
            got, want = classify(c), expected(t["key"], c)
            if got != want:
                moved.append(f"{t['key']}:{c['s']} ({c['n']}): expected {want}, got {got}")
    assert not moved, "a rule change moved these companies (edit APPROVED, with the reason, if on purpose):\n" + "\n".join(moved)


def test_every_approved_correction_is_a_company_of_the_fixture_and_differs_from_live():
    for k, (model, _) in {**APPROVED, **ONE_LINE}.items():
        theme, sym = k.split(":")
        c = company(theme, sym)
        assert (c["m"] or "unknown", "low" if c["c"] == "low" else "") != (APPROVED.get(k) or ONE_LINE[k])
        assert model in C.MODELS


# ---------- the curated anchors (the coordinator's list): each named company's way of earning or family ----------
ANCHORS = {
    ("semis", "Q"): "components", ("semis", "ENTG"): "components",                    # chip materials: ingredient makers, never equipment
    ("semis", "TSM"): "contract_manufacturing", ("semis", "UMC"): "contract_manufacturing",
    ("semis", "GFS"): "contract_manufacturing", ("semis", "TSEM"): "contract_manufacturing",
    ("semis", "STM"): "manufacturing", ("semis", "NXPI"): "manufacturing", ("semis", "ADI"): "manufacturing",
    ("semis", "AMAT"): "manufacturing", ("semis", "LRCX"): "manufacturing", ("semis", "KLAC"): "manufacturing",
    ("semis", "NVDA"): "fabless", ("semis", "AMD"): "fabless", ("semis", "QCOM"): "fabless",
    ("telecom", "JPL"): "telecom_services", ("telecom", "IDEA"): "telecom_services", ("telecom", "BHARTIARTL"): "telecom_services",
    ("retail", "AMZN"): "retail", ("retail", "GCT"): "platform", ("retail", "JMIA"): "platform",
    ("bank", "HDFCBANK"): "lending",
}


def test_anchor_companies_keep_their_way_of_earning():
    for (theme, sym), want in ANCHORS.items():
        model, out = classify(company(theme, sym))
        assert (model, out) == (want, ""), (theme, sym, model, out)


def test_texas_instruments_is_a_maker_of_its_own_chips_never_a_contract_maker():
    # its one line ("developing analog chips and embedded processors") reads as a designer: the making family, in the figures, never contract
    model, out = classify(company("semis", "TXN"))
    assert C.model_family(model) == "making" and model != "contract_manufacturing" and out == ""


def test_it_services_majors_are_in_the_outsourcing_layers_figures():
    for sym in ("WIPRO", "TCS", "INFY"):
        c = company("it", sym)
        model, out = classify(c)
        assert C.model_family(model) == "services" and out == "", (sym, model, out)
        assert c["l"].startswith("Large-scale outsourcing")


def test_solar_makers_are_out_of_every_chip_layer():
    for sym in ("FTCI", "TE"):
        assert classify(company("semis", sym))[1] == "other"
    # chip makers and equipment makers whose words also name solar stay in (Applied Materials: "... and solar products")
    for sym in ("AMAT", "Q", "NVDA", "TSM", "WOLF"):
        assert classify(company("semis", sym))[1] == ""
