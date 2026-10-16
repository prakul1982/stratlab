// Signed-out surface fixes (review 6b): alias descriptions, the features comment, and no fallback seller flash.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const seo = await import("../src/content/seo.ts");
const { seoFor } = await import("../src/lib/seo.ts");

test("/features has its own description and /upgrade says what Plans says, both kept out of search results", () => {
  const f = seoFor("/features", "gate");
  assert.equal(f.description, seo.FEATURES_DESCRIPTION);
  assert.notEqual(f.description, seo.GATE_DESCRIPTION);
  assert.equal(f.index, false);
  const u = seoFor("/upgrade", "gate");
  assert.equal(u.description, seo.pageMeta("/pricing").description);
  assert.equal(u.index, false);
  assert.equal(u.canonical, null);
  assert.equal(seoFor("/plans", "gate").description, seo.pageMeta("/pricing").description);
  assert.equal(seoFor("/account", "gate").description, seo.GATE_DESCRIPTION);
});

test("the comment on /about does not say search engines list /features", () => {
  const src = read("src/content/seo.ts");
  assert.doesNotMatch(src, /features page are what search engines list/);
  assert.match(src, /\/features is also kept out/);
  assert.match(read("vercel.json"), /features[^"]*"[\s\S]{0,300}noindex/);
});

test("the legal pages wait for the seller's details instead of showing the fallback first", () => {
  const src = read("src/pages/LegalPage.tsx");
  assert.match(src, /loaded \? <Policy path=\{page\.path\} \/>/);
  assert.match(src, /setLoaded\(true\)/);
  assert.match(src, /catch\(\(\) => \{ if \(live\) setLoaded\(true\)/);
});
