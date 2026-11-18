// Lane fix18: the LIVE13A review's market, calendar, panel and phone findings.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE13A-012/-029: the heatmap and movers say live prices, the day's last trades, or that the latest closes are being added", async () => {
  const { dayLine } = await import("../src/lib/heatmap.ts");
  const d = (iso) => ({ "2026-11-17": "17 Nov 2026", "2026-11-18": "18 Nov 2026" })[iso];
  const live = dayLine({ as_of: "2026-11-17", live: { day: "2026-11-18", time: "14:00", close: false } }, true, "map", d, "IST");
  assert.equal(`${live.lead}${live.day}${live.tail}`, "Prices at 14:00 IST, 18 Nov 2026 · the market is open; the map is redrawn every 15 minutes");
  assert.equal(live.price, "Last price");
  const lists = dayLine({ as_of: "2026-11-17", live: { day: "2026-11-18", time: "14:00", close: false } }, true, "lists", d, "IST");
  assert.match(lists.tail, /the lists are redrawn every 15 minutes$/);
  const bell = dayLine({ as_of: "2026-11-17", live: { day: "2026-11-18", time: "15:30", close: true } }, false, "map", d, "IST");
  assert.equal(`${bell.lead}${bell.day}${bell.tail}`, "Last trades of 18 Nov 2026 · the official closes replace them after the evening run");
  // 16:05 IST on 18 Nov with no prices of it: no longer a bare "Closes of 17 Nov"
  const behind = dayLine({ as_of: "2026-11-17", behind: true }, false, "map", d, "IST");
  assert.equal(`${behind.lead}${behind.day}${behind.tail}`, "Closes of 17 Nov 2026 · the latest session's closes are being added");
  assert.equal(dayLine({ as_of: "2026-11-17" }, false, "map", d, "IST").tail, "");
  assert.equal(dayLine({ as_of: null }, false, "map", d, "IST"), null);
  for (const page of ["src/pages/HeatmapPage.tsx", "src/pages/MoversPage.tsx"]) assert.match(read(page), /\{line\.lead\}<b>\{line\.day\}<\/b>\{line\.tail\}/);
});

test("LIVE13A-012: a 40-46 px heatmap tile names its symbol (over two lines when one doesn't fit)", async () => {
  const { tileWords } = await import("../src/lib/heatmap.ts");
  const width = (text) => text.length * 6.5;
  // the review's blank tiles: about 45 × 45 px boxes, so 43 × 43 px tiles
  assert.deepEqual(tileWords("BHARATFORG", "+1.2%", 43, 43, width), { px: 10, fig: false, split: 5 });
  assert.deepEqual(tileWords("SIEMENS", "+1.2%", 43, 43, width), { px: 10, fig: false, split: 4 });
  assert.deepEqual(tileWords("ABB", "+1.2%", 43, 43, width), { px: 10, fig: true });
  assert.deepEqual(tileWords("HINDUNILVR", "+1.2%", 60, 28, width), { px: 0, fig: false });       // under two lines' height: none
});

test("LIVE13A-006: the Markets panel never opens on a price read hours earlier in the same session", async () => {
  const { keptQuotes, keepQuotes, SESSION_KEEP_MS } = await import("../src/lib/watchQuotes.ts");
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  const now = Date.parse("2026-11-18T09:02:00Z");                                   // 14:32 IST, NSE open
  const q = (price, at) => ({ price, change: -2.65, change_pct: -0.9, prev_close: 293.3, at, currency: "INR", stale: false });
  keepQuotes("u", { "IN:ITC": q(290.65, "2026-11-18T09:58:00+05:30"), "IN:TCS": q(2393.8, "2026-11-18T14:25:00+05:30"),
    "US:AAPL": q(351.91, "2026-11-17T16:00:00-05:00") }, now - 60_000, store);
  const open = (k) => k.startsWith("IN:");
  const got = keptQuotes("u", now, store, undefined, undefined, open);
  assert.deepEqual(Object.keys(got).sort(), ["IN:TCS", "US:AAPL"]);                // 4 h 34 min old in the session: left out; a shut market's last close stays
  assert.equal(SESSION_KEEP_MS, 15 * 60 * 1000);
  assert.equal(Object.keys(keptQuotes("u", now, store)).length, 3);                 // without the market's state, as before
  assert.match(read("src/components/watch/WatchPanel.tsx"), /\(k\) => \{ const m = markets\.find\(\(x\) => x\.id === k\.split\(":"\)\[0\]\); return !!m && marketState\(m\)\.open; \}\)\);/);
});

test("LIVE13A-007: Mood's companies in the headlines are one row each", async () => {
  const { companyRows } = await import("../src/lib/pulseMood.ts");
  const rows = companyRows([{ name: "Tata Consultancy Services", ticker: "TCS" }, { name: "Titan Company", ticker: "TITAN" },
    { name: "Tata Consultancy Services (IT sector)", ticker: "TCS" }, { name: "Titan Company (consumer durables)", ticker: "" }, { name: "Indian IT stocks", ticker: "INFY" }]);
  assert.deepEqual(rows.map((r) => r.name), ["Tata Consultancy Services", "Titan Company"]);
});
