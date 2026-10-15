// Review 3e on the options and markets pages: the closed-for line, minutes in words, the model's "as of", the price level
// at a currency option's tick, and the lot of the expiry picked. Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const { marketState, inWords, modelStamp } = await import("../src/lib/marketHours.ts");
const { levelText, lotOf, pickedExpiry } = await import("../src/lib/options.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

const mk = (id, open, close, holidays = []) => ({ id, name: id, venues: "", currency: "INR", symbol: "₹", tz: "Asia/Kolkata",
  hours: { open, close, days: "Mon–Fri" }, what: "", costs: "", brokerage: 0, status: "live", max_days: null, holidays });
const IN = mk("IN", "09:15", "15:30", ["2026-10-20", "2026-10-23"]);        // Tuesday 20 and Friday 23 Oct are holidays
const at = (iso) => new Date(`${iso}+05:30`);

test("a normal day that has closed is not 'closed for a holiday' because the next day is one", () => {
  const mon = marketState(IN, at("2026-10-19T15:31:00"));                     // Monday, Tuesday is a holiday
  assert.equal(mon.open, false);
  assert.equal(mon.closedFor, null);
  assert.equal(mon.short, "opens Wed");                                       // Tuesday is a holiday: said as the day it opens
  assert.equal(marketState(IN, at("2026-10-22T16:00:00")).closedFor, null);   // Thursday evening, Friday a holiday
  assert.equal(marketState(IN, at("2026-10-22T08:00:00")).closedFor, null);   // before the open on a normal day
});

test("a holiday is said when today itself is one, and the weekend when it is", () => {
  assert.equal(marketState(IN, at("2026-10-20T11:00:00")).closedFor, "holiday");     // Tuesday, a holiday: all day
  assert.equal(marketState(IN, at("2026-10-20T19:00:00")).closedFor, "holiday");
  assert.equal(marketState(IN, at("2026-10-24T11:00:00")).closedFor, "weekend");     // Saturday
  assert.equal(marketState(IN, at("2026-10-16T16:00:00")).closedFor, "weekend");     // Friday evening counts as the weekend
  assert.equal(marketState(IN, at("2026-10-23T11:00:00")).closedFor, "holiday");     // a Friday holiday
  assert.equal(marketState(IN, at("2026-10-19T11:00:00")).closedFor, null);          // open
});

test("minutes in words are rounded as a total first", () => {
  assert.equal(inWords(1439.6), "1d");
  assert.equal(inWords(1439.4), "23h 59m");
  assert.equal(inWords(59.7), "1h");
  assert.equal(inWords(0.2), "1m");
  assert.equal(inWords(90), "1h 30m");
  assert.equal(inWords(1900), "1d 8h");
  assert.equal(inWords(2879.7), "2d");
});

test("the model is as of when its prices were struck, with the date, and says when they are old", () => {
  const m = (as_of, fresh) => ({ as_of, fresh });
  const open = marketState(IN, at("2026-10-14T11:00:00")), shut = at("2026-10-14T17:00:00");
  assert.equal(open.open, true);
  assert.equal(modelStamp(m("2026-10-14T10:59:40+05:30", true), IN, at("2026-10-14T11:00:00")), "as of Wed 14 Oct, 10:59 IST");
  assert.equal(modelStamp(m("2026-10-14T15:29:58+05:30", false), IN, shut), "as of Wed 14 Oct, 15:29 IST (last close, market closed)");
  assert.equal(modelStamp(m("2026-10-14T10:50:00+05:30", false), IN, at("2026-10-14T11:00:00")), "as of Wed 14 Oct, 10:50 IST (older than 2 minutes)");
  assert.equal(modelStamp(m("2026-10-09T15:29:58+05:30", undefined), IN, shut), "as of Fri 9 Oct, 15:29 IST");     // older server: nothing claimed
  assert.equal(modelStamp(m(null, false), IN, shut), "");
});

test("a currency option's levels keep their quarter paise in the tooltip, the what-if, the parity line and the roll", () => {
  assert.equal(levelText(95.1625, 0.0025), "95.1625");
  assert.equal(levelText(95.16, 0.0025), "95.1600");
  assert.equal(levelText(25025.4, 0.05), "25,025");
  const src = read("src/components/OptionModel.tsx");
  assert.doesNotMatch(src, /Math\.round\(x\)/);
  assert.match(src, /const pts = \(x: number, tick\?: number \| null\) => levelText\(x, tick\)/);
  assert.match(src, /xFormat=\{\(x\) => pts\(x, tick\)\}/);
  assert.match(src, /What-if \$\{pts\(spotW, tick\)\}/);
  assert.match(src, /parity at \$\{pts\(m\.atm \?\? m\.spot, m\.tick\)\}/);
  assert.match(src, /pts\(c\.strike, r\.model\.tick\)/);
  assert.match(read("src/pages/OptionsSession.tsx"), /Spot \$\{levelText\(g\.spot, g\.model\.tick\)\}/);
});

test("the lot shown is the picked expiry's", () => {
  const u = { lot: 65, expiries: ["2026-10-20", "2026-10-27", "2026-11-24"], lots: { "2026-10-20": 65, "2026-10-27": 65, "2026-11-24": 75 } };
  assert.equal(pickedExpiry(u.expiries, "current"), "2026-10-20");
  assert.equal(pickedExpiry(u.expiries, "next"), "2026-10-27");
  assert.equal(pickedExpiry(u.expiries, "month"), "2026-10-27");
  assert.equal(pickedExpiry(u.expiries, "2026-11-24"), "2026-11-24");
  assert.equal(pickedExpiry(u.expiries, "2030-01-01"), undefined);
  assert.equal(lotOf(u, "current"), 65);
  assert.equal(lotOf(u, "2026-11-24"), 75);                                  // a later series with another lot
  assert.equal(lotOf({ lot: 65, expiries: u.expiries }, "next"), undefined);   // no per-expiry lots (older server): not the nearest's
  assert.equal(lotOf({ lot: 65, expiries: u.expiries }, "current"), 65);
  assert.equal(lotOf(undefined, "current"), undefined);
  const page = read("src/pages/OptionsPage.tsx");
  assert.doesNotMatch(page, /und\.lot/);
});
