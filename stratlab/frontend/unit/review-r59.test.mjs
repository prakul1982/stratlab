// Round 59 (19 Oct 2026): plan views, emails and Safari — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

/** matchMedia answering as a device would: `fine` pointer or not, and the screen's width. */
const device = (fine, width) => (q) => ({ matches: q.includes("pointer: fine") ? fine : q.includes("max-width: 640px") ? width <= 640 : false });

test("R59-001: the company search takes the cursor on a desktop with a mouse, never on a phone or a touch screen", async () => {
  const { typingFirst } = await import("../src/lib/typingFirst.ts");
  const was = globalThis.matchMedia;
  try {
    globalThis.matchMedia = device(true, 1280);
    assert.equal(typingFirst(), true);
    globalThis.matchMedia = device(false, 390);        // a phone
    assert.equal(typingFirst(), false);
    globalThis.matchMedia = device(false, 1194);       // an iPad
    assert.equal(typingFirst(), false);
    globalThis.matchMedia = device(true, 400);         // a narrow window with a mouse: the box sits under the fold
    assert.equal(typingFirst(), false);
    delete globalThis.matchMedia;
    assert.equal(typingFirst(), false);
  } finally {
    globalThis.matchMedia = was;
  }
  // the Invest home's search (both of its boxes) and the Trade home's go through it
  assert.equal((read("src/pages/Research.tsx").match(/autoFocus=\{typingFirst\(\)\}/g) ?? []).length, 2);
  // the Invest home has no search box of its own: Look up a company is the one (DD-002)
  assert.doesNotMatch(read("src/pages/SpaceHomes.tsx"), /<CompanySearch/);
});

test("R59-007: a chip row that wraps keeps + Custom level with its first line", () => {
  assert.match(read("src/components/kit/ChipBar.tsx"), /className=\{`k-chiprow\$\{wrap \? " wrap" : ""\}`\}/);
  assert.match(read("src/styles.css"), /\.k-chiprow\.wrap \{ align-items: flex-start; \}/);
});

test("R59-012: on a phone the homes' countdown is as short as the banner", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.promo-countdown \.promo-full, \.promo-countdown \.promo-plans, \.promo-countdown \.promo-got-text \{ display: none; \}/);
  const src = read("src/components/PromoCountdown.tsx");
  assert.match(src, /<span className="promo-more"> After that, your plan's limits apply again\.<\/span>/);
  assert.match(src, /className="btn sm promo-plans"/);
});

test("R59-005/006: the Free Options lock names the trial; the Pro export is a notebook's", () => {
  assert.match(read("src/pages/OptionsPage.tsx"), /the Free plan's 5-market-day trial is for a notebook's strategy, not options/);
  assert.match(read("src/lib/plans.ts"), /\["export", "Export a notebook's rules and trades"\]/);
});
