// t56 (R55 review, the live R55 Payments deck: Adyen's ADR "removed ... (no longer in the theme's map)", neither a listing nor a business
// reason said): a removal for a listing reason has its own heading; a business-membership removal says so, its listing line apart.
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

test("t56: a listing removal under its own heading, a business removal with its listing line apart", async () => {
  const C = await import("../src/lib/themeChanges.ts");
  const entry = {
    at: "2026-11-16T06:00:00+00:00", d: "2026-11-16", cause: "rules", counts: { removed: 2, added: 0, moved: 0, layers: 0, restated: 0 },
    added: [], moved: [], layers: [], restated: [],
    removed: [
      { symbol: "ADYEY", name: "Adyen Nv-Unspon ADR", layer: "Merchant acquiring and processing",
        why: "business membership: its own words (read as Adyen's) were checked and don't show the work of “Merchant acquiring and processing”; listing: listed as an unsponsored depositary receipt of Adyen, which removes no company" },
      { symbol: "XOTC", name: "X Corp OTC line", layer: "Card networks", why: "listing: an over-the-counter line with no filings of its own" },
    ],
  };
  const rows = C.changeRows(entry, "$ m");
  assert.equal(rows[0].change, "Removed");
  assert.ok(rows[0].detail.startsWith("From Merchant acquiring and processing: business membership: its own words (read as Adyen's)"));
  assert.equal(rows[1].change, "Removed for a listing reason");
  assert.equal(rows[1].detail, "From Card networks: an over-the-counter line with no filings of its own");
});
