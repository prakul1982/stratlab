"""The app on the fake world, for the browser tests in stratlab/frontend/e2e: every source faked, plus a company with
loss years (TCS stands in for one, as only listed symbols open) so the charts' handling of losses can be checked.

    python -m tests.visual_server            # serves on 127.0.0.1:8765
"""
import base64
import copy
import os
import sys
from pathlib import Path

import pytest
import uvicorn

sys.path.insert(0, ".")
os.environ.setdefault("FRONTEND_ORIGIN", "http://127.0.0.1:5599,http://localhost:5599")   # the browser tests' page
from app import main  # noqa: E402
from tests import world  # noqa: E402

PORT = 8765
LOSS = "TCS"


def loss_company(p: dict) -> dict:
    """RELIANCE's page with SML-like numbers: losses for three years, then profits."""
    p = copy.deepcopy(p)
    pl = p["pl"]
    n = len(pl["cols"])
    shape = [-21.3, -133.4, -100.2, 20.05, 108.6, 122.4, 160.3]
    pl["rows"]["Net Profit"] = ([None] * max(0, n - len(shape)) + shape)[-n:]
    p["name"] = "Loss Company Ltd"
    return p


def build():
    mp = pytest.MonkeyPatch()
    w = world.build(mp)
    scr = main.research_hub.screener
    real = scr.company
    mp.setattr(scr, "company", lambda sym: loss_company(real("RELIANCE")) if sym.upper() == LOSS else real(sym))
    # the owner's holdings, imported from a Zerodha Console file, for the My Holdings page
    sample = Path(__file__).parent / "fixtures" / "holdings" / "zerodha_console_holdings.xlsx"
    w["client"].post("/holdings/import", headers=world.headers("admin-token"),
                     json={"filename": sample.name, "data": base64.b64encode(sample.read_bytes()).decode()})
    return w


if __name__ == "__main__":
    build()
    uvicorn.run(main.app, host="127.0.0.1", port=PORT, log_level="warning")
