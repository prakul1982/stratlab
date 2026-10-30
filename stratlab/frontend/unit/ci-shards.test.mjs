// CI speed (owner, 29 Oct: ~25 minutes to 12-15): the browser tests run on six shards, and no one file holds a shard up. Playwright
// shards by test count with a file per project kept whole, so pages.spec.ts (11 minutes) became six files sharing pages-kit.ts and
// a11y's axe passes a file of their own; every test is kept as it was. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const wf = readFileSync(new URL("../../../.github/workflows/tests.yml", import.meta.url), "utf8");

test("the browser job runs six shards, each told it is one of six", () => {
  assert.match(wf, /shard: \[1, 2, 3, 4, 5, 6\]/);
  assert.match(wf, /npm run e2e -- --shard=\$\{\{ matrix\.shard \}\}\/6/);
  assert.match(wf, /needs: \[backend, frontend, browser, ui-lint\]/);            // the merge waits for every shard of "browser"
});

test("pages.spec.ts is six files over one kit, and the list of pages is split in two halves that cover it", () => {
  assert.ok(!existsSync(new URL("../e2e/pages.spec.ts", import.meta.url)));
  for (const f of ["routes-a", "routes-b", "research", "money", "menu-account", "alerts-admin-markets"])
    assert.match(read(`e2e/pages-${f}.spec.ts`), /from "\.\/pages-kit";/, f);
  assert.match(read("e2e/pages-routes-a.spec.ts"), /for \(const \[path, ready\] of PAGES\.slice\(0, 20\)\) \{/);
  assert.match(read("e2e/pages-routes-b.spec.ts"), /for \(const \[path, ready\] of PAGES\.slice\(20\)\) \{/);
  const kit = read("e2e/pages-kit.ts");
  for (const h of ["session", "sessionAs", "open", "sane", "touchable", "PAGES", "API", "settle", "menu", "sharedLink"])
    assert.match(kit, new RegExp(`^export (?:async function|function|const|type) ${h}\\b`, "m"), h);
});

test("a11y's axe passes are a file of their own, over the same kit as the keyboard checks", () => {
  const axe = read("e2e/a11y-axe.spec.ts");
  for (const t of ["axe finds no serious or critical problems on the main pages", "axe: the dark theme passes too", "axe: the landing page", "axe: the company pages"])
    assert.ok(axe.includes(`test("${t}`), t);
  assert.doesNotMatch(read("e2e/a11y.spec.ts"), /test\("axe/);
  assert.match(read("e2e/a11y-kit.ts"), /^export const serious = /m);
});
