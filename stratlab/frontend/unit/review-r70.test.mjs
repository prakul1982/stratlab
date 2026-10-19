// Round 70 (19 Oct 2026): the owner on Chrome, desktop, phone and dark, the evening before a holiday — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R70-001: today's 15:30 expiry is no longer 'coming up' at 18:00, and a holiday lasts the day", async () => {
  const { happened, istHm } = await import("../src/lib/eventTime.ts");
  const exp = { date: "2026-10-19", time: "15:30", status: "scheduled" };
  assert.equal(happened(exp, "2026-10-19", "18:02"), true);
  assert.equal(happened(exp, "2026-10-19", "15:00"), false);
  assert.equal(happened({ date: "2026-10-20", time: null, status: "scheduled" }, "2026-10-20", "18:00"), false);
  assert.equal(happened({ date: "2026-10-18", time: null }, "2026-10-19", "09:00"), true);
  assert.equal(happened({ date: "2026-10-19", time: "10:00", status: "released" }, "2026-10-19", "09:00"), true);
  assert.equal(istHm(new Date("2026-10-19T12:32:00Z")), "18:02");
  assert.match(read("src/lib/mine.ts"), /happened\(e, today, nowHm\)/);
  assert.match(read("src/pages/trade/EventsPage.tsx"), /!happened\(e, v\.today, nowHm\) \|\| !!e\.figure/);
});

test("R70-005: a session at its daily loss cap says so on the paper list; no 'tomorrow' before a holiday", () => {
  assert.match(read("src/pages/PaperPage.tsx"), /r\.cap_hit && <Badge tone="warn">Loss cap hit today<\/Badge>/);
  assert.doesNotMatch(read("src/components/GroupSession.tsx"), /until tomorrow/);
  assert.doesNotMatch(read("src/components/Rules.tsx"), /until tomorrow/);
});

test("R70-009: the launch offer card waits for the overview instead of showing 'Off … Start now'", () => {
  const src = read("src/pages/admin/UsersSection.tsx");
  assert.match(src, /\{!ov \? <Skeleton label="Reading the launch offer" lines=\{2\} \/> : until \?/);
});
