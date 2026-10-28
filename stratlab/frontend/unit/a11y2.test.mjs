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

test("A11Y-2: the cookie banner comes first in the page's order and keeps what has focus clear of it", () => {
  const card = read("src/components/Tracking.tsx"), app = read("src/main.tsx"), visitor = read("src/visitor/visitorMain.tsx");
  // before the page in both halves of the site, so the keyboard and a screen reader meet the question first
  assert.ok(app.indexOf("<Tracking />") < app.indexOf("<Routed />"));
  assert.ok(visitor.indexOf("<Tracking />") < visitor.indexOf("<VisitorApp />"));
  // while it stands over the bottom of the page the page's scroll padding is its height, and goes when it does
  assert.match(card, /root\.style\.setProperty\("scroll-padding-bottom", `\$\{el\.offsetHeight \+ 24\}px`\)/);
  assert.match(card, /root\.style\.removeProperty\("scroll-padding-bottom"\)/);
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
