// LAND-2: the landing page's intro: the three spaces with three things each and three steps, drawn under the hero and written, in the
// same words, into the home page's own HTML for crawlers. LIVE3-023 / LIVE2-011 (owner, 4 Nov): its "What StratLab is" heading and
// sentence are cut (they restated the hero); the sentence lives on in the welcome pop-up only.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { HOW_MONEY, HOW_STEPS, INTRO_LINE, INTRO_SPACES } from "../src/content/intro.ts";
import { PAGES } from "../src/content/seo.ts";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const home = PAGES.find((p) => p.path === "/");
const words = JSON.stringify([INTRO_LINE, INTRO_SPACES, HOW_STEPS, HOW_MONEY, home.summary]);

test("LAND-2 / LIVE3-023: the welcome sentence is one sentence; the landing page and its own HTML no longer open with it under 'What StratLab is'", () => {
  assert.equal(INTRO_LINE.match(/\.\s/g), null, "one sentence");
  for (const part of ["testing trading ideas", "understanding your own money", "ten markets", "paper trading only", "never real orders", "facts, not tips"])
    assert.ok(INTRO_LINE.includes(part), part);
  // owner, 4 Nov: cut from the page (it restated the hero), so cut from the page's server-rendered copy too: that copy opens with Trade
  assert.ok(!home.summary.join(" ").includes(INTRO_LINE) && !home.summary.join(" ").includes("What StratLab is"));
  assert.match(home.summary[0], /^Trade, the strategy lab: /);
  const login = read("src/pages/Login.tsx");
  assert.doesNotMatch(login, /INTRO_TITLE|INTRO_LINE|intro-h|lp-intro-line/);
  assert.doesNotMatch(read("src/styles.css"), /lp-intro-line/);
  assert.equal(home.updated, "2026-11-04", "the page's words changed on this day (and backend/app/site_pages.py says so)");
});

test("LAND-2: three columns, Trade then Invest then Money, each with a one-line summary and three real things", () => {
  assert.deepEqual(INTRO_SPACES.map((s) => s.name), ["Trade", "Invest", "Money"]);
  for (const s of INTRO_SPACES) {
    assert.equal(s.things.length, 3, s.name);
    assert.ok(s.line.length < 100 && !s.line.includes("\n"), `${s.name}: one short line`);
    // the page's server-rendered copy names each space and each thing it does
    assert.ok(home.summary.some((p) => p.startsWith(`${s.name}, `)), `${s.name} is in the home page's HTML`);
  }
  const all = INTRO_SPACES.flatMap((s) => s.things.map(([t]) => t)).join(" | ");
  for (const t of ["Notebooks", "Strategy library", "Paper trading", "options", "F&O desk", "Company pages", "Screens", "IPOs", "Red flags", "Holdings", "mutual funds",
    "Net worth", "Tax report", "US tax", "ITR export", "Money calendar"]) assert.ok(all.includes(t), t);
  const trade = INTRO_SPACES[0].things[0][1];
  assert.match(trade, /four checks for luck/);
  const summary = home.summary.join(" ").toLowerCase();
  for (const t of ["notebooks", "strategy library", "paper trading", "f&o desk", "company pages", "red flags", "net worth", "money calendar", "itr-ready export", "us stocks in indian tax"])
    assert.ok(summary.includes(t), `${t} is in the home page's HTML`);
});

test("LAND-2: three steps (idea, test, paper trade; Money: files, then value, gains and tax)", () => {
  assert.deepEqual(HOW_STEPS.map(([t]) => t), ["Describe an idea", "Test it on real prices", "Trade it on paper"]);
  assert.match(HOW_STEPS[0][1], /plain words/);
  assert.match(HOW_STEPS[1][1], /luck/);
  assert.match(HOW_MONEY, /upload your files.*value, gains and tax/);
  // VR5-owner-2: "facts, not tips", "ten markets" and "paper trading only / never real orders" are in the intro's one sentence, not again in this list
  // LIVE2-011: the "what makes it different" trio is gone: its three phrases were said again by the Trade and Money sections below
  const summary = home.summary.join(" ").toLowerCase();
  assert.ok(summary.includes("how it works"));
  assert.doesNotMatch(summary, /what makes it different/);
  assert.doesNotMatch(read("src/pages/Login.tsx"), /DIFF_TITLE|DIFFERENT/);
});

test("LAND-2: no advice wording, no data-vendor names and no made-up amounts in the intro or its server-rendered copy", () => {
  // "never buy, sell or hold" is the product's own rule said aloud, and the quoted rule an idea is written as is a test input, not a call
  const stated = words.replace(/never (says )?buy, sell or hold/gi, "").replace(/\\"Buy Reliance when[^"]*?\\"/, "");
  assert.doesNotMatch(stated, /\b(buy|sell|hold)\b/i);
  assert.doesNotMatch(stated, /\b(should|best stock|recommend\w*|target price|price target|guarantee\w*|outperform\w*|top pick|returns? of)\b/i);
  assert.doesNotMatch(words, /Yahoo|Screener\b|Finnhub|Moneycontrol|Trendlyne|TradingView|Chartink|Tickertape|NSE India|Alpha ?Vantage|Polygon|Twelve ?Data/i);
  assert.doesNotMatch(words, /₹\s?\d|\$\s?\d|\d+(\.\d+)?%/);
});

test("LAND-2: the page draws the intro right under the hero, in heading order, with the three columns stacking on a phone", () => {
  const login = read("src/pages/Login.tsx");
  const hero = login.indexOf('<section id="top" className="lp-hero ruled">'), intro = login.indexOf('className="lp-sec lp-spaces-sec"'), trade = login.indexOf('<section id="trade"');
  assert.ok(hero > 0 && hero < intro && intro < trade, "hero, then the intro, then Trade");
  // LIVE3-023: no section heading of its own any more: the space names and "How it works" are h2s straight under the page's h1
  assert.match(login, /<section className="lp-sec lp-spaces-sec" aria-label="Trade, Invest and Money">/);
  assert.match(login, /\{INTRO_SPACES\.map\(\(sp\) => \(/);
  assert.match(login, /<h2 className="serif lp-space-name">\{sp\.name\}<\/h2>/);
  assert.match(login, /<h2 className="serif lp-h3">\{HOW_TITLE\}<\/h2>/);
  // what the intro replaced: the three picture cards, and Trade's own four steps (the same steps, less plainly)
  assert.doesNotMatch(login, /Three spaces, one place|function SpaceArt|Check the rules|Paper trade it/);
  const css = read("src/styles.css");
  assert.match(css, /@media \(max-width: 760px\) \{ \.lp-spaces \{ grid-template-columns: minmax\(0, 1fr\); \} \}/);
  assert.match(css, /@media \(max-width: 760px\) \{ \.lp-steps\.lp-steps-3 \{ grid-template-columns: minmax\(0, 1fr\)/);
  // one h1 for the page: the intro's parts are h2s (no h3 with no h2 above it)
  assert.doesNotMatch(login.slice(intro, trade), /<h1|<h3|<h4/);
});

// LIVE3-023 (owner, 4 Nov): the intro's sentence is cut from the page, so these claims are now said nowhere on the landing page or in its
// server-rendered copy (the hero's lede and the sections below cover the product; the meta description keeps "Facts, not tips"); the rule
// that they are never said twice still holds
test("VR5-owner-2: the landing page never says 'ten markets', 'paper trading only / never real orders' or 'facts, not tips' twice", () => {
  const login = read("src/pages/Login.tsx");
  // the hero's eyebrow and line, the line under the button and Options' tag no longer carry them
  assert.match(login, /"Trade · Invest · Money"\}<\/span>/);
  assert.doesNotMatch(login, /Ten markets|Facts and tests, never tips|Paper trading only, no real orders|No real orders, ever/);
  // nothing else drawn from the intro's data says them again: the sentence is the only place
  const rest = JSON.stringify([INTRO_SPACES, HOW_STEPS, HOW_MONEY]).toLowerCase();
  for (const claim of ["ten markets", "facts, not tips", "never real orders", "no real orders", "paper trading only", "never buy, sell or hold"])
    assert.ok(!rest.includes(claim), `${claim} is said again`);
  // and the page's own HTML says each at most once
  const html = home.summary.join(" ").toLowerCase();
  for (const claim of ["ten markets", "facts, not tips", "never real orders"]) assert.ok(html.split(claim).length - 1 <= 1, `${claim} at most once in the home page's HTML`);
  assert.doesNotMatch(html, /no real orders|never says buy, sell or hold/);
});
