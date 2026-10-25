"""The return and tax audit report due dates of each financial year: the Act's own dates, and the CBDT's extensions by
year, in one table that the tax report, the ITR export, Tax tools (section 234A and 234B months), US tax and the money
calendar all read (DH-001: the audit-case date stayed 31 October everywhere a month after CBDT moved it).

The Act's dates (section 139(1), Explanation 2; section 263 of the Income-tax Act, 2025 from tax year 2026-27):
- 31 July after the year: no business or professional income ("no_business").
- 31 August from FY 2025-26 (Finance Act 2026), 31 July before: business income (intraday, F&O) without a tax audit
  ("business").
- 31 October: accounts audited under section 44AB ("audit").
- The tax audit report (Form 3CA or 3CB, with Form 3CD) is due by the "specified date", one month before the audit
  case's return date: 30 September ("audit_report").
- A belated return by 31 December (section 139(4)); a revised return by 31 December, or by 31 March from FY 2025-26
  (Finance Act 2026; a fee of ₹1,000, or ₹5,000 above ₹5 lakh of income, when revised after 31 December).

Extensions (CBDT, under section 119; an extension of the section 139(1) date moves section 234A's date with it unless
the circular says otherwise, and none of these does):
- FY 2023-24 (AY 2024-25): audit report to 7 Oct 2024 (Circular 10/2024, 29 Sep 2024); audit-case returns to 15 Nov
  2024 (Circular 13/2024, 26 Oct 2024).
- FY 2024-25 (AY 2025-26): returns due 31 Jul to 15 Sep 2025 (Circular 6/2025, 27 May 2025), then 16 Sep 2025
  (Circular 12/2025, 15 Sep 2025); audit report to 31 Oct 2025 (Circular 14/2025, 25 Sep 2025), then 10 Nov 2025, and
  audit-case returns to 10 Dec 2025 (CBDT press release and circular of 29 Oct 2025).
- FY 2025-26 (AY 2026-27): audit report to 21 Oct 2026 and audit-case returns to 21 Nov 2026 (Circular 7/2026, 28 Sep
  2026: https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-09/Circular-7-2026.pdf).
Years before FY 2023-24 show the Act's dates only. Checked 25 Oct 2026."""
from datetime import date

KINDS = ("no_business", "business", "audit", "audit_report")
NAMES = {"no_business": "Return, no business income", "business": "Return, business income without a tax audit",
         "audit": "Return, accounts audited under section 44AB", "audit_report": "Tax audit report (Form 3CA or 3CB, with Form 3CD)"}
C7_2026 = "CBDT Circular 7/2026 of 28 Sep 2026"
EXTENSIONS: dict[int, dict[str, tuple[date, str]]] = {
    2023: {"audit_report": (date(2024, 10, 7), "CBDT Circular 10/2024 of 29 Sep 2024"),
           "audit": (date(2024, 11, 15), "CBDT Circular 13/2024 of 26 Oct 2024")},
    2024: {"no_business": (date(2025, 9, 16), "CBDT Circulars 6/2025 and 12/2025"),
           "business": (date(2025, 9, 16), "CBDT Circulars 6/2025 and 12/2025"),
           "audit_report": (date(2025, 11, 10), "CBDT Circular 14/2025 and the CBDT press release of 29 Oct 2025"),
           "audit": (date(2025, 12, 10), "the CBDT press release of 29 Oct 2025")},
    2025: {"audit_report": (date(2026, 10, 21), C7_2026), "audit": (date(2026, 11, 21), C7_2026)},
}
PENALTY_271B = ("Section 271B: not getting the accounts audited, or not furnishing the audit report by its date, can draw a "
                "penalty of 0.5% of turnover, up to ₹1.5 lakh.")


def statutory(fy: int, kind: str) -> date:
    """The Act's date for one kind (fy is the year's first year: 2025 for FY 2025-26)."""
    ay = fy + 1
    if kind == "no_business":
        return date(ay, 7, 31)
    if kind == "business":
        return date(ay, 8, 31) if fy >= 2025 else date(ay, 7, 31)
    if kind == "audit":
        return date(ay, 10, 31)
    if kind == "audit_report":
        return date(ay, 9, 30)
    raise ValueError(kind)


def due(fy: int, kind: str) -> dict:
    """{date, statutory, extended, source}: the date that holds now, the Act's own, and the extension's source."""
    law = statutory(fy, kind)
    ext = EXTENSIONS.get(fy, {}).get(kind)
    when = ext[0] if ext else law
    return {"kind": kind, "date": when, "statutory": law, "extended": when != law, "source": ext[1] if ext else None}


def return_kind(business: bool, audit: bool) -> str:
    return "audit" if audit else "business" if business else "no_business"


def return_due(fy: int, business: bool = False, audit: bool = False) -> date:
    """The return's due date for the year, with the CBDT's extension where there is one."""
    return due(fy, return_kind(business, audit))["date"]


def belated(fy: int) -> date:
    return date(fy + 1, 12, 31)


def revise_by(fy: int) -> date:
    return date(fy + 2, 3, 31) if fy >= 2025 else date(fy + 1, 12, 31)


def day(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def said(fy: int, kind: str) -> str:
    """"21 November 2026 (extended from 31 October by CBDT Circular 7/2026 of 28 Sep 2026)", or the Act's date alone."""
    x = due(fy, kind)
    return day(x["date"]) + (f" (extended from {x['statutory'].day} {x['statutory']:%B} by {x['source']})" if x["extended"] else "")


def months_late(due_day: date, on: date) -> int:
    """Section 234A's months: from the day after the due date to `on`, a part of a month counting as a month."""
    if on <= due_day:
        return 0
    n = (on.year - due_day.year) * 12 + on.month - due_day.month
    return n + (1 if on.day > due_day.day else 0)


def return_dates(fy: int) -> str:
    """The year's return due dates in one sentence."""
    ay = fy + 1
    if fy >= 2025:
        return (f"Due dates for the FY {fy}-{str(ay)[2:]} return: {said(fy, 'no_business')} with no business income, "
                f"{said(fy, 'business')} for business income without a tax audit, and {said(fy, 'audit')} with one.")
    return (f"Due dates for the FY {fy}-{str(ay)[2:]} return: {said(fy, 'no_business')} without a tax audit, and "
            f"{said(fy, 'audit')} with one.")


def audit_dates(fy: int) -> str:
    """The audit report's and the audit case's return dates, for a year a tax audit applies to."""
    return (f"Tax audit report (Form 3CA or 3CB, with Form 3CD) by {said(fy, 'audit_report')}; the return by "
            f"{said(fy, 'audit')}.")
