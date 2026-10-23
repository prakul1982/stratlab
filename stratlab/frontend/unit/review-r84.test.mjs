// Round 84 (23 Oct 2026): the owner's app in Safari and Chrome — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));


const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R84-013: a paused session is counted as paused, not stopped", async () => {
  const { notRunning } = await import("../src/lib/tradeUi.ts");
  assert.deepEqual(notRunning([{ status: "paused" }]), ["1 paused"]);
  assert.deepEqual(notRunning([{ status: "paused" }, { status: "stopped" }, { status: "ended" }, { status: "running" }]), ["1 paused", "2 stopped"]);
  assert.deepEqual(notRunning([{ status: "running" }]), []);
  for (const p of ["src/pages/SpaceHomes.tsx", "src/pages/MineHome.tsx"]) {
    const s = read(p);
    assert.match(s, /notRunning\(rows\)/);
    assert.doesNotMatch(s, /\} stopped`/);
  }
});

test("R84-019: an empty Zerodha read after the login ended says the login ended", async () => {
  const { zerodhaEmpty } = await import("../src/lib/zerodha.ts");
  const now = new Date("2026-10-23T01:00:00+00:00");                                 // 06:30 IST
  assert.equal(zerodhaEmpty({ live: false, count: 0, read_at: "2026-10-22T03:52:00+00:00" }, now),
    "Zerodha's login has ended; its last read, at 22 Oct, 09:22 IST, returned 0 holdings.");
  assert.equal(zerodhaEmpty({ live: true, count: 0, read_at: "2026-10-23T00:41:00+00:00" }, now), "Zerodha is connected; it returned 0 holdings today at 06:11 IST.");
  assert.equal(zerodhaEmpty({ live: false, count: 2, read_at: "2026-10-22T03:52:00+00:00" }, now), null);
});

test("R84-003: the kept sector chart doesn't read as a fault", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /" · kept from the last close; it updates when the market reopens"/);
  assert.doesNotMatch(s, /the last one worked out, while market data is offline/);
});
