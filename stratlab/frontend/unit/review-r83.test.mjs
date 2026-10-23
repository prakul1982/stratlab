// Round 83 (23 Oct 2026): India's open, the owner's app — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));


globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R83-008: India's close is counted to 15:30, not two minutes past it", async () => {
  const { marketState, inWords } = await import("../src/lib/marketHours.ts");
  const IN = { id: "IN", status: "live", tz: "Asia/Kolkata", holidays: [], hours: { open: "09:15", close: "15:30", days: "Mon-Fri" } };
  const now = new Date("2026-10-23T03:49:30Z");                         // 09:19:30 IST
  const st = marketState(IN, now);
  assert.equal(st.open, true);
  assert.equal(st.change.toISOString(), "2026-10-23T10:00:00.000Z");   // 15:30 IST
  const minute = new Date("2026-10-23T03:49:00Z");                      // the page's minute
  assert.equal(inWords((marketState(IN, minute).change.getTime() - minute.getTime()) / 60000), "6h 11m");
  assert.match(read("src/pages/MineHome.tsx"), /marketState\(m, new Date\(now\)\)/);
});

test("R83-003: a closed session's move in the watchlist says its day, even when it is still that day there", async () => {
  const { moverDay } = await import("../src/lib/mine.ts");
  const now = new Date("2026-10-23T03:49:00Z");                       // 09:19 IST; 23:49 on 22 Oct in New York
  assert.equal(moverDay("US", { at: "2026-10-22T20:00:00Z" }, now, true), "2026-10-22");
  assert.equal(moverDay("US", { at: "2026-10-22T20:00:00Z" }, now), null);
  assert.equal(moverDay("IN", { at: "2026-10-23T03:48:00Z" }, now, false), null);   // India live: today's move, no day
  assert.match(read("src/pages/MineHome.tsx"), /moverDay\(m\.region, m\.q, new Date\(\), !!mk && mk\.status !== "soon" && !marketState\(mk\)\.open\)/);
});

test("R83-001: a recording standing in while the live chain is read says so, and the table asks again", async () => {
  const { pcrNote } = await import("../src/lib/positioning.ts");
  const rows = [{ name: "NIFTY", exchange: "NFO", source: "recorded", as_of: "2026-10-23T04:11:00Z", reading: true },
    { name: "BANKNIFTY", exchange: "NFO", source: "live", as_of: "2026-10-23T04:16:00Z" }];
  const note = pcrNote(rows);
  assert.match(note, /The live chain is being read; this table updates when it arrives\.$/);
  assert.doesNotMatch(note, /couldn't be read/);
  const s = read("src/pages/PositioningPage.tsx");
  assert.match(s, /const waiting = Array\.isArray\(rows\) && rows\.some\(\(r\) => r\.reading\);/);
  assert.match(s, /if \(!waiting \|\| tries >= REREAD\) return;/);
});

test("R83-002: the chain panel asks again while a recording stands in for the live chain", () => {
  const s = read("src/pages/PositioningPage.tsx");
  assert.match(s, /const waiting = !!c && c !== "error" && !!c\.reading;/);
  assert.match(s, /if \(!waiting \|\| tries >= REREAD\) return;[\s\S]*\/trade\/positioning\/chain\?name=\$\{name\}&expiry=\$\{expiry\}/);
});

test("R86-001/002/003/004: phone tables become cards; the journal's catch-up is a real button", () => {
  assert.match(read("src/pages/BreadthPage.tsx"), /<DataTable stack label="Share of each sector's stocks above their 50-day average"/);
  assert.match(read("src/pages/BreadthPage.tsx"), /<DataTable stack label="The last 20 trading days"/);
  assert.match(read("src/pages/ResearchScans.tsx"), /<DataTable stack label="Where each one stands"/);
  assert.match(read("src/components/RiskOverview.tsx"), /<DataTable stack label=\{`Running sessions in/);
  assert.match(read("src/pages/trade/JournalPage.tsx"), /className="btn sm" disabled=\{busy\}[\s\S]*?\{busy \? "Bringing them in…" : "Bring in the newer ones"\}/);
});

test("R86-006: the chart legend hides the old view's candle while a new range loads", () => {
  assert.match(read("src/charts/price/PriceChart.tsx"), /\{h && status !== "loading" && <>/);
});

test("R87-002: a locked contract isn't listed beside its lock note; Pro gets the contract format when a futures search finds none", () => {
  const s = read("src/components/InstrumentSearch.tsx");
  assert.match(s, /!\(fnoLocked && \(i\.fno \|\| \["FUT", "CE", "PE"\]\.includes\(i\.type \?\? ""\)\)\)/);
  assert.match(s, /data-testid="fno-hint">Contracts are found by their symbol: NIFTY26NOVFUT for a future, NIFTY26NOV22600CE for an option\./);
});

test("R88-003: breadth's sector cards name each figure's day; heat stays inside its figure; no 'scrolls sideways' on cards", () => {
  assert.match(read("src/pages/BreadthPage.tsx"), /cardLabel: sectorColumnLabel\(c, shortDay\)/);
  const t = read("src/components/kit/DataTable.tsx");
  assert.match(t, /const label = c\.cardLabel \?\? \(typeof c\.header === "string" \? c\.header : undefined\);/);
  assert.match(t, /aria-label=\{stack && phone \? label : `\$\{label\}, scrolls sideways`\}/);
  assert.match(read("src/styles.css"), /\.k-tbl-wrap\.stack \.inv-heat-cell \{ display: inline-block; margin: 0;/);
});
