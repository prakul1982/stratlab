"""Earnings calls, analyst or investor meetings and shareholders' meetings are three kinds, each labelled as itself
(the India audit and the company page's filings list): a shareholders' meeting is never an "earnings call"."""
import pytest

from app import audit, deepdive
from app.intel import filings as F

MEET = "Analysts/Institutional Investor Meet/Con. Call Updates"


def item(subject, text, at="2026-03-01T10:00", url="https://nsearchives.nseindia.com/corporate/X_1.pdf"):
    cid, sev = F.classify(subject, text, url)
    return {"at": at, "category": cid, "label": F.LABEL[cid], "severity": sev, "subject": subject, "text": text, "url": url}


@pytest.mark.parametrize("subject,text,url,label", [
    (MEET, "XYZ has informed the Exchange about Schedule of meet", None, "Analyst or investor meeting"),
    (MEET, "XYZ has informed the Exchange about Audio Recording", None, "Earnings call"),
    (MEET, "Transcript of the Q1 earnings call", None, "Earnings call"),
    ("Updates", "Transcript of the 45th Annual General Meeting", None, "Shareholder meeting"),
    ("Updates", "Audio recording of the AGM", None, "Shareholder meeting"),
    ("Updates", "Presentation made to shareholders at the Annual General Meeting", None, "Shareholder meeting"),
    ("Updates", "Notice of the Annual General Meeting", None, "Shareholder meeting"),
    ("Updates", "Outcome of the postal ballot", None, "Shareholder meeting"),
    (MEET, "", "https://nsearchives.nseindia.com/corporate/XYZ_12082026193000_Q1FY27ConcallTranscript.pdf", "Earnings call"),
])
def test_each_kind_has_its_own_label(subject, text, url, label):
    assert item(subject, text, url=url or "")["label"] == label


def test_meetings_count_shareholder_meetings_apart_and_once_each():
    items = [item("Updates", "Notice of the 30th Annual General Meeting", at="2026-07-01T10:00"),
             item("Updates", "Outcome of the 30th Annual General Meeting", at="2026-07-25T10:00"),
             item("Updates", "Transcript of the 30th Annual General Meeting", at="2026-07-28T10:00"),
             item("Updates", "Postal ballot notice", at="2025-12-01T10:00"),
             item(MEET, "Schedule of meet", at="2026-05-01T10:00")]
    got = deepdive.meetings(items, "2024-10-05T00:00")
    assert got["shareholder"] == 2 and got["meets"] == 1 and got["calls"] == 0


def _view():
    return {"region": "IN", "documents": [], "checklist": {"checks": [], "industry": {"path": ["x"]}}, "valuation": {"value": 1}}


def test_audit_says_no_earnings_calls_with_the_shareholder_meetings_it_held():
    got = [i["detail"] for i in audit.check_view(_view(), {"meets": 0, "calls": 0, "filed": 40, "shareholder": 3})]
    assert got and all(d.startswith("No earnings calls; 3 shareholder meetings") for d in got)
    assert not any("Held no earnings call" in d for d in got)
    one = [i["detail"] for i in audit.check_view(_view(), {"meets": 0, "calls": 0, "filed": 40, "shareholder": 1})]
    assert one[0].startswith("No earnings calls; 1 shareholder meeting ")


def test_audit_with_analyst_meetings_and_shareholder_meetings_names_both():
    got = [i["detail"] for i in audit._india_documents(["presentation"], {"meets": 4, "calls": 0, "filed": 40, "shareholder": 2}, None)]
    assert got == [audit._no_calls(4, 2)]
    assert got[0].startswith("No earnings calls; 4 analyst or investor meetings and 2 shareholder meetings")


def test_audit_wording_without_shareholder_meetings_is_unchanged_and_old_stored_reads_work():
    assert [i["detail"] for i in audit._india_documents(["presentation"], {"meets": 3, "calls": 0, "filed": 9}, None)] == [audit.NO_CALLS]
    assert [i["detail"] for i in audit._india_documents(["presentation"], {"meets": 0, "calls": 0, "filed": 9}, None)] == [audit.NO_CALLS_TOLD]
