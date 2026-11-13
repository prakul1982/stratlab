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
Reported, and a failure only with --strict:
  cut text     every other text ending in "…" (a label or a sentence cut to its box)
  mixed range  a range with one end whole and the other with a decimal ("19.6% to 20%"; LIVE7A-014)
  other>40%    a theme whose "Other" group holds over 40% of the companies placed, as its coverage says: R44, "In informative layers
               137 of 252 (54%) ... 33 fit none of the map's layers; 82 not checked yet" (those that fit none, the companies not checked
               yet apart, as d1; the companies outside informative layers when the row doesn't split them); before R44, "50 of 100
               companies fit none of the map's layers": a map that places too few of its companies

A PDF that can't be read is a failure of its own (UNREADABLE). A folder with no PDF is read from its .txt files (pdftotext -layout output, pages separated by form feeds), so a saved extract can be
checked again. Standalone: nothing of the app is imported; pdftotext (poppler) must be on the PATH to read PDFs. Exit 2: nothing to read."""
import json
import os
import re
import shutil
import subprocess
import sys

FAIL = ("headline", "mid-word", "placeholder", "joining word", "count", "repeated", "hyphen minus", "no layer")
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
_INFORMATIVE = re.compile(r"In informative layers")
_INF_COUNT = re.compile(r"(?<![\w.,])(\d[\d,]*) of (\d[\d,]*)(?![\d,])")    # its count, a cell that may wrap above or below the label's line
_FIT_NONE = re.compile(r"(\d[\d,]*)\s+fit\s+none\s+of\s+the\s+map's")     # (the row's text wraps around its label's line)
_APPENDIX = "Every company's figures"
# R40: a word said twice in a row; repeated when the second is lower case or it is a joining word ("The the"), never a name ("Bora Bora")
_TWICE = re.compile(r"\b([A-Za-z]+)(?: (?! )|\n)\1\b", re.I)
_TWICE_JOIN = _JOINING | {"is", "are", "was", "were", "its", "their", "this", "these", "than", "as", "be", "it"}
_TWICE_OK = {"had", "that", "very", "so", "no", "bye", "more", "many", "much", "far", "long"}


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
            fn = _FIT_NONE.search(page[max(0, i.start() - 400):i.end() + 600])
            a = int(fn.group(1).replace(",", "")) if fn else b - inf
            if b and a > OTHER_MAX * b:
                add("other>40%", n, f"In informative layers {inf:,} of {b:,} ({round(inf / b * 100)}%); {a:,} fit none ({round(a / b * 100)}%)")
            break
        m = _OTHER.search(page)
        if m:
            a, b = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
            if b and a > OTHER_MAX * b:
                add("other>40%", n, f"{m.group(0)} ({round(a / b * 100)}%)")
            break
    counts = {k: sum(1 for f in findings if f["kind"] == k) for k in FAIL + WARN}
    return {"pages": len(pages), "counts": counts, "findings": findings}


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
