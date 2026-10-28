// The public blog (BLOG-1): the Blog link in the public header and footers, the host's rewrites to the API's pages, robots, and the
// admin panel for the posts.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const vercel = JSON.parse(read("vercel.json"));

test("Blog is in the public header menu, the public footer and the landing page's header, and is a plain link (the API serves it)", () => {
  const frame = read("src/components/PublicFrame.tsx");
  assert.match(frame, /\["\/stocks", "Companies"\], \["\/blog", "Blog"\]\];/);
  assert.match(frame, /<a className="muted" href="\/blog">Blog<\/a>/);
  assert.doesNotMatch(frame, /to="\/blog"/);                                  // not a route of the app
  const login = read("src/pages/Login.tsx");
  assert.match(login, /\["\/library", "Library"\], \["\/stocks", "Companies"\], \["\/blog", "Blog"\]\]\);/);
  assert.equal((login.match(/\/blog/g) ?? []).length, 1, "the landing page names the blog once, in its header links, not in its hero");
});

test("the signed-in app's footers (Account and Plans) link to the blog; the policy row alone does not", () => {
  const legal = read("src/components/LegalLinks.tsx");
  assert.match(legal, /export function LegalLinks\(\{ blog = false \}: \{ blog\?: boolean \}\)/);
  assert.match(legal, /\{blog && <a className="muted" href="\/blog">Blog<\/a>\}/);
  for (const f of ["src/pages/AccountPage.tsx", "src/pages/PlansPage.tsx"]) assert.match(read(f), /<LegalLinks blog \/>/, f);
  assert.match(read("src/components/PublicFrame.tsx"), /<SiteLinks \/><LegalLinks \/>/);       // the public pages: Blog is in SiteLinks, once
});

test("vercel.json sends /blog and everything under it to the API, caches the rewrite, and leaves it out of the app's no-index and catch-all rules", () => {
  const to = (s) => vercel.rewrites.find((r) => r.source === s);
  assert.equal(to("/blog/:path*").destination, "https://stratlab-production-ca25.up.railway.app/blog/:path*");
  assert.equal(to("/blog/:path*").destination.replace("/blog/:path*", ""), to("/stocks/:path*").destination.replace("/stocks/:path*", ""));      // the same API as /stocks
  const order = vercel.rewrites.map((r) => r.source);
  assert.ok(order.indexOf("/blog/:path*") < order.length - 1, "before the app's catch-all");
  const cache = vercel.headers.find((h) => h.source === "/blog/:path*");
  assert.deepEqual(cache.headers, [{ key: "x-vercel-enable-rewrite-caching", value: "1" }]);
  const catchAll = vercel.rewrites.at(-1).source;
  assert.doesNotMatch(catchAll, /blog/);
  for (const h of vercel.headers) if (/noindex/.test(JSON.stringify(h.headers))) assert.doesNotMatch(h.source, /blog/, h.source);
});

test("robots.txt allows /blog, and the API's robots.txt says the same", () => {
  const robots = read("public/robots.txt");
  assert.match(robots, /User-agent: \*\nAllow: \/\nAllow: \/blog\nDisallow: \/admin/);
  assert.match(read("../backend/app/stock_pages.py"), /User-agent: \*\\nAllow: \/\\nAllow: \/blog\\nDisallow: \/admin/);
});

test("Admin → Data and jobs has a Blog panel that lists posts, hides and shows them, adds the stored briefs and writes the research posts", () => {
  const panel = read("src/pages/admin/BlogPanel.tsx");
  assert.match(read("src/pages/admin/DataSection.tsx"), /<BlogPanel \/>/);
  for (const url of ['"/admin/blog"', "/admin/blog/research", "/admin/blog/briefs", "/admin/blog/posts/${encodeURIComponent(p.slug)}/published"]) assert.ok(panel.includes(url), url);
  assert.match(panel, /<DataTable label="Blog posts"/);
  assert.match(panel, /\{p\.published \? "Hide" : "Publish"\}/);
  assert.match(panel, /Write the research posts/);
  assert.match(panel, /Add posts for stored briefs/);
  assert.match(panel, /if \(!b\?\.running\) return;/);                           // it polls only while the generator is running
  assert.doesNotMatch(panel, /yahoo|screener|finnhub|zerodha/i);
});

test("the panel tells the last research run in plain words", async () => {
  const { runLine, postKind } = await import("../src/pages/admin/blog.ts");
  assert.equal(runLine({}), "The research posts have not been written yet.");
  const at = new Date(Date.now() - 3 * 3600 * 1000).toISOString();
  assert.match(runLine({ at, made: [{ post: "IPO listing day", slug: "x", result: "new" }, { post: "SIP vs lump sum", slug: null, result: "nothing to say" }, { post: "Classic strategies", slug: "y", result: "same" }] }),
    /^Research last written .*: IPO listing day written, SIP vs lump sum not enough data, Classic strategies unchanged\.$/);
  assert.match(runLine({ at, made: [], problems: ["sip: RuntimeError: down"] }), /\. A problem: sip: RuntimeError: down$/);
  assert.match(runLine({ at, made: [], problems: ["a", "b"] }), /2 problems: a; b$/);
  assert.equal(postKind({ kind: "brief", market: "IN" }), "Market brief · India");
  assert.equal(postKind({ kind: "brief", market: "US" }), "Market brief · US");
  assert.equal(postKind({ kind: "research", market: null }), "Research");
});
