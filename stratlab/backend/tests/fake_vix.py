"""The exchange's India VIX answers for the tests and the browser tests' world: the index list and the one-day chart
are real answers, trimmed (tests/fixtures/vix, read 5 Oct 2026); the history is made up in the real answer's shape
(70 rows at most, oldest first, dates like "01-SEP-2026"), a slow wave between about 10 and 20."""
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "vix"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def close_on(d: date) -> float:
    return round(14.5 + 4 * math.sin(d.toordinal() / 23) + 1.2 * math.sin(d.toordinal() / 5), 2)


def history_answer(frm: date, to: date, cap: int = 70) -> dict:
    rows, d = [], frm
    while d <= to and len(rows) < cap:
        if d.weekday() < 5:
            c, prev = close_on(d), close_on(d - timedelta(days=1))
            rows.append({"EOD_TIMESTAMP": d.strftime("%d-%b-%Y").upper(), "EOD_INDEX_NAME": "INDIA VIX",
                         "EOD_OPEN_INDEX_VAL": prev, "EOD_HIGH_INDEX_VAL": round(max(c, prev) + 0.6, 2),
                         "EOD_LOW_INDEX_VAL": round(min(c, prev) - 0.5, 2), "EOD_CLOSE_INDEX_VAL": c, "EOD_PREV_CLOSE": prev,
                         "VIX_PTS_CHG": round(c - prev, 2), "VIX_PERC_CHG": round((c / prev - 1) * 100, 2),
                         "HI_TIMESTAMP_ORDER": f"{d.isoformat()}T18:30:00.000Z"})
        d += timedelta(days=1)
    return {"data": rows}


def answer(path: str, params) -> dict | None:
    """The fake exchange's answer for an India VIX request, or None when the path isn't one of them."""
    if path == "/api/historicalOR/vixhistory":
        frm, to = (datetime.strptime(params[k], "%d-%m-%Y").date() for k in ("from", "to"))
        return history_answer(frm, to)
    if path == "/api/allIndices":
        return fixture("allIndices.json")
    if path == "/api/NextApi/apiClient" and params.get("functionName") == "getGraphChart":
        return fixture("graph.json")
    return None
