#!/usr/bin/env python3
"""Deck regression check: reads a folder of deck PDFs as a reader would (pdftotext) and reports, for each deck, what must never ship.

    python scripts/deck_check.py <folder of deck PDFs> [--strict] [--json]

Failures (the exit code is 1 when any deck has one):
  headline     a slide's title or headline (its first lines) ending in "…"
  mid-word     a word cut inside itself ("Semiconductor equipm…"): one the deck prints longer elsewhere and never whole
  placeholder  an unfilled field or a missing value printed as text ("{name}", "None", "nan", "undefined", "shown for x.")
  joining word text cut on a joining word ("Component and…")
  count        "N of M" where N is larger than M
  repeated     a word said twice in a row ("outside the the theme", "Of of"), whatever the case, on one line or across a line break
               (a name such as "Bora Bora" or "R R Kabel", and "had had", are English)
  hyphen minus a figure's minus sign printed as a hyphen ("-14.1%" beside "−11%"; LIVE7A-014): the deck prints the real minus
  no layer     a company of the appendix's table in no layer ("–" where its layer goes; d1: SAIL, GAIL, MercadoLibre in the live
               Release 41 decks): every company is in a layer or in "Other"
  unread ranked  gl50 (R50, the live Biotech and Capital goods decks): a layer ranked ("highest in", "lowest in") in a deck whose comparison
               basis says no way of earning was read for its companies
  unread kind  gl50: a company said to be "of the layer's kind" in a deck that says no way of earning was read
  left out>50% gl50 (the live FMCG deck, "2 of 12" in a layer's calculations; Software "2 of 11"): a layer whose calculations hold fewer than
               half of its companies (a layer of 4 or more)
  unchecked as 0  gl50 (the live decks' "100 of the 100 checked confirmed by their own description, 0 not yet" of 821): the companies past
               the membership check folded into "0 not yet"
  biz label    rv51 (R51, the live Release 49 Consumer retail deck: "Online stock-holding retailers ..., a different business model: platforms
               and marketplaces (the map's name for the layer)"): a layer left out of a ranking for "a different business model" whose model
               is read from a name ("the map's name for the layer", "stated by the layer's own name"), when no word of that model is in the
               layer's own name (or the map's name it quotes), or a model read elsewhere whose words are neither in the deck's layer names
               nor said to be how the layer's companies earn
  biz making   rv51 (the same deck: "Store retailers of home, auto and beauty goods ..., a different business model: parts, component and
               ingredient makers"): a making model (parts, components, ingredients, makers, manufacturing) given as the business model of a
               layer whose own name is a seller's or a service firm's (retailers, stores, chains, platforms, distributors, services, banks...)
  stale layer  d53 (R53, our deck reviewer and the live R52 Biotech and Cement decks: "earn the same way as those of “Pipeline-stage and
               royalty-funded drug developers”", a name the deck's layers no longer have): a layer named in a sentence ("earn the same way as
               those of “X”") that is none of the deck's layers
  same company d53 (the live R51-R52 Insurance decks: "ICICI Life Insurance Ltd" and "ICICI Prudential Life Insurance Company Ltd" on two
               rows of one revenue, margins and growth): two rows of the appendix with the same revenue and the same three figures after it
  words claim  d53 (LIVE8A-004: "Every company with figures has words of its own ... Nothing held back" beside "No description in its own
               words yet"): the claim in a deck that prints a company with no words of its own
  partial unsaid  d53 (the owner's review of the live R52 Biotech deck: 100 of 821 checked, the map read as whole): a deck whose companies
               checked are under half its list ("N checked ...; M not checked yet") that never says "A partial map"
  outlier range  d53 (LIVE8A-010: "−27994.5% to 62.2%", a median of −258.6%): a range or median of margins printed with an end beyond
               ±1,000%
  added unexplained  d53 (the owner's review of the live R52 Consumer retail deck: "added 6: CDW Corp, ..., Suburban Propane Partners LP"):
               a change log that adds companies with no reason
  verified count  d53 (our deck reviewer: "15 checked figures, 15 verified" over rows "arithmetic reproduced"): a figure-sources head whose
               verified count is all its figures while its rows say some only had their arithmetic reproduced
  adjacent ranked  d53 (the owner's review: hospital operators in a Medical devices theme): a layer said to be adjacent participants named
               highest or lowest in a ranking
  move unexplained  c54 (the owner's review of the live R53 decks: Intel moved "from “Makers of their own products” to “Chip equipment and
               subsystem suppliers”", Indo National into "Branded packaged foods manufacturing", UFP into "Surgical robotics systems", with
               nothing showing they sell what those layers are): a change log's move between layers into a layer named by what it sells (not
               "Other", not a group named by how its companies earn) with no reason beside it
  scope core   c54 (the live R53 Automotive deck: "Vehicle financiers" of lenders among the core makers; FMCG's "Mining, oil, gas and farming"):
               a layer named by a business outside the theme's own (lenders or financiers, contractors or EPC, laboratories, mining, oil
               and gas, farming), the theme's own name stating none of it, in a deck that says no company is an adjacent participant
  layer lost unsaid  c54 (the live R53 Metals deck: "“Aluminium” removed (14 companies)"): a change log's layer of five companies or more
               removed with neither where its companies went nor why
  evidence state  e54 (R54, the owner's review of the live R53 Biotech, Medical devices and Hospitals decks: "100 confirmed by their own
               description" of 100 checked beside "18 companies with figures have no description in their own words yet"): companies
               counted as confirmed by their own description and companies with no words of their own that together are more than the
               companies checked, or more companies without words than the deck keeps on their official industry only
  population mismatch  e54 (the live R53 Medical devices deck: "Companies, by count 76 of 222" while its "Each layer" row adds up to 100,
               adjacent participants among them): the layers' companies with figures adding up to another count than the deck's companies
               with figures, unless the row says how core members and adjacent participants add up to it
  identity unresolved  v55 (R55, the owner's review of the live R54 Payments deck: "Adyen Nv-Unspon ADR" among the "companies with figures
               whose own words describe other work", none of its words read): a company listed as one whose own words describe other work
               (or don't show the work) whose name is a depositary-receipt line, or that the same deck says has its own words "not confirmed
               to show the theme's work yet"
  out of scope in Other  v55 (the live R54 FMCG deck: Indo National, a battery and torch maker, moved into "Other FMCG companies", and High
               Energy Batteries there): a company of a theme's "Other" group whose name states a kind of product outside the theme's own
               (batteries, torches, dry cells; cables, transformers; steel, castings, forgings; cement; tyres; fertilisers, pesticides), in a
               theme whose title doesn't state it, unless the deck says it is not checked yet
  stage mismatch  v55 (the live R54 Biotech deck: Merck & Co, $65 bn of revenue, in "Pipeline-stage and royalty-funded drug developers"):
               a company of the appendix in a layer named by a development stage only (clinical-stage, pipeline-stage, pre-revenue,
               development-stage, pre-clinical; no commercial, specialty, large or portfolio part) with an operating profit and revenue ten
               times the layer's median developer's (those with no operating profit) and $5 bn (₹20,000 cr) or more
  coverage blur  v55 (the owner: "keep increasing checked membership without implying financial coverage grew"): a "Membership checked"
               row whose checked share rose over stored versions, with no count of the companies with figures said apart in it
  evidence unsplit  l55 (R55, the owner's review of the live R54 decks: FMCG "confirmed 160 (of 160 checked)" was 97 confirmed by their own
               description and 63 kept on their official industry, MedDev 110 + 50): a count said "confirmed" ("confirmed 160", "97 confirmed",
               "12 confirmed companies", "confirmed, with figures") without its evidence states, description-verified and industry-supported,
               named in the same sentence
  evidence counts  l55: the deck's statements of its members by evidence state ("membership checked 160 of 211: 97 description-verified, 63
               industry-supported, 51 not checked", on the findings, data-confidence and coverage pages) that differ from page to page, or
               don't add up (the states to those checked, checked + not checked to the companies); a part of the members (the informative
               layers, "by membership evidence: ...", a layer's "Membership of its 24 companies: ...") with more of a state than the deck's own count of it
  empty page   l55 (the owner's publication preflight: no empty pages): a page that prints its heading and nothing under it
  sparse page  r60b (the owner's review of the live R59 decks: a page of one membership note and the footer): a continuation page
               ("(notes)", "(continued)", ", continued") with SPARSE_MAX lines or fewer under its heading
  history end  h56 (R56, the owner's review of the live R55 Payments deck: "Membership checked 19 of 20 (95%)" beside "Checked share after
               each stored version: 100% (14 Nov 2026) → 100% (14 Nov 2026)"): the "Membership checked" row's checked share after each
               stored version whose last point is not the share of the row's count ("N of M"), or its description-verified share after each
               stored version whose last point is not the share of the "Description-verified N of M" it says just before
  y57 (R57, the full audit of the 24 live R56 decks: counts that contradict across pages, presentation gaps and the P0s a text can show):
  layer counts  a layer page's header "N companies" and its "Membership of its M companies" with M other than N, not said to count the
               companies "stored in all" (Biotech "43 companies" beside "Membership of its 214 companies")
  layer header  a layer page's header that doesn't start with "<N> companies" (FMCG "1 figure is the whole company's ...; 31 in this group")
  pe partition  "P/E of A of the N companies, B loss-makers with none" with A + B more than N (Software 78 + 29 of 100)
  loss-maker profit  an appendix whose P/E note says "none for a loss-maker" over a row with a positive net margin and no P/E (Biotech's
               Gilead at 28.9% net)
  checked counts  two counts of the companies whose membership was checked, of one total, on two pages (Biotech 313 and 423 of 820)
  figures count  the cover's "With figures" count against the appendix's "N companies with figures" with neither said to be core members
               (Payments 14 against 18)
  none screened  "none screened out as another business" in a deck whose change log removes a company on its business membership
  empty table  a layer page that prints its table's heading and no company row (Biotech's largest layer)
  few rows     a layer page that shows fewer than min(5, N) of its N companies ("The largest 1 of 12") with no continuation page after it
  same name    one name said twice where two are meant ("Leslie's, Inc. is Leslie's, Inc."; "IonQ, Inc.; IonQ, Inc." in one list)
  carried log  a change log dated before the deck's own day that doesn't say "no change since" (a log carried from an earlier version)
  reason layer  a removal's or move's reason that names a layer (“X”) the deck has in none of its versions (Payments' “Card issuers and
               lenders” for its “Card issuers and consumer lenders”)
  thin layer   a change log's layer "added (N companies)" with N under 3
  financial margin  r581 (the live R58 Regional banks deck: Fifth Third $80 m, 3152.5%; Huntington 141.5%): a net margin above 100% for a bank,
               lender or insurer (a deck whose theme names banks, lenders, finance or insurance, or a row naming one): its revenue line is
               not its total revenue
  largest left out  the theme's largest company left out of its layer's calculations as another business or for insufficient evidence, or a
               company left out for insufficient evidence whose market value is above every named company in its layer's calculations
  duplicate member  one company in a layer's calculations and left out of them in the same sentence, or two members whose names differ only
               in their legal form ("HFCL Limited" and "HFCL Ltd")
  profile unsaid  m57 (R57, the owner's review of the live R56 decks: "Airlines and travel: limited airline/hotel operating measures";
               Renewable energy's EPC contractors and Payments' processors with no measures of their own): a layer whose name and way of
               earning ("In common: they earn mainly from ...") give it a sector operating profile (airlines, hotels, hospitals, cement,
               power producers, payments processors, contractors paid on orders, property developers) that the deck covers neither on "Each layer on its own
               measures" (its "Operating profiles:" line) nor on a "Sector operating figures" page of that profile; or an "Operating
               profiles:" line saying a layer's measures are none stated on a page that prints no "Not available" line
Reported, and a failure only with --strict:
  cut text     every other text ending in "…" (a label or a sentence cut to its box)
  mixed range  a range with one end whole and the other with a decimal ("19.6% to 20%"; LIVE7A-014)
  other>40%    a theme whose "Other" group holds over 40% of the companies placed, as its coverage says: R44, "In informative layers
               137 of 252 (54%) ... 33 fit none of the map's layers; 82 not checked yet" (gl50: the companies not checked yet counted
               too, every company outside informative layers: the live Biotech deck's 73% passed on its 3% that fit none); before R44, "50
               of 100 companies fit none of the map's layers": a map that places too few of its companies

A PDF that can't be read is a failure of its own (UNREADABLE). A folder with no PDF is read from its .txt files (pdftotext -layout output, pages separated by form feeds), so a saved extract can be
checked again. Standalone: nothing of the app is imported; pdftotext (poppler) must be on the PATH to read PDFs. Exit 2: nothing to read."""
import json
import os
import re
import shutil
import subprocess
import sys

FAIL = ("headline", "mid-word", "placeholder", "joining word", "count", "repeated", "hyphen minus", "no layer", "unread ranked", "unread kind",
        "left out>50%", "unchecked as 0", "biz label", "biz making", "stale layer", "same company", "words claim", "partial unsaid",
        "outlier range", "added unexplained", "verified count", "adjacent ranked", "move unexplained", "scope core", "layer lost unsaid",
        "evidence state", "population mismatch", "identity unresolved", "out of scope in Other", "stage mismatch", "coverage blur",
        "evidence unsplit", "evidence counts", "empty page", "layer vanished", "share fall unsaid", "removal unnamed", "history end",
        "layer counts", "layer header", "pe partition", "loss-maker profit", "checked counts", "figures count", "none screened", "empty table",
        "few rows", "same name", "carried log", "reason layer", "thin layer", "largest left out", "duplicate member", "profile unsaid",
        "removal unbacked", "layer words", "words contradict", "financial margin", "sparse page")
WARN = ("cut text", "other>40%", "mixed range")
# LIVE7A-014: a minus sign as a hyphen before a figure with its unit (never a date's or a range's dash: it follows a space or a bracket)
_HYPHEN_MINUS = re.compile(r"(?:(?<=\s)|(?<=[(\[])|^)-\d[\d,]*(?:\.\d+)?(?:%|x\b| ?pts\b| ?points\b)")
_RANGE = re.compile(r"(?<![\w.,])[−-]?\d[\d,]*(\.\d+)?(%|x\b) to [−-]?\d[\d,]*(\.\d+)?(%|x\b)")
OTHER_MAX = 0.40                # R40: the share of the companies placed that "Other" may hold before the deck is flagged
HEAD_LINES = 6                  # a slide's title and headline are among its first lines (the part's name, the title, up to three lines under it)

_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_CUT_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*…")
_CUT = re.compile(r"([^\s…]*)…")
_WORD_END = re.compile(r"[A-Za-z][A-Za-z'’-]*$")
_JOINING = {"and", "or", "of", "the", "a", "an", "for", "in", "to", "with", "by", "on", "at", "from"}
_PLACEHOLDER = re.compile(r"\{[^{}\n]{0,40}\}?|(?<![A-Za-z] )\bNone\b(?! of| is| has| shows| was| were| are| for)|\b(?:nan|NaN)\b|\bundefined\b|\bshown for [a-z]{1,2}\b(?=[.,;:]|\s*$)")
_N_OF_M = re.compile(r"(?<![\d.,₹$])(\d[\d,]*) of (?:the |its |their |all |these |those )?(\d[\d,]*)(?![\d,]*\.\d)(?!\s?(?:%|x\b|pts\b|bn\b|cr\b|lakh\b|crore\b))")
# "Consumer…" beside "consumers" or "consumer-facing", "Electric…" beside "electrical": a whole word, not a cut one
_ENDINGS = ("", "s", "es", "'s", "’s", "al", "ally", "ity", "ian", "ians", "ic", "ics", "ing", "ed", "er", "ers", "ly")
_COLUMNS = re.compile(r"\S {3,}\S")     # a table's row or two blocks side by side, in pdftotext's layout
# d1: "33 of 252 fit none of the map's layers; 82 not checked yet": the share of those that fit none (the companies not checked yet apart)
_OTHER = re.compile(r"(\d[\d,]*) of (\d[\d,]*)\s+(?:companies\s+)?fit\s+none\s+of\s+the\s+map's\s+layers")
# R44: the coverage's one count of the companies placed, "In informative layers 137 of 252 (54%)", and how many of the rest fit none
_INFORMATIVE = re.compile(r"(?m)^\s*In informative(?: layers)?\b")     # gl50: the label wrapped ("In informative" above "layers": the live Biotech deck)
_INF_COUNT = re.compile(r"(?<![\w.,])(\d[\d,]*) of (\d[\d,]*)(?![\d,])")    # its count, a cell that may wrap above or below the label's line
_FIT_NONE = re.compile(r"(\d[\d,]*)\s+fit\s+none\s+of\s+the\s+map's")     # (the row's text wraps around its label's line)
_APPENDIX = "Every company's figures"
_UNREAD = re.compile(r"no way of earning read|How these layers' companies earn is not read", re.I)
_RANKED = re.compile(r"\b(?:highest|lowest) in [A-Z]")
_KIND = re.compile(r"of the layer's\s+kind")
_IN_CALC = re.compile(r"In the layer's calculations \((\d[\d,]*) of (\d[\d,]*)\)")
_ZERO_NOT_YET = re.compile(r"(\d[\d,]*) of the (\d[\d,]*) checked confirmed by their own description, 0 not yet")
# rv51 (R51): a layer left out of a ranking for its business model ("X (1.3%), a different business model: M (where it is read)")
_BIZ = re.compile(r"(?:(?<=: )|(?<=; ))([^;:]{3,120}?)(?: \([^()]*\))?, a different business model: ([^;()]{3,80}?) \(([^()]{3,160})\)")
# the coverage's "Each layer" row: "companies with figures: A 10 of 10 · B 22 of 22 · ..." (the deck's layer names)
_EACH = re.compile(r"companies with figures: (.+?)(?= Partly read\b| EBITDA margin read\b|$)")
_LAYER_COUNT = re.compile(r"^(.+?) \d[\d,]* of \d[\d,]*$")
_LAYER_COUNT_LEAD = re.compile(r"^([A-Z][^·]{2,120}?) \d[\d,]* of \d[\d,]*\b")
_MAKING_MODEL = re.compile(r"\b(?:parts?|components?|ingredients?|makers?|manufactur\w*|fabricat\w*|foundr\w*)\b", re.I)
_SELLER_NAME = re.compile(r"\b(?:retail\w*|stores?|shops?|chains?|merchants?|clubs?|marketplaces?|platforms?|online|e-?commerce|distribut\w*|"
                          r"wholesal\w*|dealers?|resellers?|services?|outsourc\w*|consult\w*|banks?|lenders?|insurers?|brokers?)\b", re.I)
# the words a layer's name states a model in without naming it (a custom synthesis or CDMO layer's contract making)
_MODEL_NAMED_BY = {"contract manufactur": r"custom synthesis|contract|cdmo|crams|foundr\w*|outsourced|osat|toll",
                   "platforms and marketplaces": r"platforms?|marketplaces?|exchanges?",
                   "parts, component": r"parts|components?|ingredients?|castings?|forgings?|apis?\b|intermediates"}
_BIZ_STOP = {"and", "their", "they", "with", "from", "that", "own", "products", "goods", "other", "others", "the", "for"}
LEFT_MIN = 4                    # gl50: a layer of this many companies or more is flagged when fewer than half are in its calculations
# R40: a word said twice in a row; repeated when the second is lower case or it is a joining word ("The the"), never a name ("Bora Bora")
_TWICE = re.compile(r"\b([A-Za-z]+)(?: (?! )|\n)\1\b", re.I)
_TWICE_JOIN = _JOINING | {"is", "are", "was", "were", "its", "their", "this", "these", "than", "as", "be", "it"}
_TWICE_OK = {"had", "that", "very", "so", "no", "bye", "more", "many", "much", "far", "long"}


# r572 (R57.2, the live R57.1 decks: "Higher-risk growth Since the previous 1 and turnaround private banks", "Identity Since the previous 7 access
# and broad enterprise software (larger)"): a table's left-column label ("Since the previous version") and its count, printed beside a cell of
# running text, are interleaved with that text's lines by pdftotext -layout. A page is read with each such left cell lifted out of the running
# text it sits beside and said before it (its fragments joined by column), so the label is never read into the text
_RUN_MIN = 40                    # a line of running text at least this long, with no columns inside, anchors a right-hand text cell
_LEFT_MAX = 3                    # at most this many lines of left cells between two lines of the running text


def _run_line(line: str, col: int) -> bool:
    body = line[col:].rstrip()
    return len(line) - len(line.lstrip()) == col and len(body) >= _RUN_MIN and not _COLUMNS.search(body)


def reflow(page: str) -> str:
    """The page's lines with each left-column cell beside a block of running text (starting at one column, 20 or more) said before that
    block instead of inside it."""
    lines = page.split("\n")
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        col = len(ln) - len(ln.lstrip()) if ln.strip() else -1
        if col < 20 or not _run_line(ln, col):
            out.append(ln)
            i += 1
            continue
        body, left, pend, j = [ln], {}, [], i + 1
        while j < len(lines):
            nx = lines[j]
            if not nx.strip():
                break
            if _run_line(nx, col) or (len(nx) - len(nx.lstrip()) == col and pend):
                for head, tail in pend:
                    for m in re.finditer(r"\S+(?: \S+)*", head):
                        left.setdefault(m.start(), []).append(m.group(0))
                    if tail:
                        body.append(" " * col + tail)
                pend = []
                body.append(nx)
                j += 1
                continue
            head, tail = nx[:col].ljust(col), nx[col:]
            if len(pend) < _LEFT_MAX and head.strip() and head[-1:] == " " and (not tail.strip() or (not tail[0].isspace() and not _COLUMNS.search(tail.rstrip()))):
                pend.append((head, tail.rstrip()))
                j += 1
                continue
            break
        j -= len(pend)                                   # left cells not followed by more of the text: read as they are
        out.extend(" ".join(left[k]) for k in sorted(left))
        out.extend(body)
        i = j
    return "\n".join(out)


def flat_text(page: str) -> str:
    """A page as one line of text, its left-column cells lifted out of the running text beside them (reflow)."""
    return re.sub(r"\s+", " ", reflow(page))


def _informative_count(page: str, at) -> "re.Match | None":
    """The count of the coverage's "In informative layers" row (R44): in its own column, on the label's line or the line above or below it
    (pdftotext wraps a narrow cell: "137 of 252" above the label, "(54%)" under it), never another row's or the row's text."""
    lines = page.split("\n")
    k = page.count("\n", 0, at.start())
    col = at.start() - (page.rfind("\n", 0, at.start()) + 1)
    for ln in (lines[k], lines[k - 1] if k else "", lines[k + 1] if k + 1 < len(lines) else ""):
        m = _INF_COUNT.search(ln[:col + 50])
        if m:
            return m
    return None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def repeated(text: str) -> list[str]:
    """The words a text says twice in a row (R40): "the the" in any case, one line or two joined by a line break."""
    out = []
    for m in _TWICE.finditer(text):
        w, second = m.group(1), m.group(0)[len(m.group(1)) + 1:]
        if w.lower() in _TWICE_JOIN or (second.islower() and len(w) >= 3 and w.lower() not in _TWICE_OK):
            out.append(m.group(0).replace("\n", " "))
    return out


def pages_of(path: str) -> list[str]:
    """A deck's pages as text: a PDF through pdftotext -layout, a .txt as saved from it."""
    if path.lower().endswith(".pdf"):
        got = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", path, "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            got = f.read()
    pages = got.split("\f")
    return pages[:-1] if len(pages) > 1 and not pages[-1].strip() else pages


def check_pages(pages: list[str]) -> dict:
    """One deck's findings: {"pages": n, "counts": {kind: n}, "findings": [{"kind", "page", "text"}]}."""
    whole = set()                              # every word the deck prints whole, so "equipm…" is told from "Tyre…"
    for p in pages:
        whole |= {w.lower() for w in _WORD.findall(_CUT_WORD.sub(" ", p))}
    findings = []

    def add(kind, page, text):
        findings.append({"kind": kind, "page": page, "text": re.sub(r"\s+", " ", text).strip()[:160]})
    for n, page in enumerate(pages, 1):
        lines = [ln for ln in page.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            flat = ln.strip()
            # R40: on the line, and across the break to the next when both are one block of running text (starting where it starts; not a
            # table's row, columns side by side or another column's cell further along)
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            run = nxt and not _COLUMNS.search(ln) and not _COLUMNS.search(lines[i + 1]) and abs(_indent(ln) - _indent(lines[i + 1])) <= 2
            pair = f"{_WORD_END.search(flat).group(0)}\n{nxt.split(' ', 1)[0]}" if run and _WORD_END.search(flat) else ""
            for w in repeated(flat) + repeated(pair):
                add("repeated", n, f"{w!r} in: {flat}" + (f" / {nxt}" if w in repeated(pair) else ""))
            for m in _PLACEHOLDER.finditer(flat):
                add("placeholder", n, f"{m.group(0)!r} in: {flat}")
            for m in _HYPHEN_MINUS.finditer(flat):
                add("hyphen minus", n, f"{m.group(0)!r} in: {flat}")
            for m in _RANGE.finditer(flat):
                if m.group(2) == m.group(4) and bool(m.group(1)) != bool(m.group(3)):
                    add("mixed range", n, f"{m.group(0)!r} in: {flat}")
            for m in _N_OF_M.finditer(flat):
                a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
                if a > b:
                    add("count", n, f"{m.group(0)!r} in: {flat}")
            if "…" not in flat:
                continue
            head = i < HEAD_LINES and flat.endswith("…") and not _COLUMNS.search(flat)
            if head:
                add("headline", n, flat)
            for m in _CUT.finditer(flat):              # each ellipsis: on a joining word, inside a word, or after a whole one
                word = _WORD_END.search(m.group(1))
                part = word.group(0).lower() if word else ""
                if part in _JOINING or m.group(1).endswith("&"):
                    add("joining word", n, f"{m.group(0)!r} in: {flat}")
                elif part and part not in whole and any(w.startswith(part) and w[len(part):] not in _ENDINGS and w[len(part)].isalpha() for w in whole):
                    add("mid-word", n, f"{m.group(0)!r} in: {flat}")
                elif not (head and m.end() == len(flat)):
                    add("cut text", n, flat)
    for n, page in enumerate(pages, 1):           # d1: the appendix's rows, each in a layer
        if _APPENDIX not in page:
            continue
        col = None
        for ln in page.split("\n"):
            cells = re.split(r"\s{2,}", ln.strip())
            if len(cells) > 2 and cells[0] == "Company" and cells[1] == "Layer":
                col = len(cells)          # a full row has a cell under each heading (a wrapped name's row has one fewer)
                continue
            if col and len(cells) == col and cells[1] == "–" and _indent(ln) <= 2:       # a name wrapped above starts at the layer's column
                add("no layer", n, f"{cells[0]} in: {ln.strip()}")
    for n, page in enumerate(pages, 1):           # R40: the coverage's count of the "Other" group, once a deck
        i = _INFORMATIVE.search(page)
        c = _informative_count(page, i) if i else None
        if c:                                     # R44: read from the coverage's "In informative layers" row
            inf, b = int(c.group(1).replace(",", "")), int(c.group(2).replace(",", ""))
            a = b - inf                           # gl50: every company outside informative layers, the not checked yet too
            if b and a > OTHER_MAX * b:
                add("other>40%", n, f"In informative layers {inf:,} of {b:,} ({round(inf / b * 100)}%); {a:,} outside them ({round(a / b * 100)}%)")
            break
        m = _OTHER.search(page)
        if m:
            a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
            if b and a > OTHER_MAX * b:
                add("other>40%", n, f"{m.group(0)} ({round(a / b * 100)}%)")
            break
    # gl50 (R50): what a classification says, checked from the text
    unread = next((n for n, p in enumerate(pages, 1) if _UNREAD.search(p)), None)
    if unread:
        for n, page in enumerate(pages, 1):
            for ln in page.split("\n"):
                if _RANKED.search(ln) and not _UNREAD.search(ln):
                    add("unread ranked", n, f"{ln.strip()} (no way of earning read: p.{unread})")
                if _KIND.search(ln):
                    add("unread kind", n, f"{ln.strip()} (no way of earning read: p.{unread})")
    for n, page in enumerate(pages, 1):
        flat = flat_text(page)
        for m in _IN_CALC.finditer(flat):
            a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
            if b >= LEFT_MIN and a * 2 < b:
                add("left out>50%", n, flat[m.start():m.start() + 140])
        for m in _ZERO_NOT_YET.finditer(flat):
            add("unchecked as 0", n, m.group(0))
    # rv51 (R51): a business model given as the reason a layer is not ranked is drawn from the layer's own records
    layers = set()
    for page in pages:
        flat = flat_text(page).replace(" Each layer ", " ")
        for m in _EACH.finditer(flat):
            for cell in m.group(1).split(" · "):
                # r572 round 2 (the live R57.1 Public sector banks deck: the row's last cell, "Government-owned infrastructure financiers 2 of
                # 2", runs on into the page's next row): a cell's layer is the words before its first "N of M"
                lm = _LAYER_COUNT.match(cell.strip()) or _LAYER_COUNT_LEAD.match(cell.strip())
                if lm:
                    layers.add(lm.group(1).strip())
    stems_of = lambda t: {w.lower()[:6] for w in _WORD.findall(t) if len(w) >= 4 and w.lower() not in _BIZ_STOP}    # noqa: E731
    seen = set()
    for n, page in enumerate(pages, 1):
        flat = flat_text(page)
        for m in _BIZ.finditer(flat):
            layer, model, where = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            if (layer, model, where) in seen:
                continue
            seen.add((layer, model, where))
            said = f"{layer}: {model} ({where})"
            if _MAKING_MODEL.search(model) and _SELLER_NAME.search(layer) and not _MAKING_MODEL.search(layer):
                add("biz making", n, said)
            if "how its companies earn" in where:
                continue
            quoted = re.search(r"“([^”]+)”", where)
            if "name" in where:
                named = quoted.group(1) if quoted else layer
                by = next((rx for k, rx in _MODEL_NAMED_BY.items() if model.lower().startswith(k)), None)
                if not stems_of(model) & stems_of(named) and not (by and re.search(by, named, re.I)):
                    add("biz label", n, said)
            elif not any(stems_of(model) & stems_of(x) for x in layers | {layer}):
                add("biz label", n, said)
    d53_checks(pages, layers, add)
    c54_checks(pages, layers, add)
    e54_checks(pages, add)
    v55_checks(pages, add)
    l55_checks(pages, add)
    t56_checks(pages, add)
    h56_checks(pages, add)
    y57_checks(pages, add)
    m57_checks(pages, add)
    p57_checks(pages, add)
    financial_checks(pages, add)
    counts = {k: sum(1 for f in findings if f["kind"] == k) for k in FAIL + WARN}
    return {"pages": len(pages), "counts": counts, "findings": findings}


# the labels of a way of earning a layer made by how its companies earn takes (the app's theme_check.MODELS labels that name no kinds)
EARNING_LABELS = {"Project and consulting services", "Managed and outsourced IT services", "Business process outsourcing",
                  "Software products and subscriptions", "Designs licensed for royalties", "Platforms and marketplaces",
                  "Hardware resale and integration", "Distribution and trading", "Retail", "Makers of their own products",
                  "Product designers that outsource making", "Parts, component and ingredient makers", "Contract manufacturing",
                  "Engineering and construction contracts", "Lenders", "Insurers", "Payment networks and processors", "Property and leasing",
                  "Transport and logistics", "Media and content", "Diversified groups", "Resale and distribution", "IT services for clients",
                  "Financial fees and commissions"}
_LAYER_HEAD = re.compile(r"(?m)^\s*Layer \d+ · (.+?)(?:\s*\((?:notes|continued)\))?\s*$")      # r571: a layer's "(notes)" page is the same layer
_SAME_WAY = re.compile(r"earn the same way as those of ((?:“[^”]+”(?:, )?)+)")
_QUOTED = re.compile(r"“([^”]+)”")
_WORDS_CLAIM = "Every company with figures has words of its own"
_NO_WORDS = re.compile(r"No description in its own words yet|no description in their own words yet")
# (l55: "membership checked 160 of 821 (the map's own picks, ...): ..., 661 not checked" as well as the form before it)
_CHECKED = re.compile(r"(?:(\d[\d,]*) checked|membership checked (\d[\d,]*) of [\d,]+) \(the map's own picks.*?(\d[\d,]*) not checked\b")
_CONSIDERED = re.compile(r"(\d[\d,]*) companies \(|(\d[\d,]*) in the exchange's industry list")
_PARTIAL = "A partial map"
_BIG = re.compile(r"(?<![\w.,])[−-](\d[\d,]*(?:\.\d+)?)%|(?<![\w.,−-])(\d[\d,]*(?:\.\d+)?)%")
_RANGE_LINE = re.compile(r"(?:^|\s)(?:Range|range|median|Median)\b|[−-]?\d[\d,]*(?:\.\d+)?% to [−-]?\d")
_ADDED = re.compile(r"added (\d[\d,]*): ([^;.]*(?:\.[^;.\s][^;.]*)*)(?=;|\.(?:\s|$))")
_SOURCES_HEAD = re.compile(r"(\d[\d,]*) checked figures?, (\d[\d,]*) verified(?!, \d)")
_ADJ = re.compile(r"([A-Z][^.;:]{3,90}?) \(\d[^)]*\), adjacent participants")
OUTLIER = 1000.0                # d53: a margin's range or median end beyond this many per cent either way


def _num(t: str) -> float:
    return float(t.replace(",", ""))


def d53_checks(pages: list[str], layers: set, add) -> None:
    """d53 (R53): the checks of the theme's membership, roles and integrity, from the text (see the module's list)."""
    flat_pages = [flat_text(p) for p in pages]
    names = set(layers)
    for p in pages:
        names |= {m.group(1).strip() for m in _LAYER_HEAD.finditer(p)}
    names |= {re.sub(r" \((?:larger|smaller)\)$", "", x) for x in names}
    for n, flat in enumerate(flat_pages, 1):
        for m in _SAME_WAY.finditer(flat):
            for q in _QUOTED.findall(m.group(1)):
                if names and q not in names:
                    add("stale layer", n, f"“{q}” in: {flat[m.start():m.start() + 140]}")
    # the appendix: two rows of one revenue and the three figures after it
    seen: dict = {}
    for n, page in enumerate(pages, 1):
        if _APPENDIX not in page:
            continue
        for ln in page.split("\n"):
            cells = re.split(r"\s{2,}", ln.strip())
            if len(cells) < 7 or cells[0] == "Company":
                continue
            fig = tuple(cells[3:7])
            if not re.search(r"\d", fig[0]) or sum(1 for x in fig if re.search(r"\d", x)) < 3:
                continue
            if fig in seen and seen[fig] != cells[0]:
                add("same company", n, f"{seen[fig]} and {cells[0]}: {' · '.join(fig)}")
            seen.setdefault(fig, cells[0])
    whole = " ".join(flat_pages)
    if _WORDS_CLAIM in whole and _NO_WORDS.search(whole):
        add("words claim", next(n for n, f in enumerate(flat_pages, 1) if _WORDS_CLAIM in f), _NO_WORDS.search(whole).group(0))
    m = _CHECKED.search(whole)
    if m and _PARTIAL not in whole:
        a, gone = _num(m.group(1) or m.group(2)), _num(m.group(3))
        if a * 2 < a + gone:
            add("partial unsaid", next(n for n, f in enumerate(flat_pages, 1) if m.group(0)[:30] in f), m.group(0)[:140])
    for n, page in enumerate(pages, 1):
        for ln in page.split("\n"):
            if not _RANGE_LINE.search(ln):
                continue
            for x in _BIG.finditer(ln):
                v = _num(x.group(1) or x.group(2))
                if v >= OUTLIER:
                    add("outlier range", n, ln.strip()[:140])
                    break
    for n, flat in enumerate(flat_pages, 1):
        for m in _ADDED.finditer(flat):
            if "(" not in m.group(2) and "Since the previous version" in flat:
                add("added unexplained", n, m.group(0)[:140])
        h = _SOURCES_HEAD.search(flat)
        # r572 round 2 (the live R57.1 Restaurants deck: "3 checked figures, 3 verified" over three rows "verified", the page's legend naming
        # the state "arithmetic reproduced: net profit over revenue worked out again"): a row's state, never the legend's
        if h and h.group(1) == h.group(2) and re.search(r"arithmetic reproduced(?!:)", flat):
            add("verified count", n, h.group(0))
    adj = {m.group(1).strip() for f in flat_pages for m in _ADJ.finditer(f)}
    for n, flat in enumerate(flat_pages, 1):
        for m in re.finditer(r"\b(?:highest|lowest) in (.+?) \(", flat):
            if any(m.group(1).strip().endswith(a) or a.endswith(m.group(1).strip()) for a in adj):
                add("adjacent ranked", n, m.group(0))


# c54: a change log's move between layers ("Intel Corp (from “A” to “B”)", or with its reason "(from “A” to “B”: its own words ...)")
_MOVE = re.compile(r"(?:^|, |: )([A-Z0-9][^,;:()“”]{1,80}?) \(from “([^”]+)” to “([^”]+)”(:[^)]*)?\)")
# the groups the split names by how their companies earn (theme_check.MODELS' and FAMILIES' names): a company is in them by its way of earning
BY_HOW = {"Project and consulting services", "Managed and outsourced IT services", "Business process outsourcing", "Software products and subscriptions",
          "Designs licensed for royalties", "Platforms and marketplaces", "Hardware resale and integration", "Distribution and trading", "Retail",
          "Makers of their own products", "Product designers that outsource making", "Parts, component and ingredient makers", "Contract manufacturing",
          "Data centres, hosting and networks", "Telecom and broadband operators", "Engineering and construction contracts", "Lenders", "Insurers",
          "Life insurers", "General and health insurers", "Reinsurers", "Brokers and distributors of financial products", "Fund and asset managers",
          "Exchanges, depositories and ratings", "Payment networks and processors", "Mining, oil, gas and farming", "Power, gas and water supply",
          "Regulated transmission and distribution", "Power generation", "Power trading and renewable project developers",
          "Miners and primary metal producers", "Metal processors and fabricators", "IT services for clients", "Resale and distribution",
          "Financial fees and commissions"}
# a layer named by a business outside most themes (theme_data.SCOPE_KINDS), and the theme names that make it the theme's own
_SCOPE_LAYER = re.compile(r"\b(?:financ\w*|lenders?|lending|banks?|EPC|(?:construction|civil|engineering) contractors?|laborator\w*|labs?|mining|"
                          r"miners?|crude oil|oil(?:,| and) gas|natural gas|oil exploration|farming|growers?)\b", re.I)
_SCOPE_THEME = re.compile(r"bank|lend|loan|credit|financ|nbfc|construct|infrastructure|EPC|engineering|capital goods|laborator|diagnost|hospital|"
                          r"health ?care services|mining|metal|oil|gas|energy|commodit|agri|farm|plantation|fertili|coal|steel|petro|chemical|resource|"
                          r"utilit|power|renewable", re.I)
_TITLE = re.compile(r"THEME DEEP DIVE\s+(.+?)\s{2,}|THEME DEEP DIVE\s*\n\s*(.+)|^\s*(.+)\n.*· Theme deep dive", re.I)
_REMOVED = re.compile(r"“([^”]+)” removed \((\d[\d,]*) compan(?:y|ies)([^)]*)\)(, [a-z][^;.]*)?")
LOST_MIN = 5


def c54_checks(pages: list[str], layers: set, add) -> None:
    """c54 (R53 review): moves without a reason into a layer named by what it sells, a layer outside the theme's own business counted as
    core, and a lost layer with nothing said of it (see the module's list)."""
    flat_pages = [flat_text(p) for p in pages]
    for n, flat in enumerate(flat_pages, 1):
        if "Since the previous version" not in flat and "against the version stored before it" not in flat:
            continue
        for m in _MOVE.finditer(flat):
            to = re.sub(r" \((?:larger|smaller)\)$", "", m.group(3))
            if not m.group(4) and to not in BY_HOW and not to.startswith("Other ") and to != re.sub(r" \((?:larger|smaller)\)$", "", m.group(2)):
                add("move unexplained", n, m.group(0).strip(" ,:")[:160])
        for m in _REMOVED.finditer(flat):
            if _num(m.group(2)) >= LOST_MIN and "to “" not in m.group(3) and not m.group(4):
                add("layer lost unsaid", n, m.group(0)[:160])
    whole = " ".join(flat_pages)
    t = _TITLE.search(pages[0] if pages else "")
    title = (t.group(1) or t.group(2) or t.group(3) or "").strip() if t else ""
    if not title or _SCOPE_THEME.search(title) or re.search(r"Core and adjacent|adjacent participants?", whole, re.I):
        return
    names = set(layers)
    for p in pages:
        names |= {m.group(1).strip() for m in _LAYER_HEAD.finditer(p)}
    for name in sorted(names):
        if _SCOPE_LAYER.search(name):
            add("scope core", 1, f"“{name}” in the {title} deck, which has no “Core and adjacent” row")


# (a table's two columns interleave in the text: the other column's words can fall inside a cell's sentence)
_EV_CHECKED = re.compile(r"(\d[\d,]*) checked\b(?:(?!\d checked).){0,160}?\(the map's own picks[^)]*\):? (\d[\d,]*) confirmed by their own\b")
_EV_L55 = re.compile(r"membership checked (\d[\d,]*) of [\d,]+(?: \((?:[^()]|\([^()]*\))*\))?: (\d[\d,]*) description-verified\b")
_EV_FULL = re.compile(r"(\d[\d,]*) checked: (\d[\d,]*) confirmed by their own\b")
_EV_ALL = re.compile(r"(\d[\d,]*) confirmed by their own\b.{0,80}?\bdescription, (\d[\d,]*) not(?: yet)?\b")
_EV_INDUSTRY = re.compile(r"(\d[\d,]*) kept on their official industry only|(\d[\d,]*) of the [\d,]+ membership-checked are industry-supported")
_EV_LIST = re.compile(r"(\d[\d,]*) kept on the theme's own list only")
_WORDLESS = re.compile(r"(\d[\d,]*) compan(?:y|ies) with figures (?:have|has) no description in\b")
_BY_COUNT = re.compile(r"Companies, by count (\d[\d,]*) of (\d[\d,]*)")
_CORE_ADJ = re.compile(r"(\d[\d,]*) core members \+ (\d[\d,]*) adjacent participants = (\d[\d,]*) with figures")
_EACH_CELL = re.compile(r"^.+? (\d[\d,]*) of \d[\d,]*\b")      # its first count (the next row's or page's text can follow the last cell)


def e54_checks(pages: list[str], add) -> None:
    """e54 (R54): the evidence states and the populations a deck's counts are of, from the text (see the module's list)."""
    flat_pages = [flat_text(p) for p in pages]
    whole = " ".join(flat_pages)
    where = lambda t: next((n for n, f in enumerate(flat_pages, 1) if t in f), 1)      # noqa: E731
    w = _WORDLESS.search(whole)
    wordless = _num(w.group(1)) if w else 0
    m = _EV_CHECKED.search(whole) or _EV_L55.search(whole)
    if m:
        checked, desc = _num(m.group(1)), _num(m.group(2))
    else:
        m = _EV_FULL.search(whole)
        if m:
            checked, desc = _num(m.group(1)), _num(m.group(2))
        else:
            m = _EV_ALL.search(whole)
            checked, desc = ((_num(m.group(1)) + _num(m.group(2))), _num(m.group(1))) if m else (None, None)
    if checked is not None and desc + wordless > checked:
        add("evidence state", where(m.group(0)[:40]), f"{m.group(0)[:110]}; {w.group(0) if w else ''}")
    ind = _EV_INDUSTRY.search(whole)
    if ind and w:
        kept = _num(ind.group(1) or ind.group(2)) + sum(_num(x.group(1)) for x in _EV_LIST.finditer(whole))
        if wordless > kept:
            add("evidence state", where(w.group(0)[:40]), f"{w.group(0)}; {ind.group(0)}")
    for n, flat in enumerate(flat_pages, 1):
        by = _BY_COUNT.search(flat)
        if not by:
            continue
        f2 = flat.replace(" Each layer ", " ")
        got = []
        for e in _EACH.finditer(f2):
            for cell in e.group(1).split(" · "):
                c = _EACH_CELL.match(cell.strip())
                if not c:
                    break
                got.append(_num(c.group(1)))
                if cell.strip()[c.end():].strip():          # the row's last cell: the text after it is another row's or page's
                    break
        if not got:
            continue
        said, sum_ = _num(by.group(1)), sum(got)
        if sum_ == said:
            continue
        ca = _CORE_ADJ.search(f2)
        if ca and _num(ca.group(1)) == said and _num(ca.group(3)) == sum_ and _num(ca.group(1)) + _num(ca.group(2)) == sum_:
            continue
        add("population mismatch", n, f"companies by count {by.group(1)}, the layers' companies with figures add up to {sum_:g}")


_OTHER_WORK_LIST = re.compile(r"whose own words (?:describe other work|don't show the work, left out of every median and total): (.{3,400}?)\.(?=\s+[A-Z(]|\s*$)")
_DEPOSITARY = re.compile(r"\b(?:ADRs?|ADSs?|GDRs?|[Uu]n-?[Ss]pon\w*|[Dd]epositary)\b")
_NOT_YET = "its own words are not confirmed to show the theme's work yet"
# (a kind of product a company's name states, and the words of a theme's title it is of: the app's theme_check.SCOPE_PRODUCTS, by name)
_SCOPE_KINDS = ((r"\b(?:batter(?:y|ies)|torch(?:es)?|flash ?lights?|dry[- ]?cells?)\b",
                 r"batter|electric|energy|auto|vehicle|mobility|power|utilit|semiconductor|electronic|durable|appliance|capital goods|"
                 r"industrial|engineering|renewab|solar|defen"),
                (r"\b(?:cables?|switchgears?|transformers)\b", r"electric|power|energy|utilit|capital goods|industrial|engineering|infrastructure|telecom|"
                 r"auto|construction|defen|renewab|solar|cable|metal"),
                (r"\b(?:steel|ferro ?alloys?|castings|forgings)\b", r"metal|steel|mining|auto|vehicle|capital goods|industrial|engineering|"
                 r"infrastructure|construction|defen|real ?estate|realty|chemical|utilit|power|energy|material"),
                (r"\b(?:cements?)\b", r"cement|building|construction|infrastructure|real ?estate|realty|housing|material"),
                (r"\b(?:tyres?)\b", r"auto|vehicle|mobility|tyre|rubber|capital goods|industrial|engineering|defen|transport"),
                (r"\b(?:fertili[sz]ers?|pesticides?|agrochemicals?)\b", r"agri|farm|crop|fertili|chemical|commodit|seed|plantation"))
_DEV_LAYER = re.compile(r"\bpre-?revenue\b|\bclinical[- ]stage\b|\bdevelopment[- ]stage\b|\bpre-?clinical\b|\bpipeline[- ]stage\b", re.I)
_COM_LAYER = re.compile(r"\bcommercial\b|\blarge\b|\bbig\b|\bestablished\b|\bportfolios?\b|\bmarketed\b|\bspecialty\b|\bmajor\b|\bmature\b", re.I)
_MONEY = re.compile(r"^([$₹])\s?([\d,]+(?:\.\d+)?)\s?(bn|m|cr|k)?$")
_PCT = re.compile(r"^([−-]?\d[\d,]*(?:\.\d+)?)%$")
STAGE_FACTOR, STAGE_FLOOR = 10.0, {"$": 5000.0, "₹": 20000.0}     # v55: $ million / ₹ crore
_NOT_CHECKED_NAMES = re.compile(r"not (?:checked|placed) yet \(([^()]{3,400})\)")          # l55 renamed the Other group's "not checked yet" to "not placed yet"


def _money(cell: str) -> tuple[str, float] | None:
    """("$" or "₹", the amount in $ million or ₹ crore) of a money cell ("$65 bn", "$603 m", "₹4,251 cr"), or None."""
    m = _MONEY.match(cell.strip())
    if not m:
        return None
    x = _num(m.group(2))
    unit = m.group(3) or ""
    if m.group(1) == "$":
        x = x * 1000 if unit == "bn" else x / 1000 if unit == "k" else x
    else:
        x = x * 100000 if unit == "bn" else x
    return m.group(1), x


def v55_checks(pages: list[str], add) -> None:
    """v55 (R55): a company excluded on words never read, an out-of-scope business kept in "Other", a commercial company displayed in a
    development-stage layer, and membership checks said as if they added figures (see the module's list)."""
    flat_pages = [flat_text(p) for p in pages]
    whole = " ".join(flat_pages)
    for n, flat in enumerate(flat_pages, 1):
        for m in _OTHER_WORK_LIST.finditer(flat):
            for name in re.split(r", (?:and \d+ more)?| and \d+ more", m.group(1)):
                name = name.strip(" .")
                if len(name) < 3:
                    continue
                said_not_yet = any(_NOT_YET in whole[i:i + 400] for i in [j.start() for j in re.finditer(re.escape(name), whole)])
                if _DEPOSITARY.search(name) or said_not_yet:
                    add("identity unresolved", n, f"{name}: listed as describing other work" + (" (a depositary-receipt line)" if _DEPOSITARY.search(name)
                                                                                               else f"; elsewhere: “{_NOT_YET}”"))
    t = _TITLE.search(pages[0] if pages else "")
    title = (t.group(1) or t.group(2) or t.group(3) or "").strip() if t else ""
    unchecked = {x.strip(" .") for m in _NOT_CHECKED_NAMES.finditer(whole) for x in re.split(r", | and \d+ more", m.group(1))}
    rows: dict = {}
    for n, page in enumerate(pages, 1):
        for ln in page.split("\n"):
            cells = [c for c in re.split(r"\s{2,}", ln.strip()) if c]
            if len(cells) < 6:
                continue
            name, layer = cells[0], cells[1]
            if title and layer.startswith("Other ") and any(re.search(k, name, re.I) and not re.search(t_, title, re.I) for k, t_ in _SCOPE_KINDS) \
                    and not any(name.startswith(u) or u.startswith(re.sub(r" (?:Ltd|Limited|Inc\.?|Corp\.?)$", "", name)) for u in unchecked):
                add("out of scope in Other", n, f"{name} in “{layer}” of the {title} deck")
            if _DEV_LAYER.search(layer) and not _COM_LAYER.search(layer):
                rev, ebitda = _money(cells[3]), _PCT.match(cells[5].strip())
                if rev:
                    rows.setdefault(layer, []).append((n, name, rev, _num(ebitda.group(1).replace("−", "-")) if ebitda else None))
    for layer, rs in rows.items():
        young = sorted(r[2][1] for r in rs if r[3] is not None and r[3] <= 0)
        mid = young[len(young) // 2] if len(young) >= 2 else None      # (with fewer than two developers shown, the floor alone)
        for n, name, (cur, rev), e in rs:
            if e is not None and e > 0 and rev >= STAGE_FLOOR[cur] and (mid is None or rev >= STAGE_FACTOR * mid):
                add("stage mismatch", n, f"{name} in “{layer}”: revenue {cur}{rev:,.0f}{' m' if cur == '$' else ' cr'}, EBITDA margin {e:g}%"
                                         + (f", the layer's median developer's {cur}{mid:,.0f}" if mid else ""))
    for n, flat in enumerate(flat_pages, 1):
        i = flat.find("Membership checked")
        if i < 0:
            continue
        row = flat[i:i + 1600]
        if "Checked share after each stored version" in row and "→" in row and not re.search(r"with figures|figures are worked out", row):
            add("coverage blur", n, row[:160])


# l55 (R55): a count said "confirmed" (one undifferentiated total): "confirmed 160 (of 160 checked)", "97 confirmed by their own
# description", "12 confirmed companies", "confirmed, with figures (...) 93", "eligible for each metric (confirmed, with the figure)"
_UNSPLIT = re.compile(r"(?<![Nn]ot )(?<![Nn]ot yet )\bconfirmed (?:\(of )?\d|(?<![\d,.])\d[\d,]* (?:of the \d[\d,]* added are )?confirmed\b(?! in the theme)|"
                      r"\bconfirmed,? with (?:figures|the figure)\b|\b\d[\d,]* confirmed compan", re.I)
_STATES_NAMED = re.compile(r"description-verified.{0,120}?industry-supported")
# the members by evidence state: the deck's own statement, or a part of it ("by membership evidence: ...", "Membership evidence of ...")
_EV_TRIPLE = re.compile(r"(\d[\d,]*) description-verified, (\d[\d,]*) industry-supported(?:, (\d[\d,]*) list-supported)?"
                        r"(?:, (\d[\d,]*) (?:whose )?own words describe other work)?, (\d[\d,]*) not checked\b")
_EV_HEAD = re.compile(r"membership checked (\d[\d,]*) of (\d[\d,]*)(?: \((?:[^()]|\([^()]*\))*\))?: $")
_PART_HEAD = re.compile(r"(?:by membership evidence|[Mm]embership (?:evidence )?of [^:]{0,90}): $")
_FOOTER = re.compile(r"Not investment advice|Theme deep dive · \d")
EMPTY_MAX = 3                   # l55: a page's eyebrow, title and headline, and nothing else
# r60b (R60, the owner's review of the live R59 decks: Medical devices p.27 and Restaurants p.22 held one membership note and the footer):
# a continuation page ("(notes)", "(continued)", ", continued") with this many lines or fewer under its heading is a sparse page
SPARSE_MAX = 2
_CONT_TITLE = re.compile(r"\((?:notes|continued)\)|, continued\b")


def l55_checks(pages: list[str], add) -> None:
    """l55 (R55): every count of the theme's members by evidence state, the same on every page, and no empty page (see the module's list)."""
    flat_pages = [flat_text(p) for p in pages]
    whole: list = []                    # (page, (description-verified, industry-, list-supported, other work, not checked), checked, of)
    parts: list = []
    for n, flat in enumerate(flat_pages, 1):
        for m in _UNSPLIT.finditer(flat):
            near = flat[max(0, m.start() - 160):m.end() + 200]
            if not _STATES_NAMED.search(near):
                add("evidence unsplit", n, flat[max(0, m.start() - 40):m.end() + 60])
        for m in _EV_TRIPLE.finditer(flat):
            got = tuple(_num(m.group(k)) if m.group(k) else 0 for k in range(1, 6))
            before = flat[max(0, m.start() - 200):m.start()]
            if _PART_HEAD.search(before):
                parts.append((n, got, m.group(0)))
                continue
            h = _EV_HEAD.search(before)
            whole.append((n, got, _num(h.group(1)) if h else None, _num(h.group(2)) if h else None, m.group(0)))
    seen = None
    for n, got, chk, of, text in whole:
        if chk is not None and (sum(got[:4]) != chk or chk + got[4] != of):
            add("evidence counts", n, f"{text}: the states make {sum(got[:4]):g} of {chk:g} checked, with those not checked {chk + got[4]:g} of {of:g}")
        if seen is None:
            seen = (n, got)
        elif got != seen[1]:
            add("evidence counts", n, f"{text}; p.{seen[0]} says " + ", ".join(f"{x:g}" for x in seen[1]))
    if seen:
        for n, got, text in parts:
            if any(a > b for a, b in zip(got, seen[1])):
                add("evidence counts", n, f"{text}: more of a state than the deck's {', '.join(f'{x:g}' for x in seen[1])} (p.{seen[0]})")
    for n, page in enumerate(pages, 1):
        lines = [ln for ln in page.split("\n") if ln.strip() and not _FOOTER.search(ln)]
        if page.strip() and _FOOTER.search(page) and len(lines) <= EMPTY_MAX:
            add("empty page", n, " / ".join(ln.strip() for ln in lines)[:140] or "(nothing but the footer)")
        elif page.strip() and _FOOTER.search(page) and len(lines) <= EMPTY_MAX + SPARSE_MAX and \
                any(_CONT_TITLE.search(ln) for ln in lines[:EMPTY_MAX]):
            add("sparse page", n, " / ".join(ln.strip() for ln in lines)[:140])


# t56 (R55): an established layer gone with no restore or reason; a fall in the informative share said with no reason; a removal from the
# theme with no named reason
_GONE_LINE = re.compile(r"gone, their companies taken by no new layer: (.+?)\.(?: [A-Z]|$)")
_GONE_ITEM = re.compile(r"“([^”]+)” \((\d[\d,]*) companies([^;)]*)(;[^)]*)?\)")
_REASON_OF = re.compile(r"of its (\d[\d,]*) companies")
_FALL = re.compile(r"in the previous live placement: (\d+) points\b")
_REMOVED_LIST = re.compile(r"\bremoved (?:for a listing reason )?(\d[\d,]*): (.+?)(?=; (?:moved|added|removed|layers changed)\b|\.\s*$|\. [A-Z]|$)")
_NAMED_REASON = re.compile(r"business membership: |listing: |another business|the same company as|outside the theme's definition|"
                           r"no figures stored for it|filed under", re.I)
FALL_MIN = 5


def _top_items(text: str) -> list[str]:
    """A list's items split at "; " outside brackets."""
    out, depth, cur = [], 0, ""
    for i, ch in enumerate(text):
        depth += (ch == "(") - (ch == ")")
        if ch == ";" and depth <= 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    return [x for x in out + [cur.strip()] if x]


def _last_paren(item: str) -> str:
    """The bracket an item ends with (its reason), "" when it ends with none."""
    s = item.rstrip(" .,")
    if not s.endswith(")"):
        return ""
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        depth += (s[i] == ")") - (s[i] == "(")
        if depth == 0:
            return s[i + 1:-1]
    return ""


def t56_checks(pages: list[str], add) -> None:
    """t56 (R55, the owner's review of the live R55 decks: Metals lost its 13-company "Aluminium" layer and Consumer retail its "Catalog and
    mail-order houses" with nothing restored, informative 52 of 66 to 39 of 66; Adyen's ADR "removed ... (no longer in the theme's map)"):
      layer vanished     a removed layer of five companies or more (the change log's "“X” removed (N companies ...)", or the coverage flag's
                         "Layers ... gone ...: “X” (N companies ...)") with no restore and no reason, or with a reason counting another
                         number of its companies than were removed ("none restored: 0 of its 5" for 6 removed)
      share fall unsaid  "N points fewer" in the informative share, N of five or more, with no "Why:" said beside it
      removal unnamed    a company removed from the theme (the change log's "removed N: ...") whose reason names neither a listing nor a
                         business-membership decision ("no longer in the theme's map", or none)"""
    flat_pages = [flat_text(p) for p in pages]
    for n, flat in enumerate(flat_pages, 1):
        for m in _REMOVED.finditer(flat):
            k = _num(m.group(2))
            why = m.group(4) or ""
            r = _REASON_OF.search(why)
            if k >= LOST_MIN and (not why or (r and _num(r.group(1)) != k and "restored:" in why and not why.startswith(", restored"))):
                add("layer vanished", n, m.group(0)[:200])
        for g in _GONE_LINE.finditer(flat):
            for m in _GONE_ITEM.finditer(g.group(1)):
                if _num(m.group(2)) >= LOST_MIN and not m.group(4):
                    add("layer vanished", n, m.group(0)[:200])
        for m in _FALL.finditer(flat):
            if int(m.group(1)) >= FALL_MIN and "Why:" not in flat[m.end():m.end() + 400]:
                add("share fall unsaid", n, flat[max(0, m.start() - 120):m.end()][:220])
        if "Since the previous version" not in flat and "against the version stored before it" not in flat:
            continue
        for m in _REMOVED_LIST.finditer(flat):
            listing = m.group(0).startswith("removed for a listing reason")          # its heading names the kind: each item its reason
            for it in _top_items(m.group(2)):
                if not (_NAMED_REASON.search(_last_paren(it)) or (listing and _last_paren(it).strip())):
                    add("removal unnamed", n, it[:200])


# h56 (R56): a coverage row's history ("Checked share after each stored version: 64% (07 Nov 2026) → 88% (14 Nov 2026)"; the columns of a
# PDF's table may put the row's label and count inside the phrase) and the row's own count ("19 of 20 (95%)", a cell of its own)
_HIST = {"Membership checked": re.compile(r"Checked share after each stored\b"),
         "Description-verified": re.compile(r"description-verified share after each stored\b")}
_DV_SAID = re.compile(r"Description-verified (\d[\d,]*) of (\d[\d,]*)\b")
_HIST_POINT = re.compile(r"(\d{1,3})% \((\d{2} [A-Z][a-z]{2} \d{4})\)")
_HIST_END = re.compile(r"\)\.(?:\s|$)")
_ROW_COUNT = re.compile(r"^(\d[\d,]*) of (\d[\d,]*)(?: \(\d{1,3}%\))?$")


def h56_checks(pages: list[str], add) -> None:
    """h56 (R56): a coverage row's history ends on the share the row states (see the module's list)."""
    for n, page in enumerate(pages, 1):
        lines = page.split("\n")
        flat = flat_text(page)
        for label, rx in _HIST.items():
            m = rx.search(flat)
            if not m:
                continue
            tail = flat[m.end():m.end() + 700]
            end = _HIST_END.search(tail)
            points = _HIST_POINT.findall(tail[:end.end()] if end else tail)
            if not points:
                continue
            if label == "Description-verified":          # (said in the row's own words, just before its history)
                said = list(_DV_SAID.finditer(flat[max(0, m.start() - 300):m.start()]))
                if said:
                    _end_check(add, n, "", said[-1], points)
                continue
            at = [i for i, ln in enumerate(lines) if [c for c in re.split(r"\s{2,}", ln.strip()) if c][:1] == [label]]
            if not at:
                continue
            best = None              # the row's count: the "N of M" cell on the label's line or the nearest line by it
            for i in sorted(range(max(0, at[0] - 3), min(len(lines), at[0] + 4)), key=lambda j: abs(j - at[0])):
                for c in re.split(r"\s{2,}", lines[i].strip()):
                    hit = _ROW_COUNT.match(c)
                    if hit:
                        best = hit
                        break
                if best:
                    break
            if best:
                _end_check(add, n, label, best, points)


def _end_check(add, n: int, label: str, count, points) -> None:
    """h56: the history's last point against the share of the row's count ("N of M")."""
    a, b = _num(count.group(1)), _num(count.group(2))
    if not b:
        return
    share = round(a * 100 / b)
    share = 99 if share == 100 and a < b else share          # (the deck never says 100% while one is short of the whole)
    if int(points[-1][0]) != share:
        add("history end", n, f"{label} {count.group(0)}".strip() + f": its share after each stored version ends on {points[-1][0]}% ({points[-1][1]})")


# y57 (R57): the full audit of the 24 live R56 decks (see the module's list)
_LAYER_TOP = re.compile(r"^\s*Layer \d+ · (.+?)\s*$")
_HEAD_COUNT = re.compile(r"^(\d[\d,]*) compan(?:y|ies)\b")
_MEMBERSHIP_OF = re.compile(r"Membership of its (\d[\d,]*) compan(?:y|ies)\b([^:]{0,90}):")
_PE_SPLIT = re.compile(r"P/E of (\d[\d,]*) of the (\d[\d,]*) companies, (\d[\d,]*) loss-makers? with none")
_CHECKED_N = re.compile(r"[Mm]embership checked (\d[\d,]*) of (\d[\d,]*)\b|\bchecked for (\d[\d,]*) of the theme's (\d[\d,]*)\b")
_APX_WITH = re.compile(r"(\d[\d,]*) companies with figures([^;]{0,160}?), one row each")
_NONE_SCREENED = "none screened out as another business"
_REMOVED_BIZ = re.compile(r"\bremoved \d[\d,]*: [^.;]{0,200}?\(business membership:")
_SHOWN_OF = re.compile(r"The (?:first|largest) (\d[\d,]*) of (\d[\d,]*)\b")
_TABLE_END = re.compile(r"^\s*(?:Median\b|Range\b|The (?:first|largest) \d|In the layer's calculations|Membership of its|StratLab ·)")
_ROW_FIG = re.compile(r"(?:^|\s)(?:[−-]?\d[\d,]*(?:\.\d+)?(?:%|x)|[$₹]\s?[\d,.]+(?: lakh)?(?: ?(?:bn|m|cr|k))?|–|[A-Z][a-z]{2} \d{4})(?:\s|$)")
_IS_SELF = re.compile(r"(?<![\w'’])([A-Z][\w.,&'’ -]{2,70}?) is \1(?=[;.,]?(?:\s|$))")
_LIST_TWICE = re.compile(r"(?:: |; )([A-Z][^;:]{2,60}?); \1(?=;|\.|,| and \d|$)")
_DECK_DAY = re.compile(r"Theme deep dive · (\d{1,2} [A-Z][a-z]{2} \d{4})")
_LOG_DAY = re.compile(r"On (\d{1,2} [A-Z][a-z]{2} \d{4})(, the latest change \(no change since\))?, against the version stored before it")
_WORK_OF = re.compile(r"(?:don't show the work of|show it is of|not the work of|the work of) “([^”]+)”")
_LAYER_SAID = re.compile(r"“([^”]+)” (?:renamed|removed|added|split|merged)|renamed “([^”]+)”|from “([^”]+)” to “([^”]+)”|from “([^”]+)”\)|into “([^”]+)”")
_ADDED_LAYER = re.compile(r"“([^”]+)” added \((\d[\d,]*) compan(?:y|ies)\)")
_LARGEST = re.compile(r"; (.{3,80}?) is the largest at ")
_ROLL = re.compile(r"In the layer's calculations \((\d[\d,]*) of (\d[\d,]*)\): (.*?)\. Left out \((\d[\d,]*)\): (.*?)\.(?= Every one| Membership| [A-Z(]|$)")
_MV = re.compile(r"^([$₹])\s?([\d,]+(?:\.\d+)?)\s?(lakh cr|bn|m|cr|k)?$")
_LEGAL_WORDS = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "llc", "lp", "nv", "sa", "ag", "se", "the",
                "and"}
_DAY_ORDER = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}


def _day_key(d: str) -> tuple:
    dd, mon, yy = d.split()
    return int(yy), _DAY_ORDER.get(mon, 0), int(dd)


def _name_key(name: str) -> tuple:
    """A company's name with its legal form, punctuation and "&"/"and" left off: "HFCL Limited" and "HFCL Ltd" are one."""
    words = re.sub(r"[^a-z0-9]+", " ", name.lower().replace("&", " ")).split()
    return tuple(w for w in words if w not in _LEGAL_WORDS)


def _same_co(a: tuple, b: tuple) -> bool:
    """Two name keys of one company: one the start of the other (a roll's short name, "Eli Lilly", of "Eli Lilly & Co")."""
    if not a or not b:
        return False
    k = min(len(a), len(b))
    return a[:k] == b[:k] and (k >= 2 or len(a) == len(b) == 1)


def _mv(cell: str) -> float | None:
    """A market value cell in $ million or ₹ crore ("$1,358 bn", "₹4.13 lakh cr", "₹28,053 cr")."""
    m = _MV.match(cell.strip())
    if not m:
        return None
    x, u = _num(m.group(2)), m.group(3) or ""
    return x * 100000 if u == "lakh cr" else x * 1000 if u == "bn" else x / 1000 if u == "k" else x


def _roll_names(text: str) -> list[str]:
    """The names a roll's part lists ("A, B (partial: ...) and 3 more; C"), each reason before its names dropped."""
    out = []
    for part in _top_items(text):
        part = re.sub(r"^[a-z][^:]*: ", "", part)                       # "another business: ...", "insufficient evidence (...): ..."
        depth, cur = 0, ""
        for ch in part:
            depth += (ch == "(") - (ch == ")")
            if ch == "," and depth == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
        out.append(cur)
    names = []
    for x in out:
        x = re.sub(r"\([^()]*(?:\([^()]*\)[^()]*)*\)", "", x)
        x = re.sub(r" and \d[\d,]* more$", "", x.strip()).strip(" .")
        if x and not re.match(r"^(?:and )?\d[\d,]* more$", x):
            names.append(x)
    return names


def _appendix_values(pages: list[str]) -> dict:
    """{name key: market value} of the appendix's rows (the first money cell after the company's name)."""
    got = {}
    for page in pages:
        if _APPENDIX not in page:
            continue
        for ln in page.split("\n"):
            if _indent(ln) > 2:
                continue
            cells = [c for c in re.split(r"\s{2,}", ln.strip()) if c]
            if len(cells) < 4 or cells[0] == "Company":
                continue
            v = next((_mv(c) for c in cells[1:4] if _mv(c) is not None), None)
            if v is not None:
                got.setdefault(_name_key(cells[0]), v)
    return got


def _value_of(key: tuple, values: dict) -> float | None:
    return next((v for k, v in values.items() if _same_co(key, k)), None)


def y57_checks(pages: list[str], add) -> None:
    """y57 (R57, the full audit of the 24 live R56 decks): see the module's list."""
    flat_pages = [flat_text(p) for p in pages]
    whole = " ".join(flat_pages)
    for n, page in enumerate(pages, 1):
        lines = [ln for ln in page.split("\n") if ln.strip()]
        top = next((i for i, ln in enumerate(lines) if _LAYER_TOP.match(ln)), None)
        if top is None:
            continue
        layer = _LAYER_TOP.match(lines[top]).group(1)
        if layer.endswith(("(continued)", "(notes)")):     # a layer page's notes: its header and table are on the page before
            continue
        head = lines[top + 1].strip() if top + 1 < len(lines) else ""
        hc = _HEAD_COUNT.match(head)
        if not hc:
            add("layer header", n, f"{layer}: {head[:120]}")
        flat = flat_pages[n - 1]
        mo = _MEMBERSHIP_OF.search(flat)
        if hc and mo and _num(mo.group(1)) != _num(hc.group(1)) and "stored in all" not in mo.group(2):
            add("layer counts", n, f"{layer}: “{hc.group(0)}” beside “Membership of its {mo.group(1)} companies”")
        # the table: its heading's line, then its rows until the median, the shown line or the notes
        at = next((i for i, ln in enumerate(lines) if i > top and re.match(r"^\s*Company\s{2,}\S", ln)), None)
        if at is not None:
            rows = 0
            for ln in lines[at + 1:]:
                if _TABLE_END.match(ln):
                    break
                cells = [c for c in re.split(r"\s{2,}", ln.strip()) if c]
                if len(cells) >= 3 and len(_ROW_FIG.findall(" " + "  ".join(cells[1:]) + " ")) >= 2:
                    rows += 1
            if rows == 0:
                add("empty table", n, f"{layer}: its table's heading and no company row")
        so = _SHOWN_OF.search(flat)
        nxt = flat_pages[n] if n < len(flat_pages) else ""
        if so and _num(so.group(1)) < min(5, _num(so.group(2))) and not (layer in nxt[:300] and "(continued)" in nxt[:300]):      # (a notes page shows no row)
            add("few rows", n, f"{layer}: {so.group(0)}")
    for n, flat in enumerate(flat_pages, 1):
        for m in _PE_SPLIT.finditer(flat):
            if _num(m.group(1)) + _num(m.group(3)) > _num(m.group(2)):
                add("pe partition", n, m.group(0))
        for m in _IS_SELF.finditer(flat):
            add("same name", n, m.group(0).strip(":;. "))
        for m in _LIST_TWICE.finditer(flat):
            add("same name", n, m.group(0).strip(":;. "))
    # the appendix's P/E note against its rows: a profitable row with no P/E is no loss-maker
    for n, page in enumerate(pages, 1):
        if _APPENDIX not in page or "none for a loss-maker" not in flat_pages[n - 1]:
            continue
        right = None
        for ln in page.split("\n"):
            cells = [c for c in re.split(r"\s{2,}", ln.strip()) if c]
            if "P/E" in cells and "Net" in cells:
                right = cells[cells.index("Net"):]
                continue
            if not right or len(cells) < len(right) + 2 or _indent(ln) > 2:
                continue
            got = dict(zip(right, cells[-len(right):]))
            net = _PCT.match(got.get("Net", "").replace("†", "").replace("‡", ""))
            if net and _num(net.group(1).replace("−", "-")) > 0 and got.get("P/E") == "–":
                add("loss-maker profit", n, f"{cells[0]}: net margin {got['Net']}, no P/E, under “none for a loss-maker”")
    # one count of the companies whose membership was checked
    seen: dict = {}
    for n, flat in enumerate(flat_pages, 1):
        for m in _CHECKED_N.finditer(flat):
            a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            seen.setdefault(_num(b), {}).setdefault(_num(a), n)
    for b, by in seen.items():
        if len(by) > 1:
            (a1, p1), (a2, p2) = sorted(by.items(), key=lambda x: x[1])[:2]
            add("checked counts", p2, f"membership checked {a2:g} of {b:g} (p.{p2}) against {a1:g} of {b:g} (p.{p1})")
    # the cover's companies with figures against the appendix's
    cover = None
    if pages:
        cl = pages[0].split("\n")
        for i, ln in enumerate(cl):
            x = ln.find("With figures")
            if x < 0:
                continue
            for ln2 in cl[i + 1:i + 4]:
                m = re.compile(r"\d[\d,]*").search(ln2, max(0, x - 4))
                if m and m.start() <= x + 12:
                    cover = (_num(m.group(0)), "core" in ln + " ".join(cl[i + 1:i + 6]))
                    break
            break
    apx = next(((n, m) for n, f in enumerate(flat_pages, 1) for m in [_APX_WITH.search(f)] if m and _APPENDIX in f), None)
    if cover and apx and cover[0] != _num(apx[1].group(1)) and not cover[1] and "core" not in (apx[1].group(2) or ""):
        add("figures count", apx[0], f"cover “With figures {cover[0]:g}” against “{apx[1].group(0)}”")
    if _NONE_SCREENED in whole and _REMOVED_BIZ.search(whole) and "removed by the membership re-check" not in whole:
        n = next(i for i, f in enumerate(flat_pages, 1) if _NONE_SCREENED in f)
        add("none screened", n, f"“{_NONE_SCREENED}” beside “{_REMOVED_BIZ.search(whole).group(0)[:100]}”")
    # the change log: its day, the layers its reasons name, the layers it adds
    dd = _DECK_DAY.search(whole)
    for n, flat in enumerate(flat_pages, 1):
        for m in _LOG_DAY.finditer(flat):
            if dd and _day_key(m.group(1)) < _day_key(dd.group(1)) and not m.group(2):
                add("carried log", n, f"a change log of {m.group(1)} in a deck of {dd.group(1)}, not said to be carried")
        for m in _ADDED_LAYER.finditer(flat):
            if _num(m.group(2)) < 3:
                add("thin layer", n, m.group(0))
    names = set()
    for p in pages:
        names |= {re.sub(r" \((?:continued|notes)\)$", "", m.group(1).strip()) for ln in p.split("\n") for m in [_LAYER_TOP.match(ln)] if m}
    for f in flat_pages:
        for m in _LAYER_SAID.finditer(f):
            names |= {g for g in m.groups() if g}
        for e in _EACH.finditer(f.replace(" Each layer ", " ")):
            for cell in e.group(1).split(" · "):
                lm = _LAYER_COUNT.match(cell.strip())
                if lm:
                    names.add(lm.group(1).strip())
    names |= {re.sub(r" \((?:larger|smaller)\)$", "", x) for x in names}
    for n, flat in enumerate(flat_pages, 1):
        for m in _WORK_OF.finditer(flat):
            q = re.sub(r" \((?:larger|smaller)\)$", "", m.group(1))
            if names and q not in names and not any(x.startswith(q) for x in names):
                add("reason layer", n, f"“{m.group(1)}”, a layer the deck has in none of its versions: {flat[max(0, m.start() - 100):m.end()]}"[:200])
    # who is left out of a layer's calculations against the theme's largest company and the layer's own
    values = _appendix_values(pages)
    big = _LARGEST.search(whole)
    big_key = _name_key(big.group(1)) if big else ()
    for n, flat in enumerate(flat_pages, 1):
        for m in _ROLL.finditer(flat):
            ins = [_name_key(x) for x in _roll_names(m.group(3))]
            out_part = m.group(5)
            for item in _top_items(out_part):
                kind = item.split(":", 1)[0]
                for name in _roll_names(item):
                    k = _name_key(name)
                    if any(_same_co(k, i) for i in ins):
                        add("duplicate member", n, f"{name}: in the layer's calculations and left out ({kind}) in one sentence")
                        continue
                    if kind.startswith(("another business", "insufficient evidence")) and _same_co(k, big_key):
                        add("largest left out", n, f"{name}, the theme's largest company, left out: {kind}")
                        continue
                    if kind.startswith("insufficient evidence"):
                        mine, theirs = _value_of(k, values), [v for v in (_value_of(i, values) for i in ins) if v is not None]
                        if mine is not None and theirs and mine > max(theirs):
                            add("largest left out", n, f"{name} (market value above every named company in the layer's calculations) left out: {kind}")
    # two members whose names differ only in their legal form
    rows: dict = {}
    for n, page in enumerate(pages, 1):
        if _APPENDIX not in page:
            continue
        for ln in page.split("\n"):
            cells = [c for c in re.split(r"\s{2,}", ln.strip()) if c]
            if len(cells) >= 4 and cells[0] != "Company" and _indent(ln) <= 2 and any(_mv(c) is not None for c in cells[1:4]):
                rows.setdefault(_name_key(cells[0]), set()).add((cells[0], n))
    for k, got in rows.items():
        named = sorted({nm for nm, _ in got})
        if k and len(named) > 1:
            add("duplicate member", min(p for _, p in got), f"{' and '.join(named)}: one name but for its legal form, on two rows")
# m57 (R57): the sector operating profiles a layer's name and way of earning give it (app/intel/sector_ops.PROFILES, as decks print them): its
# name's words, the words of how it earns ("In common: they earn mainly from ..."), and the "Sector operating figures: <x>" page of the profile
PROFILE_HINTS = (
    ("airlines", r"\bairlines?\b|air charter|air carriers?", ("moving and storing goods or people",)),
    ("hotel operators", r"\bhotels?\b|\bresorts?\b", ("stays, trips, meals or courses", "rent and leases on property")),
    ("hospital operators", r"\bhospitals?\b|multi-?specialty|super-?specialty", ("fees for care, treatment and tests",)),
    ("cement makers", r"\bcement\b", ("finished products of their own", "selling products of their own", "parts, components or ingredients")),
    ("power producers", r"\bpower\b|generation|generators?|renewable (?:power|energy) (?:producers|developers)|\bhydro|thermal",
     ("selling the power their own plants generate", "developing, selling or running renewable projects")),
    ("payments companies", r".", ("fees on the value or number of payments they process",)),
    ("contractors and equipment makers", r"\bEPC\b|contractors?\b|\bconstruction\b|engineering",
     ("contracts to design and build projects for clients",)),
    ("property developers", r"develop|residential|homes|housing", ("selling homes, offices and plots they build",)),
)
_LAYER_PAGE = re.compile(r"^\s*Layer \d+ · (.+?)\s*$", re.M)
_EARNS = re.compile(r"In common: they earn mainly from (.+?)\.")
_PROFILES_LINE = re.compile(r"Operating profiles: (.+?)\.(?: Its last column| Not in this|$)")
LAYER_PROFILE_PAGE = "Each layer on its own measures"


def m57_checks(pages: list[str], add) -> None:
    """m57 (R57): every layer with a sector operating profile prints its measures or says they aren't available (see the module's list)."""
    flats = [flat_text(p) for p in pages]
    said, paged, nots = {}, set(), 0
    for n, (page, flat) in enumerate(zip(pages, flats), 1):
        head = "\n".join(page.split("\n")[:6])
        if LAYER_PROFILE_PAGE in head:
            nots += flat.count("Not available:")
            for m in _PROFILES_LINE.finditer(flat):
                for item in m.group(1).split("; "):
                    name, _, rest = item.partition(": ")
                    said[name.rsplit(", ", 1)[0].strip().lower()] = rest          # (the note repeats on each page of the table)
        for many, _, _ in PROFILE_HINTS:
            if re.search(r"Sector operating figures: " + re.escape(many) + r"\b", head):
                paged.add(many)
    for n, (page, flat) in enumerate(zip(pages, flats), 1):
        lm = _LAYER_PAGE.search("\n".join(page.split("\n")[:6]))
        em = _EARNS.search(flat)
        if not lm or not em:
            continue
        # r572 round 2: a layer's notes or continued page is that layer's (the offline R57.2 Real estate deck: "Residential developers
        # (larger) (notes)" read as a layer of its own)
        name, earns = re.sub(r" \((?:notes|continued)\)$", "", lm.group(1).strip()), em.group(1)
        for many, name_rx, ways in PROFILE_HINTS:
            if not any(w in earns for w in ways) or not re.search(name_rx, name, re.I):
                continue
            if name.lower() not in said and many not in paged:
                add("profile unsaid", n, f"{name}: a layer of {many} with none of its operating measures and no line saying they aren't available")
            break
    none_said = sum(1 for rest in said.values() if rest.startswith("none of its"))
    if none_said > nots:
        add("profile unsaid", 0, f"{none_said} layers said to state none of their operating measures, {nots} \"Not available\" lines printed")
# p57 (R56, the owner's review: Capital One "removed ... its own words don't show the work of “Card issuers and lenders”", Sarepta removed on
# "“Commercial specialty biotechs”", neither a layer the deck has; Duolingo, a language-course app, alone in "Hotels, travel and consumer
# services"): the placement contract read from a deck's text
_PLAIN_NAME = {"and", "the", "of", "for", "with", "other", "company", "companies", "provider", "providers", "maker", "makers", "supplier",
               "suppliers", "product", "products", "service", "services", "business", "businesses", "own", "their", "large", "larger",
               "smaller", "small", "mid", "sized", "based", "leading", "specialty", "diversified", "portfolio", "portfolios", "mixed", "various",
               "general", "group", "groups", "makers", "producers", "producer", "manufacturers", "manufacturer", "manufacturing", "operators",
               "operator", "consumer", "consumers", "integrated", "regional", "pan", "india", "national", "domestic", "global", "focused",
               "tier", "high", "value", "added", "basic", "performance", "premium", "quality", "commercial", "stage", "scale", "makers",
               "platform", "platforms", "system", "systems", "solution", "solutions", "software", "technology", "technologies"}
# the labels of a way of earning a layer made by how its companies earn takes (the app's theme_check.MODELS labels that name no kinds)
EARNING_LABELS = {"Project and consulting services", "Managed and outsourced IT services", "Business process outsourcing",
                  "Software products and subscriptions", "Designs licensed for royalties", "Platforms and marketplaces",
                  "Hardware resale and integration", "Distribution and trading", "Retail", "Makers of their own products",
                  "Product designers that outsource making", "Parts, component and ingredient makers", "Contract manufacturing",
                  "Engineering and construction contracts", "Lenders", "Insurers", "Payment networks and processors", "Property and leasing",
                  "Transport and logistics", "Media and content", "Diversified groups", "Resale and distribution", "IT services for clients",
                  "Financial fees and commissions"}
_LAYER_HEAD = re.compile(r"^\s*Layer \d+ · (.+?)(?:\s*\((?:notes|continued)\))?\s*$", re.M)          # r571: "(notes)" pages aside
_CITED = re.compile(r"“([^”]{3,80})”")
_SAYS_NOT = re.compile(r"(?:don't|doesn't|do not|does not) (?:show the work of|support|say what|say it sells what) “([^”]{3,80})”")
_OFFICIAL_SAID = re.compile(r"an official industry of the theme")


def _kind_words(name: str) -> set:
    out = set()
    for w in re.findall(r"[a-z]+", name.lower().replace("-", " ")):
        w = w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith("ss") else w
        if len(w) >= 3 and w not in _PLAIN_NAME and f"{w}s" not in _PLAIN_NAME:
            out.add(w)
    return out


def _says_word(text: str, w: str) -> bool:
    return bool(re.search(r"\b" + re.escape(w[:max(5, len(w) - 2)] if len(w) > 6 else w), text.lower()))


def _layer_names(pages: list[str]) -> set:
    names = set()
    for p in pages:
        for m in _LAYER_HEAD.finditer(p):
            names.add(re.sub(r" \((?:larger|smaller)\)$", "", m.group(1)))
    return names


def _small_layer_chunks(page: str) -> list[tuple[str, str]]:
    """(layer name, the rest of its rows' text) of a "Smaller layers" table: a layer's cell starts at the line's start with a capital, a
    lower-case start continues its name. r581 (the live R58 Cybersecurity and Insurance decks: the layer's cell is set in the middle of its
    first row, so the row's lines above it, "It provides endpoint security", were read as the layer before's): a row is the lines between
    blank lines, all of them the layer's whose cell the row holds; a row with none holds another company of the layer before."""
    out, name, body = [], None, []
    started, row = False, []

    def flush():
        nonlocal name, body
        cells = []
        for ln in row:
            cell = re.split(r"\s{2,}", ln.strip())[0] if ln[:2].strip() else ""
            cells.append(cell)
        rests = [ln.strip()[len(c):] if c else ln for ln, c in zip(row, cells)]
        heads = [c for c in cells if c]
        if heads and heads[0][:1].isupper():
            if name is not None:
                out.append((name, " ".join(body)))
            name, body = " ".join(heads), rests
        elif name is not None:
            name, body = " ".join([name] + heads), body + rests
        row.clear()
    for ln in page.split("\n"):
        if re.match(r"^\s*Layer\s{2,}Company\b", ln):
            started = True
            continue
        if not started or ln.startswith("StratLab ·"):
            continue
        if not ln.strip():
            if row:
                flush()
            continue
        row.append(ln)
    if row:
        flush()
    if name is not None:
        out.append((name, " ".join(body)))
    return out


def p57_checks(pages: list[str], add) -> None:
    """p57 (R56): the placement contract, failures:
      removal unbacked   a company removed from the theme on a check's answer naming a group that is no layer of the deck ("its own words
                         were checked and don't show the work of “Card issuers and lenders”" beside "Card issuers and consumer lenders"), or
                         one said to be filed under an official industry of the theme with no other reason
      layer words        a layer (its page, or its rows of the "Smaller layers" table) whose name's words of a kind of business are said by
                         none of its companies' lines ("Hotels, travel and consumer services" holding a language-course app)
      words contradict   a removal or move whose reason says a company's words don't show a layer's work ("don't show the work of “X”",
                         "doesn't support “X”") while the deck prints that company's own words saying a word of that layer's name"""
    layers = _layer_names(pages)
    flat_pages = [flat_text(p) for p in pages]
    for n, page in enumerate(pages, 1):
        flat = flat_text(page)
        if "Since the previous version" in flat or "against the version stored before it" in flat:
            for m in _REMOVED_LIST.finditer(flat):
                for it in _top_items(m.group(2)):
                    why = _last_paren(it)
                    cited = [c for c in _CITED.findall(why) if c not in layers]
                    if layers and "business membership" in why and _SAYS_NOT.search(why) and cited:
                        add("removal unbacked", n, it[:200])
                    elif _OFFICIAL_SAID.search(why) and not re.search(r"listing: |another business|outside the theme's definition|the same company as", why):
                        add("removal unbacked", n, it[:200])
                    said = _SAYS_NOT.search(why)
                    if said:
                        who = re.sub(r"\s*\(.*$", "", it).strip()
                        who = re.sub(r"\s+\d+\s+version\s+", " ", who)
                        words = _kind_words(said.group(1))
                        seen = ""
                        for k, other in enumerate(flat_pages, 1):          # its own words as another page prints them beside its name
                            at = other.find(who) if len(who) >= 6 and k != n else -1
                            if at >= 0:
                                seen = other[at + len(who):at + len(who) + 300]
                                break
                        if seen and words and any(_says_word(seen, w) for w in words):
                            add("words contradict", n, it[:200])
        if re.search(r"^\s*Smaller layers\s*$", page, re.M):
            for name, body in _small_layer_chunks(page):
                name = re.sub(r" \((?:larger|smaller)\)$", "", name)
                if name.startswith("Other ") or name in EARNING_LABELS:
                    continue                 # "Other", and a label of how its companies earn (their models show it), name no kind
                words = _kind_words(name)
                if words and body.strip() and not any(_says_word(body, w) for w in words):
                    add("layer words", n, f"“{name}”: none of its companies' lines says {', '.join(sorted(words))}")


_FIN_THEME = re.compile(r"\b(?:banks?|banking|lenders?|lending|financ\w*|insur\w*|nbfcs?)\b", re.I)
_BIG_PCT = re.compile(r"(?<![+−\-(\d.,])(\d{3,}(?:,\d{3})*(?:\.\d+)?)%(?!\s+(?:of|more|less|above|below)\b)")


def financial_checks(pages: list[str], add) -> None:
    """r581: "financial margin", a net margin above 100% printed for a bank, lender or insurer (the deck's theme names them, its name read
    under the cover's head, or the row's own line does). A margin column's figure is the one checked: a growth figure carries its sign, a share its bracket."""
    lines = [ln.strip() for ln in (pages[0].split("\n") if pages else []) if ln.strip()]
    title = next((lines[i + 1] for i, ln in enumerate(lines[:-1]) if "THEME DEEP DIVE" in ln), "")      # the theme's name, under the cover's head
    fin_deck = bool(_FIN_THEME.search(title))
    for n, page in enumerate(pages, 1):
        for ln in page.split("\n"):
            if not (fin_deck or _FIN_THEME.search(ln)):
                continue
            for m in _BIG_PCT.finditer(ln):
                if float(m.group(1).replace(",", "")) > 100.0:
                    add("financial margin", n, ln.strip()[:200])
                    break


def check_text(text: str) -> dict:
    """check_pages for a deck's whole text, its pages separated by form feeds."""
    pages = text.split("\f")
    return check_pages(pages[:-1] if len(pages) > 1 and not pages[-1].strip() else pages)


def failed(result: dict, strict: bool = False) -> bool:
    return bool(result.get("error")) or any(result["counts"][k] for k in FAIL + (WARN if strict else ()))


def check_file(path: str) -> dict:
    """check_pages for one file; a file that can't be read is a failure of its own ("error"), never a crash of the whole run."""
    try:
        return check_pages(pages_of(path))
    except (OSError, subprocess.CalledProcessError) as e:
        return {"pages": 0, "counts": {k: 0 for k in FAIL + WARN}, "findings": [], "error": f"could not be read ({type(e).__name__})"}


def report(results: dict, strict: bool = False, show: int = 8) -> str:
    """The per-deck table, then each deck's findings (the first `show` of a kind)."""
    kinds = FAIL + WARN
    head = ["deck", "pages"] + list(kinds) + ["result"]
    rows = [[name, str(r["pages"])] + [str(r["counts"][k]) for k in kinds] + ["UNREADABLE" if r.get("error") else "FAIL" if failed(r, strict) else "ok"] for name, r in results.items()]
    wide = [max(len(x[i]) for x in [head] + rows) for i in range(len(head))]
    out = ["  ".join(c.ljust(w) for c, w in zip(x, wide)).rstrip() for x in [head] + rows]
    for name, r in results.items():
        for k in kinds:
            got = [f for f in r["findings"] if f["kind"] == k]
            if not got or (k == "cut text" and not strict):        # R40: a theme mostly in "Other" is listed whatever the mode
                continue
            out.append(f"\n{name}: {k} ({len(got)})")
            out += [f"  p.{f['page']}: {f['text']}" for f in got[:show]]
            if len(got) > show:
                out.append(f"  and {len(got) - show} more")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    strict, as_json = "--strict" in args, "--json" in args
    paths = [a for a in args if not a.startswith("--")]
    if len(paths) != 1 or not os.path.isdir(paths[0]):
        print(__doc__, file=sys.stderr)
        return 2
    names = sorted(os.listdir(paths[0]))
    files = [n for n in names if n.lower().endswith(".pdf")] or [n for n in names if n.lower().endswith(".txt")]
    if not files:
        print(f"deck_check: no .pdf (or .txt) in {paths[0]}", file=sys.stderr)
        return 2
    if files[0].lower().endswith(".pdf") and not shutil.which("pdftotext"):
        print("deck_check: pdftotext (poppler) is not on the PATH", file=sys.stderr)
        return 2
    results = {n: check_file(os.path.join(paths[0], n)) for n in files}
    print(json.dumps(results, ensure_ascii=False, indent=1) if as_json else report(results, strict))
    return 1 if any(failed(r, strict) for r in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
