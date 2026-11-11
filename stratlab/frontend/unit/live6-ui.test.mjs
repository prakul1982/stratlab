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
