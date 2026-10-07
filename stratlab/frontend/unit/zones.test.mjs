// Market times are written in the market's own zone, with the zone's name, on a 24-hour clock, whatever the reader's
// own zone is ("7 Oct 2026, 13:26 IST", "09:30 ET"); a reader's own event can be in the reader's zone, labelled.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

process.env.TZ = "America/Los_Angeles";          // a reader far from both exchanges: nothing may come out in this zone unasked
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { asOf, dayIn, ET, fmtDateTime, fmtTime, IST, localTz, marketTz, parseClock, tzLabel, when } = await import("../src/lib/format.ts");
const { vixFreshness } = await import("../src/lib/vix.ts");

const AT = "2026-10-07T07:56:00Z";                 // 13:26 in India, 03:56 in New York, 00:56 in Los Angeles

test("zones have the short names people read", () => {
  assert.equal(tzLabel(IST), "IST");
  assert.equal(tzLabel("Asia/Calcutta"), "IST");
  assert.equal(tzLabel(ET), "ET");
  assert.equal(tzLabel("UTC"), "UTC");
  assert.match(tzLabel("Europe/Berlin", new Date(AT)), /^(CEST|GMT\+2)$/);
  assert.equal(localTz(), "America/Los_Angeles");
  assert.match(tzLabel(), /^(PDT|GMT-7)$/);         // no zone: the reader's own
  assert.equal(marketTz("IN"), IST);
  assert.equal(marketTz("US"), ET);
  assert.equal(marketTz(undefined), IST);
});

test("as-of chips are in the market's zone with its name, never the reader's", () => {
  assert.equal(asOf(AT), "7 Oct 2026, 13:26 IST");                          // India's by default
  assert.equal(asOf(AT, { tz: ET }), "7 Oct 2026, 03:56 ET");
  assert.equal(asOf(AT, { year: false }), "7 Oct, 13:26 IST");
  assert.equal(asOf(AT, { zone: false }), "7 Oct 2026, 13:26");             // where the sentence already says the zone
  assert.equal(asOf("2026-10-03"), "3 Oct 2026");                           // a day alone has no time and no zone
  assert.equal(asOf(null), null);
  assert.equal(asOf("not a time"), null);
});

test("fmtDateTime and fmtTime: 24-hour, the zone named only when asked, the old calls unchanged", () => {
  assert.equal(fmtDateTime(AT, { tz: IST, zone: true }), "7 Oct 2026, 13:26 IST");
  assert.equal(fmtDateTime(AT, { tz: IST, year: false, zone: true, seconds: true }), "7 Oct, 13:26:00 IST");
  assert.equal(fmtDateTime(AT, { tz: IST }), "7 Oct 2026, 13:26");           // as before: no name unless asked
  assert.equal(fmtDateTime("2026-10-07T18:30:00Z", { tz: IST, zone: true }), "8 Oct 2026, 00:00 IST");   // midnight is 00, never 24
  assert.equal(fmtDateTime(AT, { zone: true }), "7 Oct 2026, 00:56 PDT".replace("PDT", tzLabel()));      // the reader's own, labelled
  assert.equal(fmtTime(AT, { tz: IST, zone: true }), "13:26 IST");
  assert.equal(fmtTime("2026-10-07T13:30:00Z", { tz: ET, zone: true }), "09:30 ET");
  assert.equal(fmtTime(AT, { tz: IST }), "13:26");
  assert.equal(fmtTime(null), "–");
});

test("a paper session's start reads in the exchange's zone, labelled", () => {
  assert.equal(when("2026-10-07T12:49:00Z", IST, true, true), "7 Oct, 18:19 IST");
  assert.equal(when("2026-10-07T12:49:00Z", IST, true), "7 Oct, 18:19");    // the old call
  assert.equal(when("2026-10-07T12:49:00Z", IST, false), "7 Oct 2026");
});

test("dayIn gives the market's calendar day of a moment", () => {
  assert.equal(dayIn("2026-10-06T20:00:00Z"), "2026-10-07");                // already the 7th in India
  assert.equal(dayIn("2026-10-06T20:00:00Z", ET), "2026-10-06");
  assert.equal(dayIn(null), null);
});

test("typed times are read on the 24-hour clock", () => {
  assert.equal(parseClock("09:30"), "09:30");
  assert.equal(parseClock("9:30"), "09:30");
  assert.equal(parseClock("0930"), "09:30");
  assert.equal(parseClock("14.45"), "14:45");
  assert.equal(parseClock("23:59"), "23:59");
  for (const bad of ["24:00", "9:60", "02:45 PM", "", "9", "abc"]) assert.equal(parseClock(bad), null, bad);
});

const VIX = { quote: { as_of: "2026-10-05T06:34:00Z" }, intraday: [{ t: "2026-10-05T04:00:00Z", v: 14.5 }, { t: "2026-10-05T06:34:00Z", v: 15.03 }] };

test("India VIX read on an earlier day is labelled stale and never titled today", () => {
  const f = vixFreshness({ ...VIX, today: "2026-10-07" });
  assert.equal(f.stale, true);
  assert.equal(f.asOf, "5 Oct, 12:04 IST");
  assert.match(f.rangeLabel, /^Range on Mon,? 5 Oct$/);             // ICU writes "Mon 5 Oct" or "Mon, 5 Oct"
  assert.match(f.lineTitle, /^Mon,? 5 Oct$/);
  assert.equal(f.lineStale, true);
});

test("India VIX read today keeps its today titles", () => {
  const f = vixFreshness({ ...VIX, today: "2026-10-05" });
  assert.equal(f.stale, false);
  assert.equal(f.rangeLabel, "Today's range");
  assert.equal(f.lineTitle, "Today");
  assert.equal(f.lineStale, false);
  const none = vixFreshness({ quote: null, intraday: [], today: "2026-10-07" });
  assert.equal(none.stale, false);
  assert.equal(none.asOf, null);
  assert.equal(none.lineTitle, "Today");
});
