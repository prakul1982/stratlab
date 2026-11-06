// LIVE4-001: every row asked for ends in a value or a dash within the deadline, in the order shown, whatever the server answers.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readRows, shownOrder } from "../src/lib/rowReads.ts";

const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

test("rows answered at once are put, pending ones asked again, and what never comes back is a dash by the deadline", async () => {
  const put = {}, calls = [];
  const list = Array.from({ length: 30 }, (_, i) => `S${i}`);
  const t0 = Date.now();
  await readRows(list, async (part) => {
    calls.push(part);
    // S0..S9 answer, S10..S19 are pending once then answer, S20..S29 are always pending (a source that stays busy)
    const round = calls.filter((c) => c.includes(part[0])).length;
    const pending = part.filter((s) => { const n = +s.slice(1); return (n >= 10 && n < 20 && round === 1) || n >= 20; });
    return { got: Object.fromEntries(part.filter((s) => !pending.includes(s)).map((s) => [s, { v: s }])), pending };
  }, (got) => Object.assign(put, got), { size: 12, parallel: 3, deadlineMs: 400, pauseMs: 50 });
  assert.ok(Date.now() - t0 < 1000);
  assert.deepEqual(Object.keys(put).sort(), [...list].sort());              // every row: a value or a dash
  for (let i = 0; i < 20; i += 1) assert.deepEqual(put[`S${i}`], { v: `S${i}` });
  for (let i = 20; i < 30; i += 1) assert.equal(put[`S${i}`], null);
  assert.deepEqual(calls[0], list.slice(0, 12));                            // in the order given: the rows on screen first
});

test("a call that hangs past the deadline still leaves dashes on time, and a failed call is a dash at once", async () => {
  const put = {};
  const t0 = Date.now();
  await readRows(["A", "B", "C"], async (part) => {
    if (part.includes("A")) { await sleep(2000); return { got: { A: 1 }, pending: [] }; }
    throw new Error("429");
  }, (got) => Object.assign(put, got), { size: 1, parallel: 3, deadlineMs: 200 });
  assert.ok(Date.now() - t0 < 1000, "the deadline does not wait for a hung call");
  assert.deepEqual(put, { A: null, B: null, C: null });
});

test("nothing is put once the page has moved on", async () => {
  const put = {};
  let on = true;
  await readRows(["A", "B"], async () => { on = false; return { got: { A: 1, B: 2 }, pending: [] }; }, (got) => Object.assign(put, got),
    { size: 2, deadlineMs: 100, alive: () => on });
  assert.deepEqual(put, {});
});

test("the rows are read in the order a person sees them: days to come first, then the folded days gone by", () => {
  const weeks = [{ rows: [{ symbol: "OLD1", date: "2026-11-02" }, { symbol: "TODAY1", date: "2026-11-06" }, { symbol: "OLD2", date: "2026-11-03" }, { symbol: "TODAY2", date: "2026-11-06" }] },
    { rows: [{ symbol: "NEXT", date: "2026-11-09" }] }];
  assert.deepEqual(shownOrder(weeks, "2026-11-06").map((r) => r.symbol), ["TODAY1", "TODAY2", "NEXT", "OLD1", "OLD2"]);
});
