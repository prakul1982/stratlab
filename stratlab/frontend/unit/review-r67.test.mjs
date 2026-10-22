/* Round 67 (19 Oct 2026): India's close before the Tue 20 Oct holiday — each fix on the reviewer's own example. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R67-003: the loss-cap banner says the next market day, and the engine's note isn't shown under it", () => {
  const src = read("src/pages/OptionsSession.tsx");
  assert.doesNotMatch(src, /starts again tomorrow/);
  assert.match(src, /trades again from the next market day/);
  assert.match(src, /snap\.note && !p && !\(a\.halted && \/loss cap\/i\.test\(snap\.note\)\)/);
});

test("R67-004: after the close the breadth chip and the day card don't call 16 Oct the last close", async () => {
  const { breadthChipLabel, dailyTitle } = await import("../src/lib/breadthLive.ts");
  assert.equal(breadthChipLabel({ state: "final" }), "Daily figures to");
  assert.equal(breadthChipLabel({ state: "live" }), "Daily figures to");
  assert.equal(breadthChipLabel(null), "Prices as of");
  assert.equal(dailyTitle("16 Oct", { state: "final" }), "Previous session · 16 Oct");
  assert.equal(dailyTitle("16 Oct", { state: "live" }), "Last close · 16 Oct");
  assert.equal(dailyTitle("16 Oct", null), "Latest numbers · 16 Oct");
});
