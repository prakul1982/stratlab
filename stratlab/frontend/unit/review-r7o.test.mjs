// Round 7, the owner's review on the live site (9 Oct 2026): frontend side, each on the reviewer's real example.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Red flags and the breadth card open on the reader's own market (R7O-003, R6O-007 residue)", async () => {
  const { homeRegion } = await import("../src/lib/homeMarket.ts");
  assert.equal(homeRegion("Asia/Kolkata"), "IN");
  assert.equal(homeRegion("Asia/Riyadh"), "IN");
  assert.equal(homeRegion("UTC"), "IN");
  assert.equal(homeRegion("America/New_York"), "US");
  assert.match(read("src/pages/ResearchScans.tsx"), /useRegion\(homeRegion\(\)\)/);
  const card = read("src/components/BreadthCard.tsx");
  assert.match(card, /const region = homeRegion\(\)/);
  assert.doesNotMatch(card, /savedRegion/);                       // an old S&P 500 pick or a US company look-up doesn't move it
  // an old pick stored for the US never opens India's card on the S&P 500
  const store = new Map([["stratlab.breadth", JSON.stringify({ group: "sp500", range: "1y" })]]);
  globalThis.localStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  const { savedPick } = await import("../src/lib/breadthPick.ts");
  assert.equal(savedPick("IN").group, "nifty500");
});

test("Admin: a running job says Running on Overview too, and only errors since the start count as since the restart (R7O-006)", async () => {
  const { attention, errorCounts, lights } = await import("../src/pages/admin/attention.ts");
  const job = { id: "breadth", name: "Market breadth", schedule: "x", last_run: new Date(Date.now() - 21 * 60_000).toISOString(), error: null, state: "ok", running: true, log: [], run: [] };
  const sv = { server: { kite_ready: true, kite_token_day: null, feed_connected: false, live_sessions: 0, india_sessions: 0,
    auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, ai: [], research: { finnhub: true },
    recent_errors: [{ ref: "a", at: "2026-09-25T10:00:00+05:30" }, { ref: "b", at: "2026-10-09T09:00:00+05:30" }],
    server_started_at: "2026-10-09T01:00:00+05:30" }, stats: {} };
  assert.match(lights(sv, [job]).feeds[0].detail, /^Running · Last run/);
  assert.deepEqual(errorCounts(sv.server), { since: 1, before: 1 });
  assert.deepEqual(errorCounts({ recent_errors: [{ at: "2026-09-25T10:00:00+05:30" }] }), { since: 0, before: 1 });   // an older server: never "since the restart"
  assert.ok(attention(sv, null, [job]).some((a) => a.text === "1 server error since the last restart."));
});

test("Plans: a price converted from the rupee charge says so; dollars stay as set (R7O-008)", async () => {
  const { approx } = await import("../src/lib/approx.ts");
  const sar = { symbol: "SAR ", basic: 27, pro: 77, charged_in: "INR", converted: true };
  assert.equal(approx(sar, "INR"), "≈ ");
  assert.equal(approx({ ...sar, symbol: "$", converted: false }, "INR"), "");   // dollars: $8 and $20 as the owner set them
  assert.equal(approx(sar, "SAR"), "");                          // charged in riyals: the amount is the charge itself
  assert.match(read("src/pages/PlansPage.tsx"), /shown: approx\(row, chargedIn\) \+ money/);
});

test("A paper session's minute-by-minute value across days is labelled by day, never one day's clock times (R7O-010)", async () => {
  const { dayTicks, spansDays } = await import("../src/lib/chartFormat.ts");
  const t = [];
  for (const d of ["2026-10-07", "2026-10-08", "2026-10-09"]) for (const h of ["09:15", "12:00", "15:29"]) t.push(Date.parse(`${d}T${h}:00+05:30`));
  assert.ok(spansDays(t[0], t[t.length - 1], "Asia/Kolkata"));
  assert.ok(!spansDays(t[0], t[2], "Asia/Kolkata"));
  assert.deepEqual(dayTicks(t, 0, t.length - 1, "Asia/Kolkata"), [{ i: 0, label: "7 Oct" }, { i: 3, label: "8 Oct" }, { i: 6, label: "9 Oct" }]);
  assert.match(read("src/components/chart/XYChart.tsx"), /intraday && spansDays\(ta, tb, p\.tz\)/);
});

test("Phone and accessibility: + Custom beside its row, 32px ticks, an h1 while a page loads and on a gone strategy (R7O-010)", () => {
  const chips = read("src/components/kit/ChipBar.tsx");
  assert.match(chips, /<\/div>\s*\{custom && <button ref=\{opener\}/);          // outside the scrolling row
  const css = read("src/styles.css");
  assert.match(css, /\.k-chiprow \{ display: flex/);
  assert.match(css, /input\[type=checkbox\], input\[type=radio\],[\s\S]{0,200}width: 32px; height: 32px/);
  assert.match(read("src/main.tsx"), /<h1 className="sr-only">Opening the page<\/h1>/);
  assert.match(read("src/pages/PublicLibrary.tsx"), /<h1 className="k-h1">This strategy isn't available<\/h1>/);
});

test("The rule line reads \"3% stop\", never \"3 % stop\" (R6O-010 leftover)", () => {
  const rules = read("src/components/Rules.tsx");
  assert.match(rules, /\{stopType === "pct" \? "" : " "\}\{unitTok\("stop"\)\}/);
  assert.match(rules, /\{tgtType === "pct" \? "" : " "\}\{unitTok\("tgt"\)\}/);
});

test("Small things: the trade card names its figure, Mine names the US part of today, a bank's quarters, the class move, a removable snapshot (R7O-012, R7O-013)", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /net after charges/);
  assert.match(read("src/pages/MineHome.tsx"), /usTodayNote\(markets, h\.us, h\.usd_inr\)/);
  const research = read("src/components/Research.tsx");
  assert.match(research, /bank \? "Financing margin" : "EBITDA margin"/);
  assert.match(research, /s\.note \? ` \$\{s\.note\}` : ""/);
  const nw = read("src/pages/money/NetWorthPage.tsx");
  assert.match(nw, /\/money\/net-worth\/history\/\$\{encodeURIComponent\(d\)\}/);
  assert.match(nw, /Remove the snapshot of/);
  assert.match(read("src/pages/EtfGapsPage.tsx"), /nav_doubtful/);
  assert.match(read("src/pages/Screens.tsx"), /"Oldest close" : "Prices as of"/);
});
