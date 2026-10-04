"""The exchange's F&O contract file and circulars, made up around today's month for the fake world (the unit tests
read the fixed sample files in fixtures/fo_changes): NIFTY's lot goes from 75 to 65 in the third month, RELIANCE's
from 500 to 250, EXIDEIND leaves after the second month and NUVAMA after the first; one circular of each kind."""
import calendar
import json
from datetime import date, timedelta
from pathlib import Path

SAMPLES = Path(__file__).parent / "fixtures" / "fo_changes"


def _months(today: date) -> list[str]:
    out, y, m = [], today.year, today.month
    for _ in range(3):
        out.append(f"{calendar.month_abbr[m].upper()}-{y % 100:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def lots_text(today: date | None = None) -> str:
    a, b, c = _months(today or date.today())
    rows = [("UNDERLYING", "SYMBOL", a, b, c), ("NIFTY 50", "NIFTY", "75", "75", "65"), ("NIFTY BANK", "BANKNIFTY", "35", "35", "35"),
            ("Derivatives on Individual Securities", "Symbol", "", "", ""),
            ("EXIDE INDUSTRIES LTD", "EXIDEIND", "1800", "1800", ""), ("NUVAMA WEALTH MANAGEMENT LTD", "NUVAMA", "75", "", ""),
            ("RELIANCE INDUSTRIES LTD", "RELIANCE", "500", "500", "250"), ("INFOSYS LIMITED", "INFY", "400", "400", "400"),
            ("TATA STEEL LIMITED", "TATASTEEL", "5500", "5500", "5500")]
    return "\n".join(",".join(f"{x:<12}" for x in r) for r in rows) + "\n"


def circulars(today: date | None = None) -> dict:
    t = today or date.today()
    day = lambda n: (t - timedelta(days=n)).strftime("%B %d, %Y")  # noqa: E731
    return {"data": [
        {"circDisplayNo": "FAOP/71001", "cirDisplayDate": day(2), "sub": "Exclusion of EXIDEIND and NUVAMA from F&O segment"},
        {"circDisplayNo": "FAOP/71003", "cirDisplayDate": day(5), "sub": "Revision in market lot of derivative contracts on indices"},
        {"circDisplayNo": "FAOP/71004", "cirDisplayDate": day(9), "sub": "Change in expiry day of NIFTY weekly options contracts"},
        {"circDisplayNo": "LIST/71006", "cirDisplayDate": day(3), "sub": "Listing of new debentures"},
    ]}


def answer(path: str):
    """What the fake exchange sends for a path, or None when it isn't one of these."""
    if path == "/content/fo/fo_mktlots.csv":
        return lots_text()
    if path == "/api/circulars":
        return circulars()
    return None


def sample(name: str):
    text = (SAMPLES / name).read_text()
    return json.loads(text) if name.endswith(".json") else text
