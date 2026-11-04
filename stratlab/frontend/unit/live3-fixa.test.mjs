// LIVE3 review (live, 4 Nov), the FIXA lane's frontend checks.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const T = await import("../src/charts/price/ticks.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// a candle's `w` is its wall-clock time on the exchange's clock, kept as if it were UTC
const wall = (iso) => Date.parse(iso + "Z");

test("LIVE3-011: the chart says Live only while the market is open or a candle is forming now; shut, it says when it last closed", () => {
  const live = { live: true };
  const last15 = { t: wall("2026-11-04T09:45:00"), w: wall("2026-11-04T15:15:00") };
  // every combination: the market shut never says Live, whatever the source says
  for (const f of [{ live: true }, { delayed: true }, { live: true, delayed: true }])
    for (const streaming of [true, false]) for (const forming of [true, false])
      assert.notEqual(T.marketPill(false, f, streaming, forming, last15, "15m", "IN")?.cls, "live");
  assert.equal(T.marketPill(false, live, false, false, last15, "15m", "IN").text, "Closed · last close 4 Nov, 15:30 IST");
  assert.equal(T.marketPill(false, live, false, false, { t: 0, w: wall("2026-11-04T15:15:00") }, "1h", "IN").text, "Closed · last close 4 Nov, 15:30 IST");   // never past the session's close
  assert.equal(T.marketPill(false, live, false, false, { t: 0, w: wall("2026-11-04T00:00:00") }, "1d", "IN").text, "Closed · last close 4 Nov");
  assert.equal(T.marketPill(false, live, false, false, { t: 0, w: wall("2026-11-04T15:59:00") }, "1m", "US").text, "Closed · last close 4 Nov, 16:00 ET");
  assert.equal(T.marketPill(true, live, true, true, last15, "15m", "IN").text, "Live");
  // not told whether the market is open: Live only while the newest candle's window holds now (fresh prices)
  assert.equal(T.marketPill(null, live, false, true, last15, "15m", "IN").text, "Live");
  assert.equal(T.marketPill(undefined, live, false, false, last15, "15m", "IN"), null);
  assert.equal(T.marketPill(true, { delayed: true }, false, false, last15, "15m", "IN").text, "Delayed");
  assert.equal(T.marketPill(true, {}, false, false, last15, "15m", "IN"), null);
});

test("LIVE3-011: every chart with live prices is told its market (the company page's and the workspace's)", () => {
  const research = read("src/components/Research.tsx");
  assert.match(research, /marketOpen=\{open\} market=\{region\}/);
  assert.match(research, /marketState\(market\)\.open/);
  assert.match(read("src/components/watch/ChartWorkspace.tsx"), /marketOpen=\{open\} market=\{item\.market\}/);
  assert.doesNotMatch(read("src/charts/price/PriceChart.tsx"), /text: "Market closed"/);
});

test("LIVE3-018: one rule for a ratio and one for big money, on every page", async () => {
  const F = await import("../src/lib/format.ts");
  assert.equal(F.ratio(0.0016), "<0.01");                  // HAL's debt to equity: never 0.0016, never a zero it isn't
  assert.equal(F.ratio(0), "0.00");
  assert.equal(F.ratio(0.21), "0.21");
  assert.equal(F.ratio(1.4699), "1.47");
  assert.equal(F.ratio(-0.002), "−<0.01");
  assert.equal(F.ratio(null), "–");
  const TF = await import("../src/lib/themeFormat.ts");
  // a market value reads the same in a theme as on the company page, the screens and Compare
  for (const crore of [1137500, 1137449, 37205, 39327.4, 999.6, 120000, 99999.6])
    assert.equal(TF.amount(crore, "IN"), F.bigMoney(crore * 1e7, "INR"), String(crore));
  assert.equal(TF.amount(1137449, "IN"), "₹11.37 lakh cr");
  // every "Market value" column and tile goes through that rule
  const files = ["src/pages/Research.tsx", "src/pages/Screens.tsx", "src/pages/ResultsPage.tsx", "src/pages/CorpActionsPage.tsx", "src/components/ThemeDive.tsx"];
  for (const f of files) {
    for (const line of read(f).split("\n").filter((l) => /"Market value"/.test(l) && /cell:|value=/.test(l)))
      assert.match(line, /bigMoney\(|screenCap\(|amount\(|cap\(r\.market_cap/, `${f}: ${line.trim().slice(0, 120)}`);
  }
  // debt to equity: the ratio rule in the screens and the theme's balance sheet
  assert.match(read("src/pages/Screens.tsx"), /label: "Debt to equity", cell: \(r\) => ratio\(r\.debt_equity\)/);
  assert.match(read("src/components/ThemeDive.tsx"), /med\(bal\.debt_equity, \(v\) => `\$\{ratio\(v\)\}x`\)/);
});

test("LIVE3-006/007: every job stuck or failing is under Needs your attention, with how long it has run", async () => {
  const { attention, runningFor } = await import("../src/pages/admin/attention.ts");
  const sv = { server: { kite_ready: true, kite_token_day: null, feed_connected: false, live_sessions: 0, india_sessions: 0,
    auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, ai: [], research: { finnhub: true },
    recent_errors: [], server_started_at: "2026-10-09T01:00:00+05:30" }, stats: {} };
  const ago = (min) => new Date(Date.now() - min * 60_000).toISOString();
  // the server marks a job stuck (bad, with why) or stalled (warn, with why): whatever the job, it is listed
  const jobs = [
    { id: "breadth", name: "Market breadth", schedule: "x", last_run: ago(900), running: true, running_since: ago(900), state: "bad",
      error: "Stuck: running for 15 h (since 04 Nov 03:35 IST), longer than any run takes.", log: [], run: [] },
    { id: "ipo", name: "IPOs", schedule: "x", last_run: ago(5), running: false, state: "warn",
      error: "Offer documents: no summary written today (67 waiting). The last pass failed: the AI couldn't answer.", log: [], run: [] },
    { id: "anything", name: "Any other job", schedule: "x", last_run: ago(5), running: false, state: "bad", error: "It failed.", log: [], run: [] },
  ];
  const said = attention(sv, null, jobs).map((a) => a.text).join("\n");
  assert.match(said, /Market breadth: Stuck: running for 15 h/);
  assert.match(said, /IPOs \(Offer documents: no summary written today/);
  assert.match(said, /Any other job: It failed\./);
  assert.equal(runningFor({ running: true, running_since: ago(12) }), "Running for 12 min");
  assert.equal(runningFor({ running: true, running_since: null }), "Running");
  assert.equal(runningFor({ running: false, running_since: ago(12) }), "");
});
