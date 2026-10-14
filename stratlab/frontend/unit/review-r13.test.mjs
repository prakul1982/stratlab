// Round 13 review: the US close and the US brief, watched live on Fri 9 Oct 2026 (16:00 ET is 20:00 UTC). The app's side.
// Every clock here is a fixed instant; no weekday or time of day matters. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

const US = { id: "US", tz: "America/New_York", hours: { open: "09:30", close: "16:00", days: "Mon–Fri" }, holidays: [] };
const at = (h, m, day = 9) => new Date(Date.UTC(2026, 9, day, h, m));          // UTC
const dayText = (iso) => `${Number(iso.slice(8, 10))} ${["Sep", "Oct"][Number(iso.slice(5, 7)) - 9]}`;

test("R13-001: BRK.B is written BRK-B, and the company page moves to that address", async () => {
  const { canonTicker } = await import("../src/lib/research.ts");
  assert.equal(canonTicker("US", "BRK.B"), "BRK-B");
  assert.equal(canonTicker("US", "brk.b"), "BRK-B");
  assert.equal(canonTicker("US", "BF/B"), "BF-B");
  assert.equal(canonTicker("US", "BRK-B"), "BRK-B");
  assert.equal(canonTicker("US", "BAC.PRL"), "BAC.PRL");            // a preferred series is not a share class
  assert.equal(canonTicker("IN", "m&m"), "M&M");
  const page = read("src/pages/Research.tsx");
  assert.match(page, /const sym = canonTicker\(region, symbol\)/);
  assert.match(page, /if \(moved\) nav\(`\/research\/\$\{region\}\/\$\{encodeURIComponent\(sym\)\}/);
});

test("R13-002: a currency option with no live quote isn't priced, and the spot rate is named", async () => {
  const { spotText, levelText } = await import("../src/lib/options.ts");
  assert.equal(spotText("USDINR", 96.76, 0.0025, "spot"), "USDINR ₹96.7600 (the spot rate: the future has no live quote)");
  assert.equal(spotText("USDINR", 96.135, 0.0025, "quote"), "USDINR ₹96.1350");
  assert.equal(spotText("NIFTY", 25012.3, 0.05, "quote"), "NIFTY ₹25,012.30");
  // breakevens at the contract's tick (93.94 and 98.31 were shown "94 and 98")
  assert.equal(levelText(93.94, 0.0025), "93.9400");
  assert.equal(levelText(98.3137, 0.0025), "98.3125");
  const page = read("src/pages/OptionsPage.tsx");
  assert.match(page, /preview && !!preview\.no_live && <Notice tone="warn" role="status" className="opt-no-live">/);
  assert.match(page, /preview && preview\.units !== 0 && !preview\.no_live && <Payoff/);
  assert.match(page, /p\?\.no_live \? "no live quote" : "no quote"/);
  assert.match(page, /outside = \(v: number \| null, x: number\) => v != null && \(x < lo \|\| x > hi\) \? levelText\(x, p\.tick\)/);
});

test("R13-003: a Market Brief's stamp is its close, and the US brief's promised time is 4:50 PM", async () => {
  const { issueStamp } = await import("../src/lib/news.ts");
  assert.equal(issueStamp({ kind: "market", region: "US", day: "2026-10-09" }, "9 Oct 2026, 16:32 ET"), "the 16:00 ET close of 9 Oct 2026");
  assert.equal(issueStamp({ kind: "market", region: "IN", day: "2026-10-09" }, "9 Oct 2026, 16:15 IST"), "the 15:30 IST close of 9 Oct 2026");
  assert.equal(issueStamp({ kind: "my_stocks", region: null, day: "2026-10-09" }, "9 Oct 2026, 16:16 IST"), "9 Oct 2026, 16:16 IST");
  assert.match(read("src/components/NewslettersCard.tsx"), /the US about 4:50 PM New York time once the closing prices have settled/);
  const vercel = JSON.parse(read("vercel.json"));
  assert.ok(vercel.rewrites.some((r) => r.source === "/news-link/:issue/:n" && /\/news-link\/:issue\/:n$/.test(r.destination)));
});

test("R13-004: the US tab never shows India's brief, and its own issue is open and highlighted", async () => {
  const { issueTab, issueToShow } = await import("../src/lib/news.ts");
  assert.equal(issueTab("market.US.2026-10-08"), "US");
  assert.equal(issueTab("market.IN.2026-10-09"), "IN");
  assert.equal(issueTab("my_stocks.u-1.2026-10-09-weekly"), "mine");
  assert.equal(issueTab("nonsense"), null);
  const us = [{ id: "market.US.2026-10-08" }, { id: "market.US.2026-10-07" }];
  // 20:24 UTC on 9 Oct: India's issue open, the US tab picked before the day's US issue exists
  assert.equal(issueToShow("US", us, "market.IN.2026-10-09", true), "market.US.2026-10-08");
  assert.equal(issueToShow("US", us, "market.IN.2026-10-09", false), null);          // a phone: the list, no stale pane
  assert.equal(issueToShow("US", null, "market.IN.2026-10-09", true), null);         // the list still loading: nothing shown
  assert.equal(issueToShow("US", [], "market.IN.2026-10-09", true), null);           // no US issue at all: the empty state
  assert.equal(issueToShow("US", us, "market.US.2026-10-07", true), "market.US.2026-10-07");   // a pick of this tab's stands
  const page = read("src/pages/NewsPage.tsx");
  assert.match(page, /const rows = list && list\.tab === tab \? list\.rows : null;/);
  assert.match(page, /aria-current=\{shown === r\.id \? "true" : undefined\}/);
  assert.match(page, /<IssueView id=\{shown\} \/>/);
});

test("R13-005: a US price between the close and its settle point says it is still settling, everywhere", async () => {
  const { priceLabel, settlingNow, SETTLING, closeLabel } = await import("../src/lib/research.ts");
  assert.equal(SETTLING, "Latest, closing prints still settling");
  assert.deepEqual(priceLabel({ market_open: false, phase: "settling" }), { label: SETTLING, since: "on the day" });
  assert.deepEqual(priceLabel({ market_open: false, phase: null }), { label: "Last close", since: "on the day" });
  assert.equal(settlingNow(US, at(20, 12)), true);                 // 16:12 ET
  assert.equal(settlingNow(US, at(20, 44)), true);
  assert.equal(settlingNow(US, at(20, 45)), false);                // 16:45 ET: settled
  assert.equal(settlingNow(US, at(19, 59)), false);
  assert.equal(settlingNow(US, at(20, 12, 10)), false);            // Saturday
  assert.equal(settlingNow({ ...US, holidays: ["2026-10-09"] }, at(20, 12)), false);
  assert.equal(settlingNow({ ...US, id: "IN", tz: "Asia/Kolkata", hours: { close: "15:30" } }, at(10, 5)), false);
  assert.equal(closeLabel("2026-10-09", { settling: true, dayText }), "Latest, closing prints still settling · 9 Oct");
  assert.match(read("src/components/Research.tsx"), /\{settling && <span className="k-stat-k">\{SETTLING\}<\/span>\}/);
  assert.match(read("src/pages/Research.tsx"), /settling=\{c\.phase === "settling"\}/);
  assert.match(read("src/pages/Research.tsx"), /data-testid="watch-settling">\{SETTLING\}/);
});

test("R13-007: after the close every price says 'Last close, 9 Oct', and the alert says when it is next checked", async () => {
  const { closeLabel, sessionClosed } = await import("../src/lib/research.ts");
  assert.equal(closeLabel("2026-10-09", { dayText }), "Last close, 9 Oct");
  assert.equal(closeLabel("2026-10-09", { open: true, dayText }), null);
  assert.equal(closeLabel(null, { dayText }), null);
  assert.equal(sessionClosed("2026-10-09", "2026-10-09", false), true);
  assert.equal(sessionClosed("2026-10-09", "2026-10-09", true), false);
  assert.equal(sessionClosed("2026-10-08", "2026-10-09", true), true);
  assert.match(read("src/pages/ResearchScans.tsx"), /data-testid="scan-price-day">Prices: \{label\}/);

  const { alertPriceHint } = await import("../src/lib/alerts.ts");
  assert.equal(alertPriceHint("AAPL", "$336.64", null), "AAPL is at $336.64 now");
  assert.equal(alertPriceHint("AAPL", "$336.64", { day: "9 Oct", next: "Mon 12 Oct" }),
    "AAPL, last close, 9 Oct: $336.64 · Market closed · next check Mon 12 Oct, market open");
  assert.equal(alertPriceHint(null, "$336.64", { day: "9 Oct", next: "Mon 12 Oct" }),
    "Last close, 9 Oct: $336.64 · Market closed · next check Mon 12 Oct, market open");
  assert.equal(alertPriceHint(null, "$336.64", null), "Now $336.64");

  const { pulseLede, pulseClosedDay } = await import("../src/lib/researchFormat.ts");
  assert.equal(pulseLede(null, "9 Oct"), "Last close, 9 Oct: index levels and headlines, with an AI read of the mood.");
  assert.equal(pulseLede(null), "Live index levels and headlines, with an AI read of the mood.");
  assert.equal(pulseClosedDay([{ live: false, day: "2026-10-09" }, { live: false, day: "2026-10-09" }]), "2026-10-09");
  assert.equal(pulseClosedDay([{ live: true, day: "2026-10-09" }, { live: false, day: "2026-10-09" }]), null);
  assert.equal(pulseClosedDay([]), null);

  const { tileWhen, tileMarket, MARKET_TILES } = await import("../src/lib/mine.ts");
  assert.equal(tileWhen("2026-10-09", "2026-10-09", dayText, true), "on 9 Oct");      // the S&P 500 after its close, as India's tiles
  assert.equal(tileWhen("2026-10-09", "2026-10-09", dayText, false), null);          // while it trades: today's move
  assert.equal(tileMarket(MARKET_TILES.find((t) => t.id === "sp500")), "US");
  assert.equal(tileMarket(MARKET_TILES.find((t) => t.id === "usdinr")), null);
});

test("R13-009: a prior day revised by a later run is said beside the numbers", async () => {
  const { revisionLines } = await import("../src/lib/breadth.ts");
  const r = (adv, dec, unch) => ({ adv, dec, unch });
  assert.deepEqual(revisionLines([{ day: "2026-10-08", before: r(337, 163, 1), after: r(338, 163, 1) }], dayText),
    ["8 Oct revised: 338 rose, 163 fell, 1 unchanged (was 337, 163, 1)"]);
  // two runs: from the first count to the last
  assert.deepEqual(revisionLines([{ day: "2026-10-08", before: r(337, 163, 1), after: r(338, 163, 1) },
    { day: "2026-10-08", before: r(338, 163, 1), after: r(339, 162, 1) }], dayText), ["8 Oct revised: 339 rose, 162 fell, 1 unchanged (was 337, 163, 1)"]);
  assert.deepEqual(revisionLines([{ day: "2026-10-08", before: r(1, 2, 3), after: r(2, 2, 3) }, { day: "2026-10-08", before: r(2, 2, 3), after: r(1, 2, 3) }], dayText), []);
  assert.deepEqual(revisionLines(undefined, dayText), []);
  assert.match(read("src/pages/BreadthPage.tsx"), /data-testid="breadth-revised"/);
});

test("R13-012: the holidays read failing with months on file is one Check, said the Services light's way", async () => {
  const { attention, services, holidaysDown } = await import("../src/pages/admin/attention.ts");
  const ov = { server: { kite_ready: true, kite_token_day: null, feed_connected: true, live_sessions: 0, india_sessions: 0,
    auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, ai: [], research: { finnhub: true },
    recent_errors: [], server_started_at: "2026-10-09T01:00:00+05:30", calendar: { days_left: 83 } }, stats: {} };
  const job = { id: "holidays", name: "Exchange holidays", schedule: "Every day", last_run: null, error: "Couldn't reach the exchange.",
    state: "warn", running: false, log: [], run: [], note: "Holidays on file for 83 more days · live feed down" };
  assert.equal(holidaysDown(job), true);
  assert.equal(holidaysDown({ ...job, error: null, state: "warn" }), false);
  const cal = services(ov, [job]).find((s) => s.key === "cal");
  assert.deepEqual([cal.state, cal.detail], ["warn", "Holidays on file for 83 more days · live feed down"]);
  const todo = attention(ov, null, [job]).map((a) => a.text);
  assert.ok(todo.includes("Exchange holidays: holidays on file for 83 more days · live feed down. Couldn't reach the exchange."), todo.join("\n"));
  assert.ok(!todo.some((t) => /data feeds? on Check/.test(t)), todo.join("\n"));       // said once, not again among the feeds
});
