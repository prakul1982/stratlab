// Round 73 (19 Oct 2026): payments, look only, and reliability — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Plans says no GST is added while the invoices carry none (R73-001)", async () => {
  const { finePrint } = await import("../src/lib/offer.ts");
  const live = { mode: "paid", payments: true, yearly: true };
  const none = finePrint(live, { currency: "INR", inRupees: false, inRupeesYear: false, gst: false }).join(" ");
  assert.match(none, /The price shown is all you pay: no GST is added\./);
  assert.match(read("src/pages/PlansPage.tsx"), /"The price shown is all you pay: no GST is added\. Every payment gets an invoice in Account\."/);
});

test("the launch offer's line says when a paid period starts (R73-005)", async () => {
  const { pricingIntro } = await import("../src/lib/offer.ts");
  const o = { mode: "promo", promo_until: "2026-10-22T11:50:00Z", payments: true };
  const { lede } = pricingIntro(o, {}, "app");
  assert.match(lede, /Basic and Pro are on sale now too\. A paid month or year starts on the day you pay, not when the offer ends\./);
});

test("a chart that failed to load offers Try again, which reads the candles again (R73-003)", () => {
  const src = read("src/charts/price/PriceChart.tsx");
  assert.match(src, /className="pc-btn pc-retry" onClick=\{\(\) => setAttempt\(\(n\) => n \+ 1\)\}>Try again<\/button>/);
  assert.match(src, /syncData, attempt\]\);/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-retry \{ pointer-events: auto;/);
});
