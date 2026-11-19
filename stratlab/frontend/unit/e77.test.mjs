// Lane e77: the members card's count line adds up (LIVE14A-004). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

test("e77: one company listed under two symbols is counted once, and the count line says so", async () => {
  const { countsLine } = await import("../src/lib/themeFormat.ts");
  const twice = (n) => Array.from({ length: n }, (_, i) => ({ ticker: `T${i}`, kept: `K${i}` }));
  // fails before: "584 companies: 588 from the official industry list, 2 added (2 description-verified)."
  assert.equal(countsLine(584, { base: 588, named: 0, added: 2, confirmed: 2, same_company: twice(6) }),
    "584 companies: 588 from the official industry list, 2 added (2 description-verified), less 6 listed twice under another symbol, counted once.");
  assert.equal(countsLine(195, { base: 199, added: 0, same_company: twice(4) }),
    "195 companies: 199 from the official industry list, 0 added, less 4 listed twice under another symbol, counted once.");
  // (guard) as before where nothing is listed twice (e2e themes.spec)
  assert.equal(countsLine(6, { base: 5, added: 1, confirmed: 1 }), "6 companies: 5 from the official industry list, 1 added (1 description-verified).");
  assert.equal(countsLine(9, { base: 6, named: 2, added: 1, confirmed: 0 }),
    "9 companies: 4 from the official industry list, 2 named in the theme's list, 1 added (0 description-verified), 2 more, neither on the official list nor added by the AI.");
});
