// Round 10 visitor review of the live site, the frontend's side (R10V-005, R10V-006): a verdict page's title is the
// shortfall, a short strategy name and StratLab in about 60 characters and its description at most 160; a page kept out of
// search results (/about, the 404, a sign-in gate) names no canonical address; a cold /library, /pricing or /faq keeps its
// own words on screen until the page is ready, keeps its tab title, and is drawn at its section, not moved there.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const seo = await import("../src/content/seo.ts");
const { seoFor } = await import("../src/lib/seo.ts");
const { pageFiles, libraryFiles } = await import("../scripts/seoPages.mjs");
const { startupHtml } = await import("../src/lib/held.ts");

const template = read("index.html");
const tag = (html, re) => (html.match(re) ?? [])[1];

// the headlines the server's verdicts give, by their shape (backend/app/library.py)
const HEADLINES = [
  "117.1 points behind buy and hold after costs; passed all 3 checks run.",
  "4.0 points ahead of buy and hold after costs; passed 2 of 3 checks run.",
  "19.1 points behind buy and hold after costs; failed 1 of 3 checks run.",
  "1,234.5 points ahead of buy and hold after costs; passed all 3 checks run.",
];
const entryFor = ([id, name], i) => ({
  id, name, market: id.endsWith("-in") ? "IN" : "US", reason: i % 2 ? "Too few trades to say much about it." : null,
  group: { name: name.split(" · ")[1] ?? "25 most liquid F&O stocks", members: Array.from({ length: 20 }, (_, k) => `S${k}`) },
  verdict: { verdict: "edge", label: "Passed all 3 checks run", headline: "Passed all 3 checks run.", fact_headline: HEADLINES[i % HEADLINES.length],
    fact_summary: "It returned +55.8% after costs; buying and holding returned +172.9%, 117.1 points more." },
});

test("every verdict page's title is about 60 characters and leads with the shortfall; its description is at most 160 (R10V-005)", () => {
  const entries = Object.fromEntries(seo.LIBRARY_SEEDS.map((s, i) => [s[0], entryFor(s, i)]));
  const files = Object.fromEntries(libraryFiles(template, entries));
  assert.equal(Object.keys(files).length, 19);
  const titles = new Set();
  seo.LIBRARY_SEEDS.forEach(([id, name], i) => {
    const page = files[`library/${id}/index.html`];
    const title = tag(page, /<title>([^<]*)<\/title>/);
    const desc = tag(page, /<meta name="description" content="([^"]*)">/).replace(/&amp;/g, "&");
    assert.ok(title.length <= seo.TITLE_MAX && title.length >= 30, `${title.length}: ${title}`);
    assert.match(title, /^(?:\d[\d,.]* (?:points|pts) (?:behind|ahead of) buy and hold): .+ · StratLab$/, title);
    assert.ok(!/ after costs/.test(title), title);
    assert.equal(tag(page, /<meta property="og:title" content="([^"]*)">/), title);
    assert.ok(desc.length <= seo.DESCRIPTION_MAX, `${desc.length}: ${desc}`);
    assert.ok(desc.startsWith(HEADLINES[i % HEADLINES.length].replace(/\.$/, "")) || desc.startsWith(HEADLINES[i % HEADLINES.length]), desc);
    assert.ok(desc.includes(seo.plainTerms(name).split(" · ")[0]), desc);
    titles.add(title);
  });
  assert.ok(titles.size >= 15, "titles stay told apart");
});

test("the title is the shortfall, a short strategy name, then StratLab; it gives up words in a fixed order to fit (R10V-005)", () => {
  const { libraryTitle } = seo;
  const fact = "117.1 points behind buy and hold after costs; passed all 3 checks run.";
  assert.equal(libraryTitle("Supertrend flip · 20 US large caps", fact, "x"), "117.1 points behind buy and hold: Supertrend flip · StratLab");
  // too long as written: "points" becomes "pts"
  assert.equal(libraryTitle("ST S2: Stage 2 + Supertrend · NIFTY 50 stocks", fact, "x"), "117.1 pts behind buy and hold: Stage 2 + Supertrend · StratLab");
  // ...then the name loses its bracket
  assert.equal(libraryTitle("Opening-range breakout (intraday) · 25 most liquid F&O stocks", fact, "x"), "117.1 pts behind buy and hold: Opening-range breakout · StratLab");
  // a very long name is cut at a word
  const long = libraryTitle("An extraordinarily long strategy name that cannot possibly fit in a title", fact, "x");
  assert.ok(long.length <= seo.TITLE_MAX && long.includes("…") && long.endsWith(" · StratLab"), long);
  // no headline: the verdict's label leads, and with neither, the name alone
  assert.equal(libraryTitle("Supertrend flip · 20 US large caps", null, "Probably luck."), "Probably luck: Supertrend flip · StratLab");
  assert.equal(libraryTitle("Supertrend flip · 20 US large caps", null, null), "Supertrend flip · StratLab");
  // a long label (an entry the server gave no fact headline for) is cut to its first clause
  assert.equal(libraryTitle("Supertrend flip · 20 US large caps", null, "Passed all 3 checks run, and returned more than buy and hold"), "Passed all 3 checks run: Supertrend flip · StratLab");
});

test("the description keeps the headline and the strategy, then what still fits, never more than 160 (R10V-005)", () => {
  const { libraryDescription } = seo;
  const fact = "117.1 points behind buy and hold after costs; passed all 3 checks run.";
  const d = libraryDescription({ name: "Supertrend flip · 20 US large caps", where: "20 US large caps", group: "20 US large caps", factHeadline: fact, headline: "x", reason: null });
  assert.ok(d.startsWith(`${fact} Supertrend flip · 20 US large caps.`) && d.length <= 160, d);
  assert.equal(d.match(/20 US large caps/g).length, 1, d);
  // a reason is kept when it fits, dropped when it doesn't
  const short = libraryDescription({ name: "Golden cross", where: "NIFTY 50 stocks", factHeadline: "4.0 points ahead of buy and hold after costs.", reason: "Few trades." });
  assert.match(short, /^4\.0 points ahead of buy and hold after costs\. Golden cross on NIFTY 50 stocks\. Few trades\. /);
  const dropped = libraryDescription({ name: "Golden cross", where: "NIFTY 50 stocks", factHeadline: fact, reason: "An explanation that is a great deal too long to fit beside the headline and the strategy's name in a description." });
  assert.ok(dropped.length <= 160 && !dropped.includes("An explanation"), dropped);
  // a headline alone longer than the room is cut, not run on
  const huge = libraryDescription({ name: "X", factHeadline: "word ".repeat(80), reason: null });
  assert.ok(huge.length <= 160 && huge.includes("…"), huge);
  // no double full stops
  assert.doesNotMatch(libraryDescription({ name: "A", factHeadline: "Ahead.", reason: "Because." }), /\.\s*\./);
});

test("a strategy the server did not describe at build time keeps the same lengths (R10V-005)", () => {
  const files = Object.fromEntries(libraryFiles(template));
  for (const [id, name] of seo.LIBRARY_SEEDS) {
    const page = files[`library/${id}/index.html`];
    const title = tag(page, /<title>([^<]*)<\/title>/);
    assert.ok(title.length <= seo.TITLE_MAX && title.endsWith(": rules and verdict · StratLab"), `${title.length}: ${title}`);
    assert.ok(tag(page, /<meta name="description" content="([^"]*)">/).length <= seo.DESCRIPTION_MAX, id);
  }
});

test("a page kept out of search results names no canonical address, in its HTML and once drawn (R10V-005)", () => {
  const files = Object.fromEntries(pageFiles(template));
  for (const p of seo.PAGES) {
    const html = files[p.path === "/" ? "index.html" : `${p.path.slice(1)}/index.html`];
    const noindex = /<meta name="robots" content="noindex/.test(html);
    assert.equal(noindex, !p.index, p.path);
    assert.equal(/rel="canonical"/.test(html), p.index, `${p.path} canonical`);
    assert.equal(/property="og:url"/.test(html), p.index, `${p.path} og:url`);
    if (!p.index) assert.equal(p.canonical, undefined, p.path);
  }
  // /about: the app sends it to /features signed in and scrolls the landing page to its About place signed out, and the host
  // and the page table both keep it out of search results, so it stays out of them (R10V-005 checked), with no canonical
  assert.match(files["about/index.html"], /<meta name="robots" content="noindex, follow">/);
  assert.match(read("vercel.json"), /\|about\|/);
  assert.match(read("src/main.tsx"), /<Route path="\/about" element=\{<Navigate to="\/features" replace \/>\} \/>/);
  assert.equal(seoFor("/about").canonical, null);
  assert.equal(seoFor("/about").index, false);
  assert.equal(seoFor("/nope", "notfound").canonical, null);
  assert.equal(seoFor("/research/IN/X", "gate").canonical, null);
  assert.equal(seoFor("/verdict/abc", "verdict").canonical, null);
  // an indexed page keeps its own, and a page that turns itself back on (a library strategy) names its own address
  assert.equal(seoFor("/pricing").canonical, "https://stratlab.studio/pricing");
  assert.equal(seoFor("/library/seed-supertrend-us", "public", { index: true, canonical: seo.absolute("/library/seed-supertrend-us") }).canonical,
    "https://stratlab.studio/library/seed-supertrend-us");
  assert.match(read("src/pages/PublicLibrary.tsx"), /canonical: absolute\(`\/library\/\$\{id\}`\), index: true/);
});

// ---------- R10V-006: a cold page keeps its own words until it is ready ----------
const block = (cls = "boot boot-wait") =>
  `<main><div class="${cls}" data-boot><h1>Plans and prices</h1><p>StratLab has three plans.</p></div></main>`;
const rootWith = (html, closest = true) => {
  const el = { getAttribute: (n) => (n === "class" ? /class="([^"]*)"/.exec(html)[1] : null), outerHTML: html.replace(/^<main>|<\/main>$/g, ""), closest: closest ? () => ({ outerHTML: html }) : undefined };
  return { querySelector: (s) => (s === "[data-boot]" ? el : null) };
};

test("the start-up block is kept as drawn, without its fade-in class, so drawing it again changes nothing the visitor sees (R10V-006)", () => {
  const kept = startupHtml(rootWith(block()));
  assert.equal(kept, '<main><div class="boot" data-boot><h1>Plans and prices</h1><p>StratLab has three plans.</p></div></main>');
  assert.doesNotMatch(kept, /boot-wait/);
  assert.equal(startupHtml(null), "");
  assert.equal(startupHtml({ querySelector: () => null }), "", "no block: nothing kept");
  assert.equal(startupHtml(rootWith(block("boot boot-now"))), "", "the load-error card is not kept");
});

test("the visitor half draws the kept words while a page's code downloads, and the app starts from them (R10V-006)", () => {
  const visitor = read("src/visitor/VisitorApp.tsx");
  assert.match(visitor, /const words = heldStartup\(\);/);
  assert.match(visitor, /words \? <div style=\{\{ display: "contents" \}\} data-held dangerouslySetInnerHTML=\{\{ __html: words \}\} \/> : wait/);
  assert.match(visitor, /<Suspense fallback=\{fallback\}>/);
  // with nothing kept, the splash is still a main landmark with a heading (R6V-013)
  assert.match(visitor, /<main id="main" tabIndex=\{-1\}><h1 className="sr-only">StratLab<\/h1><Opening label="Opening StratLab" \/><\/main>/);
  const entry = read("src/entry.tsx");
  assert.ok(entry.indexOf("holdStartup(root)") > entry.indexOf("readConfig()") && entry.indexOf("holdStartup(root)") < entry.indexOf('import("./visitor/visitorMain")'),
    "kept after the config is read and before either half draws over it");
  // the start-up guard still sees the kept words as "the app has not drawn yet"
  assert.match(read("public/boot.js"), /root\.querySelector\("\[data-boot\]"\)/);
});

test("a strategy's tab keeps the title its own HTML carried until its data names it (R10V-006)", () => {
  const visitor = read("src/visitor/VisitorApp.tsx");
  assert.match(visitor, /if \(start && view\.kind === "libraryEntry" && document\.title && document\.title !== HOME_TITLE\) return;/);
  assert.match(visitor, /const first = useRef\(true\);/);
  // the page itself still sets the name once the strategy is here
  assert.match(read("src/pages/PublicLibrary.tsx"), /document\.title = title;/);
});

test("the landing page is drawn at its section from the first frame, and moves again only if the visitor has not (R10V-006)", () => {
  const login = read("src/pages/Login.tsx");
  const effect = login.slice(login.indexOf("useLayoutEffect(() => {\n    if (!section) return;"), login.indexOf("useEffect(() => {\n    if (error"));
  assert.match(effect, /scrollIntoView\(\{ behavior: "instant" \}\)/);
  assert.match(effect, /if \(Math\.abs\(window\.scrollY - y\) < 2\) go\(\)/);
  assert.doesNotMatch(effect, /useEffect/);
  assert.match(login.split("\n")[0], /useLayoutEffect/);
});
