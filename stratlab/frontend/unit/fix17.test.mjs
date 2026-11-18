// Lane fix17 (LIVE13B review of Release 71): the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE13B-003: 'Coming up' keeps the monthly F&O expiry of the week, as /calendar lists it", async () => {
  const { comingMarketEvents } = await import("../src/lib/eventTime.ts");
  const ev = (id, kind, date, title, time = "15:30") => ({ id, kind, date, time, title, detail: "", figure: null, previous: null, url: null, status: "scheduled" });
  // Wed 18 Nov 2026: SENSEX weekly Thu 19, the monthly moved to Mon 23 (Tue 24 a holiday), the next SENSEX weekly Thu 26
  const events = [ev("sx", "expiry", "2026-11-19", "SENSEX weekly expiry"), ev("m", "expiry", "2026-11-23", "Monthly F&O expiry"),
    ev("h", "holiday", "2026-11-24", "Exchange holiday", null), ev("sx2", "expiry", "2026-11-26", "SENSEX monthly expiry"),
    ev("m2", "expiry", "2026-12-29", "Monthly F&O expiry")];
  const o = { today: "2026-11-18", nowHm: "14:16", end: "2026-12-18", weekEnd: "2026-11-25" };
  assert.deepEqual(comingMarketEvents(events, o).map((e) => e.id), ["sx", "m", "h"]);
  // once the week moves on, the next month's is the nearest of its name
  assert.deepEqual(comingMarketEvents(events, { ...o, today: "2026-11-24", weekEnd: "2026-12-01" }).map((e) => e.id), ["h", "sx2"]);
  assert.deepEqual(comingMarketEvents(events, { ...o, region: "US" }).map((e) => e.id), []);
});

// ---------- LIVE13B-001 / 002: the home page's start-up frame is the landing's own hero; scripts off, the notice comes first ----------
test("LIVE13B-001: the home page's start-up frame is the landing's header and hero, with its lede and buttons, in the landing's classes", async () => {
  const { pageFiles, HERO_EYEBROW, HERO_LEDE, HERO_SMALL, heroFonts } = await import("../scripts/seoPages.mjs");
  const home = Object.fromEntries(pageFiles(read("index.html"), ["fraunces-latin-400-italic-AbC1.woff2"]))["index.html"];
  // the header: the landing's (logo with its wordmark, the site's links in the same boot-nav, the phone menu, Sign in)
  assert.match(home, /<header class="lp-nav" data-boot-head><a href="\/" class="brand" aria-label="StratLab home"><span class="logo logo-46"><svg [^>]*class="logo-mark">/);
  assert.match(home, /<span class="logo-word"><b>Strat<\/b>Lab<\/span><\/span><\/a><nav class="boot-nav" aria-label="Site"><a href="\/library">Library<\/a>/);
  assert.match(home, /<details class="lp-menu"><summary>Menu<\/summary>/);
  assert.match(home, /<a class="btn outline sm boot-js" href="\/login">Sign in<\/a><\/header>/);
  // the hero: the same column, eyebrow, heading, lede, the three buttons and the small line as Login.tsx draws them
  const login = read("src/pages/Login.tsx");
  for (const words of [HERO_EYEBROW, HERO_LEDE, HERO_SMALL]) assert.ok(login.includes(words), `Login.tsx draws "${words}"`);
  assert.match(login, /<h1 className="serif lp-h1">Is your trading idea <em>skill<\/em> or luck\?<\/h1>/);
  assert.match(login, /<div className=\{`lp-wrap lp-hero-grid\$\{full \? "" : " lp-hero-solo"\}/);
  assert.match(home, new RegExp(`<span class="eyebrow boot-js">${HERO_EYEBROW}</span>\\n<h1 class="serif lp-h1">Is your trading idea <em>skill</em> or luck\\?</h1>\\n<p class="serif lp-lede boot-js">`));
  assert.match(home, /<div class="row wrap g12 boot-js"><a class="btn lp-cta" href="\/login"><svg[^]*?<\/svg>Continue with Google<\/a><a class="btn outline email-way lp-cta-2" href="\/login#email"><svg[^]*?<\/svg>Sign in with email<\/a><a class="btn quiet lp-cta-2" href="\/library">See real results, no sign-in<\/a><\/div>/);
  assert.match(home, /<p class="small muted boot-js">Free to start · No card · No coding<\/p>/);
  // the example card's place on a wide screen, so the heading sits where the card centres it
  assert.match(home, /<\/div><div class="boot-demo" aria-hidden="true"><\/div><\/div>\n<\/div>/);
  assert.match(home, /@media \(min-width: 1001px\) \{ \.boot-demo \{ display: block; min-height: 689px; \} \}/);
  // shown at once (no fade: it is the page itself) and only on the home address
  assert.doesNotMatch(home, /boot-wait boot-hero|class="lp-hero ruled boot-hero boot-wait"/);
  assert.match(home, /html:not\(\[data-home\]\) \.boot-hero \.boot-js, html:not\(\[data-home\]\) \.boot-demo \{ display: none; \}/);
  assert.match(read("public/boot.js"), /\(path === "\/" \|\| path === "\/index\.html"\) && !\/\[\?&\]\(fbclid=[^\n]*\n\s*document\.documentElement\.setAttribute\("data-home", "1"\)/);
  // the heading's italic face asked for at once, only on the home page
  assert.match(home, /<link rel="preload" as="font" type="font\/woff2" crossorigin href="\/assets\/fraunces-latin-400-italic-AbC1\.woff2">\n<\/head>/);
  assert.deepEqual(heroFonts(["fraunces-latin-400-italic-x1.woff2", "fraunces-latin-400-italic-x1.woff", "fraunces-latin-400-normal-y.woff2", "a.js"]), ["fraunces-latin-400-italic-x1.woff2"]);
  // crawlers and scripts off: every word of the page's own text is still there
  assert.match(home, /<p class="boot-text">Trade, the strategy lab: /);
  assert.match(home, /<ul class="boot-links boot-text">\n<li><a href="\/stocks\/in">India A–Z<\/a><\/li>/);
  assert.match(home, /<p class="boot-foot boot-text"><a href="\/terms">Terms<\/a>/);
});

test("LIVE13B-001: the words kept for the app to draw while the code downloads keep the landing's header", async () => {
  const { startupHtml } = await import("../src/lib/held.ts");
  const head = { className: "lp-nav", hasAttribute: (n) => n === "data-boot-head", outerHTML: '<header class="lp-nav" data-boot-head><a href="/">StratLab</a></header>' };
  const main = { outerHTML: '<main><div class="lp-hero ruled boot-hero" data-boot><h1>Is</h1></div></main>', previousElementSibling: head };
  const el = { getAttribute: (n) => (n === "class" ? "lp-hero ruled boot-hero" : null), closest: () => main };
  assert.equal(startupHtml({ querySelector: (s) => (s === "[data-boot]" ? el : null) }),
    '<header class="lp-nav" data-boot-head><a href="/">StratLab</a></header><main><div class="lp-hero ruled boot-hero" data-boot><h1>Is</h1></div></main>');
  // another element before the page is not taken for its header
  const other = { ...main, previousElementSibling: { className: "x", hasAttribute: () => false, outerHTML: "<div class=x></div>" } };
  assert.equal(startupHtml({ querySelector: () => ({ ...el, closest: () => other }) }), other.outerHTML);
});

test("LIVE13B-002: with scripts off the notice comes first, in a card, and the home page wears the landing's column and fonts", async () => {
  const html = read("index.html");
  assert.ok(html.indexOf("StratLab needs JavaScript.") < html.indexOf('<div id="root">'), "the notice is before the page");
  assert.match(html, /<body>\n<noscript>\n<div class="boot" data-js-off>/);
  assert.match(html, /\.boot\[data-js-off\] \{ box-sizing: border-box; max-width: min\(720px, calc\(100% - 32px\)\); margin: 16px auto;/);
  // the page's links as one row of buttons, not four stacked boxes of four widths
  assert.match(html, /\.boot-hero ul\.boot-links \{ display: flex; flex-wrap: wrap; gap: 12px;/);
  // the home page's header and heading take the landing's classes, which the stylesheet in the head styles with scripts off too
  const { pageFiles } = await import("../scripts/seoPages.mjs");
  const home = Object.fromEntries(pageFiles(html))["index.html"];
  assert.match(home, /<header class="lp-nav" data-boot-head>/);
  assert.match(home, /<h1 class="serif lp-h1">/);
  assert.match(html, /\.boot-head \.boot-nav \{ display: flex;/);       // the plain header's rules stay on the plain header
});
