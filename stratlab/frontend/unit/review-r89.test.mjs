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

test("R86-004: in a phone-wide window the filter chips and the chart's tool buttons are 44px, as on a touch screen", () => {
  const css = read("src/styles.css");
  const phone = css.indexOf("@media (max-width: 640px) { .k-chip { height: 44px; } }");
  assert.ok(phone > css.indexOf(".k-chip { flex: none; height: 32px;"));                 // after the 32px rule it overrides
  const chart = read("src/charts/price/priceChart.css");
  assert.match(chart, /@media \(max-width: 640px\) \{\s*\.pc-btn, \.pc-sel, \.pc-seg \.pc-btn \{ min-height: 44px; \}\s*\.pc-btn\.icon \{ width: 44px; \}/);
  // nothing under 44px in a touch rule (R13S-011: a 40px rule after the touch screen's 44px one shrank the iPad's buttons)
  assert.ok(!chart.includes("@media (max-width: 640px), (pointer: coarse)"));
  assert.ok(!css.includes(".k-chip { height: 40px; }"));
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

test("R89-005: the previous close shows after the close and while prints settle, not only while the market trades", () => {
  const src = read("src/components/Research.tsx");
  assert.match(src, /\{!preOpen && q\.change != null && <span className="k-note" data-testid="price-prev">Previous close \{price\(q\.price - q\.change, currency\)\}<\/span>\}/);
  assert.doesNotMatch(src, /!closed && !preOpen && !settling && q\.change != null && <span className="k-note" data-testid="price-prev">/);
});

test("R89-006: a price scale whose margin reaches under zero labels no gridline below zero; percent and signed studies keep theirs", async () => {
  const { ValueScale } = await import("../src/charts/price/scales.ts");
  const s = new ValueScale();
  s.top = 0; s.height = 400;
  s.fit(0.1, 350, 0.1, 0.22);                         // AAPL monthly since 1980, with the volume band under it
  assert.ok(s.lo < 0);                                 // the margin itself still reaches below zero (the bars keep their room)
  const t = s.ticks();
  assert.ok(t.length >= 3 && t.every((v) => v >= 0), String(t));
  const m = new ValueScale();
  m.top = 0; m.height = 400;
  m.fit(-2, 3);                                         // MACD: a signed study keeps its negative lines
  assert.ok(m.ticks().some((v) => v < 0));
  const p = new ValueScale();
  p.mode = "percent"; p.base = 100; p.top = 0; p.height = 400;
  p.fit(90, 120);                                       // percent mode: −10% is a real line
  assert.ok(p.ticks().some((v) => v < 100));
});

test("R90-005: the watchlist's price column says last session whenever the tab's market is shut, not only when a quote is dated", () => {
  const src = read("src/pages/Research.tsx");
  assert.match(src, /const shut = \(\(\) => \{ const m = markets\.find\(\(x\) => x\.id === region\); return m \? !marketState\(m\)\.open : false; \}\)\(\);/);
  assert.match(src, /header: `Price · \$\{shut \|\| Object\.values\(quotes \?\? \{\}\)\.some\(\(q\) => sessionOf\(q, marketTz\(region\)\)\) \? "last session" : "today"\}`/);
});

test("R90-008/010/012: a US company's move says its day after the close; Pulse and the money calendar say what their dates are", () => {
  assert.match(read("src/components/Research.tsx"), /closed && \(q\.change_day \|\| quoteDay\) \? `on \$\{fmtDate\(\(q\.change_day \|\| quoteDay\)!, \{ year: false \}\)\}` : since/);
  assert.match(read("src/pages/Research.tsx"), /title=\{pulseClosedDay\(data\?\.indices\) \? "How the market felt at the last close" : "How the market feels today"\}/);
  assert.match(read("src/pages/money/MoneyCalendarPage.tsx"), /asOfLabel="As of"/);
});
