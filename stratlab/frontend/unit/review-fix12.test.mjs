// fix12 (17 Nov 2026): what fix11 left of LIVE10A / LIVE10B / CX2. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10A-010: the headlines card asks again while the read shown is the session's earlier one, and says so", async () => {
  const { pulseAskAgain, PULSE_AI_TRIES } = await import("../src/lib/pulseMood.ts");
  assert.equal(pulseAskAgain(0, { updating: true }), true);
  assert.equal(pulseAskAgain(0, { updating: false }), false);
  assert.equal(pulseAskAgain(0, null, "The read is being written now. It fills in here in a moment."), true);
  assert.equal(pulseAskAgain(PULSE_AI_TRIES, { updating: true }), false);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /if \(mine === seq\.current && pulseAskAgain\(tries, out\)\) setTimeout/);
  assert.match(page, /\{ai\.updating && <p className="k-note" data-testid="pulse-ai-updating">\{PULSE_UPDATING_NOTE\}<\/p>\}/);
});

test("LIVE10A-027: a chart's range chips are one scrolling line on a phone, '+ Custom' beside them, not 'All' alone on a second line", () => {
  const bar = read("src/components/kit/ChipBar.tsx");
  assert.match(bar, /const wrapRow = !oneLine && \(wrap \|\| all\.length <= 12\);/);
  assert.match(read("src/components/kit/RangeChips.tsx"), /<ChipBar label=\{label\} options=\{options\} value=\{value\} onChange=\{onChange\} oneLine/);
  assert.match(read("src/pages/BreadthPage.tsx"), /<ChipBar oneLine label="History charts' range"/);
});

test("LIVE10A-027: Breadth on a phone folds its later measures, the sectors and the last 20 days under their headings (nothing removed)", () => {
  const page = read("src/pages/BreadthPage.tsx");
  assert.match(page, /const phone = usePhone\(\);/);
  assert.match(page, /<PhoneFold phone=\{phone\} title="More breadth measures" meta="6 charts" testId="breadth-more">/);
  assert.match(page, /<FoldCard title=\{SECTORS_TITLE\} info=\{help\.sectors\} meta=\{`\$\{data\.sectors\.rows\.length\} sectors`\}/);
  assert.match(page, /<FoldCard title=\{RECENT_TITLE\} info=\{RECENT_INFO\}/);
  // every chart is still drawn: six inside the fold, four above it
  const more = page.slice(page.indexOf('title="More breadth measures"'), page.indexOf("</PhoneFold>"));
  assert.equal((more.match(/<Box title=/g) || []).length, 6);
  assert.equal((page.slice(0, page.indexOf('title="More breadth measures"')).match(/<Box title=/g) || []).length, 4);
});

test("CX2: a filing the exchange listed more than once is one row on the company page that says so", () => {
  assert.match(read("src/components/Filings.tsx"), /\(i\.copies \?\? 1\) > 1 && <span className="k-note" data-testid="filing-copies"> · listed \{i\.copies\} times by the exchange<\/span>/);
});
