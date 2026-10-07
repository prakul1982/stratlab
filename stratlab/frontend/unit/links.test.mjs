// Every address written into a link, a redirect or the menu opens a page. A link to an address with no route used to drop
// the reader on the home page (the catch-all route) without saying so: the journal's "tax report" link was one.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { ALL_PAGES } = await import("../src/lib/nav.ts");

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src");
const main = fs.readFileSync(path.join(root, "main.tsx"), "utf8");
const routes = [...main.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((r) => r !== "*");
// pages shown before sign-in, outside the route list (main.tsx: LEGAL_PAGES and the public verdict)
const OUTSIDE = ["/terms", "/privacy", "/refunds", "/contact"];
const patterns = routes.map((r) => new RegExp("^" + r.replace(/\/\*/g, "(/.*)?").replace(/:[A-Za-z]+/g, "[^/]+") + "/?$"));
const opens = (p) => OUTSIDE.includes(p) || patterns.some((r) => r.test(p));

function walk(d) { return fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]); }

test("every page in the menu has a route", () => {
  for (const { page } of ALL_PAGES) assert.ok(opens(page.to), `${page.to} has no route`);
});

test("every literal in-app link, redirect and navigate call has a route", () => {
  const bad = [];
  const re = /(?:\bto|\bhref|navigate\(|\bnav\(|to:|href:|link:)\s*=?\s*[{(]?\s*["'`](\/[A-Za-z0-9_\-/:.]*)(?:[?#"'`$][^"'`]*)?["'`]?/g;
  for (const f of walk(root).filter((x) => /\.tsx?$/.test(x))) {
    const s = fs.readFileSync(f, "utf8");
    for (const m of s.matchAll(re)) {
      const p = m[1];
      if (p === "/" || p.endsWith("/") || /^\/(api|assets|v|c|stocks|sitemaps?|robots|og-image|favicon|public)(\/|$)/.test(p)) continue;   // a prefix a path is added to, or the API and the site's own files
      if (!opens(p)) bad.push(`${p} (${path.relative(root, f)}:${s.slice(0, m.index).split("\n").length})`);
    }
  }
  assert.deepEqual(bad, []);
});

test("the old addresses still open the page that replaced them", () => {
  for (const [from, to] of [["/all", "/mine"], ["/scans", "/research/scan"], ["/research/scans", "/research/scan"], ["/watchlist", "/research/watchlist"]]) {
    assert.ok(new RegExp(`<Route path="${from}" element=\\{<Navigate to="${to}" replace />\\} />`).test(main), `${from} should redirect to ${to}`);
  }
});
