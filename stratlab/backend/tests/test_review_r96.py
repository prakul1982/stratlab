"""24 Oct 2026 (owner, L&T's report card): a customer saw "None of the earnings-call transcripts could be read. 16 filings
held only a short letter…; 2026-08-03: the letter links to https://…pdf, which couldn't be read (The document is too large
to read here.)". What a reader sees about skipped documents is now plain: no web addresses or raw errors, which go to the
server log."""
from app import deepdive


def test_stored_lines_lose_their_web_addresses():
    raw = ["16 filings held only a short letter, not the document itself",
           "2026-08-03: the letter links to https://investors.example.com/upload/a.pdf, which couldn't be read (too large)",
           "Q1 FY26 call: couldn't be opened"]
    out = deepdive.customer_problems(raw)
    assert out[0] == raw[0] and out[2] == raw[2] and "://" not in out[1] and "the company's website" in out[1]
    assert deepdive.customer_problems(None) == []


class _Docs:
    def text(self, url, **kw):
        if "big" in url:
            raise RuntimeError("The document is too large to read here.")
        if "bad" in url:
            raise RuntimeError("HTTP 500 from https://cdn.example.com/x.pdf")
        return "Please find the transcript at https://investors.example.com/t.pdf"     # a short letter


def test_a_failed_read_keeps_its_error_for_the_log(capsys):
    problems = []
    docs = [{"title": "Transcript Q1", "url": "https://x/bad.pdf", "at": "2026-08-03T10:00:00", "kind": "transcript"}]
    assert deepdive.readable(_Docs(), docs, 1, problems, ()) == []
    assert problems == ["Transcript Q1: couldn't be opened"]
    assert "HTTP 500" in capsys.readouterr().out


def test_a_cover_letter_says_so_without_its_links():
    problems = []
    docs = [{"title": "Transcript Q1", "url": "https://x/letter.pdf", "at": "2026-08-03T10:00:00", "kind": "transcript"}]
    deepdive.readable(_Docs(), docs, 1, problems, ())
    assert problems and all("://" not in p for p in problems), problems
    assert "held only a short letter" in problems[0]


class _BigLink(_Docs):
    def text(self, url, **kw):
        if url.endswith("letter.pdf"):
            return "The annual report is at https://investors.example.com/upload/big.pdf"
        return super().text(url, **kw)


def test_a_linked_document_that_fails_gives_its_reason_not_its_address(capsys):
    problems = []
    docs = [{"title": "Transcript Q1", "url": "https://x/letter.pdf", "at": "2026-08-03T10:00:00", "kind": "transcript"}]
    deepdive.readable(_BigLink(), docs, 1, problems, ())
    line = next(p for p in problems if p.startswith("2026-08-03"))
    assert line == ("2026-08-03: the letter links to a document on the company's website, which couldn't be read "
                    "(The document is too large to read here)")
    assert "investors.example.com/upload/big.pdf" in capsys.readouterr().out
