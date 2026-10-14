// Email and newsletter review fixes. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a weekly brief's close is the last weekday before its Saturday, not the Saturday", () => {
  const src = read("src/lib/news.ts");
  const fn = src.match(/export function closeDay\(day: string, weekly\?: boolean\): string \{([\s\S]*?)\n\}\n/)[1];
  const closeDay = new Function("day", "weekly", fn);
  assert.equal(closeDay("2026-10-17", true), "2026-10-16");
  assert.equal(closeDay("2026-10-18", true), "2026-10-16");
  assert.equal(closeDay("2026-10-16", true), "2026-10-16");
  assert.equal(closeDay("2026-10-17", false), "2026-10-17");
  assert.match(src, /closeDay\(issue\.day, issue\.weekly\)/);
});

test("the Briefs page shows My stocks' price and move", () => {
  const page = read("src/pages/NewsPage.tsx");
  assert.match(page, /it\.price != null/);
  assert.match(page, /pct\(it\.change_pct, 2\)/);
});
