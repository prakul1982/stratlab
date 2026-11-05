// Old builds' page code kept for KEEP_DAYS (owner, 5 Nov: buttons needed many clicks after each deploy: a tab from before a
// deploy asked for /assets/<old name>.js, which the new build didn't have).
import { test } from "node:test";
import assert from "node:assert/strict";
import { KEEP_DAYS, MAX_FILES, namesIn, plan } from "../scripts/keepAssets.mjs";

const NOW = new Date("2026-11-05T18:00:00Z");
const day = (n) => new Date(NOW.getTime() - n * 86400_000).toISOString();

test("the last build's files that this build doesn't have are carried, starting today", () => {
  const got = plan({ files: ["index-OLD.js", "Page-same.js", "a.css"], kept: {} }, ["index-NEW.js", "Page-same.js"], NOW);
  assert.deepEqual(got.fetch.sort(), ["a.css", "index-OLD.js"]);
  assert.equal(got.kept["index-OLD.js"], NOW.toISOString());
  assert.ok(!("Page-same.js" in got.kept));                   // still current: served by this build itself
});

test("a file already carried keeps the day it stopped being current, and goes after KEEP_DAYS", () => {
  const got = plan({ files: [], kept: { "x-1.js": day(2), "y-2.js": day(KEEP_DAYS + 1) } }, ["z.js"], NOW);
  assert.deepEqual(got.fetch, ["x-1.js"]);
  assert.equal(got.kept["x-1.js"], day(2));
});

test("nothing odd is carried: a path, an HTML page, a bad date; no list at all carries nothing", () => {
  const got = plan({ files: ["../secret.js", "index.html", "ok-1.js"], kept: { "late.js": "soon", "far.js": day(-5) } }, [], NOW);
  assert.deepEqual(got.fetch, ["ok-1.js"]);
  assert.deepEqual(plan(null, ["a.js"], NOW), { fetch: [], kept: {} });
  assert.deepEqual(plan({ files: "nope" }, [], NOW), { fetch: [], kept: {} });
});

test("what is carried is bounded, newest first", () => {
  const kept = Object.fromEntries(Array.from({ length: MAX_FILES + 50 }, (_, i) => [`f${i}.js`, day((i % 6) + 0.5)]));
  const got = plan({ files: [], kept }, [], NOW);
  assert.equal(got.fetch.length, MAX_FILES);
  assert.ok(got.fetch.every((n, i, a) => i === 0 || got.kept[a[i - 1]] >= got.kept[n]));
});

test("a live site without a list yet: the asset names its page and entry script mention", () => {
  const html = '<script type="module" src="/assets/index-Dh2O6s.js"></script><link href="/assets/index-a1.css" rel="stylesheet">';
  assert.deepEqual(namesIn(html), ["index-Dh2O6s.js", "index-a1.css"]);
  const entry = 'const m={"x":()=>import("./assets/Page-AbC_1.js")};f("assets/Other-z9.js");import("./Side-q.js");"https://e.com/assets/no.png"';
  assert.deepEqual(namesIn(entry), ["Page-AbC_1.js", "Other-z9.js", "Side-q.js"]);
});
