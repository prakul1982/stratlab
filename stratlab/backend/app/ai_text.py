"""What every AI reply goes through before anyone reads it (LIVE5-005: a company read ended "What to watch: No ex-dividend date or
shareholder meeting date is given in the FACTS.", the prompt's own word shown to people).

A sentence that talks about the prompt instead of the company or the market ("given in the FACTS", "the data provided", "in the
context") is taken out; rupees written "Rs 10,445" are written "₹10,445" as on every page. It works on the reply's text, JSON or
not, one sentence at a time, never across a quoted string's edge, so a JSON reply stays JSON (a string that was only such a
sentence is left empty, which the readers drop). Facts only: nothing is added."""
import re

# words that only make sense to the model: the prompt's own section names and talk about "the data" it was handed
_JARGON = re.compile(
    r"\bFACTS\b|\bJSON\b|(?i:\bthe (?:facts|data|information|figures|context|input) (?:provided|given|supplied|above|below)\b"
    r"|\b(?:provided|given|supplied) (?:facts|data|information|context|figures)\b|\bin the (?:facts|prompt|context|input|json)\b"
    r"|\bthe prompt\b|\bper the (?:facts|data)\b|\bnot (?:included|listed|given|provided|mentioned|stated) in the (?:facts|data)\b)")
# one sentence inside a string: no quote, no line break, ending at its full stop (or at the string's end)
_SENTENCE = re.compile(r'[^".!?\n]*?(?:' + _JARGON.pattern + r')[^".!?\n]*(?:[.!?](?=\s|"|$)\s*|(?="|\n|$))')
_RUPEES = re.compile(r"\bRs\.?\s?(?=\d)")


def has_jargon(text: str) -> bool:
    return bool(_JARGON.search(text or ""))


def clean_reply(text: str) -> str:
    """The reply with every sentence about the prompt taken out and rupees written with the ₹ sign."""
    if not isinstance(text, str) or not text:
        return text
    # a sentence runs from the last full stop, quote or line break, so a label before it ("What to watch: ...") goes with it
    out = _RUPEES.sub("₹", text)           # first, so "Rs." is not read as a sentence's end
    return _SENTENCE.sub("", out) if _JARGON.search(out) else out
