// fix11 (17 Nov 2026): open LIVE10A / LIVE10B / CX2 findings. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10A-025: a weekly date axis ticks on Mondays, seven days apart; Flows places its days by date", async () => {
  const { timeTicks } = await import("../src/lib/chartFormat.ts");
  const ticks = timeTicks(Date.UTC(2026, 9, 6), Date.UTC(2026, 10, 16), 7, "Asia/Kolkata", true);
  assert.deepEqual(ticks.map((t) => t.label), ["12 Oct", "19 Oct", "26 Oct", "2 Nov", "9 Nov", "16 Nov"]);
  for (let k = 1; k < ticks.length; k++) assert.equal(ticks[k].t - ticks[k - 1].t, 7 * 86400000);
  assert.match(read("src/pages/FlowsPage.tsx"), /x=\{shown\.map\(\(p\) => Date\.parse\(`\$\{p\.day\.slice\(0, 10\)\}T00:00:00Z`\)\)\}/);
});

test("LIVE10A-036: Briefs reads the other market's list ahead and paints a list it has read at once", () => {
  const page = read("src/pages/NewsPage.tsx");
  assert.match(page, /const seen = new Map<string, IssueRow\[\]>\(\);/);
  assert.match(page, /setList\(had \? \{ tab, rows: had \} : null\);/);
  assert.match(page, /if \(tab !== "mine" && !seen\.has\(other\)\) readList\(other\)/);
});
