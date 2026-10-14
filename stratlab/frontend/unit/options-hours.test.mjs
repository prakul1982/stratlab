// An options paper session keeps its own exchange's hours, not India's cash market's. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { marketState, optionsMarket, sessionFeed } = await import("../src/lib/marketHours.ts");

const mk = (id, tz, open, close, extra = {}) => ({ id, name: id, venues: "", currency: "INR", symbol: "₹", tz, hours: { open, close, days: "Mon–Fri", ...extra },
  what: "", costs: "", brokerage: 0, status: "live", max_days: null, holidays: [] });
// as the server sends them: MCX's close is the day's (23:55 in winter), India's has the futures and options close beside it
const winter = [mk("IN", "Asia/Kolkata", "09:15", "15:30", { fo_close: "15:40" }), mk("MCX", "Asia/Kolkata", "09:00", "23:55"), mk("CDS", "Asia/Kolkata", "09:00", "17:00")];
const WED = (hm) => new Date(`2026-11-11T${hm}:00+05:30`);       // a Wednesday

test("each exchange's session uses its own market", () => {
  assert.equal(optionsMarket(winter, "MCX").id, "MCX");
  assert.equal(optionsMarket(winter, "CDS").id, "CDS");
  assert.equal(optionsMarket(winter, "NFO").id, "IN");
  assert.equal(optionsMarket(winter, "BFO").id, "IN");
  assert.equal(optionsMarket([], "MCX"), null);
});

test("an MCX session is open in the evening, to the 23:55 winter close the server sends", () => {
  const mcx = optionsMarket(winter, "MCX");
  assert.equal(marketState(mcx, WED("18:00")).open, true);          // India's cash market has long closed
  assert.equal(marketState(optionsMarket(winter, "NFO"), WED("18:00")).open, false);
  assert.equal(marketState(mcx, WED("23:50")).open, true);          // not shut at the summer 23:30
  assert.equal(marketState(mcx, WED("23:58")).open, false);
  assert.equal(sessionFeed({ feedConnected: false, lastTickAt: null, market: mcx, now: WED("20:00") }).text, "Reconnecting to prices");
  assert.match(sessionFeed({ feedConnected: false, lastTickAt: null, market: mcx, now: WED("23:58") }).text, /^Market closed/);
});

test("a currency session closes at 17:00 and an NFO session at the futures and options close", () => {
  assert.equal(marketState(optionsMarket(winter, "CDS"), WED("16:50")).open, true);
  assert.equal(marketState(optionsMarket(winter, "CDS"), WED("17:05")).open, false);
  const nfo = optionsMarket(winter, "NFO");
  assert.equal(marketState(nfo, WED("15:35")).open, true);          // cash is shut, options trade to 15:40
  assert.equal(marketState(nfo, WED("15:45")).open, false);
  assert.equal(marketState(winter[0], WED("15:35")).open, false);   // the market list itself is unchanged
});

test("the options session page asks for its exchange's market", () => {
  const src = readFileSync(new URL("../src/pages/OptionsSession.tsx", import.meta.url), "utf8");
  assert.match(src, /optionsMarket\(markets, s\.exchange\)/);
  assert.doesNotMatch(src, /markets\.find\(\(m\) => m\.id === "IN"\)/);
});
