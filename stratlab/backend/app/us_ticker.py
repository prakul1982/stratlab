"""One way to write a US share-class ticker everywhere in the app: with a dash (BRK-B, BF-B), the way the price source,
the SEC's list and the public pages (which 301 BRK.B to BRK-B) write it.

R13-001: /research/US/BRK.B asked every source for "BRK.B": the price source has nothing under that name, so the page
had no chart (502), no 52-week range and no P/E, and its market value ($983.7B) came from another share basis than
BRK-B's ($1.104T). A dotted or slashed class letter is now the dashed ticker before any source is asked."""
import re

# a class of common stock: one letter after a dot or a slash (BRK.B, BF/B, MOG.A). A preferred series (BAC.PRL) or
# anything longer is left as typed: it isn't a share class, and its own rules are elsewhere (intel/sec.price_symbol)
CLASS = re.compile(r"^([A-Z][A-Z0-9]{0,5})[./]([A-Z])$")


def canon_us(symbol: str | None) -> str:
    """BRK.B, brk.b and BRK/B -> BRK-B; any other ticker upper-cased and trimmed, otherwise as it is."""
    s = str(symbol or "").strip().upper()
    m = CLASS.match(s)
    return f"{m.group(1)}-{m.group(2)}" if m else s


# an Indian symbol as other sites and brokers write it: TCS.NS and TCS.BO (a price site's tickers), TCS-EQ (the exchange's series), NSE:TCS
EXCHANGE = re.compile(r"^(?:NSE|BSE)\s*[:/]\s*|(?:\.NS|\.BO|\.NSE|\.BSE|-EQ)$")


def canon_in(symbol: str | None) -> str:
    """TCS.NS, tcs.bo, TCS-EQ and NSE:TCS -> TCS; any other symbol upper-cased and trimmed, as it is (RC5-010: /research/IN/TCS.NS
    said no such company). The suffix is the exchange's, never part of the company's own symbol."""
    s = str(symbol or "").strip().upper()
    out = EXCHANGE.sub("", s).strip()
    return out if out and not EXCHANGE.search(out) else s       # a lone ".NS" stays as typed


def canon(region: str | None, symbol: str | None) -> str:
    """A ticker as the app keeps it for a region: US share classes with a dash; Indian symbols without an exchange's affix."""
    return canon_us(symbol) if str(region or "").upper() == "US" else canon_in(symbol)
