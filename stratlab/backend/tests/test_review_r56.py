"""Round 56: a change waiting for a look names each circular once."""
from app import main  # noqa: F401  (loads the modules in the order they need)
from app import rules_watch as RW


def test_a_pending_change_names_each_circular_once():
    c = {"date": "October 16, 2026", "subject": "Review of certain aspects of the Closing Auction Session", "url": "u"}
    pending = {"at": "2026-10-16T18:00", "why": "new circular",
               "items": [{**c, "id": "a"}, {**c, "id": "b"}, {**c, "id": "c", "subject": c["subject"] + " "}, {**c, "id": "d"},
                         {"id": "e", "date": "October 15, 2026", "subject": "Revision in lot sizes", "url": "v"}]}
    got = RW._once(pending)
    assert [i["date"] for i in got["items"]] == ["October 16, 2026", "October 15, 2026"]
    assert RW._once(None) is None


def test_a_certificate_failure_is_said_in_words():
    """R57-014: an unread source's error is a sentence, not "[SSL: CERTIFICATE_VERIFY_FAILED] …"."""
    import ssl
    msg = RW._plain_error(ssl.SSLCertVerificationError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))
    assert "CERTIFICATE" not in msg and "certificate" in msg
    assert RW._plain_error(ValueError("No fee rate found on the page.")) == "No fee rate found on the page."


def test_a_half_of_the_range_claim_must_match_the_levels():
    """R58-001: "upper half of their 52-week ranges" for indices about a quarter of the way up is dropped."""
    from app.intel import grounding as G
    idx = [{"name": "NIFTY 50", "price": 25000.0, "low52": 23955.6, "high52": 28486.8, "change_pct": 0.65},
           {"name": "SENSEX", "price": 82000.0, "low52": 78228.0, "high52": 94545.0, "change_pct": 0.6}]
    facts = G.market_facts(idx)
    assert not G.range_claims_ok("Both broad indices remain in the upper half of their 52-week ranges.", facts)
    assert G.range_claims_ok("Both indices sit in the lower half of their 52-week ranges.", facts)
    assert G.range_claims_ok("NIFTY 50 closed at 25,000, up 0.65%.", facts)
