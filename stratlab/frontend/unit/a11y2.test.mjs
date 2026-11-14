// A11Y-2 (28 Oct 2026): accessibility review of the pages people use most, again, now with the landing intro, the welcome pop-up and tour, the
// cookie banner, the house ad card, the blog, the company directories and company pages with their chart, and the policy pages: what was
// fixed, held in place.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("A11Y-2: the policy pages' own row of links is not named like the footer's (two landmarks, two names)", () => {
  const page = read("src/pages/LegalPage.tsx"), footer = read("src/components/LegalLinks.tsx");
  assert.match(page, /<nav className="legal-tabs" aria-label="Policy pages">/);
  assert.match(footer, /aria-label="Policies"/);
});

test("A11Y-2: each fund's sales table is named after the fund, so open folds do not repeat one region name", () => {
  const page = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(page, /<DataTable label=\{`Redemptions matched to purchases, \$\{name\}`\}/);
});

test("A11Y-2: the cookie banner has its place in the page's order and keeps what has focus clear of it", () => {
  const card = read("src/components/Tracking.tsx"), app = read("src/main.tsx"), visitor = read("src/visitor/visitorMain.tsx"), shell = read("src/components/Shell.tsx");
  // (updated on purpose, LIVE7B-006: signed in, the Shell draws it in the page column)
  // (updated on purpose, LIVE8B-004: before the page, "Skip to content" landed on it and its arrival pushed the page down) after the page in
  // both halves of the site
  assert.match(app, /<Shell ask=\{<Tracking \/>\}>/);
  assert.match(app, /return <><VisitorApp \/><Tracking \/><\/>;/);
  assert.ok(shell.indexOf("{ask}") > shell.indexOf('<main className="main" id="main"'));
  assert.ok(visitor.indexOf("<Tracking />") > visitor.indexOf("<VisitorApp />"));
  // (updated on purpose, LIVE7B-006) it is in the page's own flow, so nothing can be under it: no scroll padding is needed any more
  assert.doesNotMatch(card, /scroll-padding-bottom/);
  assert.match(card, /role="dialog" aria-modal="false" aria-label=\{`\$\{title\} on StratLab`\} aria-describedby=\{text\}/);
});

test("A11Y-2: the answer on a page the server draws puts focus somewhere on purpose, not on the top of the document", () => {
  const js = read("public/ads.js");
  assert.match(js, /function keep\(n\) \{\s*if \(!n\) return;\s*n\.setAttribute\("tabindex", "-1"\);\s*try \{ n\.focus\(\{ preventScroll: true \}\); \}/);
  assert.match(js, /load\(\); keep\(box\); \}\);/);                                        // after Allow: on the box, which now says "Advertisement"
  assert.match(js, /write\("no"\); boxes\.forEach\(drop\); keep\(document\.getElementById\("main"\)\); \}\);/);      // after No thanks: the page's main part
});

test("A11Y-2: on a phone the footer's short links, a one-word chip and the rupee link are 44px to tap", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.legal-links a, \.lp-foot \.legal-links a \{ display: inline-flex; align-items: center; min-height: 44px; padding-block: 12px; min-width: 44px;/);
  assert.match(css, /\.k-chip \{ min-width: 44px; \}/);
  assert.match(css, /@media \(max-width: 640px\) \{ \.link-btn\.inr-pick \{ min-height: 44px; \} \}/);
});

test("A11Y-2: a loading placeholder that has a name also has a role, so axe allows the label (aria-prohibited-attr on /plans)", () => {
  // A bare <span>/<div> may not carry aria-label; the skeletons only show while prices or the chart load.
  for (const [f, name] of [["src/pages/Login.tsx", "Loading the price"], ["src/charts/price/lazy.tsx", "Loading the chart"]]) {
    const tag = read(f).match(new RegExp(`<(?:span|div)[^>]*aria-label="${name}"[^>]*>`))[0];
    assert.match(tag, /role="img"/, `${f}: ${tag}`);
  }
});
