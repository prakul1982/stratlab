"""The audit's "must be considered" check (aud57 RC6 b) on a directory of placement inputs (GET /research/theme-dive/placement-inputs):
each listed company is a member (in a layer or "Other"), a candidate of the theme with its reason (placements.peer_candidates), or left
out with a reason the deck prints (placements.dropped, placements.same_company); anything else is MISSING. Read-only; exit 1 on a miss.

    python scripts/must_consider.py <inputs dir> [names.json]   (default: tests/fixtures/themes_live/must_consider_r57.json)"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.intel.theme_identity import norm_name  # noqa: E402

DEFAULT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "themes_live" / "must_consider_r57.json"


def find(d: dict, want: str) -> str:
    """How a theme's inputs hold a company named `want`: "member (layer)", "candidate: why", "left out: why" or "MISSING"."""
    w = norm_name(want)
    hit = lambda n: bool(w) and (norm_name(n) == w or norm_name(n).startswith(w + " "))      # noqa: E731
    for v in d.get("value_chain") or []:
        for c in v.get("companies") or []:
            if hit(c.get("name")):
                return f"member ({v.get('layer')})"
    pl = d.get("placements") or {}
    for x in pl.get("peer_candidates") or []:
        if hit(x.get("name")):
            return f"candidate: {x.get('why')}"
    for x in (pl.get("dropped") or []) + (pl.get("same_company") or []):
        if isinstance(x, dict) and hit(x.get("name")):
            return f"left out: {x.get('said') or x.get('why') or x.get('scope') or ('another listing line of ' + str(x.get('kept')))}"
    return "MISSING"


def run(inputs: pathlib.Path, names: dict) -> tuple[list[str], int]:
    lines, missing = [], 0
    for key, want in sorted((k, v) for k, v in names.items() if isinstance(v, list)):
        f = inputs / f"{key}.json"
        if not f.exists():
            lines.append(f"{key}: no inputs file")
            continue
        d = json.loads(f.read_text())
        for n in want:
            got = find(d, n)
            missing += got == "MISSING"
            lines.append(f"{key:10} {n:32} {got}")
    return lines, missing


if __name__ == "__main__":
    names = json.loads(pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else DEFAULT).read_text())
    lines, missing = run(pathlib.Path(sys.argv[1]), names)
    print("\n".join(lines))
    print(f"{missing} missing")
    sys.exit(1 if missing else 0)
