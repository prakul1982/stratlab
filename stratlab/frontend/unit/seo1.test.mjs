// SEO-1: the company directories (A-Z and index lists) are linked from the home page's footer and its crawler HTML.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { BROWSE_COMPANIES, PAGES } = await import("../src/content/seo.ts");
const { HOME_LINKS, pageFiles } = await import("../scripts/seoPages.mjs");

test("the directories are four plain links: India and US A to Z, NIFTY 50 and the S&P 500, at the addresses the API serves", () => {
  assert.deepEqual(BROWSE_COMPANIES.map(([to]) => to), ["/stocks/in", "/stocks/us", "/stocks/in/index/nifty-50", "/stocks/us/index/sp-500"]);
  assert.ok(BROWSE_COMPANIES.every(([to, name]) => to.startsWith("/stocks/") && name.length > 2));
});

test("the public footer (the landing page's and every public page's) carries 'Browse companies' as plain links", () => {
  const frame = read("src/components/PublicFrame.tsx");
  assert.match(frame, /aria-label="Browse companies"/);
  assert.match(frame, /Browse companies:/);
  assert.match(frame, /BROWSE_COMPANIES\.map\(\(\[to, name\]\) => <a key=\{to\} className="muted" href=\{to\}>\{name\}<\/a>\)/);
  assert.doesNotMatch(frame, /<Link [^>]*to=\{to\}[^>]*>\{name\}/);           // a page of the API, not a route of the app
  assert.match(read("src/pages/Login.tsx"), /<SiteLinks \/>/);                // the landing page's footer uses it
});

test("the home page's own HTML names the directories in words and links them, for a crawler that runs no script", () => {
  const home = PAGES.find((p) => p.path === "/");
  assert.ok(home.summary.some((p) => /Browse companies:.*A to Z.*NIFTY 50.*S&P 500/.test(p)));
  for (const [to] of BROWSE_COMPANIES) assert.ok(HOME_LINKS.includes(`href="${to}"`), to);
  const files = Object.fromEntries(pageFiles(read("index.html")));
  const html = files["index.html"];
  for (const [to] of BROWSE_COMPANIES) assert.ok(html.includes(`href="${to}"`), to);
  assert.ok(!files["terms/index.html"].includes('href="/stocks/in/index/nifty-50"'));      // only the home page carries them
});

test("vercel.json already sends every /stocks address, so the directories need no new rewrite", () => {
  const vercel = JSON.parse(read("vercel.json"));
  assert.ok(vercel.rewrites.some((r) => r.source === "/stocks/:path*"));
});
