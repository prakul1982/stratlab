// The account's preferences are saved in the order they were changed, and a /me read while a save is on its way keeps the
// later changes (lib/prefsSync.ts; DI-006: "Move Markets up" twice left the account on the first move). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
const { prefsSync } = await import("../src/lib/prefsSync.ts");

const later = () => { let ok; const p = new Promise((r) => { ok = r; }); return { p, ok }; };

test("a save is sent only once the one before it is answered, so the server ends on the last change", async () => {
  const q = prefsSync();
  const sent = [], answers = [];
  const send = (b) => { sent.push(b.mine.order[1]); const a = later(); answers.push(a); return a.p; };
  const one = q.save({ mine: { order: ["networth", "pnl", "markets"] } }, send);
  const two = q.save({ mine: { order: ["networth", "markets", "pnl"] } }, send);
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(sent, ["pnl"]);                       // the second waits
  answers[0].ok();
  await one;
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(sent, ["pnl", "markets"]);
  answers[1].ok();
  await two;
});

test("a save that fails is said to its caller and doesn't stop the next", async () => {
  const q = prefsSync();
  const sent = [];
  const bad = q.save({ level: "some" }, async () => { sent.push(1); throw new Error("offline"); });
  const good = q.save({ level: "pro" }, async () => { sent.push(2); });
  await assert.rejects(bad, /offline/);
  await good;
  assert.deepEqual(sent, [1, 2]);
});

test("an answer to /me keeps the changes made after it was asked for, and only those", () => {
  const q = prefsSync();
  q.save({ focus: "money" }, async () => undefined);
  const since = q.mark();
  q.save({ mine: { order: ["networth", "markets"] } }, async () => undefined);
  const stale = { level: "some", focus: "money", mine: { order: ["networth", "pnl"] } };
  assert.deepEqual(q.overlay(stale, since).mine.order, ["networth", "markets"]);
  assert.equal(q.overlay(stale, q.mark()), stale);           // nothing since: the answer as it is
  assert.deepEqual(q.overlay({ focus: "trade" }, since).focus, "trade");   // a change from before the ask is the server's to say
});
