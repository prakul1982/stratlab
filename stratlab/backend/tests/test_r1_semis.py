"""R36 lane r1 (GPT review of the live R35 decks): four classification defects, fixed generically, checked on the live map shapes
(tests/fixtures/themes_live/*_us_r35.json: GET /research/sector on 11 Nov 2026) through the placement the dive uses (theme_base.place_rest
with the kept answer, no AI).
1. STMicroelectronics among the contract makers: foundry words with products of its own named are no foundry's (an IDM).
2. Tower Semiconductor among "Memory and logic chip fabricators": chips made "using specialty process technologies" are a specialty foundry's.
3. FTC Solar and T1 Energy among chip makers: a solar maker filed as semiconductors stays in the theme's "Other" group.
4. Amazon among marketplaces earning commissions: a company selling goods it owns is a retailer, and goes to the map's retail layer of its
   own official industry."""
import json
import pathlib

from app.intel import theme_base as B
from app.intel import theme_check as C

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"


def replay(name: str):
    """The live map placed again from its kept answer: the map's own layers with the companies the kept placement left there, every company
    the split moved (and the "Other" group's) back in one official group, each company's words its encyclopedia summary and its one line."""
    d = json.loads((LIVE / name).read_text())
    own, rest, models, conf, tags, words = [], [], {}, {}, {}, {}
    for v in d["layers"]:
        stay = []
        for c in v["companies"]:
            words[c["ticker"]] = " ".join(x for x in (d["about"].get(c["ticker"]), c["what"]) if x)
            row = {k: c[k] for k in ("ticker", "name", "what", "industry", "cap", "basis")}
            if c["model"]:
                models[c["ticker"]], conf[c["ticker"]] = c["model"], c["model_confidence"]
            if c["model_tags"]:
                tags[c["ticker"]] = c["model_tags"]
            (rest if v.get("official") or v.get("by_model") or c.get("moved") else stay).append(row)
        if not v.get("official") and not v.get("by_model"):
            own.append({"layer": v["layer"], "description": v["description"], "companies": stay})
    m = {"sector": d["theme"], "value_chain": own + [{"layer": "Official", "official": True, "basis": "industry", "companies": rest}]}
    kept = {"assign": {c["ticker"]: {"layer": "", "by": "ai"} for c in rest}, "models": models, "model_confidence": conf, "model_tags": tags}
    out, _ = B.place_rest(m, d["theme"], lambda s: words.get(s) or "", ask=None, kept=kept)
    DROPPED[name] = {x["ticker"] for x in (out.get("placements") or {}).get("off_industry") or []}
    return out["value_chain"]


DROPPED: dict = {}          # R40: the companies of another business each replay dropped from the theme (theme_base.without_off_industry)


def layer_of(vc, sym):
    return next(v for v in vc for c in v["companies"] if c["ticker"] == sym)


def row_of(vc, sym):
    return next(c for v in vc for c in v["companies"] if c["ticker"] == sym)


STM = ("Industry: Semiconductors & Related Devices. STMicroelectronics NV is a European multinational semiconductor contract manufacturing and "
       "design company. It is the largest of such companies in Europe. It manufactures a wide range of microelectronics, including the widely "
       "used STM8 and STM32 microcontrollers.")
GFS = ("Industry: Semiconductors & Related Devices. GlobalFoundries Inc. is a multinational semiconductor technology development, design and "
       "contract manufacturing company domiciled in the Cayman Islands and headquartered in Malta, New York.")
TOWER = ("Industry: Semiconductors & Related Devices. Tower Semiconductor Ltd. is an Israeli company that manufactures integrated circuits "
         "using specialty process technologies, including SiGe, BiCMOS, Silicon Photonics, SOI, mixed-signal and RFCMOS.")


# ---------- 1 and 2: foundry or maker of its own chips ----------
def test_foundry_words_with_own_products_named_are_an_idm():
    assert not C.foundry(STM) and C.chip_idm(STM)
    assert C.refine_model("contract_manufacturing", STM) == "manufacturing"
    assert C.foundry(GFS) and not C.chip_idm(GFS)                          # contract manufacturing and no product of its own: a foundry
    assert C.refine_model("contract_manufacturing", GFS) == "contract_manufacturing"
    assert C.refine_model("manufacturing", GFS) == "contract_manufacturing"


def test_customers_designs_or_osat_words_keep_a_contract_maker_whatever_products_it_names():
    for ev in ("Industry: Semiconductors. As a foundry, we manufacture semiconductors for our customers based on designs provided by them, "
               "and offer a wide range of process technologies.",
               "Industry: Semiconductors. A leading provider of semiconductor packaging and test services; its products include advanced packages.",
               "Industry: Semiconductors. We make wafers to customer specifications and sell a broad portfolio of our own products."):
        assert C.foundry(ev) and not C.chip_idm(ev)
        assert C.refine_model("contract_manufacturing", ev) == "contract_manufacturing"


def test_a_specialty_process_foundry_is_a_contract_maker_shown_by_its_own_words():
    assert C.foundry(TOWER)
    assert C.refine_model("manufacturing", TOWER) == "contract_manufacturing"
    assert C.model_confidence("contract_manufacturing", TOWER, "medium") == "medium"     # in the layer's figures, not "way of earning not shown"
    # a maker of its own chips stays one: memory and analog makers never read as foundries
    for ev in ("Industry: Semiconductors & Related Devices. manufactures computer memory and computer data storage products, including DRAM.",
               "Industry: Semiconductors & Related Devices. We design, manufacture, test and market a broad portfolio of solutions."):
        assert not C.foundry(ev)
        assert C.refine_model("manufacturing", ev) == "manufacturing"


def test_contract_making_outside_chips_is_never_read_as_an_idm():
    # a drug CDMO or an EMS maker naming its own brands keeps contract manufacturing (the rule is about chip makers only)
    for ev in ("Industry: Pharmaceuticals. A CDMO that makes drugs on behalf of global pharma companies; its own brands are sold in India.",
               "Industry: Industrial Electronics. An EMS provider; we offer a wide range of electronics manufacturing services for global OEMs."):
        assert not C.chip_idm(ev)
        assert C.refine_model("contract_manufacturing", ev) == "contract_manufacturing"


def test_live_semis_contract_layer_holds_the_foundries_and_not_stmicro():
    vc = replay("semis_us_r35.json")
    cm = layer_of(vc, "TSM")
    assert (cm.get("model") or {}).get("id") == "contract_manufacturing"
    assert {"TSM", "UMC", "GFS", "TSEM"} <= {c["ticker"] for c in cm["companies"]}
    assert "STM" not in {c["ticker"] for c in cm["companies"]}
    assert row_of(vc, "STM")["model"] == "manufacturing" and not row_of(vc, "STM").get("model_out")
    assert row_of(vc, "TSEM")["model"] == "contract_manufacturing" and not row_of(vc, "TSEM").get("model_out")
    # the rest of the map as it stood: memory makers, equipment, fabless designers and materials suppliers where they were
    assert {"MU", "SKHY", "INTC"} <= {c["ticker"] for c in layer_of(vc, "MU")["companies"]}
    assert layer_of(vc, "AMAT")["layer"] == "Semiconductor equipment"
    assert layer_of(vc, "NVDA")["layer"] == "Fabless chip design"
    assert row_of(vc, "Q")["model"] == "components" and layer_of(vc, "Q") is layer_of(vc, "ENTG")
    # R37 lane r2 (updated on purpose): Amkor's "packaging and test services" are contract making in so many words, so it is counted, in the
    # packaging and test layer (foundries keep their own contract layer); the materials makers keep a layer of their own
    assert row_of(vc, "AMKR")["model"] == "contract_manufacturing" and not row_of(vc, "AMKR").get("model_out")
    assert layer_of(vc, "AMKR")["layer"] == "Packaging, test and materials suppliers" and layer_of(vc, "AMKR") is not cm
    assert "Q" not in {c["ticker"] for c in layer_of(vc, "AMKR")["companies"]}


# ---------- 3: solar makers filed as semiconductors ----------
def test_solar_words_and_no_chips_under_a_chip_industry_are_another_business():
    for own in ("We are a global provider of solar tracker systems, supported by proprietary software and value-added engineering services",
                "T1 Energy Inc. is an energy solutions provider building an integrated U.S. solar supply chain for solar modules",
                "It provides products, technologies, software, and services to installers, distributors, and OEMs within the photovoltaic industry"):
        assert C.off_industry(f"Industry: Semiconductors & Related Devices. {own}.")
        assert not C.off_industry(f"Industry: Electrical Equipment. {own}.")      # only where the code files it with chips
    for own in ("supplies equipment, services and software for the manufacture of semiconductor chips for electronics and solar products",
                "a developer and manufacturer of power semiconductors used in solar inverters and electric vehicles"):
        assert not C.off_industry(f"Industry: Semiconductors & Related Devices. {own}.")


def test_live_semis_solar_makers_stay_in_other_and_out_of_chip_layers():
    vc = replay("semis_us_r35.json")
    # R40 (lane s3-r40, updated on purpose): another business filed under the theme's industry is dropped from the theme, never placed in
    # "Other", and named on its coverage
    names = {"FTCI", "TE", "TYGO", "MAXNQ", "ASTI"}
    assert names <= DROPPED["semis_us_r35.json"]
    for v in vc:
        assert not names & {c["ticker"] for c in v["companies"]}


def test_an_off_industry_company_the_map_placed_in_a_layer_is_left_out_as_another_business():
    vc = [{"layer": "Chip makers", "description": "", "companies": [
        {"ticker": "A", "industry": "Semiconductors", "what": "manufactures microcontrollers and analog chips in its own fabs"},
        {"ticker": "B", "industry": "Semiconductors", "what": "makes power management chips and integrated circuits"},
        {"ticker": "S", "industry": "Semiconductors", "what": "designs and manufactures photovoltaic panels"}]}]
    out = B.by_model(vc, {"A": "manufacturing", "B": "manufacturing", "S": "manufacturing"}, "Semiconductors",
                     confidence={"A": "high", "B": "high", "S": "high"})
    s = row_of(out, "S")
    assert s["model_out"] == "other" and layer_of(out, "S")["layer"] == "Chip makers"
    assert not row_of(out, "A").get("model_out")


# ---------- 4: a retailer with a marketplace beside it ----------
def test_selling_its_own_goods_makes_a_platform_a_retailer():
    amzn = ("Industry: Retail-Catalog & Mail-Order Houses. We design our stores to enable hundreds of millions of unique products to be sold "
            "by us and by third parties across dozens of product categories.")
    assert C.refine_model("platform", amzn) == "retail"
    for ev in ("Industry: Retail-Catalog & Mail-Order Houses. GigaCloud Technology Inc. is an American e-commerce company that helps retailers "
               "buy and sell big and bulky, non-standardized items. They own a business-to-business online marketplace.",
               "Industry: Retail-Catalog & Mail-Order Houses. Our platform consists of our marketplace, which connects sellers with customers.",
               "Industry: Retail-Miscellaneous Retail. The RealReal, Inc. is an online marketplace for users to buy and sell luxury goods. "
               "In addition, we operate several larger footprint flagship stores."):
        assert C.refine_model("platform", ev) == "platform"


def test_live_retail_amazon_joins_the_online_retailers_and_the_marketplace_line_follows_its_members():
    vc = replay("retail_us_r35.json")
    assert row_of(vc, "AMZN")["model"] == "retail"
    assert layer_of(vc, "AMZN")["layer"] == "Online direct-to-consumer retailers"
    mk = layer_of(vc, "JMIA")
    assert mk["layer"] == "Online marketplaces and e-commerce sellers" and "AMZN" not in {c["ticker"] for c in mk["companies"]}
    assert mk["model"]["id"] == "platform" and mk["model"]["line"].startswith("They earn mainly from commissions, listing fees or advertising")
    assert {c["model"] for c in mk["companies"]} == {"platform"}
    # R37 lane r2 (updated on purpose): an online seller the split moved out of the "Other" group goes to the online retailers, the layer of its
    # own official industry, not to the largest layer of its family ("Apparel and fashion retail chains")
    assert layer_of(vc, "CPNG")["layer"] == "Online direct-to-consumer retailers"
