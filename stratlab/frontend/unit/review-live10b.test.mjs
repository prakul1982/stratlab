// LIVE10B (17 Nov 2026): the live end-to-end review of Release 60. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10B-024: a holdings file naming stocks already held is asked about, and the chosen way is said before reading", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /overlap_ok: overlapOk/);                                         // sent only once the user says so
  assert.match(page, /data-testid="holdings-overlap"/);
  assert.match(page, />Add these shares too</);
  assert.match(page, /setReplacing\(f\); \}\}>Start again with this file</);            // the replace path keeps its confirm
  assert.match(page, /data-testid="holdings-mode-note"/);
  assert.match(page, /you're asked before anything is added/);
});

test("LIVE10B-001: the rupee note names StratLab's US prices and says only rupee prices are charged in rupees", async () => {
  const { usdNote } = await import("../src/lib/usdAbout.ts");
  const note = usdNote(93.56, false, { basic: 8, pro: 20 });
  assert.match(note, /^Prices in ₹ are charged in rupees\./);
  assert.doesNotMatch(note, /Every price is charged in rupees/);
  assert.match(note, /at ₹93\.56 to the dollar \(today's rate\): StratLab's US prices are Basic \$8 and Pro \$20 a month/);
  assert.doesNotMatch(usdNote(93.56), /US prices/);                                   // no US prices read: not named
  for (const p of ["src/pages/PlansPage.tsx", "src/pages/Login.tsx"]) assert.match(read(p), /usdNote\(rate, pricing\?\.usd_inr\?\.fallback, usd\)/);
});

test("LIVE10B-002: the dollar view's yearly small print is in dollars", () => {
  assert.match(read("src/pages/Login.tsx"), /const yearly = \(p: "basic" \| "pro"\) => \(cur === "USD" && usd \? dollarText\(usd\[`\$\{p\}_year`\]\) : rupees\(p, true\)\);/);
});

test("LIVE10B-013: the paper chart's forming candle takes the server's open, high and low", () => {
  const page = read("src/pages/PaperPage.tsx");
  assert.match(page, /forming\.current = \{ t: f\.t, o: f\.o \?\? f\.c, h: f\.h \?\? f\.c, l: f\.l \?\? f\.c \}/);
  assert.match(page, /if \(f\.o != null\) forming\.current\.o = f\.o;/);
});
