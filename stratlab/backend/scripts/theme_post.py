"""Draft and check a theme's blog post from its live data (blog2: the owner, 16 Nov, "keep posting blog of the 9+ decks").

A theme post ships with a release: its figures, read from the theme's live dive, are committed to app/blog_themes/<slug>.json, and the
deploy stores and publishes the post at its first check (app/blog_research.seed_theme_posts). Nothing is written to the live site by hand;
production is only read.

1. Save the theme's live dive (the figures its deck is made from) with a GET, signed in as the owner:

       GET <API>/research/theme-dive?q=<theme name>&region=<IN|US>

   e.g. with the owner's saved browser profile: node wk-save.mjs "/research/theme-dive?q=IT%20services&region=IN" it.json
   (one call at a time). Use the theme's name as the app's theme list shows it ("IT services", "Private banks", "Medical devices").

2. Draft the post and read it, with its checks:

       cd stratlab/backend && python scripts/theme_post.py draft it.json --theme "IT services" --region IN

   It prints the post as text (the value chain table as the deck prints it) and what would keep it off the site: fewer than two layers
   with a median of 3 companies or more, a headline for a name, a word of advice, a data provider named, or a number the figures don't hold.

3. Keep it: add --write to save app/blog_themes/<slug>.json, run the blog tests (tests/test_blog2_theme_posts.py checks every committed
   post), commit, and release. A post whose checks fail is never written.

       python scripts/theme_post.py check        # every committed post again: its checks, and its page from the stored figures

A committed post is published once for each committed read; a later read of the theme brings its figures up to date on its own
(blog_research.carry_to_stored), and a rules change works them out again (refresh_theme_posts_if_due).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import blog, blog_research as br  # noqa: E402


def as_text(post: dict) -> str:
    """The post as plain text, its tables as rows, for reading before it is committed."""
    out = [post["title"], "=" * len(post["title"]), ""]
    for b in post["blocks"]:
        t = b["t"]
        if t == "table":
            out.append(" | ".join(b["head"]))
            out += [" | ".join(c if isinstance(c, str) else blog.plain_text([{"t": "p", "text": c}]) for c in r) for r in b["rows"]]
        elif t == "hbar":
            out += [f"  {r['label']}: {r['text']}" for r in b["rows"]]
        elif t == "stats":
            out.append(" · ".join(f"{i['v']} {i['l']} ({i['s']})" for i in b["items"]))
        elif t == "fold":
            out.append(f"## {b['title']} ({b['note']})")
            out += ["  - " + blog.plain_text([{"t": "p", "text": i}]) for x in b["blocks"] for i in x.get("items") or []]
        elif t in ("h2", "h3"):
            out += ["", f"# {b['text']}"]
        else:
            out.append(blog.plain_text([b]))
    return "\n".join(out)


def draft(args) -> int:
    d = json.loads(Path(args.dive).read_text(encoding="utf-8"))
    d = d.get("data", d) if isinstance(d, dict) else d
    if not isinstance(d, dict) or not (d.get("chain") or {}).get("rows"):
        print("not a theme dive: no value chain in it", file=sys.stderr)
        return 2
    src = br.theme_source(d, args.theme, args.region.upper())
    post = br.theme_post_from(src)
    print(as_text(post))
    problems = br.theme_post_problems(src, post)
    print("\nslug:", post["slug"])
    print("checks:", "passed" if not problems else "; ".join(problems))
    if problems:
        return 1
    if args.write:
        br.SEED_DIR.mkdir(exist_ok=True)
        path = br.SEED_DIR / f"{post['slug']}.json"
        path.write_text(json.dumps(src, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("written:", path)
    return 0


def check(_args) -> int:
    bad = 0
    for src in br.committed_theme_sources():
        problems = br.theme_post_problems(src)
        print(f"{br.theme_slug(src)}: read {src.get('read_on')}: {'passed' if not problems else '; '.join(problems)}")
        bad += bool(problems)
    return 1 if bad else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft", help="draft a theme post from a saved live dive and check it")
    d.add_argument("dive", help="the theme's dive saved from GET /research/theme-dive")
    d.add_argument("--theme", required=True, help="the theme's name as the app's theme list shows it")
    d.add_argument("--region", required=True, choices=["IN", "US", "in", "us"])
    d.add_argument("--write", action="store_true", help="save it to app/blog_themes/ when its checks pass")
    sub.add_parser("check", help="check every committed theme post")
    args = p.parse_args(argv)
    return draft(args) if args.cmd == "draft" else check(args)


if __name__ == "__main__":
    sys.exit(main())
