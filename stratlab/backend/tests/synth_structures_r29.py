"""Release 29 (lane r29-cover): synthetic broad themes whose AI layers mix businesses that earn differently (the owner's outside review of
the live R27 decks: utilities, metals and mining, consumer retail). Each company's model is the broad one an AI answer gives ("utility",
"resources", "manufacturing") made exact by its own evidence (theme_check.refine_model), as theme_base.place_rest does. Self-contained, built
on tests.synth_structures_r27class.build; synthetic only, no real company's name or figure.

structures() yields (name, theme) where theme = {"region", "map", "facts", "models", "tags", "confidence", "apart", "given"}: `apart` lists
pairs of models that must never share a layer; `given` the broad model each company started from."""
from app.intel import theme_check as C
from tests.synth_structures_r27class import build


def _rows(prefix, n, name, what, ind, model):
    return [(f"{prefix}{i}", f"{name} {i} Ltd", what, ind, model, (), "high") for i in range(n)]


def _refined(t: dict) -> dict:
    """The theme with each company's broad model made exact by its evidence (its official industry and its own words)."""
    ev = {c["ticker"]: C.model_evidence(c.get("industry") or "", c.get("what") or "") for v in t["map"]["value_chain"] for c in v["companies"]}
    t["given"] = dict(t["models"])
    t["models"] = {s: C.refine_model(md, ev[s]) for s, md in t["models"].items()}
    return t


def utilities_in():
    return _refined(build("IN", "Utilities", [
        ("Power companies", "Companies that move, make and trade power.",
         _rows("RTX", 3, "Gridline", "owns and runs power transmission lines and substations, earning tariffs set by the regulator",
               "Power - Transmission", "utility")
         + _rows("GNR", 4, "Thermagen", "generates electricity at its thermal and hydro power plants of 4,000 MW and sells it under long-term "
                                        "contracts", "Power Generation", "utility")
         + _rows("PTD", 3, "Sunmart", "trades electricity and develops solar and wind projects under power purchase agreements", "Power Trading",
                 "utility")),
        ("Power equipment", "Equipment for the grid.",
         _rows("PEQ", 3, "Coilworks", "manufactures transformers and switchgear in its plants", "Heavy Electrical Equipment", "manufacturing")),
    ], [("regulated_utility", "power_generation"), ("regulated_utility", "power_trading"), ("power_generation", "power_trading"),
        ("regulated_utility", "manufacturing")]))


def metals_in():
    return _refined(build("IN", "Metals and mining", [
        ("Metals", "Companies that mine, make and shape metal.",
         _rows("ORE", 3, "Orecrest", "mines iron ore and coal and sells it to steel makers", "Industrial Minerals", "resources")
         + _rows("ISP", 3, "Furnaceco", "makes steel from iron ore in its integrated steel plant with blast furnaces", "Iron & Steel", "manufacturing")
         + _rows("PRC", 4, "Tubeform", "makes steel pipes, tubes and galvanised sheets from steel coils it buys", "Iron & Steel Products",
                 "manufacturing")),
    ], [("commodity_mining", "metal_processing")]))


def retail_us():
    return _refined(build("US", "Consumer retail", [
        ("Retail", "Companies whose goods reach consumers.",
         _rows("STO", 3, "Basketry", "sells groceries and household goods to consumers in its own stores, holding its own inventory",
               "Retail-Grocery Stores", "retail")
         + _rows("MKP", 3, "Stallhub", "runs an online marketplace where third-party sellers list goods, earning commissions and advertising",
                 "Services-Business Services, Nec", "platform")),
    ], [("retail", "platform")]))


BROAD = {"utilities (IN)": utilities_in, "metals and mining (IN)": metals_in, "consumer retail (US)": retail_us}


def structures():
    for name, fn in BROAD.items():
        yield name, fn()
