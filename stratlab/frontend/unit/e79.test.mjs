// e79 (Release 78, LIVE15A theme items). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE15A-009: a layer with members but none with figures says how many it lists, never that nobody is placed there", async () => {
  const { emptyLayerLines } = await import("../src/lib/themeFormat.ts");
  const got = emptyLayerLines([
    { layer: "Fertilizer makers", companies: [{}], placed: 9 },
    { layer: "Property developers", companies: [], placed: 3 },
    { layer: "Distribution and trading", companies: [], placed: 0 },
  ]);
  assert.deepEqual(got, [
    "Property developers: 3 companies listed in it, none among the companies whose figures are worked out, so no figure of it is shown.",
    "No listed company is shown for the layer Distribution and trading: none of the companies the map named has a description that shows it does this work.",
  ]);
  // (guard) a dive kept before "placed" was: as before
  assert.deepEqual(emptyLayerLines([{ layer: "A", companies: [] }, { layer: "B", companies: [] }]),
    ["No listed company is shown for the layers A and B: none of the companies the map named has a description that shows it does this work."]);
  assert.match(read("src/pages/ThemesPage.tsx"), /emptyLayerLines\(dive\.layers\)/);
});

test("LIVE15A-021: the app's map date in the market's own time, as the public page and the deck say it", async () => {
  const { mapStamp } = await import("../src/lib/themeFormat.ts");
  const day = (iso) => iso;
  const made = Date.UTC(2026, 10, 15, 20, 0) / 1000;          // 15 Nov 20:00 UTC = 16 Nov 01:30 IST
  assert.equal(mapStamp(made, "2026-11-19T09:35:00+00:00", "x", day, "Asia/Kolkata"), "Map made 2026-11-16 · checked 2026-11-19");
  assert.equal(mapStamp(made, "2026-11-19T09:35:00+00:00", "x", day), "Map made 2026-11-15 · checked 2026-11-19");      // (no zone: as before)
  assert.match(read("src/pages/ThemesPage.tsx"), /fmtDate, marketTz\(region\)\)/);
});

test("LIVE15A-014: a phone card leaves out a lead cell that is only a dash (no lone \"–\" quote lines)", () => {
  assert.match(read("src/components/kit/DataTable.tsx"), /cardsNow && \(!!compact \|\| !!c\.lead\) && !c\.rowHeader && dashOnly\(cellText\(v\)\)/);
});
