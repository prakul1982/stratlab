"""The demo world's theme map (the browser tests' world): what the AI answers for a theme, for the check that each company does its layer's
work and for the check that a claim is still current, so the theme page (e2e/themes.spec.ts) shows a deep dive on made-up companies.

Everything the AI says here is made up; every figure on the page is worked out from the demo companies' own stored pages."""
import json

THEME = "India steel and mining"
MAP = {
    "sector": THEME, "summary": "Steel makers depend on ore and coal from miners, and power plants run the furnaces.",
    "etfs": [], "core": "ore and coal turned into steel",
    "sub_themes": [
        {"name": "Flat steel", "detail": "Sheet steel for cars and appliances.", "companies": [{"name": "Tata Steel", "ticker": "TATASTEEL"}, {"name": "JSW Steel", "ticker": "JSWSTEEL"}]},
        {"name": "Coal mining", "detail": "Digging coal for steel and power.", "companies": [{"name": "Coal India", "ticker": "COALINDIA"}]},
        {"name": "Rare earth magnets", "detail": "Magnets for motors.", "companies": []}],
    "clusters": [], "screen": [],
    "value_chain": [
        {"layer": "Coal and metal mining", "description": "Miners dig coal and metal ore out of the ground; their margin follows what the ore sells for and how much machinery and land they need.",
         "companies": [{"name": "Coal India", "ticker": "COALINDIA"}, {"name": "Vedanta", "ticker": "VEDL"}]},
        {"layer": "Steel making", "description": "Steel makers turn ore and coal into steel; capital needs are heavy and prices follow the world market.",
         "companies": [{"name": "Tata Steel", "ticker": "TATASTEEL"}, {"name": "JSW Steel", "ticker": "JSWSTEEL"}, {"name": "Steel Authority of India", "ticker": "SAIL"},
                       {"name": "Oil and Natural Gas Corporation", "ticker": "ONGC"}]},
        {"layer": "Power generation", "description": "Power generators sell electricity to the plants and the grid.", "companies": [{"name": "NTPC", "ticker": "NTPC"}]}],
    "tailwinds": [{"text": "Public spending on roads and rail raises the demand for steel.", "policy": "", "search": ""},
                  {"text": "The old steel export scheme extension supports sales abroad.", "policy": "Old steel scheme", "search": "Old steel scheme"}],
    "risks": [{"text": "Imports from abroad can pull domestic prices down.", "policy": "", "search": ""}],
}


def answer(system: str, text: str) -> str | None:
    """The AI's reply to a theme prompt, or None when the prompt is not one of them."""
    if "mapping a sector or theme" in system:
        return json.dumps(MAP)
    if "where listed companies belong" in system:
        body = json.loads(text.split("CHECKS:\n", 1)[1])
        return json.dumps({"checks": [{"id": f"{g}|{c['symbol']}", "does": c["symbol"] != "ONGC", "quote": " ".join(c["description"].split()[:9])}
                                      for c in body["companies"] for g in c["check_groups"]]})
    if "still current" in system:
        body = json.loads(text.split("CLAIMS:\n", 1)[1])
        return json.dumps({"claims": [{"id": c["id"], "status": "outdated" if "old steel" in c["claim"].lower() else "unclear", "headline": c["headlines"][0]["id"]}
                                      for c in body["claims"] if c["headlines"]]})
    return None
