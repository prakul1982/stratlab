"""Lane fix98: four production faults of 26-27 Nov 2026. Each test fails on origin/main a8816c5 and passes after, except those marked
as guards."""
from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
import httpx
import pytest

from app.intel import filings as F
from app.intel import nse_archive as A
from app.intel.net import SourceError

EQUITY_CSV = ("SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
              + "".join(f"CO{i},Company {i} Limited,EQ,01-Jan-2010,10,1,INE{i:09d},10\n" for i in range(150)))


# ---------- 1. the exchange's archive: every host in turn ----------
def test_the_list_of_companies_is_read_from_the_next_archive_host_when_one_refuses():
    """Fails on main: production's address got 403 on nsearchives.nseindia.com for EQUITY_L.csv every hour from 26 Nov 19:51 UTC
    ("stock list IN failed: The exchange's list of companies was refused (403)") while the .in host and archives.nseindia.com served
    the same file. The .in host is asked first (as R93), then .com, then archives.nseindia.com."""
    asked = []

    def handler(r):
        asked.append(r.url.host)
        return httpx.Response(200, text=EQUITY_CSV) if r.url.host == "archives.nseindia.com" else httpx.Response(403)
    feed = F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    got = feed.all_equities()
    assert len(got) == 150 and got[0]["symbol"] == "CO0"
    assert asked == ["nsearchives.nseindia.in", "nsearchives.nseindia.com", "archives.nseindia.com"]
    # the .in host answering: asked once, nothing else
    asked.clear()
    feed = F.NSEFilings(transport=httpx.MockTransport(lambda r: (asked.append(r.url.host), httpx.Response(200, text=EQUITY_CSV))[1]))
    assert len(feed.all_equities()) == 150 and asked == ["nsearchives.nseindia.in"]


def test_the_list_of_companies_fails_only_when_every_host_refuses():
    asked = []
    feed = F.NSEFilings(transport=httpx.MockTransport(lambda r: (asked.append(r.url.host), httpx.Response(403))[1]))
    with pytest.raises(SourceError, match=r"list of companies was refused \(403\)"):
        feed.all_equities()
    assert asked == list(A.MIRRORS)
    # a host that can't be reached moves on too; the last refusal is what is said
    calls = []

    def flaky(r):
        calls.append(r.url.host)
        if r.url.host == "nsearchives.nseindia.in":
            raise httpx.ConnectError("down")
        return httpx.Response(403)
    with pytest.raises(SourceError, match=r"\(403\)"):
        F.NSEFilings(transport=httpx.MockTransport(flaky)).all_equities()
    assert calls == list(A.MIRRORS)


def test_a_missing_file_is_the_archives_answer_and_is_not_asked_three_times():
    """Guard: only a refusal (401/403) or no connection moves on; a 404 (not published) or a 5xx is the archive's answer."""
    for code in (404, 500, 200):
        asked = []
        http = httpx.Client(transport=httpx.MockTransport(lambda r: (asked.append(r.url.host), httpx.Response(code))[1]))
        assert A.get(http, F.SEC_LIST).status_code == code and asked == ["nsearchives.nseindia.in"]


def test_every_archive_address_in_the_app_goes_through_the_one_rule():
    """The rule is the host, not a list of addresses: each archive file the app reads (price bands, F&O ban, index files, lot sizes,
    ETF list, bhavcopies, participant files) is asked on each host in turn, and the allow-lists of documents take every host."""
    from app import docs, ipo, ipo_docs, positioning, shareholders
    assert A.mirrors("https://archives.nseindia.com/content/fo/fo_mktlots.csv") == [
        "https://nsearchives.nseindia.in/content/fo/fo_mktlots.csv", "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv",
        "https://archives.nseindia.com/content/fo/fo_mktlots.csv"]
    assert A.mirrors("https://www.nseindia.com/api/x") == ["https://www.nseindia.com/api/x"]
    # no address names the older host as a second address of its own any more: the rule asks it
    assert all("//archives." not in u for u in (*F.sec_list_urls(), *positioning.FILE_URLS))
    for host in A.HOSTS:
        assert host in docs.ALLOWED_HOSTS and host in ipo_docs.HOSTS and host in shareholders.XBRL_HOSTS
        assert f"https://{host}/" in ipo.LINK_HOSTS and F._archive_url(f"https://{host}/x.xml")
    # the per-stock desks' and positioning's files (positioning.Feed) read through the same rule
    asked = []

    def handler(r):
        asked.append(r.url.host)
        if r.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, text="a,b\n1,2\n") if r.url.host == "archives.nseindia.com" else httpx.Response(403)
    f = positioning.Feed(F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None), sleep=lambda s: None)
    assert f.raw("https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261126_F_0000.csv.zip") == b"a,b\n1,2\n"
    assert asked[-3:] == list(A.MIRRORS)


def test_a_filed_document_refused_on_one_host_is_read_from_the_next():
    """A filing's PDF linked on the .com host and refused there is read from the archive's other hosts."""
    from app import docs
    asked = []

    def handler(r):
        asked.append(str(r.url))
        return httpx.Response(200, content=b"%PDF-1.4 x") if r.url.host == "archives.nseindia.com" else httpx.Response(403)
    d = docs.Docs(transport=httpx.MockTransport(handler), check_host=lambda h: True)
    url = "https://nsearchives.nseindia.com/corporate/X_1.pdf"
    assert d._download(url, (), 1000) == b"%PDF-1.4 x"
    assert asked == [url, "https://nsearchives.nseindia.in/corporate/X_1.pdf", "https://archives.nseindia.com/corporate/X_1.pdf"]
    with pytest.raises(SourceError, match=r"\(403\)"):
        docs.Docs(transport=httpx.MockTransport(lambda r: httpx.Response(403)), check_host=lambda h: True)._download(url, (), 1000)
