// VR-4 (28 Oct 2026): the visual review of what shipped that day. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("VR4-001: Account's six data cards share the row (3 + 3), not 4 + 2 with the right half of the second row empty", () => {
  const src = read("src/pages/AccountPage.tsx");
  assert.match(src, /import \{ TileGrid \} from "\.\.\/components\/TileGrid";/);
  assert.match(src, /<TileGrid className="k-linkcards" fill>\{DATA\.map/);
  assert.doesNotMatch(src, /<div className="k-linkcards">/);
});

test("VR4-005: the business-update filings' titles start at one x, whatever the width of each date", () => {
  assert.match(read("src/components/BizUpdates.tsx"), /<span className="k-note biz-day">\{day\(f\.at\)\}<\/span> \{tidyTitle\(f\.title\)\}/);
  assert.match(read("src/styles.css"), /\.biz-day \{ display: inline-block; min-width: 6\.5em; font-variant-numeric: tabular-nums; \}/);
});

test("VR4-008: the welcome pop-up no longer says the four spaces, which the tour's first step says straight after", () => {
  const src = read("src/components/LevelPrompt.tsx");
  assert.doesNotMatch(src, /<p className="k-muted">StratLab has four spaces/);
  assert.match(src, /<p className="k-muted welcome-note">\{here \?/);
  assert.match(src, /pick \$\{SPACES\[here\]\.label\} to stay, or another to open its home\./);           // the part that is about where they are stays
});

test("VR4-011: the Invest breadth card dates nothing under its figures when all three are today's (the rule itself is in breadth-thrusts.test.mjs)", () => {
  const src = read("src/lib/breadth.ts");
  assert.match(src, /if \(d\.today\?\.day === live\.day\) return null;/);
  assert.doesNotMatch(src, /sameDay \? `Today, /);
});

test("VR4-012: the cookie question's two buttons are one width", () => {
  assert.match(read("src/styles.css"), /\.consent-btns \.btn \{ min-width: 104px; justify-content: center; \}/);
});

test("VR4-013: the company page does not say the one-line description and the entry's first sentence both, nor 'Listed' under the heading that says it", () => {
  const src = read("src/pages/Research.tsx");
  assert.match(src, /wiki\?\.description && !\(wiki\.extract && wiki\.extract\.toLowerCase\(\)\.includes\(wiki\.description\.toLowerCase\(\)\)\) && <p className="k-sub">/);
  assert.match(src, /const shownFacts = c\.facts\.filter\(\(f\) => !\/market cap\/i\.test\(f\.label\) && !\(\/\^listed\$\/i\.test\(f\.label\) && f\.value\.includes\(c\.symbol\)\)\);/);
  assert.match(src, /rows=\{shownFacts\}/);
});

test("VR4-014: My space's watchlist card has a title short enough to stay on one line beside Open at 1280px", () => {
  const src = read("src/pages/MineHome.tsx");
  assert.match(src, /every\(\(m\) => day\(m\)\) \? "Your watchlist" : "Your watchlist today"/);
  assert.doesNotMatch(src, /Your watchlist, last session/);
});

test("VR4-owner-1: every tile of My space's Markets card is coloured by its own direction, the dollar and gold like the indices", () => {
  const mine = read("src/lib/mine.ts"), home = read("src/pages/MineHome.tsx");
  assert.doesNotMatch(mine, /neutral\?: boolean|neutral: true/);
  assert.match(mine, /\{ id: "usdinr", label: "USD\/INR", from: \{ instrument: "FX:USDINR=X" \}, fmt: fixed\(2\) \}/);
  assert.match(mine, /\{ id: "gold", label: "Gold", from: \{ instrument: "CMDTY:GC=F" \}, fmt: fixed\(0, "\$"\), unit: "\$\/oz" \}/);
  assert.doesNotMatch(home, /t\.neutral/);
  assert.match(home, /<Delta value=\{s\.changePct\}>\{pct\(s\.changePct, 2\)\}<\/Delta>/);
  assert.match(home, /<Spark values=\{s\.values\} tone=\{s\.changePct != null && s\.changePct < 0 \? "down" : "up"\}/);
});
