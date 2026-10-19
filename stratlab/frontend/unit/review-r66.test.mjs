// Round 66 (19 Oct 2026): the owner on desktop Safari and a dark 400px phone — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R66-001: the VIX card's IV note is whole sentences", async () => {
  const { vixIvNote } = await import("../src/lib/positioning.ts");
  const f = (v) => v.toLocaleString("en-IN");
  assert.equal(vixIvNote(22900, "Chain at the close, 19 Oct, 15:41 IST", f),
    "At the 22,900 strike · Chain at the close, 19 Oct, 15:41 IST. The IV of the nearest expiry's options. India VIX measures the next 30 days, so the two differ, most of all near expiry.");
});

test("R66-006, R66-007: the chain card's note isn't the page's again; an expired chain says why it has no IV", () => {
  const src = read("src/pages/PositioningPage.tsx");
  assert.match(src, /<p className="k-note">\{chainCounts\(c\)\.note\}<\/p>/);
  assert.doesNotMatch(src, /\{chainCounts\(c\)\.note\} \{c\.note\}/);
  assert.match(src, /c\.atm_iv == null \? EXPIRED_IV : EXPIRING_IV/);
  assert.match(src, /These options expired at today's close, so there is no time left to work out an IV from/);
});

test("R66-002, R66-008, R66-009: a slow rotation says so; the Money tax card has no price stamp; short chip rows wrap", () => {
  const scans = read("src/pages/ResearchScans.tsx");
  assert.match(scans, /const ROTATION_SLOW_MS = 6000;/);
  assert.match(scans, /data-testid="rotation-slow">Still working: the first look after the close/);
  assert.match(scans, /<ChipBar label="Scan rule sets" wrap /);
  assert.match(read("src/pages/trade/FoChangesPage.tsx"), /<ChipBar label="Kind of change" wrap /);
  assert.doesNotMatch(read("src/pages/SpaceHomes.tsx"), /<AsOf parts=\{\[\["Prices", t\.prices_at\]\]\} \/>/);
});
