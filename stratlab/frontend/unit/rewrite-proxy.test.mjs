// `vite` and `vite preview` forward the same paths to the API that vercel.json does, so a link into the API's pages
// (the public company page, a shared verdict card, the sitemaps) works on a local copy as it does on the site.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { forwardedPaths, rewriteProxy, sourceRegex } from "../scripts/rewriteProxy.mjs";

const vercel = JSON.parse(fs.readFileSync(new URL("../vercel.json", import.meta.url), "utf8"));
const config = fs.readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8");
const external = (r) => /^https?:\/\//.test(r.destination);

test("the forwarded paths are exactly vercel.json's rewrites to the API", () => {
  // /unsubscribe and /email/confirm: email links on the site's own domain, answered by the API (R6V-016)
  assert.deepEqual(forwardedPaths().sort(), ["/c/:token", "/email/confirm", "/sitemap.xml", "/sitemaps/:path*", "/stocks/:path*", "/unsubscribe", "/v/:token"]);
  assert.deepEqual(forwardedPaths(), vercel.rewrites.filter(external).map((r) => r.source));
  // the only other rewrite is the app's own catch-all
  assert.deepEqual(vercel.rewrites.filter((r) => !external(r)).map((r) => r.destination), ["/index.html"]);
});

test("the proxy sends each of them to the API, for the dev server and for preview", () => {
  const p = rewriteProxy("http://127.0.0.1:1234");
  assert.equal(Object.keys(p).length, forwardedPaths().length);
  for (const [k, v] of Object.entries(p)) { assert.ok(k.startsWith("^"), `${k} is a pattern`); assert.equal(v.target, "http://127.0.0.1:1234"); }
  assert.match(config, /server:\s*\{\s*proxy: forwarded/);
  assert.match(config, /preview:\s*\{\s*proxy: forwarded/);
});

test("a pattern matches the whole path the site's host would forward, and nothing else of the app's", () => {
  const hits = (path) => forwardedPaths().some((s) => new RegExp(sourceRegex(s)).test(path));
  for (const yes of ["/stocks/in/TCS", "/stocks/us/AAPL", "/stocks", "/stocks?q=tcs&m=in", "/stocks/in/TCS?ref=abc", "/v/abc123", "/c/abc123", "/sitemap.xml", "/sitemaps/in-1.xml"]) assert.ok(hits(yes), yes);
  // the app's own files and pages that only start with the same letters
  for (const no of ["/config.js", "/charts", "/c", "/verdict/abc", "/v", "/stockss/in", "/sitemap.xml.js", "/research/IN/TCS", "/assets/c/x.js"]) assert.ok(!hits(no), no);
});
