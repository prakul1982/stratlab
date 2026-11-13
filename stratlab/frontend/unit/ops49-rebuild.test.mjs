// Admin → Data: how far the company pages are rebuilt to the current facts version, per market (owner, 13 Nov: "show how far the
// company-page rebuild has got"). Every value is fixed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("A market's rebuild line says N of M pages at the current facts version, the share, and what is left", async () => {
  const { rebuildLine } = await import("../src/pages/admin/rebuild.ts");
  const part = rebuildLine({ region: "IN", counted: true, current: 1234, of: 2000, at: null }, 10);
  assert.equal(part.value, "1,234 of 2,000");
  assert.equal(part.note, "61% at facts version 10; 766 still at an earlier one, rebuilt a few at a time, the largest first");
  const done = rebuildLine({ region: "US", counted: true, current: 50, of: 50, at: null }, 10);
  assert.equal(done.value, "50 of 50");
  assert.ok(done.note.startsWith("100% at facts version 10; every page is rebuilt"));
  // a count from an earlier version (or none yet) is not this version's progress
  const none = rebuildLine({ region: "US", counted: false, at: null }, 10);
  assert.equal(none.value, "Not counted yet");
  assert.match(none.note, /facts version 10/);
});

test("Data and jobs shows the rebuild panel, read from its own admin route", () => {
  const data = read("src/pages/admin/DataSection.tsx");
  assert.ok(data.includes("<PagesRebuildPanel />"));
  assert.ok(read("src/pages/admin/PagesRebuildPanel.tsx").includes('"/admin/stock-pages/rebuild"'));
});

test("A server error says which build it happened on, against the live one (the list outlives a deploy)", async () => {
  const { errorBuild, groupErrors } = await import("../src/pages/admin/attention.ts");
  assert.equal(errorBuild("9baf605", "9baf605d5a38"), "on this build");
  assert.equal(errorBuild("586a678", "9baf605"), "on an earlier build (586a678)");
  assert.equal(errorBuild(null, "9baf605"), "");                  // kept from before builds were recorded
  assert.equal(errorBuild("586a678", null), "");                  // a local run: no build known
  const e = (ref, at, build) => ({ ref, at, method: "GET", path: "/x", error: "KeyError: 'x'", where: "main.py:1 in x", build });
  const g = groupErrors([e("a", "2026-11-12T10:00:00Z", "586a678"), e("b", "2026-11-13T10:00:00Z", "9baf605")]);
  assert.equal(g[0].build, "9baf605");                            // the newest's
  assert.ok(read("src/pages/admin/SystemSection.tsx").includes("errorBuild(x.build, live)"));
});
