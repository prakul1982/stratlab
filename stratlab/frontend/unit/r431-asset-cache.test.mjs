// R43.1 smoke: a code file that answered 404 while a deploy switched over stayed a 404 in the browser's cache (the host keeps every
// /assets/ answer for a year), so every retry and the reload got the kept 404 and "Couldn't load StratLab" never went away. Before
// each retry the failed file is now asked for past the cache, which replaces the kept answer.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const { importWithRetry, failedAsset } = await import("../src/lib/lazyRetry.ts");

test("the failed code file's address is read from the import error", () => {
  assert.equal(failedAsset(new Error("Failed to fetch dynamically imported module: https://stratlab.studio/assets/markets-BRSLFXwJ.js")),
    "https://stratlab.studio/assets/markets-BRSLFXwJ.js");
  assert.equal(failedAsset(new Error("Unable to preload CSS for /assets/page-1a2b.css")), "/assets/page-1a2b.css");
  assert.equal(failedAsset(new Error("network down")), null);
});

test("before the next try the failed file is asked for past the browser's cache", async () => {
  const asked = [];
  const real = globalThis.fetch;
  globalThis.fetch = async (url, init) => { asked.push([String(url), init && init.cache]); return { ok: true }; };
  try {
    let n = 0;
    const got = await importWithRetry(async () => {
      if (++n < 2) throw new Error("Failed to fetch dynamically imported module: https://stratlab.studio/assets/markets-BRSLFXwJ.js");
      return { ok: 1 };
    }, [1], 200);
    assert.deepEqual(got, { ok: 1 });
    assert.deepEqual(asked, [["https://stratlab.studio/assets/markets-BRSLFXwJ.js", "reload"]]);
  } finally { globalThis.fetch = real; }
});

test("the start-up script asks a failed file past the cache before it reloads", () => {
  const boot = readFileSync(new URL("../public/boot.js", import.meta.url), "utf8");
  assert.match(boot, /cache: "reload"/);
  assert.match(boot, /var asked = refetch\(url\);\s*if \(asked\) asked\.then\(recover\); else recover\(\);/);
});
