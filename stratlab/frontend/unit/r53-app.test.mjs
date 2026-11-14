// Release 53, lane app53: whole-app fixes from the LIVE8A / LIVE8B reviews (frontend side).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE8B-002: a business-update chart puts each point at its month, so unread months are a stretch of the axis", async () => {
  const { monthIndex, monthOf, periodName } = await import("../src/lib/biz.ts");
  assert.equal(monthIndex("2026-06") - monthIndex("2025-10"), 8);       // Oct 2025 → Jun 2026 is eight months, not one step
  assert.equal(monthOf(monthIndex("2026-10")), "2026-10");
  assert.equal(monthOf(monthIndex("2026-01")), "2026-01");
  assert.ok(Number.isNaN(monthIndex("junk")));
  assert.equal(periodName(monthOf(monthIndex("2025-12"))), "Dec 2025");
  const chart = read("src/components/BizUpdates.tsx");
  assert.match(chart, /x: xs, xFormat/);
});

test("LIVE8B-006: the Free plan's change is a Limit / Now / From table on Account, one line on My space", async () => {
  const fc = await import("../src/lib/freeChange.ts");
  const NOTICE = { on: "2026-11-27T00:00:00+05:30", moves: ["The tax report's CSV and PDF downloads move to Basic"],
    rows: [{ key: "ai_reads_per_day", label: "Fresh AI reads a day", before: 60, after: 5 }, { key: "stock_alerts", label: "Stock alerts on at a time", before: 5, after: 3 },
      { key: "group_size", label: "Instruments in a group test", before: 10, after: 10 }] };
  assert.deepEqual(fc.changeRows(NOTICE), [["Fresh AI reads a day", "60", "5"], ["Stock alerts on at a time", "5", "3"]]);
  const comp = read("src/components/FreeChangeNotice.tsx");
  assert.match(comp, /<th scope="col">Limit<\/th>/);
  assert.match(comp, /From \{day\}/);
  assert.match(read("src/pages/MineHome.tsx"), /<FreeChangeNotice line \/>/);
});

test("LIVE8B-007 / LIVE8B-025: Account's kept limits are there from the plan before the counts come, with Plans' words", async () => {
  const acct = await import("../src/lib/account.ts");
  const rows = acct.plannedKept({ stock_alerts: 5, screens: 2, holdings: 30, mf_schemes: 5, networth_items: 5, journal_trades: 50, name: "Free" });
  assert.deepEqual(rows.map((r) => acct.keptRow(r)), [["Stock alerts on", "Up to 5"], ["Saved screens", "Up to 2"], ["Holdings kept", "Up to 30"],
    ["Mutual fund schemes kept", "Up to 5"], ["Net worth entries", "Up to 5"], ["Trades the journal keeps", "The last 50"]]);
  assert.deepEqual(acct.plannedKept(null), []);
  assert.match(read("src/pages/AccountPage.tsx"), /kept \?\? plannedKept\(/);
});

test("LIVE8B-004 / LIVE8A-017: the analytics question comes after the page, once it has drawn; a policy's footer waits for its words", () => {
  const shell = read("src/components/Shell.tsx"), card = read("src/components/Tracking.tsx"), css = read("src/styles.css");
  assert.ok(shell.indexOf("{ask}") > shell.indexOf('<main className="main" id="main"'));
  assert.match(card, /if \(guiding \|\| !settled\) return null;/);
  assert.match(card, /export const ASK_AFTER_LOAD_MS = 1200;/);
  assert.match(css, /\.shell > \.consent \{ grid-column: -2 \/ -1; grid-row: 2;/);
  assert.match(read("src/components/PublicFrame.tsx"), /\{foot && <footer/);
});
