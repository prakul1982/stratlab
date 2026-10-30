# LO-1: the last leftovers before the weekly reset (30 Oct 2026). Part 2: the offer document's holder tables in every layout the stored
# documents use, the promoter/public split, and a plain word when a table can't be read (LO1-2).
import gzip
import json

from tests import fake_ipo as F


def _doc(name: str) -> list[str]:
    """The capital structure pages of a real red herring prospectus (the other pages are empty strings)."""
    got = json.load(gzip.open(F.DIR / "holding_layouts_pages.json.gz", "rt", encoding="utf8"))[name]
    out = [""] * got["count"]
    for i, t in got["pages"].items():
        out[int(i)] = t
    return out


def test_an_issue_layout_with_one_promoter_roman_serials_and_bare_percents_is_read():
    # Jio Platforms: "Pre-Issue", "Promoter" (one), "(i)" on a line of its own, "66.43" without a % sign, names over many lines
    from app import ipo_docs as D
    h = D.shareholding(_doc("JPL"))
    assert h["layout"] == "holders" and h["page"] == 109
    rows = h["rows"]
    assert rows[0] == {"group": "Promoter", "name": "Reliance Industries Limited", "shares": 5_937_841_645, "pct": 66.43, "post_shares": None, "post_pct": None,
                       "total": False, "promoter": True}
    top = [r for r in rows if r["group"].startswith("Additional top 10")]
    assert len(top) == 10 and top[1]["name"] == "Google International LLC" and top[1]["pct"] == 7.73
    assert top[0]["name"].startswith("Jaadhu Holdings, LLC (an affiliate of Meta Platforms")
    assert rows[-1]["name"] == "Public shareholders" and rows[-1]["shares"] == 156_868_465 and rows[-1]["pct"] == 1.75
    assert sum(r["shares"] for r in rows) == 8_939_030_830                                      # every holder, nothing read twice: the pattern's total
    # the split is the document's shareholding pattern: (A) promoter and promoter group, (B) public
    assert h["split"] == {"page": 107, "promoter_shares": 5_937_841_645, "promoter_pct": 66.43, "public_shares": 3_001_189_185, "public_pct": 33.57, "basis": "pattern"}


def test_a_company_its_promoter_holds_whole_is_one_row_and_a_split_with_no_public():
    # Bonfiglioli: one holder, "187,995,834*" with a note mark, "S.p.A.(3)"; the pattern's figure broke over two lines ("187,995,\n834")
    from app import ipo_docs as D
    pages = _doc("BONFIG")
    h = D.shareholding(pages)
    assert h["layout"] == "holders" and h["page"] == 109
    assert [(r["name"], r["shares"], r["pct"]) for r in h["rows"]] == [("Bonfiglioli S.p.A.", 187_995_834, 100.0)]
    assert h["split"]["promoter_pct"] == 100.0 and h["split"]["public_pct"] == 0.0 and h["split"]["public_shares"] == 0 and h["split"]["page"] == 106
    # the table of holders of 1% two years ago, on the page before, is not taken for it
    assert all(r["shares"] != 125_330_556 for r in h["rows"])
    # once the price is set the prospectus fills the post-offer columns: the upper end of the price band is the one kept
    filled = list(pages)
    filled[108] = filled[108].replace("187,995,834* 100.00 [●] [●] [●] [●]", "187,995,834* 100.00 187,995,834 80.12 187,995,834 81.50")
    got = D.shareholding(filled)["rows"][0]
    assert got["post_shares"] == 187_995_834 and got["post_pct"] == 81.5


def test_the_sme_layout_of_promoters_and_promoter_group_with_negligible_holdings_is_read():
    # M. K. Sons (SME): no combined table; the promoters' and promoter group's own table, "Total (A)", "Negligible", and the build-up table after it
    from app import ipo_docs as D
    h = D.shareholding(_doc("MKSONS"))
    assert h["layout"] == "promoters" and h["page"] == 91
    names = [(r["group"], r["name"], r["shares"], r["pct"], r["total"]) for r in h["rows"]]
    assert names == [("Promoters", "Ramchand Murlidhar Raimalani", 41_090_760, 96.25, False), ("Promoters", "Neelam Ramchand Raimalani", 1_599_500, 3.75, False),
                     ("Promoters", "Kush Ramchand Raimalani", 100, 0.0, False), ("Promoters", "Total (A)", 42_690_360, 100.0, True),
                     ("Promoter Group", "Murlidhar Murajmal Raimalani", 100, 0.0, False), ("Promoter Group", "Nitin Sajandas Manghwani", 100, 0.0, False),
                     ("Promoter Group", "Shakuntala Sajandas Manghwani", 100, 0.0, False), ("Promoter Group", "Total (B)", 300, 0.0, True)]
    assert h["split"] == {"page": 89, "promoter_shares": 42_690_660, "promoter_pct": 99.99, "public_shares": 100, "public_pct": 0.0, "basis": "pattern"}


def test_the_combined_layout_gives_its_own_split_and_a_table_that_does_not_add_up_is_left_out():
    from app import ipo_docs as D
    h = D.shareholding(F.pages_of("sfc_rhp"))
    assert h["layout"] == "holders" and h["split"]["basis"] == "holders"
    assert h["split"]["promoter_pct"] == 48.18 and h["split"]["public_pct"] == 51.81                 # (A) 42.84 + (B) 5.34; (C) 37.79 + (D) 14.02
    assert h["split"]["promoter_shares"] == 40_019_595 + 4_991_820 and "post_promoter_pct" not in h["split"]
    # a sub-total that isn't the sum of its rows: the holders aren't shown (a misread), the pattern's split still is
    bad = _doc("MKSONS")
    bad[90] = bad[90].replace("Total (A) 42,690,360", "Total (A) 42,690,361")
    got = D.shareholding(bad)
    assert got["rows"] == [] and got["layout"] == "pattern" and got["split"]["promoter_pct"] == 99.99
    assert D.shareholding([""] * 5) is None and D.holding_split([""] * 5) is None


def test_the_page_says_when_the_table_couldnt_be_read_and_older_facts_stay_until_read_again(monkeypatch):
    from app import ipo as I, ipo_docs as D
    monkeypatch.setattr(I, "doc_to_read", lambda row: {"kind": "RHP", "url": "u", "source": "nse"})
    now = {"kind": "RHP", "promoters": ["A"], "pages_read": 3, "excerpt": "words", "reader": D.READER}
    monkeypatch.setattr(I, "facts_of", lambda d: now)
    assert I.facts_view({"market": "IN", "id": "x"})["holding_unread"] is True
    monkeypatch.setattr(I, "facts_of", lambda d: {**now, "holding": {"page": 1, "rows": []}})
    assert "holding_unread" not in I.facts_view({"market": "IN", "id": "x"})
    old = {**now, "reader": D.READER_KEPT}
    monkeypatch.setattr(I, "facts_of", lambda d: old)
    assert "holding_unread" not in I.facts_view({"market": "IN", "id": "x"})                 # an older reader's facts: read again soon, not "couldn't"
    assert I.facts_stale(old) and not I.facts_stale(now) and not I.facts_stale(None)
    monkeypatch.setattr(I, "facts_of", lambda d: {"kind": "424B4", "us": {}, "reader": D.READER})
    assert "holding_unread" not in I.facts_view({"market": "US", "id": "y"})


def test_facts_an_older_reader_made_still_show_and_are_read_again_after_the_unread_ones(monkeypatch):
    from datetime import datetime, timezone
    from app import db, ipo as I, ipo_docs as D
    kept: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k, default=None: kept.get(k, default))
    monkeypatch.setattr(db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    d_old, d_new = {"kind": "RHP", "url": "https://nsearchives.nseindia.com/a.zip"}, {"kind": "RHP", "url": "https://nsearchives.nseindia.com/b.zip"}
    db.set_setting(D.FACTS_KEY + I.doc_key(d_old), json.dumps({"kind": "RHP", "reader": D.READER_KEPT, "promoters": ["A"]}))
    assert I.facts_of(d_old)["promoters"] == ["A"]                                            # shown meanwhile: no IPO page goes blank
    db.set_setting(D.FACTS_KEY + I.doc_key(d_new), json.dumps({"kind": "RHP", "reader": 1}))
    assert I.facts_of(d_new) is None
    rows = [{"id": "in-a", "market": "IN", "name": "A Ltd", "open": "2026-10-29", "close": "2026-11-02", "d": d_old},
            {"id": "in-b", "market": "IN", "name": "B Ltd", "open": "2026-11-05", "close": "2026-11-07", "d": d_new}]
    monkeypatch.setattr(I, "load", lambda m: {"rows": rows if m == "IN" else []})
    monkeypatch.setattr(I, "doc_to_read", lambda r: r["d"])
    monkeypatch.setattr(I, "stage_of", lambda r, now: "open" if r["id"] == "in-a" else "upcoming")
    read = []
    monkeypatch.setattr(I, "read_doc", lambda r, d, sebi: read.append(r["id"]))
    monkeypatch.setattr(I, "_wire", {"sebi": lambda: None, "ai": None})
    I.Job().read_docs(datetime(2026, 10, 30, 6, tzinfo=timezone.utc), limit=5)
    assert read == ["in-b", "in-a"]                                                            # the one never read first, though the other is open


# ---- LO1-3: the NIFTY 100's business updates coverage, and the update filings the reader missed ----
def _store(monkeypatch):
    from app import biz_updates as B, db
    kept: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k, default=None: kept.get(k, default))
    monkeypatch.setattr(db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: None)
    B.forget()
    return kept


def test_the_nifty_100s_missed_update_filings_are_taken_and_an_earnings_presentation_is_not():
    # the exchange's own rows (NSE, Oct 2026): "Production Release", "Provisional Financial figures for Qtr", "Update for Q1 FY27", and
    # a "General Updates" whose file is the provisional figures; Max Healthcare's "Earnings Update" presentation is not one
    from app import biz_updates as B
    got = json.load(open(F.DIR.parent / "business_updates" / "n100_missed.json", encoding="utf8"))
    for sym in ("HINDZINC", "UNIONBANK", "TRENT", "VAML"):
        assert got[sym] and all(B.is_update(i) for i in got[sym]), sym
    assert got["MAXHEALTH"] and not any(B.is_update(i) for i in got["MAXHEALTH"])
    assert not B.is_update({"subject": "Updates", "text": "Infosys Limited has informed the Exchange regarding 'Form 20-F and Press Release'.", "url": "https://nsearchives.nseindia.com/corporate/x.pdf"})


def test_the_nifty_100_coverage_line_counts_the_covered_and_says_why_for_the_rest(monkeypatch):
    from datetime import date
    from app import biz_updates as B
    kept = _store(monkeypatch)
    fig = {"figures": [{"metric": "Total sales", "value": 1}], "period": "2026-09"}

    def put(sym, reads=None, checked=None):
        kept[B.KEY + sym] = json.dumps({"reads": reads or {}, **({"checked": checked} if checked else {})})

    put("MARUTI", {"a": {"at": "2026-10-01T12:00:00", **fig}}, {"at": "2026-10-29T14:00:00", "found": 30, "newest": "2026-10-01"})
    put("UNIONBANK", {"b": {"at": "2026-10-01T22:00:00", "figures": [], "period": None, "problem": "No figure could be checked against the document."}},
        {"at": "2026-10-29T14:00:00", "found": 2, "newest": "2026-10-01"})
    put("TCS", None, {"at": "2026-10-29T14:00:00", "found": 0})
    put("HINDZINC", {"c": {"at": "2026-04-02T12:00:00", **fig}}, {"at": "2026-10-29T14:00:00", "found": 3, "newest": "2026-10-03"})    # filed, the newest not read yet
    put("ASIANPAINT", {"d": {"at": "2026-03-01T12:00:00", **fig}}, {"at": "2026-10-29T14:00:00", "found": 1, "newest": "2026-03-01"})  # nothing lately
    put("ITC", {"e": {"at": "2026-10-05T12:00:00", "skip": True, "problem": "Not a business update."}}, None)                           # never looked through
    got = B.index_coverage(date(2026, 10, 30), ["MARUTI", "UNIONBANK", "TCS", "HINDZINC", "ASIANPAINT", "ITC"])
    assert got["companies"] == 6 and got["covered"] == 1 and got["days"] == 120
    why = {r["symbol"]: r["why"] for r in got["without"]}
    assert why == {"UNIONBANK": "unreadable", "TCS": "none_found", "HINDZINC": "not_fetched", "ASIANPAINT": "none_found", "ITC": "not_fetched"}
    assert got["counts"] == {"unreadable": 1, "not_fetched": 2, "none_found": 2}
    u = next(r for r in got["without"] if r["symbol"] == "UNIONBANK")
    assert u["problem"].startswith("No figure") and u["why_text"] == "Filing unreadable" and u["newest_filed"] == "2026-10-01"


def test_the_index_list_is_kept_and_the_daily_run_looks_through_it_and_notes_the_newest_update(monkeypatch):
    from datetime import datetime, timezone
    from app import biz_updates as B
    kept = _store(monkeypatch)
    hundred = [f"S{i:03d}" for i in range(100)]

    class Feed:
        def __init__(self, members):
            self.members, self.asked = members, []

        def index_members(self, name):
            assert name == "NIFTY 100"
            if self.members is None:
                raise RuntimeError("turned away")
            return self.members

        def announcements(self, sym, days):
            self.asked.append(sym)
            return [{"at": "2026-10-03 14:00:00", "subject": "Updates", "text": "Production Release for the second quarter", "url": "https://nsearchives.nseindia.com/corporate/x.pdf"}] if sym == "S001" else []

    feed = Feed(hundred)
    monkeypatch.setattr(B, "_wire", {"feed": lambda: feed, "docs": lambda: None, "ai": None})
    assert B.index_symbols() == hundred and json.loads(kept[B.INDEX_KEY]) == hundred
    feed.members = None
    assert B.index_symbols() == hundred                                                        # the exchange turning us away: the kept list
    feed.members = hundred
    monkeypatch.setattr(B, "SECTORS", {})
    monkeypatch.setattr(B, "user_symbols", lambda: [])
    monkeypatch.setattr(B, "read_new", lambda *a, **k: {"read": 0, "problems": []})
    B.Job(lambda rows, now: 0, lambda: []).run(datetime(2026, 10, 30, 14, tzinfo=timezone.utc))
    assert sorted(feed.asked) == hundred                                                       # no NIFTY 100 company is left "not looked at"
    assert B.checked("S001") == {"at": "2026-10-30T14:00:00+00:00", "found": 1, "newest": "2026-10-03"} and B.checked("S002")["found"] == 0
