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
