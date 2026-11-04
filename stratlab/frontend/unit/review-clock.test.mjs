// CLOCK (owner, 31 Oct: "the PR fails are a real issue we are not able to solve"): the browser tests' world runs at one fixed moment,
// the backend's (backend/tests/e2e_clock.py) and the browser's (e2e/fixtures.ts) the same, and every spec gets it without asking.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const py = read("../backend/tests/e2e_clock.py");
const fx = read("e2e/fixtures.ts");

test("the two named moments are the backend's and the browser's alike: a Wednesday mid-session, and a shut Sunday on a month's first day", () => {
  const backend = (name) => py.match(new RegExp(`^${name} = "([^"]+)"`, "m"))?.[1];
  const browser = (name) => fx.match(new RegExp(`export const ${name} = "([^"]+)"`))?.[1];
  assert.equal(browser("E2E_NOW"), backend("OPEN"));
  assert.equal(browser("E2E_NOW_CLOSED"), backend("CLOSED"));
  const ist = (iso) => new Date(new Date(iso).getTime() + 330 * 60_000);       // the moment's wall clock in India
  const open = ist(backend("OPEN")), shut = ist(backend("CLOSED"));
  assert.equal(open.getUTCDay(), 3);                                            // a Wednesday...
  assert.ok(open.getUTCHours() * 60 + open.getUTCMinutes() > 9 * 60 + 15 && open.getUTCHours() < 15);   // ...inside 09:15-15:30
  assert.equal(shut.getUTCDay(), 0);                                            // a Sunday...
  assert.equal(shut.getUTCDate(), 1);                                           // ...the month's first (the net worth's two snapshots)
});

test("every spec's \"@playwright/test\" is the fixtures file, which takes Playwright from the package beneath it", () => {
  assert.match(read("playwright.config.ts"), /tsconfig: "\.\/e2e\/tsconfig\.json"/);
  assert.deepEqual(JSON.parse(read("e2e/tsconfig.json")).compilerOptions.paths["@playwright/test"], ["./fixtures.ts"]);
  assert.match(fx, /from "playwright\/test";/);
  assert.doesNotMatch(fx, /from "@playwright\/test"/);                          // it would import itself
  // each context starts at the world's time now, read from the server, not at a constant the server has moved on from
  assert.match(fx, /\/e2e\/now/);
  assert.match(fx, /context\.clock\.install\(\{ time: now \}\)/);
  assert.match(read("../backend/tests/visual_server.py"), /AT = e2e_clock\.start\(\)[^\n]*\nfrom app import main/);
});
