// Round 8 visitor review of the live site, the frontend's side (R8V-008, R8V-013): a library strategy's own HTML leads
// with its result, as the drawn page does; the raw HTML's h1 is the one the page draws at every landing address; the 404
// page names no canonical address; a visitor's first page asks the server its public questions alongside its code, the
// public pages leave the sign-in library and the account code out, and the service worker waits until the page is idle.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const seo = await import("../src/content/seo.ts");
const { pageFiles, libraryFiles, libraryEntries, apiBase } = await import("../scripts/seoPages.mjs");
const { publicReads } = await import("../src/lib/entry.ts");

const template = read("index.html");
const h1s = (html) => [...html.matchAll(/<h1[^>]*>([^<]*)<\/h1>/g)].map((m) => m[1]);
const tag = (html, re) => (html.match(re) ?? [])[1];

// the public library's entry for one strategy, as GET /public/library gives it (the fields the build reads)
const supertrend = {
  id: "seed-supertrend-us", name: "Supertrend flip · 20 US large caps", market: "US", reason: null,
  group: { name: "20 US large caps", members: Array.from({ length: 20 }, (_, i) => `S${i}`) },
  verdict: { verdict: "edge", label: "Passed all 3 checks run", headline: "Passed all 3 checks run.",
    fact_headline: "117.1 points behind buy and hold after costs; passed all 3 checks run.",
    fact_summary: "It returned +55.8% after costs; buying and holding over the same period returned +172.9%, 117.1 points more." },
};

test("a library strategy's raw HTML leads with its result: title, description, og:title and h1, as the drawn page (R8V-008)", () => {
  const files = Object.fromEntries(libraryFiles(template, { "seed-supertrend-us": supertrend }));
  const page = files["library/seed-supertrend-us/index.html"];
  // changed on purpose in R10V-005: about 60 characters, the shortfall then a short strategy name then StratLab
  const title = "117.1 points behind buy and hold: Supertrend flip · StratLab";
  assert.equal(tag(page, /<title>([^<]*)<\/title>/), title);
  assert.equal(tag(page, /<meta property="og:title" content="([^"]*)">/), title);
  assert.equal(tag(page, /<meta name="twitter:title" content="([^"]*)">/), title);
  const desc = tag(page, /<meta name="description" content="([^"]*)">/);
  assert.ok(desc.startsWith("117.1 points behind buy and hold after costs;"), desc);
  assert.equal(desc.match(/20 US large caps/g).length, 1, desc);
  assert.equal(tag(page, /<meta property="og:description" content="([^"]*)">/), desc);
  assert.deepEqual(h1s(page), ["117.1 points behind buy and hold after costs; passed all 3 checks run."]);
  assert.match(page, /<p>Supertrend flip · 20 US large caps<\/p>/);
  assert.match(page, /It returned \+55\.8% after costs/);
  assert.match(page, /Enters when the price crosses above the Supertrend \(10, 3\)/);
  assert.doesNotMatch(page, /rules and verdict/);
  // the same words the app's own code writes once the page has drawn
  const { libraryTitle, libraryDescription } = seo;
  assert.equal(libraryTitle(supertrend.name, supertrend.verdict.fact_headline, supertrend.verdict.label), title);
  assert.equal(libraryDescription({ name: supertrend.name, where: "20 US large caps", group: "20 US large caps",
    factHeadline: supertrend.verdict.fact_headline, headline: supertrend.verdict.headline, reason: null }), desc);
  // a strategy the server didn't give (unreachable at build time): its own words, as before
  const plain = files["library/seed-golden-cross-in/index.html"];
  assert.match(plain, /<title>Golden cross · NIFTY 50 stocks: rules and verdict · StratLab<\/title>/);
  assert.deepEqual(h1s(plain), ["Golden cross · NIFTY 50 stocks"]);
  for (const html of Object.values(files)) assert.doesNotMatch(html, /recommend|buy now|should buy|Yahoo|Finnhub|Screener/i);
});

test("the build reads the public library from the API once, and carries on without it (R8V-008)", async () => {
  const vercel = JSON.parse(read("vercel.json"));
  const base = apiBase({}, vercel);
  assert.equal(base, vercel.rewrites.find((r) => r.source === "/stocks/:path*").destination.replace("/stocks/:path*", ""));
  assert.equal(apiBase({ STRATLAB_API_BASE: "https://api.example/" }), "https://api.example");
  const asked = [];
  const ok = async (url) => { asked.push(url); return { ok: true, json: async () => ({ entries: [supertrend, { id: 5 }, null] }) }; };
  const host = { STRATLAB_API_BASE: "https://api.example", VERCEL: "1" };          // the site's host builds it
  const got = await libraryEntries(host, ok);
  assert.deepEqual(Object.keys(got), ["seed-supertrend-us"]);
  assert.deepEqual(asked, ["https://api.example/public/library?limit=200"]);
  assert.deepEqual(Object.keys(await libraryEntries({ STRATLAB_API_BASE: "https://api.example", STRATLAB_SEO_ONLINE: "1" }, ok)), ["seed-supertrend-us"]);
  assert.deepEqual(await libraryEntries(host, async () => ({ ok: false })), {});
  assert.deepEqual(await libraryEntries(host, async () => { throw new Error("down"); }), {});
  // a local or test build (no VERCEL), or one told to stay offline: never asks, whatever the server holds
  assert.deepEqual(await libraryEntries({ STRATLAB_API_BASE: "https://api.example" }, ok), {});
  assert.deepEqual(await libraryEntries({ ...host, STRATLAB_SEO_OFFLINE: "1" }, ok), {});
  assert.equal(asked.length, 2, "only the host's and the asked-for builds read");
  assert.match(read("scripts/seoPages.mjs"), /async closeBundle\(\) \{[\s\S]*await libraryEntries\(\)/);
});

test("every landing address's raw h1 is the h1 the page draws there (R8V-008)", () => {
  const files = Object.fromEntries(pageFiles(template));
  // the home page (and /plans, /upgrade, /features, which are index.html): the tagline the landing page draws
  assert.equal(seo.pageMeta("/").heading, seo.TAGLINE);
  assert.deepEqual(h1s(files["index.html"]), ["Test it, research it, track it."]);
  assert.deepEqual(h1s(template), ["Test it, research it, track it."]);
  for (const p of ["/plans", "/upgrade", "/features", "/"]) assert.equal(seo.landingHeading(p), undefined, p);
  // an address with a page of its own: that page's heading, which the landing page then draws as its h1
  const own = { "/pricing": "Plans and prices", "/faq": "Questions", "/about": "About StratLab", "/help": "Help",
    "/login": "Sign in to StratLab", "/signup": "Sign up for StratLab" };
  for (const [p, h] of Object.entries(own)) {
    assert.equal(seo.landingHeading(p), h, p);
    assert.equal(seo.landingHeading(p + "/"), h, p);
    assert.deepEqual(h1s(files[`${p.slice(1)}/index.html`]), [h], p);
  }
  const login = read("src/pages/Login.tsx");
  assert.match(login, /heading \? <h1 className="eyebrow">\{heading\}<\/h1>/);
  assert.match(login, /\? <p className="serif lp-h1"><em>Test<\/em> it, research it, track it\.<\/p>/);
  assert.match(read("src/visitor/VisitorApp.tsx"), /<Login section=\{view\.section\} panel=\{view\.panel\} heading=\{landingHeading\(pathname\)\} \/>/);
  assert.match(read("src/styles.css"), /h1\.eyebrow \{ font-weight: 400; \}/);
});

test("the 404 page names no canonical address, in its HTML and once drawn (R8V-008)", async () => {
  const files = Object.fromEntries(pageFiles(template));
  const nf = files["404.html"];
  assert.doesNotMatch(nf, /rel="canonical"/);
  assert.doesNotMatch(nf, /og:url/);
  assert.match(nf, /<meta name="robots" content="noindex, follow">/);
  assert.match(files["terms/index.html"], /<link rel="canonical" href="https:\/\/stratlab\.studio\/terms">/);
  const { seoFor } = await import("../src/lib/seo.ts");
  assert.equal(seoFor("/nope", "notfound").canonical, null);
  // changed on purpose in R10V-005: a page kept out of search results (a sign-in gate included) names no canonical address either
  assert.equal(seoFor("/research/IN/X", "gate").canonical, null);
  assert.match(read("src/lib/seo.ts"), /if \(s\.canonical === null\) \{\s*document\.head\.querySelectorAll\('link\[rel="canonical"\]'\)\.forEach\(\(el\) => el\.remove\(\)\);/);
});

test("a visitor's first page asks its public questions alongside its code (R8V-013)", () => {
  assert.deepEqual(publicReads("/library"), ["/public/library"]);
  assert.deepEqual(publicReads("/library/"), ["/public/library"]);
  assert.deepEqual(publicReads("/library/seed-supertrend-us"), ["/public/library/seed-supertrend-us"]);
  assert.deepEqual(publicReads("/library/a%20b?x=1"), ["/public/library/a%20b"]);
  assert.deepEqual(publicReads("/verdict/tok_123"), ["/public/v/tok_123"]);
  for (const p of ["/", "/pricing", "/faq", "/login"]) assert.deepEqual(publicReads(p), ["/pricing", "/public/library?sort=new&limit=60"], p);
  for (const p of ["/terms", "/research/IN/TCS", "/nope"]) assert.deepEqual(publicReads(p), [], p);
  // each is exactly the address its page asks for
  assert.match(read("src/pages/PublicLibrary.tsx"), /publicGet<\{ entries: LibEntry\[\] \}>\("\/public\/library"\)/);
  assert.match(read("src/pages/PublicLibrary.tsx"), /publicGet<LibEntry>\(`\/public\/library\/\$\{encodeURIComponent\(id\)\}`\)/);
  assert.match(read("src/pages/PublicVerdict.tsx"), /publicGet<Snapshot>\(`\/public\/v\/\$\{encodeURIComponent\(token\)\}`\)/);
  assert.match(read("src/lib/currency.ts"), /publicGet<Pricing>\("\/pricing"\)/);
  assert.match(read("src/pages/Login.tsx"), /publicGet<\{ entries: LibEntry\[\]; total: number \}>\("\/public\/library\?sort=new&limit=60"\)/);
  assert.match(read("src/entry.tsx"), /const reads = publicReads\(path\);\s*if \(reads\.length\) import\("\.\/lib\/http"\)\.then\(\(m\) => reads\.forEach\(\(r\) => m\.prefetchPublic\(r\)\)\)/);
});

test("a read started early is taken once by the page that asks for it (R8V-013)", async () => {
  globalThis.window = { STRATLAB_CONFIG: { API_BASE: "https://api.example", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
  const calls = [];
  globalThis.fetch = async (url) => { calls.push(url); return { ok: true, status: 200, json: async () => ({ n: calls.length }) }; };
  const http = await import("../src/lib/http.ts");
  http.prefetchPublic("/public/library");
  http.prefetchPublic("/public/library");                      // asked twice before the page: still one read
  assert.equal(calls.length, 1);
  assert.deepEqual(await http.publicGet("/public/library"), { n: 1 });
  assert.equal(calls.length, 1, "the page took the early answer");
  assert.deepEqual(await http.publicGet("/public/library"), { n: 2 });   // asking again reads afresh
  assert.equal(calls.length, 2);
  globalThis.fetch = async () => ({ ok: false, status: 404, json: async () => ({ detail: { code: "not_found", message: "Not here." } }) });
  http.prefetchPublic("/public/library/nope");
  await assert.rejects(http.publicGet("/public/library/nope"), (e) => e.status === 404 && e.message === "Not here.");
  delete globalThis.window;
});

test("the public pages' code leaves out the sign-in library and the account code; the service worker waits (R8V-013)", () => {
  const vite = read("vite.config.ts");
  const kitPublic = vite.match(/\{ name: "kit-public",[^}]*test: \/([^\n]*)\/ \}/);
  assert.ok(kitPublic, "a kit group of its own for the public pages");
  assert.ok(vite.indexOf('name: "kit-public"') < vite.indexOf('name: "kit",'), "listed before the rest of the kit");
  // every kit piece a public page imports is in that group
  const re = new RegExp(kitPublic[1].replace(/\\\\/g, "\\"));
  const pages = ["src/pages/PublicLibrary.tsx", "src/pages/PublicVerdict.tsx", "src/components/LibraryBits.tsx", "src/pages/Gate.tsx", "src/pages/LegalPage.tsx"];
  for (const f of pages) {
    for (const m of read(f).matchAll(/from "(?:\.\.\/components\/|\.\/)kit\/(\w+)"/g)) {
      if (m[1] === "Seg" || m[1] === "Dialog") continue;            // kit-lite
      assert.ok(re.test(`src/components/kit/${m[1]}.tsx`), `${f}: kit/${m[1]}`);
    }
  }
  // none of those pieces reads the account
  for (const name of ["Badge", "Card", "DataTable", "Stat", "States", "Form", "PageHeader", "LinkCard", "Signed"]) {
    assert.doesNotMatch(read(`src/components/kit/${name}.tsx`), /lib\/(api|app|account)"|PlanInterest/, name);
  }
  const pwa = read("src/lib/pwa.ts");
  assert.match(pwa, /export function registerPwa\(\{ later = false \}/);
  assert.match(pwa, /window\.addEventListener\("load", \(\) => \(later \? window\.setTimeout\(\(\) => idle\(register\), 4000\) : register\(\)\)\)/);
  assert.match(read("src/entry.tsx"), /registerPwa\(\{ later: !account \}\)/);
});
