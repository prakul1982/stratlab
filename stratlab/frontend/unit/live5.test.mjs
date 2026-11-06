// LIVE5 (re-score after Release 13, 6 Nov 2026): the fixes that can be checked without a browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { pricesNote, quoteAsk, readRows, sessionDayOf } from "../src/lib/rowReads.ts";

const day = (iso) => ({ "2026-11-05": "Thu 5 Nov", "2026-11-06": "Fri 6 Nov" })[iso] ?? iso;

test("LIVE5-001: a stock the server's price source was busy for is asked again until it has a price; a failed call too", async () => {
  const calls = [];
  let round = 0;
  const ask = quoteAsk(async (part) => {
    calls.push(part);
    round += 1;
    if (round === 2) throw new Error("503");                       // a call that failed: its rows are asked again, not a dash
    // the first call: half the stocks past the source's budget (pending); later calls answer everything
    const busy = round === 1 ? part.filter((_, i) => i % 2) : [];
    return { quotes: Object.fromEntries(part.filter((s) => !busy.includes(s)).map((s) => [s, { price: 10, at: "2026-11-06T10:00:00Z" }])), pending: busy };
  });
  const put = {};
  const list = Array.from({ length: 6 }, (_, i) => `S${i}`);
  await readRows(list, ask, (got) => Object.assign(put, got), { size: 6, parallel: 1, deadlineMs: 2000, pauseMs: 10 });
  for (const s of list) assert.equal(put[s]?.price, 10, s);          // every row priced: none kept the day before's close
  assert.equal(calls.length, 3);
});

test("LIVE5-001: a stock answered with no price is a dash at once; the answer under the asked ticker is found", async () => {
  const ask = quoteAsk(async () => ({ quotes: { ABB: { price: 6774, at: "x" }, OIL: null, "BRK.B": { price: 1 } }, pending: [] }));
  const got = await ask(["ABB", "OIL", "brk.b"]);
  assert.deepEqual(got.pending, []);
  assert.equal(got.got.ABB.price, 6774);
  assert.equal(got.got.OIL, null);
  assert.equal(got.got["brk.b"].price, 1);
});

test("LIVE5-001: the session the prices are of is the newest read's day in the market's zone", () => {
  // 15:29 IST on 6 Nov is 09:59 UTC; 23:50 UTC on 5 Nov is 05:20 IST on 6 Nov
  assert.equal(sessionDayOf(["2026-11-05T09:59:00Z", "2026-11-06T09:59:00Z", null], "Asia/Kolkata"), "2026-11-06");
  assert.equal(sessionDayOf(["2026-11-05T23:50:00Z"], "Asia/Kolkata"), "2026-11-06");
  assert.equal(sessionDayOf(["2026-11-05T23:50:00Z"], "America/New_York"), "2026-11-05");
  assert.equal(sessionDayOf([], "Asia/Kolkata"), null);
});

test("LIVE5-001: the footer names the day of the prices shown and counts the rows still on an older close", () => {
  const base = { live: false, asOf: null, rows: 76, cap: 1000, closeDay: "2026-11-06", older: 0, olderDay: null };
  assert.equal(pricesNote(base, day), "Prices are each company's last close, Fri 6 Nov; the market is not trading now.");
  assert.equal(pricesNote({ ...base, older: 3, olderDay: "2026-11-05", reading: true }, day),
    "Prices are each company's last close, Fri 6 Nov; the market is not trading now. 3 companies' prices are still being read; they show the close of Thu 5 Nov, in grey.");
  assert.match(pricesNote({ ...base, older: 1, olderDay: "2026-11-05" }, day), /1 company's price couldn't be read just now; it shows the close of Thu 5 Nov/);
  assert.equal(pricesNote({ ...base, live: true, asOf: "10:31 IST" }, day),
    "Prices as of 10:31 IST, read for the 76 companies shown and again each minute while the market trades.");
  assert.equal(pricesNote({ ...base, rows: 0 }, day), "");
});
