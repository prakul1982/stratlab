// `vite` and `vite preview` forward the same paths to the API that vercel.json does, so a link into the API's pages
// (the public company page, a shared verdict card, the sitemaps) works on a local copy as it does on the site.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { forwardedPaths, rewriteProxy } from "../scripts/rewriteProxy.mjs";

const vercel = JSON.parse(fs.readFileSync(new URL("../vercel.json", import.meta.url), "utf8"));
const config = fs.readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8");
const external = (r) => /^https?:\/\//.test(r.destination);

test("the forwarded paths are exactly vercel.json's rewrites to the API", () => {
  assert.deepEqual(forwardedPaths().sort(), ["/c", "/sitemap.xml", "/sitemaps", "/stocks", "/v"]);
  const rewrites = vercel.rewrites.filter(external);
  assert.equal(forwardedPaths().length, rewrites.length);
  for (const r of rewrites) assert.ok(forwardedPaths().includes(r.source.replace(/\/:.*$/, "")), `${r.source} is not proxied`);
  // the only other rewrite is the app's own catch-all
  assert.deepEqual(vercel.rewrites.filter((r) => !external(r)).map((r) => r.destination), ["/index.html"]);
});

test("the proxy sends each of them to the API, for the dev server and for preview", () => {
  const p = rewriteProxy("http://127.0.0.1:1234");
  assert.deepEqual(Object.keys(p).sort(), ["/c", "/sitemap.xml", "/sitemaps", "/stocks", "/v"]);
  for (const v of Object.values(p)) assert.equal(v.target, "http://127.0.0.1:1234");
  assert.match(config, /server:\s*\{\s*proxy: forwarded/);
  assert.match(config, /preview:\s*\{\s*proxy: forwarded/);
});
