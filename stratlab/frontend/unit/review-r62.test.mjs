// Round 62 (19 Oct 2026): the full owner pass on a laptop — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R62-003: an edge that didn't pass every check it ran says how many passed, not 'Passed the checks'", async () => {
  const { badgeLabel } = await import("../src/lib/tradeUi.ts");
  assert.equal(badgeLabel({ verdict: "edge", passed: 2, total: 3 }), "3 of 4 checks run · 2 passed");
  assert.equal(badgeLabel({ verdict: "edge", passed: 4, total: 4 }), undefined);
  assert.equal(badgeLabel({ verdict: "no_edge", passed: 1, total: 4 }), undefined);
  for (const p of ["src/pages/NotebookPage.tsx", "src/pages/CompareExperiments.tsx"])
    assert.match(read(p), /<VerdictBadge v=\{e\.verdict\.verdict\} label=\{badgeLabel\(e\.verdict\)\} \/>/, p);
});

test("R62-002: the words box warns once the rules were changed by hand", () => {
  const src = read("src/components/Rules.tsx");
  assert.match(src, /const \[handEdited, setHandEdited\] = useState\(false\);/);
  assert.match(src, /\{handEdited && <Notice tone="warn"[^>]*>These words are from before you changed the rules by hand\./);
});

test("R62-007: Compare says a whole-year test period in years", async () => {
  const { changes, spanIn } = await import("../src/lib/compare.ts");
  assert.equal(spanIn(1825), "5 years");
  assert.equal(spanIn(365), "1 year");
  assert.equal(spanIn(400), "400 days");
  const s = { tf: "1d", entry: [], exit: [], risk: { capital: 1, sl: 0, tgt: 0 } };
  const out = changes({ strategy: s, instrument: { symbol: "TCS" }, days: 1825 }, { strategy: s, instrument: { symbol: "TCS" }, days: 730 });
  assert.ok(out.includes("Test period: 5 years → 2 years"), out.join(" | "));
});

test("R62-005, R62-011, R62-014: removing says what stays; a saved screen asks first; the library says who publishes", () => {
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /Earlier days in the history chart keep it until you remove that day's snapshot/);
  const screens = read("src/pages/Screens.tsx");
  assert.match(screens, /onClick=\{\(\) => setDropping\(s\)\}><Trash/);
  assert.match(screens, /confirmLabel="Delete this screen"/);
  assert.match(read("src/pages/LibraryPage.tsx"), /Published by StratLab and its users/);
});
