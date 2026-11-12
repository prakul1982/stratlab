"""The browser tests' world for the earnings-call calendar (concalls.py) and the business groups (groups.py): a made-up
store of calls and meetings around the world's day (notices with a time, a zone and a webcast link, a run of meetings,
calls held with their transcript, recording and presentation), and made-up promoter names in the shareholding store
for a dozen of the world's companies, so that the groups rule makes out three groups. Names of promoters are invented."""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ARCHIVE = "https://nsearchives.nseindia.com/corporate/"
JOIN = "https://services.choruscall.in/DiamondPassRegistration/register?confirmationNumber=1000001&linkSecurityString=e2e"
# (symbol, name) of the world's companies the groups are made of (all have daily prices in the world)
GROUPS = [
    ("Northwind Holdings Private Limited", ["TCS", "TATASTEEL", "INFY", "WIPRO", "HCLTECH"]),
    ("Riverbend Family Trust", ["RELIANCE", "ONGC", "ITC"]),
    ("Lakeside Investments Limited", ["JSWSTEEL", "SAIL", "VEDL"]),
]


def _events(today) -> list[dict]:
    d = lambda n: (today + timedelta(days=n)).isoformat()          # noqa: E731
    at = lambda n, hm="18:00": f"{d(n)}T{hm}"                      # noqa: E731
    notice = lambda s, n: {"k": "notice", "u": f"{ARCHIVE}{s}_{n}_EarningsCallIntimation.pdf", "at": at(-3)}   # noqa: E731
    rows = [
        ("TCS", "Tata Consultancy Services Limited", 0, "call", "16:00", "IST", [notice("TCS", 1), {"k": "join", "u": JOIN, "at": at(-3)}]),
        ("MARUTI", "Maruti Suzuki India Limited", 1, "call", "11:00", "IST", [notice("MARUTI", 1), {"k": "join", "u": JOIN, "at": at(-3)}]),
        ("INFY", "Infosys Limited", 1, "meet", "09:00", "SGT", [notice("INFY", 2)]),
        ("RELIANCE", "Reliance Industries Limited", 2, "call", "19:30", "IST", [notice("RELIANCE", 1)]),
        ("HDFCBANK", "HDFC Bank Limited", 3, "meet", None, None, [notice("HDFCBANK", 1)]),
        ("JSWSTEEL", "JSW Steel Limited", 6, "call", "15:00", "IST", [notice("JSWSTEEL", 1), {"k": "join", "u": JOIN, "at": at(-2)}]),
        ("TVSMOTOR", "TVS Motor Company Limited", 9, "call", "10:00", "IST", [notice("TVSMOTOR", 1)]),
        ("ITC", "ITC Limited", 12, "meet", None, None, [notice("ITC", 1)]),
        ("WIPRO", "Wipro Limited", -2, "call", "18:30", "IST", [notice("WIPRO", 1),
            {"k": "transcript", "u": f"{ARCHIVE}WIPRO_Transcript_Earnings_Call.pdf", "at": at(-1)},
            {"k": "audio", "u": "https://www.example.com/investors/Q2_Earnings_Call_Audio.mp3", "at": at(-2, "22:00")},
            {"k": "presentation", "u": f"{ARCHIVE}WIPRO_Investor_Presentation.pdf", "at": at(-2, "15:00")}]),
        ("SBIN", "State Bank of India", -5, "call", "16:00", "IST", [notice("SBIN", 1),
            {"k": "transcript", "u": f"{ARCHIVE}SBIN_Transcript.pdf", "at": at(-1)}]),
        ("DABUR", "Dabur India Limited", -6, "call", None, None, [{"k": "transcript", "u": f"{ARCHIVE}DABUR_Transcript.pdf", "at": at(-3)}]),
    ]
    out = []
    for sym, name, n, typ, tm, tz, links in rows:
        e = {"id": f"{sym}|{d(n)}|{typ}", "symbol": sym, "name": name, "date": d(n), "type": typ, "filed": at(min(n, 0) - 4), "links": links}
        if tm:
            e.update(time=tm, tz=tz)
        if typ == "meet" and sym == "HDFCBANK":
            e.update(until=d(5), dates=[d(3), d(4), d(5)])
        if sym == "DABUR":
            e["from_followup"] = True
        out.append(e)
    return out


def _filing(rows, ppct):
    return {"rec": "e2e", "filed": "2026-10-15T10:00", "url": f"{ARCHIVE}xbrl/SHP_E2E.xml", "parser": 3, "ppct": ppct,
            "rows": [[n, k, "promoter", 1000000, p] for n, k, p in rows]}


def seed(uids=("u-load-271", "u-load-274")):
    from app import concalls, db, groups, screens, shareholders
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    db.set_setting(concalls.KEY, json.dumps({"events": _events(today), "pending": [], "seen": {}, "through": today.isoformat(),
                                             "at": f"{(today - timedelta(days=1)).isoformat()}T21:40"}))
    names = {r["symbol"]: r.get("name") for r in screens.load_index("IN").get("rows") or []}
    for gi, (anchor, syms) in enumerate(GROUPS):
        for i, sym in enumerate(syms):
            big = 40.0 - 4 * i
            rows = [(anchor, "Trust" if "Trust" in anchor else "Company", big)]
            if gi == 0 and i % 2:
                rows.append(("Asha Northwind", "Individual or HUF", 2.5))
            co = {"name": names.get(sym) or sym, "isin": "", "q": {"2026-09-30": _filing(rows, round(big + 3.1, 2))}}
            old = db.json_value(db.get_setting(shareholders.KEY + sym), {})
            if isinstance(old.get("q"), dict) and old["q"]:
                co["q"] = {**old["q"], **co["q"]}       # the named holders' own samples stay for the quarters before
            db.set_setting(shareholders.KEY + sym, json.dumps(co))
    shareholders.forget()
    groups.forget()
    concalls.forget()
    for uid in uids:
        db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"symbol": "MARUTI", "region": "IN"}, {"symbol": "TVSMOTOR", "region": "IN"},
                                                                  {"symbol": "TCS", "region": "IN"}]}))
