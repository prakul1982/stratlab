// LIVE6 (11 Nov review), lane p2-ui: the app UI and privacy fixes that can be checked without a browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// a source file's own imports name no extension ("./api"): try ".ts" (as unit/live5.test.mjs does)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("LIVE6-012: the search box's theme list is the shared library, never worded as this account's reading", async () => {
  const { libraryLabel, LIBRARY_HEAD } = await import("../src/lib/themeFormat.ts");
  const day = (iso) => ({ "2026-11-11": "11 Nov" })[iso] ?? iso;
  assert.equal(LIBRARY_HEAD, "Ready to open:");
  assert.equal(libraryLabel({ name: "Cybersecurity", region: "US", at: "2026-11-11T09:12:00Z" }, day), "Cybersecurity · US, updated 11 Nov");
  assert.equal(libraryLabel({ name: "Automotive", region: "IN", at: null }, day), "Automotive · India");
  const page = src("pages/ThemesPage.tsx");
  assert.doesNotMatch(page, /Already read:|, read \$\{/);
  assert.match(page, /\{LIBRARY_HEAD\}/);
});

test("LIVE6-005: the heatmap's note says which theme companies are grey at their last price and which have nothing", async () => {
  const { closesNote } = await import("../src/lib/heatmap.ts");
  assert.equal(closesNote({ members: 16, with_prices: 16, price_only: 0 }, "in the theme"), null);
  assert.equal(closesNote({ members: 16, with_prices: 14, price_only: 2 }, "in the theme"),
    "2 of the 16 companies in the theme have no closes on record yet and are shown in grey at the last price.");
  assert.equal(closesNote({ members: 16, with_prices: 14, price_only: 1 }, "in the theme"),
    "1 of the 16 companies in the theme has no closes on record yet and is shown in grey at the last price. 1 of the 16 companies in the theme has no closes or price on record and is not shown.");
  assert.equal(closesNote({ members: 500, with_prices: 498 }, "in this group"), "2 of the 500 companies in this group have no closes or price on record and are not shown.");
  assert.doesNotMatch(src("pages/HeatmapPage.tsx"), /have no stored closes and are not shown/);
});
