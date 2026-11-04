// A library test that ends long before it was run says its market's prices stop there (owner, 4 Nov: the rupee currency futures
// entries ran to 6 Jun 2023 while coins ran to the latest close). Swept over the window's edges, not one example.
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the app's own extension-less imports ("./format") resolve to their .ts files
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const { pricesStop, STOPS_AFTER_DAYS } = await import("../src/lib/libraryText.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("a test that ends long before its run day says the prices stop; one that ran to the latest prices says nothing", () => {
  assert.equal(pricesStop({ from: "2021-06-07", to: "2023-06-06" }, "2026-11-02T10:00:00+00:00"), "Prices stop on 6 Jun 2023, the latest this market's data has.");
  const ran = "2026-11-02T10:00:00+00:00";
  for (let gap = 0; gap <= 60; gap++) {
    const to = new Date(Date.parse("2026-11-02") - gap * 86_400_000).toISOString().slice(0, 10);
    assert.equal(pricesStop({ from: "2021-01-01", to }, ran) !== null, gap > STOPS_AFTER_DAYS, `${gap} days`);
  }
  assert.equal(pricesStop(null, ran), null);
  assert.equal(pricesStop({ from: "2021-01-01", to: "2023-06-06" }, null), null);
});

test("the card, the strategy's own page and the API's entry all carry it", () => {
  for (const f of ["src/components/LibraryBits.tsx", "src/pages/PublicLibrary.tsx"]) assert.match(read(f), /pricesStop\(e\.range, e\.ran_at \?\? e\.published_at\)/, f);
  assert.match(readFileSync(new URL("../../backend/app/library.py", import.meta.url), "utf8"), /"ran_at": datetime\.now\(timezone\.utc\)\.isoformat\(\)/);
});
