"""Every company whose layer changed between two sets of theme maps (lane s1-fit, Release 38): run after each release, before decks go out,
to see each move the new rules make.

    python scripts/layer_diff.py BEFORE_DIR AFTER_DIR [--halves] [--json]

Each folder holds sec_<key>.json files, the GET /research/sector answer (or a replay of it): {"sector", "value_chain": [{"layer",
"official", "companies": [{"ticker", "name"}]}]}. A theme found in only one folder is reported, not compared. The halves of a layer split by
market value ("... (larger)", "... (smaller)") count as one layer unless --halves is given; a company of the theme's "Other" group (an
"official" layer) is shown as in "Other". Prints one line per moved company (theme, symbol, name, from, to) and the count; --json prints the
same as a JSON list. Standard library only."""
import argparse
import json
import pathlib
import re
import sys

_HALF = re.compile(r"( \((?:larger|smaller)\))+$")


def layers_of(doc: dict, halves: bool = False) -> dict:
    """{symbol: (name, layer)} of one map; "Other" for an official group."""
    out = {}
    for v in doc.get("value_chain") or []:
        name = "Other" if v.get("official") else str(v.get("layer") or "")
        if not halves:
            name = _HALF.sub("", name)
        for c in v.get("companies") or []:
            sym = c.get("ticker") or c.get("symbol")
            if sym and sym not in out:
                out[sym] = (c.get("name") or "", name)
    return out


def diff(before: pathlib.Path, after: pathlib.Path, halves: bool = False) -> tuple[list[dict], list[str]]:
    """(the moves, notes on themes or companies found on one side only)."""
    moves, notes = [], []
    keys_b = {p.stem[4:]: p for p in before.glob("sec_*.json")}
    keys_a = {p.stem[4:]: p for p in after.glob("sec_*.json")}
    for k in sorted(set(keys_b) ^ set(keys_a)):
        notes.append(f"{k}: only in {'before' if k in keys_b else 'after'}")
    for k in sorted(set(keys_b) & set(keys_a)):
        b = layers_of(json.loads(keys_b[k].read_text()), halves)
        a = layers_of(json.loads(keys_a[k].read_text()), halves)
        for s in sorted(set(b) ^ set(a)):
            notes.append(f"{k}:{s}: only in {'before' if s in b else 'after'}")
        for s in sorted(set(b) & set(a)):
            if b[s][1] != a[s][1]:
                moves.append({"theme": k, "symbol": s, "name": a[s][0] or b[s][0], "from": b[s][1], "to": a[s][1]})
    return moves, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("before", type=pathlib.Path)
    ap.add_argument("after", type=pathlib.Path)
    ap.add_argument("--halves", action="store_true", help="count the halves of a layer split by market value as two layers")
    ap.add_argument("--json", action="store_true", help="print the moves as JSON")
    a = ap.parse_args(argv)
    for p in (a.before, a.after):
        if not p.is_dir():
            print(f"not a folder: {p}", file=sys.stderr)
            return 2
    moves, notes = diff(a.before, a.after, a.halves)
    if a.json:
        print(json.dumps(moves, ensure_ascii=False, indent=1))
        return 0
    for n in notes:
        print("note:", n)
    for m in moves:
        print(f"{m['theme']}\t{m['symbol']}\t{m['name']}\t{m['from']}\t->\t{m['to']}")
    print(f"{len(moves)} companies changed layer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
