#!/usr/bin/env python3
"""Deck-level release gate (lane g57, Release 57; the owner's review of the live R56 decks): two folders of theme decks, as a reader gets
them (PDF through pdftotext -layout, or the .txt saved from it), compared theme by theme, with the reason each deck prints, and what must
never ship flagged from the deck's own text.

    python scripts/deck_diff.py <old decks folder> <new decks folder> [--only key,key] [--json] [--show N]

A theme is a file stem found in both folders (<key>.pdf or <key>.txt; the PDF is read when both are there). Per theme:
  companies  added, removed and moved between layers, as the new deck's change log ("Since the previous version") prints them with their
             reasons, and each company whose layer in the appendix table ("Every company's figures") differs between the two decks
  layers     added and removed (the value chain's table of layers), with the change log's line for each

FAIL (the exit code is 1 when any theme has one):
  removal unreasoned   a company the change log removes with no reason in brackets
  layer-only removal   a company removed because its own words don't show one layer's work ("don't show the work of “X”", "not backed by
                       its own words"): a mismatch with a layer is a reason to place it elsewhere, never to remove it from the theme
  own industry out     a removed company either deck says is filed under an official industry of the theme, unless its reason is that its
                       own words describe another business or a scope the theme's definition excludes
  reason contradicted  a removal saying its own words don't show a layer's work while the words either deck prints for it say that
                       layer's name
  layer words          a layer the new deck adds, or a layer a company is moved or added into, whose name shares no word with what the
                       decks print of its companies' own words ("What it does", or the lines that name the company): a hotels and travel
                       layer holding a language-learning app (a layer named by a way of earning, such as "Hotels, travel and consumer
                       services", is that way of earning printed as the company's model, so this also catches a printed model its words
                       contradict); a layer name with no word of three letters or more
  one-company layer    a layer of the new deck's value chain (not "Other ...") holding one company whose words, as the deck prints them,
                       don't say what it is, or for which a statistic is printed (r60, updated on purpose: the owner's R59 review P0)
Exit codes: 0 no FAIL, 1 a FAIL, 2 bad usage. Read-only: reads the decks, writes nothing."""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import deck_check as DC                          # noqa: E402
import release_gate as G                         # noqa: E402  (the same words and reasons as the placement gate)

_LOG_AT = "against the version stored before it"
_SECTION = re.compile(r"\b(added|removed(?: for a listing reason)?|moved between layers|layers changed|restated) (\d[\d,]*): ")
_FOOT = re.compile(r"^\s*StratLab · ")
_ADJ = re.compile(r"\s*\(adjacent\)\s*$")
_COUNT = re.compile(r"^(\d[\d,]*)(?: of (\d[\d,]*))?$")
_SUFFIX = re.compile(r"[,.]?\s+(?:inc\.?|corp\.?|corporation|co\.?|ltd\.?|limited|plc|holdings?|group|n\.?v\.?|s\.?a\.?|ag|se|lp|llc|"
                     r"company|industries|international|technologies|enterprises?|& co\.?)$", re.I)
LAYER_ONLY = re.compile(r"don't show the work of|not backed by its own words", re.I)
OFFICIAL = "an official industry of the theme"


# ---------- reading a deck ----------
def deck_path(folder: pathlib.Path, key: str) -> pathlib.Path | None:
    for ext in (".pdf", ".txt"):
        p = folder / f"{key}{ext}"
        if p.exists():
            return p
    return None


def _cells(ln: str) -> list[str]:
    return [c for c in re.split(r"\s{2,}", ln.strip()) if c]


def full_names(pages: list[str]) -> dict:
    """{short layer name: full name} from the appendix's "Layer names in full: A = B; C = D." notes."""
    out = {}
    for page in pages:
        for m in re.finditer(r"Layer names in full: (.+?)(?:\n\s*\n|\Z)", page, re.S):
            text = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
            for part in text.split("; "):
                if " = " in part:
                    a, b = part.split(" = ", 1)
                    out[a.strip()] = b.strip().rstrip(".")
    return out


def appendix(pages: list[str]) -> dict:
    """{company: its layer} of the appendix's table ("Every company's figures"), a layer name wrapped onto the lines around its row
    read whole, a short name given in full."""
    names = full_names(pages)
    out = {}
    for page in pages:
        if DC._APPENDIX not in page:
            continue
        lines = page.split("\n")
        cols = None
        rows = []                    # [company, layer, index]
        for i, ln in enumerate(lines):
            if cols is None:
                if re.match(r"^\s*Company\s{2,}Layer\s{2,}", ln):
                    heads = [m.start() for m in re.finditer(r"\S+(?: \S+)*", ln)]
                    cols = (heads[1], heads[2] if len(heads) > 2 else len(ln))
                continue
            if _FOOT.match(ln) or ln.startswith("Latest full year"):
                break
            if not ln.strip():
                continue
            comp, lay, rest = ln[:cols[0]].strip(), ln[cols[0]:cols[1]].strip(), ln[cols[1]:]
            cells = _cells(lay)
            lay = cells[0] if cells and not re.match(r"^[$₹]|^\d", cells[0]) else ""      # a market value under no heading of its own
            if re.search(r"\$|₹|\d", rest) or len(cells) > 1:
                rows.append([comp, lay, i])
        for comp, lay, i in rows:
            if not lay:              # a wrapped layer name: its first part on the line above, the rest on the line below
                above = lines[i - 1][cols[0]:cols[1]].strip() if i > 0 and not re.search(r"\$|₹|\d", lines[i - 1][cols[1]:]) else ""
                below = lines[i + 1][cols[0]:cols[1]].strip() if i + 1 < len(lines) and not re.search(r"\$|₹|\d", lines[i + 1][cols[1]:]) else ""
                lay = " ".join(x for x in (above, below) if x)
            lay = _ADJ.sub("", names.get(lay, lay))
            if comp and comp not in out:
                out[comp] = lay or "–"
    return out


def layer_counts(pages: list[str]) -> dict:
    """{layer: its companies} of the value chain's table of layers ("The value chain by layer": a "Companies" cell of "N" or "N of M",
    M the layer's companies), a name wrapped over the lines of its row read whole."""
    out = {}
    for page in pages:
        if "The value chain by layer" not in page:
            continue
        lines = page.split("\n")
        col = None
        rows: list = []              # [name parts, count]
        pending: list[str] = []
        cur = None

        def close():
            for parts, n in rows:
                name = _ADJ.sub("", re.sub(r"\s+", " ", " ".join(parts)).strip())
                if name and name not in out:
                    out[name] = n
            rows.clear()
        for ln in lines:
            if col is None:
                if re.match(r"^\s*Layer\s{2,}Companies\b", ln):
                    col = ln.index("Companies")
                continue
            if _FOOT.match(ln) or (not ln.startswith(" ") and ln.strip() and rows):
                break                # the page's notes under the table
            if not ln.strip():
                pending, cur = [], None
                continue
            left = ln[:max(col - 8, 0)].strip()
            m = _COUNT.match(ln[max(col - 8, 0):col + 14].strip())
            if m:                    # a row: its name on this line, after a part wrapped onto the line above
                cur = [pending + ([left] if left else []), int((m.group(2) or m.group(1)).replace(",", ""))]
                rows.append(cur)
                pending = []
            elif left:
                (cur[0] if cur is not None else pending).append(left)
        close()
    # r571 (the live R57 decks: Consumer retail "layers 9 -> 5", Biotech "6 -> 4"): a row the table's layout put off its "Companies" column
    # is read from the layer's own page ("Layer N · X", its "(notes)" and "(continued)" pages aside): "N companies, ..." under its title
    for page in pages:
        for m in _LAYER_PAGE.finditer(page):
            name = _ADJ.sub("", m.group(1).strip())
            if name in out or re.search(r"\((?:notes|continued)\)$", name):
                continue
            n = re.search(r"(\d[\d,]*) compan", page[m.end():m.end() + 400])
            if n:
                out[name] = int(n.group(1).replace(",", ""))
    return out


_LAYER_PAGE = re.compile(r"(?m)^\s*Layer \d+ · (.+?)\s*$")


def descriptions(pages: list[str]) -> dict:
    """{company: what the deck prints it does} of the tables with a "What it does" column (a layer of two companies or fewer)."""
    out = {}
    for page in pages:
        lines = page.split("\n")
        cols = None
        block: list[str] = []
        for ln in lines + [""]:
            if cols is None or re.match(r"^\s*Layer\s{2,}Company\s{2,}What it does", ln):
                if re.match(r"^\s*Layer\s{2,}Company\s{2,}What it does", ln):
                    cols = (ln.index("Company"), ln.index("What it does"),
                            ln.index("Revenue") if "Revenue" in ln else len(ln))
                    block = []
                continue
            if _FOOT.match(ln) or ln.startswith("Each of these layers") or ln.startswith("Rows in"):
                cols = None
                continue
            if ln.strip():
                block.append(ln)
                continue
            comp = " ".join(b[cols[0]:cols[1]].strip() for b in block if b[cols[0]:cols[1]].strip())
            what = " ".join(b[cols[1]:cols[2]].strip() for b in block if b[cols[1]:cols[2]].strip())
            if comp and what and comp not in out:
                out[comp] = what
            block = []
    return out


def change_log(pages: list[str]) -> str:
    """The change log's text as printed in its column ("On <day>, against the version stored before it, ...: added N: ...")."""
    for page in pages:
        lines = page.split("\n")
        for i, ln in enumerate(lines):
            if _LOG_AT not in ln:
                continue
            col = ln.index("On ") if "On " in ln else ln.index(_LOG_AT)
            parts, blank = [], 0
            for x in lines[i:]:
                if _FOOT.match(x):
                    break
                if not x.strip():
                    blank += 1
                    if blank >= 2:
                        break
                    continue
                blank = 0
                label = x[:max(col - 1, 0)].strip()
                if parts and label and not re.fullmatch(r"(?:Since the previous(?: version)?|version|\d+)", label):
                    break            # the next row of the table
                parts.append(x[max(col - 1, 0):].strip())
            return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    return ""


def _items(text: str) -> list[str]:
    """A section's items: split at ", " after a closing bracket (names hold commas: "Duolingo, Inc. (...)")."""
    out, depth, cur = [], 0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and text.startswith(", ", i) and cur.rstrip().endswith(")"):
            out.append(cur.strip())
            cur = ""
            i += 2
            continue
        cur += ch
        i += 1
    return [x for x in out + [cur.strip().rstrip(".")] if x]


def log_rows(text: str) -> dict:
    """{kind: [(item, its reason in brackets)]} of a change log, kinds "added", "removed", "moved", "layers"."""
    out: dict = {"added": [], "removed": [], "moved": [], "layers": [], "unnamed": []}
    marks = list(_SECTION.finditer(text))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        body = text[m.end():end].strip().rstrip(";").strip()
        kind = {"moved between layers": "moved", "layers changed": "layers"}.get(m.group(1), m.group(1).split()[0])
        if kind == "restated":
            continue
        items = DC._top_items(body) if kind == "layers" else _items(body)
        more = re.search(r",? and (\d[\d,]*) more\.?$", body)
        if more:                     # "... and 8 more": the rest not named
            items = DC._top_items(body[:more.start()]) if kind == "layers" else _items(body[:more.start()])
            out.setdefault("unnamed", []).append((kind, int(more.group(1).replace(",", ""))))
        for it in items:
            it = it.strip().rstrip(".;")
            why = DC._last_paren(it)
            name = it[:len(it) - len(why) - 2].strip() if why else it
            out[kind].append((name, why))
    return out


def base_name(company: str) -> str:
    n = re.sub(r"\s*\([^)]*\)\s*$", "", company).strip()
    for _ in range(3):
        n2 = _SUFFIX.sub("", n).strip().rstrip(",")
        if n2 == n or not n2:
            break
        n = n2
    return n


def _same(a: str, b: str) -> bool:
    return base_name(a).lower() == base_name(b).lower()


def canon(layer: str) -> str:
    """A layer's name as compared: "&" as "and", and the halves of a layer split by market value ("... (larger)", "... (smaller)") as
    the one layer (scripts/layer_diff.py does the same by default)."""
    return G._HALF.sub("", re.sub(r"\s*&\s*", " and ", str(layer or "")).strip())


def words_in_deck(pages: list[str], company: str, drop: list[str], descr: dict) -> tuple[str, str]:
    """(what a deck prints of a company's own words, where from: "what" its "What it does" text, "lines" the lines that name it, without
    any layer's name or anything quoted (“...”) on them)."""
    for k, v in descr.items():
        if _same(k, company):
            return v, "what"
    base = base_name(company)
    if len(base) < 3:
        return "", ""
    key = " ".join(base.split()[:2]).lower()
    got = []
    for page in pages:
        for ln in page.split("\n"):
            if key not in ln.lower() or _LOG_AT in ln:
                continue
            keep = []
            for c in _cells(ln):
                cl = c.lower()
                if any(cl in d.lower() or d.lower() in cl for d in drop if d):
                    continue
                keep.append(re.sub(r"“[^”]*”", " ", c))
            got.append(" ".join(keep))
    return " ".join(got), "lines"


# ---------- the gate ----------
def diff_theme(old_pages: list[str], new_pages: list[str]) -> dict:
    a = {k: canon(v) for k, v in appendix(old_pages).items()}
    b = {k: canon(v) for k, v in appendix(new_pages).items()}
    la = {canon(k): v for k, v in layer_counts(old_pages).items()}
    lb = {canon(k): v for k, v in layer_counts(new_pages).items()}
    known = set(la) | set(lb)

    def whole(name):                 # a name the table cut short ("Medical device & consumables"): the one layer it starts
        if name in known:
            return name
        hits = [k for k in known if k.startswith(name)]
        return hits[0] if len(hits) == 1 else name
    a = {k: whole(v) for k, v in a.items()}
    b = {k: whole(v) for k, v in b.items()}
    ka = {base_name(c).lower(): c for c in a}
    kb = {base_name(c).lower(): c for c in b}
    log = log_rows(change_log(new_pages))
    ren = {}
    for name, _ in log["layers"]:
        m = re.match(r"“([^”]+)” renamed “([^”]+)”", name)
        if m:
            ren[canon(m.group(1))] = canon(m.group(2))
    descr = {**descriptions(old_pages), **descriptions(new_pages)}
    # r60: the "Smaller layers" rows as deck_check reads them (a cell ends at a two-space gap, so a right-aligned figure never joins its words)
    descr.update({comp: what for _, comp, what in DC.small_rows(new_pages) if comp and what})
    layers_all = sorted(set(la) | set(lb) | set(a.values()) | set(b.values()), key=len, reverse=True)
    flat_all = " ".join(re.sub(r"\s+", " ", p) for p in old_pages + new_pages)
    rows, fails = [], []

    def fail(kind, subject, detail):
        fails.append({"fail": kind, "subject": subject, "detail": detail})

    def printed(kind, company):
        for name, why in log[kind]:
            if _same(name, company) or company.lower().startswith(name.lower()) or name.lower().startswith(base_name(company).lower()):
                return why
        return None
    # the change log's own rows
    for name, why in log["removed"]:
        rows.append({"kind": "removed", "company": name, "from": "", "to": "", "reason": why})
        if not why:
            fail("removal unreasoned", name, "removed with no reason")
            continue
        if LAYER_ONLY.search(why):
            fail("layer-only removal", name, why)
        m = re.search(re.escape(base_name(name)) + r"[^()]{0,60}\(filed under ([^,()]+), " + OFFICIAL, flat_all)
        if m and not G.OWN_REASON.search(why):
            fail("own industry out", name, f"filed under {m.group(1)}, {OFFICIAL}; {why}")
        g = re.findall(r"“([^”]+)”", why)
        if g and LAYER_ONLY.search(why):
            text = words_in_deck(old_pages + new_pages, name, layers_all, descr)[0]
            hit = [x for x in g if G.shares(x, text)]
            if hit:
                fail("reason contradicted", name, f"the decks print words of “{hit[0]}” for it; printed: {why}")
    for name, why in log["added"]:
        rows.append({"kind": "added", "company": name, "from": "", "to": "", "reason": why})
    for name, why in log["moved"]:
        m = re.match(r"from “([^”]*)” to “([^”]*)”:?\s*(.*)$", why or "")
        frm, to, reason = (m.group(1), m.group(2), m.group(3)) if m else ("", "", why)
        rows.append({"kind": "moved", "company": name, "from": frm, "to": to, "reason": reason})
    for name, why in log["layers"]:
        rows.append({"kind": "layer", "company": "", "from": "", "to": name, "reason": why})
    # the appendix's table: every company whose layer differs, with the change log's reason when it prints one
    renamed_moves = 0
    for k in sorted(set(ka) & set(kb)):
        ca, cb = ka[k], kb[k]
        if a[ca] != b[cb]:
            if ren.get(a[ca]) == b[cb]:
                renamed_moves += 1   # its layer renamed: said once, on the layer's row
                continue
            why = printed("moved", cb)
            unnamed = sum(n for kd, n in log["unnamed"] if kd == "moved")
            rows.append({"kind": "table moved", "company": cb, "from": a[ca], "to": b[cb],
                         "reason": why if why is not None else (f"(not named: the change log ends “and {unnamed} more”)" if unnamed
                                                                 else "(no reason printed)")})
    for k in sorted(set(ka) - set(kb)):
        why = printed("removed", ka[k])
        rows.append({"kind": "table out", "company": ka[k], "from": a[ka[k]], "to": "",
                     "reason": why if why is not None else "not in the new deck's figures table (no removal printed)"})
    for k in sorted(set(kb) - set(ka)):
        why = printed("added", kb[k])
        rows.append({"kind": "table in", "company": kb[k], "from": "", "to": b[kb[k]],
                     "reason": why if why is not None else "new in the figures table (no addition printed)"})
    for name in sorted(set(lb) - set(la)):
        if name in ren.values():
            continue                 # a renamed layer: the change log's row says it
        rows.append({"kind": "layer +", "company": "", "from": "", "to": name, "reason": next((w for n, w in log["layers"] if name in n), "")})
    for name in sorted(set(la) - set(lb)):
        if name in ren:
            continue
        rows.append({"kind": "layer -", "company": "", "from": name, "to": "", "reason": next((w for n, w in log["layers"] if name in n), "")})
    # the new deck's layers
    for name, n in lb.items():
        if name.startswith("Other "):
            continue
        if not re.search(r"[A-Za-z]{3,}", name):
            fail("layer words", f"“{name}”", f"a layer name with no word, {n} companies")
        if n == 1:
            # r60 (R60, updated on purpose: the owner's R59 review P0, "valid industry roles are being hidden simply because their category
            # contains one company"): a layer of one company fails only when what the deck prints of its company's words doesn't say what it
            # is (its name or concept), or when a statistic is printed for it; r582 failed every one. A stricter test of evidence
            who = [c for c, x in b.items() if x == name]
            rows_ = [r for r in DC.small_rows(new_pages) if r[0] == name]
            said_ = bool(rows_) and all(DC.says_layer(name, w) or G.shares(name, w) for _, _, w in rows_)
            stat_ = DC.thin_stat(new_pages, name)
            if not said_ or stat_:
                fail("one-company layer", f"“{name}”", ((who[0] + " alone") if who else "1 company")
                     + (f", a statistic printed: {stat_[:60]}" if stat_ else ", what the deck prints of its words not saying what it is"))
    # a layer new to the deck, or one a company was moved or added into: its name against its companies' words
    into: dict = {}
    for r in rows:
        if r["kind"] in ("moved", "table moved", "table in") and r["to"] and r["company"]:
            into.setdefault(canon(r["to"]), set()).add(r["company"])
    for name in set(lb) - set(la) - set(ren.values()):
        into.setdefault(name, set()).update(c for c, x in b.items() if x == name)
    for name, cos in sorted(into.items()):
        if name.startswith("Other ") or name not in set(lb) | set(b.values()):
            continue
        for comp in sorted(cos):
            text, src = words_in_deck(old_pages + new_pages, comp, layers_all, descr)
            if src != "what" or re.search(r"no description", text, re.I):
                continue             # only what the deck prints a company does ("What it does"): the lines naming it say too little
            if text.strip() and G.shares(name, text) is False:
                fail("layer words", f"“{name}”", f"{comp}: what the decks print of its words says no word of the layer's name ({text[:90]})")
    if renamed_moves:
        rows.append({"kind": "table", "company": f"{renamed_moves} companies", "from": "", "to": "",
                     "reason": "in a layer the change log says was renamed"})
    return {"changes": rows, "fails": sorted(fails, key=lambda f: (f["fail"], f["subject"])),
            "layers": {"old": len(la), "new": len(lb)}, "table": {"old": len(a), "new": len(b)}}


def report(key: str, g: dict, show: int = 40) -> str:
    lines = [f"== {key}: layers {g['layers']['old']} -> {g['layers']['new']}; figures table {g['table']['old']} -> {g['table']['new']} companies"]
    ch = g["changes"]
    if ch:
        lines.append(f"   changes ({len(ch)}):")
        lines += ["     " + x for x in G.table([["kind", "company", "from", "to", "reason"]] +
                                               [[r["kind"], r["company"], r["from"], r["to"], r["reason"] or "(no reason)"] for r in ch[:show]],
                                               [11, 34, 30, 30, 100])]
        if len(ch) > show:
            lines.append(f"     ... and {len(ch) - show} more")
    else:
        lines.append("   changes: none")
    fs = g["fails"]
    lines.append(f"   FAIL ({len(fs)}):" if fs else "   FAIL: none")
    if fs:
        lines += ["     " + x for x in G.table([["class", "subject", "detail"]] + [[f["fail"], f["subject"], f["detail"]] for f in fs[:show]],
                                               [19, 42, 130])]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("old", type=pathlib.Path)
    ap.add_argument("new", type=pathlib.Path)
    ap.add_argument("--only", default="", help="comma-separated keys (file stems)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show", type=int, default=40)
    a = ap.parse_args(argv)
    for p in (a.old, a.new):
        if not p.is_dir():
            print(f"not a folder: {p}", file=sys.stderr)
            return 2
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    stems = lambda f: {p.stem for p in f.iterdir() if p.suffix.lower() in (".pdf", ".txt")}      # noqa: E731
    keys = sorted((stems(a.old) & stems(a.new)) - ({""} if not only else set()))
    keys = [k for k in keys if not only or k in only]
    if not keys:
        print("no theme in both folders", file=sys.stderr)
        return 2
    results = {}
    for k in keys:
        results[k] = diff_theme(DC.pages_of(str(deck_path(a.old, k))), DC.pages_of(str(deck_path(a.new, k))))
        if not a.json:
            print(report(k, results[k], a.show), flush=True)
    failing = [k for k, g in results.items() if g["fails"]]
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        tot: dict = {}
        for g in results.values():
            for f in g["fails"]:
                tot[f["fail"]] = tot.get(f["fail"], 0) + 1
        only_one = sorted((stems(a.old) ^ stems(a.new)))
        print(f"\n{len(results)} themes compared; {len(failing)} with a FAIL" + (": " + ", ".join(failing) if failing else "")
              + ("; " + ", ".join(f"{k} {n}" for k, n in sorted(tot.items())) if tot else "")
              + (f"; in one folder only: {', '.join(only_one)}" if only_one else ""))
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
