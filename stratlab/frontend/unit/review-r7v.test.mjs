// Round 7 visitor review of the live site, the frontend's side: a library strategy's tab title and description lead with
// the result and name the universe once (R7V-006); an unknown strategy's address is a real 404, and the library and
// policy pages carry their own heading and words in the raw HTML, one h1 each, with the FAQ's structured data on /faq
// (R7V-008).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const seo = await import("../src/content/seo.ts");
const { FAQ } = await import("../src/content/faq.ts");
const { pageFiles, libraryFiles } = await import("../scripts/seoPages.mjs");
const { libraryTitle, libraryDescription } = await import("../src/lib/libraryText.ts");

const template = read("index.html");
const files = Object.fromEntries([...pageFiles(template), ...libraryFiles(template)]);
const h1s = (html) => [...html.matchAll(/<h1[^>]*>([^<]*)<\/h1>/g)].map((m) => m[1]);
const ld = (html) => [...html.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs)].flatMap((m) => JSON.parse(m[1]));

test("a library strategy's tab title leads with the result, and its description names the universe once (R7V-006)", () => {
  const name = "Supertrend flip · 20 US large caps";
  const fact = "117.1 points behind buy and hold after costs; passed all 3 checks run.";
  assert.equal(libraryTitle(name, fact, "Passed all 3 checks run"), "117.1 points behind buy and hold after costs: Supertrend flip · 20 US large caps · StratLab");
  // an older entry without the fact headline: its label leads
  assert.equal(libraryTitle(name, null, "Probably luck."), "Probably luck: Supertrend flip · 20 US large caps · StratLab");
  const desc = libraryDescription({ name, where: "20 US large caps", group: "20 US large caps", factHeadline: fact, headline: "Likely a real edge.", reason: null });
  assert.ok(desc.startsWith("117.1 points behind buy and hold after costs;"), desc);
  assert.equal(desc.match(/20 US large caps/g).length, 1, desc);
  assert.doesNotMatch(desc, / on 20 US large caps/);
  assert.doesNotMatch(desc, /\.\s*\./);
  // a strategy whose name doesn't say where it ran still says so, once
  const orb = libraryDescription({ name: "Opening-range breakout", where: "25 most liquid F&O stocks", factHeadline: "4.0 points ahead of buy and hold after costs.", reason: "Few trades." });
  assert.match(orb, /^4\.0 points ahead of buy and hold after costs\. Opening-range breakout on 25 most liquid F&O stocks\. Few trades\./);
  const pub = read("src/pages/PublicLibrary.tsx");
  assert.match(pub, /libraryTitle\(plainTerms\(e\.name\), e\.verdict\.fact_headline/);
  assert.doesNotMatch(pub, /\$\{plainTerms\(e\.name\)\} on \$\{where\(e\)\}/);
});

test("an unknown library address is a real 404 with a noindex head, the known ones are files of their own (R7V-008)", () => {
  const vercel = JSON.parse(read("vercel.json"));
  const app = vercel.rewrites.find((r) => r.destination === "/index.html");
  const re = new RegExp("^" + app.source + "$");
  assert.ok(!re.test("/library/seed-nope"), "/library/<id> must not fall through to the home page");
  assert.ok(!re.test("/library"), "/library is its own file");
  for (const [id] of seo.LIBRARY_SEEDS) assert.ok(files[`library/${id}/index.html`], id);
  assert.ok(files["library/index.html"]);
  assert.match(files["404.html"], /<meta name="robots" content="noindex, follow">/);
  assert.match(files["404.html"], /<h1>Page not found<\/h1>/);
});

test("the library and policy pages have their own h1 and words in the raw HTML, and one h1 each (R7V-008)", () => {
  const want = { "terms/index.html": "Terms of service", "privacy/index.html": "Privacy policy", "refunds/index.html": "Cancellation and refunds",
    "contact/index.html": "Contact us", "pricing/index.html": "Plans and prices", "faq/index.html": "Questions", "about/index.html": "About StratLab",
    "library/index.html": "StratLab's own strategies", "library/seed-supertrend-us/index.html": "Supertrend flip · 20 US large caps" };
  for (const [file, h] of Object.entries(want)) {
    assert.deepEqual(h1s(files[file]), [h], file);                       // the noscript note has no second h1
    assert.doesNotMatch(files[file], /<h1>StratLab: test it/, file);
  }
  for (const [file, html] of Object.entries(files)) assert.equal(h1s(html).length, 1, file);
  assert.match(files["library/seed-supertrend-us/index.html"], /Enters when the price crosses above the Supertrend \(10, 3\)/);
  assert.match(files["terms/index.html"], /No real orders are ever placed/);
  assert.match(files["privacy/index.html"], /What StratLab collects and why/);
  // the noscript note is a paragraph, and the page's own words show with scripts off
  assert.match(template, /<noscript>\s*<div class="boot"[^>]*>\s*<p><b>StratLab needs JavaScript\.<\/b><\/p>/);
  assert.doesNotMatch(template, /\[data-boot\] \{ display: none; \}/);
  for (const html of Object.values(files)) assert.doesNotMatch(html, /recommend|buy now|should buy|Yahoo|Finnhub|Screener/i);
});

test("/faq carries the FAQ's structured data and every question as text; the home page keeps its own (R7V-008)", () => {
  const faq = files["faq/index.html"];
  const graph = ld(faq);
  assert.deepEqual(graph.map((x) => x["@type"]), ["FAQPage"]);
  assert.deepEqual(graph[0].mainEntity.map((q) => q.name), FAQ.map((f) => f.q));
  for (const f of FAQ) assert.ok(faq.includes(`<h2>${f.q.replace(/&/g, "&amp;")}</h2>`), f.q);
  assert.deepEqual(ld(files["index.html"]).map((x) => x["@type"]), ["Organization", "WebSite", "FAQPage"]);
  assert.deepEqual(ld(files["terms/index.html"]), []);
});

test("each library strategy's rules match its slug, and every seed has rules (R7V-008)", () => {
  assert.equal(seo.librarySlug("seed-golden-cross-in"), "golden-cross");
  assert.equal(seo.librarySlug("seed-orb-15m-fo"), "orb-15m");
  for (const [id] of seo.LIBRARY_SEEDS) assert.ok(seo.LIBRARY_RULES[seo.librarySlug(id)], id);
});
