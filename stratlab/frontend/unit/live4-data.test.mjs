// LIVE4 data lane: what the pages say when a source is busy, and requests that are never sent twice.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE4-004: a company page standing on its last stored figures says so in one line", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /c\.figures_kept && <p className="k-small k-muted" data-figures-kept>/);
  assert.match(page, /the latest couldn't be read just now\./);
  assert.match(read("src/lib/research.ts"), /figures_kept\?: string \| true;/);
});
