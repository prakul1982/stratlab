#!/usr/bin/env python3
"""Deck regression check: reads a folder of deck PDFs as a reader would (pdftotext) and reports, for each deck, what must never ship.

    python scripts/deck_check.py <folder of deck PDFs> [--strict] [--json]

Failures (the exit code is 1 when any deck has one):
  headline     a slide's title or headline (its first lines) ending in "…"
  mid-word     a word cut inside itself ("Semiconductor equipm…"): one the deck prints longer elsewhere and never whole
  placeholder  an unfilled field or a missing value printed as text ("{name}", "None", "nan", "undefined", "shown for x.")
  joining word text cut on a joining word ("Component and…")
  count        "N of M" where N is larger than M
Reported, and a failure only with --strict:
  cut text     every other text ending in "…" (a label or a sentence cut to its box)

A PDF that can't be read is a failure of its own (UNREADABLE). A folder with no PDF is read from its .txt files (pdftotext -layout output, pages separated by form feeds), so a saved extract can be
checked again. Standalone: nothing of the app is imported; pdftotext (poppler) must be on the PATH to read PDFs. Exit 2: nothing to read."""
import json
import os
import re
import shutil
import subprocess
import sys

FAIL = ("headline", "mid-word", "placeholder", "joining word", "count")
WARN = ("cut text",)
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
            for m in _PLACEHOLDER.finditer(flat):
                add("placeholder", n, f"{m.group(0)!r} in: {flat}")
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
            if not got or (k in WARN and not strict):
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
