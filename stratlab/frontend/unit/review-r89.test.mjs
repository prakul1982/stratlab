// Round 89 (23 Oct 2026): leftovers from rounds 86–88 — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R88-007: the landing FAQ answers what it costs and how to cancel, in the refunds page's words", async () => {
  const { FAQ, faqText } = await import("../src/content/faq.ts");
  const cost = FAQ.find((f) => f.q === "What does it cost, and can I cancel?");
  assert.ok(cost);
  const a = faqText(cost);
  assert.match(a, /The Free plan costs nothing/);
  assert.match(a, /Account → Plan and usage/);                     // the section's real name, as /refunds says it
  assert.match(read("src/content/legal.ts"), /Account → Plan and usage → Cancel subscription/);
  assert.match(a, /stratlab\.studio\/plans/);
  assert.match(a, /stratlab\.studio\/refunds/);
  assert.doesNotMatch(a, /₹\d|\$\d/);                               // no price written here to go stale; the Plans page has them
});

test("R88-009: the Free card says ₹0 always, not per month or year, on the Plans page and the landing page", () => {
  for (const f of ["src/pages/PlansPage.tsx", "src/pages/Login.tsx"]) assert.match(read(f), /p === "free" \? " always"/, f);
});

test("R86-015: a company's price move keeps its decimals, as the price beside it does", async () => {
  const { signedMove } = await import("../src/lib/format.ts");
  assert.equal(signedMove(2), "+2.00");
  assert.equal(signedMove(0.7), "+0.70");
  assert.equal(signedMove(-1234.5, 2, "US"), "−1,234.50");
  assert.equal(signedMove(-123456.5), "−1,23,456.50");             // India's grouping
  assert.equal(signedMove(0.001), "0.00");                          // rounds to nothing: no sign
  assert.equal(signedMove(null), "–");
  assert.match(read("src/components/Research.tsx"), /signedMove\(q\.change, 2\)/);
});

test("R86-005: a scan running a few seconds says the day's first scan is the slow one", () => {
  const src = read("src/pages/ResearchScans.tsx");
  assert.match(src, /setTimeout\(\(\) => setShow\(true\), 3000\)/);
  assert.match(src, /The day's first scan of a list reads each stock's daily chart, so a long list can take 20 seconds or more\. Scans after that take a second or two\./);
  assert.match(src, /<ScanElapsed count=\{cur\?\.count\} \/><\/p><SlowFirstScan \/>/);
});

test("R86-004: on a phone the filter chips and the chart's tool buttons are 40px targets", () => {
  const css = read("src/styles.css");
  const phone = css.indexOf("@media (max-width: 640px), (pointer: coarse) { .k-chip { height: 40px; } }");
  assert.ok(phone > css.indexOf(".k-chip { flex: none; height: 32px;"));                 // after the 32px rule it overrides
  const chart = read("src/charts/price/priceChart.css");
  assert.match(chart, /@media \(max-width: 640px\), \(pointer: coarse\) \{\s*\.pc-btn, \.pc-sel, \.pc-seg \.pc-btn \{ min-height: 40px; \}\s*\.pc-btn\.icon \{ width: 40px; \}/);
  assert.ok(chart.lastIndexOf("min-height: 40px") > chart.indexOf(".pc-seg .pc-btn { border: 0;"));   // after the 32px rule it overrides
});

test("R89-002: the US prints count as settling for 50 minutes after a traded close, and the rotation page says provisional then", async () => {
  const { usSettling, SETTLE_US_MIN } = await import("../src/lib/marketHours.ts");
  const US = { id: "US", tz: "America/New_York", status: "live", hours: { open: "09:30", close: "16:00", days: "Mon–Fri" }, holidays: [] };
  const IN = { id: "IN", tz: "Asia/Kolkata", status: "live", hours: { open: "09:15", close: "15:30", days: "Mon–Fri" }, holidays: [] };
  assert.equal(SETTLE_US_MIN, 50);
  assert.equal(usSettling(US, new Date("2026-10-23T20:20:00Z")), true);        // 16:20 ET, Fri
  assert.equal(usSettling(US, new Date("2026-10-23T20:55:00Z")), false);       // 16:55 ET: final
  assert.equal(usSettling(US, new Date("2026-10-23T19:50:00Z")), false);       // still open
  assert.equal(usSettling(US, new Date("2026-10-24T20:20:00Z")), false);       // Saturday: nothing traded
  assert.equal(usSettling({ ...US, holidays: ["2026-10-23"] }, new Date("2026-10-23T20:20:00Z")), false);
  assert.equal(usSettling(IN, new Date("2026-10-23T10:10:00Z")), false);       // only the US settles
  assert.equal(usSettling(null), false);
  const src = read("src/pages/ResearchScans.tsx");
  assert.match(src, /asOfLabel=\{provisional \? "Provisional closes \(prints still settling\) up to" : "Closes up to"\}/);
  assert.match(src, /region === "US" && !!out\?\.as_of && out\.as_of\.slice\(0, 10\) === dayIn\(now, marketTz\("US"\)\)/);
  assert.match(read("src/pages/MineHome.tsx"), /usSettling\(id === "US"/);
});

test("R89-003: the tile's long 'closing prints settling' words wrap inside the tile; 'on 16 Oct' stays together", () => {
  assert.match(read("src/pages/MineHome.tsx"), /className=\{w\.includes\("settling"\) \? "k-note" : "k-note nowrap"\} data-testid="mine-mkt-when"/);
});
