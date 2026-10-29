// VR-5 (28 Oct 2026): the visual review of the most-used pages on a phone. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the source's own imports have no .ts ending
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("VR5-001 and VR5-002: the Invest home's eyebrow says something its crumb and title do not, and the breadth card's live words have no second Live pill", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /<Head eyebrow="Invest · companies and markets" title="Invest home">/);
  const card = read("src/components/BreadthCard.tsx");
  assert.doesNotMatch(card, /tone="live"/);
  assert.match(card, /<StatRow>/);                                   // and its three figures go two across on a phone (VR5-006)
});

test("VR5-003: the public library's header button reads 'Sign in' on a small phone, and the logo is never squeezed", () => {
  const src = read("src/pages/PublicLibrary.tsx");
  assert.match(src, /<span className="pub-long">\{label\}<\/span><span className="pub-short" aria-hidden="true">Sign in<\/span>/);
  assert.match(src, /"aria-label": label/);                          // a screen reader still hears "Continue with Google"
  const css = read("src/styles.css");
  assert.match(css, /\.pub-nav > a:first-child \{ flex: none; \}/);
  assert.match(css, /@media \(max-width: 400px\) \{ \.pub-nav \.pub-long \{ display: none; \} \.pub-nav \.pub-short \{ display: inline; \} \}/);
  assert.match(css, /\.pub-nav \.pub-menu\.pub-menu-start nav \{ left: auto; right: 0; \}/);
});

test("VR5-004: a chip or badge longer than the screen wraps in its own box on a phone instead of pushing the page sideways; the cookie question is smaller", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(max-width: 380px\) \{\n  \.k-badge \{ max-width: 100%; white-space: normal;/);
  assert.match(css, /\.k-chip \{ max-width: 100%; height: auto; min-height: 44px;/);
  assert.match(css, /\.consent \{ right: 12px; left: 12px; .* font-size: 13px;/);
  assert.match(css, /\.consent-btns \.btn \{ flex: 1 1 0; min-width: 0; \}/);          // still one width for Allow and No thanks (VR4-012)
});

test("VR5-005: the words of a notebook's rules and the Invest red flags' symbols are bigger to tap on a phone", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.token \{ padding: 6px 10px; \}/);
  assert.match(css, /\.add-rule \{ min-height: 44px;/);
  assert.match(css, /\.space-flag > a\.link \{ display: inline-flex; align-items: center; min-height: 44px; \}/);
});

test("VR5-006: a row of figures goes two across on a phone when each fits its half on one line", () => {
  const src = read("src/components/kit/Stat.tsx");
  assert.match(src, /function useDuo/);
  assert.match(src, /classList\.add\("duo"\)/);
  assert.match(src, /if \(wraps \|\| uneven\) \{\n\s*el\.classList\.remove\("duo", "tight"\);/);          // a figure that would wrap keeps the old one-per-row
  const css = read("src/styles.css");
  assert.match(css, /\.k-stats\.duo \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  assert.match(css, /\.k-stats\.duo > \.k-stat:last-child:nth-child\(odd\) \{ grid-column: 1 \/ -1; \}/);
});

test("VR5-010: 'Only 11 trades: too few to judge.' under the verdict headline and 'Only 11 trades in this period.' in the summary are one statement", async () => {
  const { heroSummary } = await import("../src/lib/tradeUi.ts");
  const few = "Only 11 trades in this period. That's too few to tell a real edge from a lucky streak, whatever the return says.";
  assert.deepEqual(heroSummary(few, "Only 11 trades: too few to judge."), ["That's too few to tell a real edge from a lucky streak, whatever the return says."]);
  assert.deepEqual(heroSummary(few, ""), ["Only 11 trades in this period.", "That's too few to tell a real edge from a lucky streak, whatever the return says."]);
});

test("VR5-011: a hyphenated word in a plan table's note stays whole, so '(5-market-day trial)' is two lines, not five", () => {
  assert.match(read("src/components/PlanCompare.tsx"), /split\(\/\(\\S\+-\\S\+\)\/\)\.map\(\(x, i\) => \(i % 2 \? <span key=\{i\} className="k-nowrap">/);
  assert.match(read("src/styles.css"), /\.k-nowrap \{ white-space: nowrap; \}/);
});

test("VR5-012: the business-update chart's axis names only the period; the note that a figure was stated a year later stays in the hover text", () => {
  const src = read("src/components/BizUpdates.tsx");
  assert.match(src, /axisLabels=\{pts\.map\(\(p\) => periodName\(p\.period, m\.span\)\)\}/);
  assert.match(src, /\(as stated a year later\)/);
});

test("VR5-014: on a phone the tile picker's tiles are rows with the picture beside the words", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(max-width: 640px\) \{\n  \.k-tiles \{ grid-template-columns: minmax\(0, 1fr\); gap: 8px; \}/);
  assert.match(css, /\.k-tile \{ display: grid; grid-template-columns: 34px minmax\(0, 1fr\);/);
});

test("VR5-015: a fold's 'what is inside' line takes its own line under its title on a phone", () => {
  assert.match(read("src/styles.css"), /\.k-disclosure > summary \.k-more-what \{ flex: 1 0 100%;/);
});

test("VR5-owner-1: the Invest home's watchlist shows six, with See all in its header for a longer list, and no market label over the stocks", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.match(src, /export const WATCH_SHOWN = 6;/);
  assert.match(src, /symbols=\{by\(r\)\.slice\(0, WATCH_SHOWN\)\.map/);
  assert.match(src, /\(by\(region\)\.length > WATCH_SHOWN\) && <Link to="\/research\/watchlist" className="link" data-testid="watch-see-all">See all \{by\(region\)\.length\} →<\/Link>/);
  assert.doesNotMatch(src, /<span className="eyebrow">\{REGION_NAME\[r\]\}<\/span>\n\s+<QuoteGrid/);
  assert.match(read("src/styles-invest.css"), /\.inv-tile \{ display: flex; flex-direction: column; gap: 3px; padding: 10px 10px;/);
});
