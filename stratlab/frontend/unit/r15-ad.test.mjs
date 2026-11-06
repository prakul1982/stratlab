// R15 (owner, 7 Nov): the ad landing. The social ad's visitors (all to "/") saw the full landing once and left; /start, and "/" for a
// visit from the ad, is one screen with one way in. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the app's own imports leave out ".ts"
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R15 ad landing: /start, and / with Meta's click id or a social utm_source, is the ad view; anything else is as before", async () => {
  const { visitorView, isAdVisit } = await import("../src/lib/deepLinks.ts");
  assert.deepEqual(visitorView("/start"), { kind: "ad" });
  assert.deepEqual(visitorView("/start/", "?utm_source=x"), { kind: "ad" });
  for (const q of ["?fbclid=abc", "?utm_source=facebook&utm_medium=paid", "?utm_source=IG", "?utm_source=instagram", "?utm_source=meta", "?utm_source=fb"]) {
    assert.ok(isAdVisit(q), q);
    assert.deepEqual(visitorView("/", q), { kind: "ad" }, q);
  }
  for (const q of ["", "?utm_source=google", "?ref=x", "?utm_medium=facebook"]) assert.equal(visitorView("/", q).kind, "landing", q);
  assert.equal(visitorView("/pricing", "?fbclid=x").kind, "landing", "only the home address turns into the ad view");
});

test("R15 ad landing: its own file and stylesheet, loaded only for the ad view; the events; its built page names / as canonical", async () => {
  const visitor = read("src/visitor/VisitorApp.tsx");
  assert.match(visitor, /export const loadAd = \(\) => import\("\.\.\/pages\/AdLanding"\);/);
  const page = read("src/pages/AdLanding.tsx");
  assert.match(page, /import "\.\/adlanding\.css";/);
  assert.match(page, /track\("ad_landing_view", \{ kind, source \}\)/);
  assert.match(page, /track\("ad_signup_click", \{ kind, source \}\)/);
  assert.match(page, />Try free with Google</);
  assert.match(page, /<Link className="small adl-more" to="\/">See everything StratLab does →<\/Link>/);
  // nothing in the landing page's start-up imports it statically (R5V-020)
  for (const f of ["src/entry.tsx", "src/visitor/visitorMain.tsx", "src/visitor/VisitorApp.tsx", "src/pages/Login.tsx"]) assert.doesNotMatch(read(f), /from "[./]+(pages\/)?AdLanding"/, f);
  const { pageFiles } = await import("../scripts/seoPages.mjs");
  const html = Object.fromEntries(pageFiles(read("index.html")))["start/index.html"];
  assert.match(html, /<title>Try StratLab free · StratLab<\/title>/);
  assert.match(html, /<link rel="canonical" href="https:\/\/stratlab\.studio\/">/);
  const { sitemapPages } = await import("../src/content/seo.ts");
  assert.ok(!sitemapPages().some((p) => p.path === "/start"), "not in the sitemap: it is the home page's");
  // its words stay out of the landing page's download (content/seo.ts), in content/ad.ts that only it and the build read
  assert.doesNotMatch(read("src/content/seo.ts"), /Try StratLab free|AD_HEADLINE/);
  assert.match(page, /from "\.\.\/content\/ad"/);
});
