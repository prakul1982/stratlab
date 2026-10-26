// MO-5 (26 Oct 2026): the library's card is one calm face, and the library has samples for every market the backtester reads.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("MO-5a: a card's title is the strategy's name, and where it was tested is one small line", async () => {
  const { strategyName, libMeta } = await import("../src/lib/libraryList.ts");
  const e = { name: "ST S2: Stage 2 + Supertrend · 20 of the largest US companies", official: true, market: "US", tf: "1d", side: "long",
    group: { name: "20 of the largest US companies", members: new Array(20).fill({}) }, instrument: null };
  assert.equal(strategyName(e), "Stage 2 + Supertrend");
  assert.equal(libMeta(e), "United States · 20 of the largest US companies · Daily candles");
  // a reader's own notebook name is theirs: only the universe on its end goes, never a part of the name itself
  assert.equal(strategyName({ name: "Gap fade · my rules", official: false, group: null, instrument: { symbol: "RELIANCE" } }), "Gap fade · my rules");
  assert.equal(strategyName({ name: "Gap fade · RELIANCE", official: false, group: null, instrument: { symbol: "RELIANCE" } }), "Gap fade");
  assert.equal(strategyName({ name: "Golden cross", official: true, group: null, instrument: null }), "Golden cross");
  assert.equal(libMeta({ market: "FX", tf: "1d", side: "both", group: { name: "7 major currency pairs", members: new Array(7).fill({}) }, instrument: null }),
    "Forex · 7 major currency pairs · Daily candles · long and short");
  assert.equal(libMeta({ market: "IN", tf: "15m", side: "long", group: null, instrument: { symbol: "TCS" } }), "India · TCS · 15-minute candles");
});

test("MO-5a: the card says each fact once: one author line, one figure row, the gap once, checks and unseen part on one line", () => {
  const bits = read("src/components/LibraryBits.tsx");
  const card = bits.slice(bits.indexOf("export function LibraryCard"));
  assert.match(card, /By \{e\.author\}/);
  assert.doesNotMatch(card, /<Badge tone="ok"|e\.badge/, "no StratLab badge beside a \"by StratLab\" line");
  assert.doesNotMatch(card, /<BehindHold|<HoldLine|k-eyebrow/);
  // three figures: total after costs, total buy and hold, worst fall; the unseen part goes to the status line
  assert.match(card, /\[TOTAL_AFTER_COSTS, sh\.ret,/);
  assert.match(card, /\[TOTAL_HOLD, sh\.buy_hold,/);
  assert.match(card, /\["Worst fall", sh\.mdd,/);
  assert.equal((card.match(/<Stat /g) ?? []).length, 1, "one Stat, mapped over the three figures");
  assert.match(card, /className="k-small lib-vs" data-testid="lib-hold"/);
  assert.match(card, /\{unseenLabel\(e\)\} <Signed value=\{sh\.unseen\}/);
  // the dates, the check results, the full words and the rules are behind one fold
  assert.match(card, /<Disclosure summary="Rules and details" className="lib-details">[^]*data-testid="lib-window"[^]*e\.reason[^]*<Rules s=\{e\.strategy\} \/>/);
  // both libraries draw it; the public one has no fold (its own page has the rules and the checks)
  assert.match(read("src/pages/LibraryPage.tsx"), /<LibraryCard e=\{e\} actions=/);
  assert.match(read("src/pages/PublicLibrary.tsx"), /<LibraryCard e=\{e\} details=\{false\} actions=/);
  for (const f of ["src/pages/LibraryPage.tsx", "src/pages/PublicLibrary.tsx"]) assert.doesNotMatch(read(f), /Rules and all figures|lib-oneline|k-mini-stats/, f);
});

test("MO-5a: the cards of a row share their rows, so figures and buttons line up (a subgrid), and a phone gets one column", () => {
  const css = read("src/pages/trade/trade.css");
  assert.match(css, /\.k-card\.lib-card \{ display: grid; grid-row: span 7; grid-template-rows: subgrid;/);
  assert.match(css, /\.k-card\.lib-card\.lib-lean \{ grid-row: span 6; \}/);
  assert.match(css, /\.lib-figs \{ display: grid; grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);/);
  assert.match(css, /\.lib-figs > \.k-stat \{ display: grid; grid-row: span 2; grid-template-rows: subgrid;/);
  assert.match(css, /\.lib-by \{[^}]*white-space: nowrap;/, "who made it is one line");
  assert.match(css, /\.lib-meta \{ display: -webkit-box; -webkit-line-clamp: 2;/, "where it was tested is two lines at most, so its last words (the candles) aren't cut");
  // the card has as many children as its rows: head, description, figures, gap, checks, fold, buttons
  const bits = read("src/components/LibraryBits.tsx");
  const card = bits.slice(bits.indexOf("export function LibraryCard"));
  for (const c of ["lib-head", "lib-about", "lib-figs", "lib-vs", "lib-status", "lib-details", "lib-actions"]) assert.ok(card.includes(c), c);
  assert.match(card, /<div className="k-stack k-tight lib-actions">\{actions\}<\/div>/);
});

test("MO-5a: green and red stay on signed figures only, and a result that trails buy and hold isn't coloured as a win", () => {
  const bits = read("src/components/LibraryBits.tsx");
  assert.match(bits, /sh\.ret == null \|\| sh\.ret === 0 \|\| trails\(e\) \? undefined : sh\.ret > 0 \? "up" : "down"/);
  assert.doesNotMatch(bits.slice(bits.indexOf("export function LibraryCard")), /Behind buy and hold by|Passed: |Not run: /);
});

test("MO-5b: the market filter offers only markets that have samples, each with its count, in the library's order", async () => {
  const { marketChoices, marketName, MARKET_NAMES } = await import("../src/lib/libraryList.ts");
  assert.deepEqual(Object.keys(MARKET_NAMES), ["IN", "US", "UK", "EU", "JP", "CRYPTO", "FX", "MCX", "CDS", "CMDTY"]);
  const got = marketChoices({ US: 12, IN: 14, JP: 3, FX: 3 }, [], "");
  assert.deepEqual(got.map((c) => c.value), ["", "IN", "US", "JP", "FX"]);
  assert.deepEqual(got.map((c) => c.label), ["All markets", "India · 14", "United States · 12", "Japan · 3", "Forex · 3"]);
  // the one picked stays so it can be undone, even when nothing is left under it; without the server's counts the rows are counted
  assert.deepEqual(marketChoices({ IN: 2 }, [], "UK").map((c) => c.value), ["", "IN", "UK"]);
  assert.deepEqual(marketChoices(undefined, [{ market: "EU" }, { market: "EU" }, { market: "CDS" }], "").map((c) => c.label), ["All markets", "Europe · 2", "Indian currency futures · 1"]);
  assert.equal(marketName("CMDTY"), "Global commodities");
  for (const f of ["src/pages/LibraryPage.tsx", "src/pages/PublicLibrary.tsx"]) {
    const src = read(f);
    assert.match(src, /<ChipBar label="Market" options=\{(choices|markets)\} value=\{market\} onChange=\{setMarket\} wrap \/>/, f);   // (VR1-181: wrapped on a phone too)
    assert.doesNotMatch(src, /label="Market" value=\{market\}/, `${f}: the dropdown of every market is gone`);
  }
  assert.match(read("src/pages/LibraryPage.tsx"), /markets\?: Record<string, number>/);
});

test("MO-5b: the sites own list of library pages names the other markets' samples, and their slugs find their rules", async () => {
  const seo = await import("../src/content/seo.ts");
  const ids = seo.LIBRARY_SEEDS.map(([id]) => id);
  assert.equal(new Set(ids).size, ids.length);
  for (const [id] of seo.LIBRARY_SEEDS) {
    assert.ok(/^[A-Za-z0-9_-]{6,24}$/.test(id), `${id} fits the library's ids`);
    assert.ok(seo.LIBRARY_RULES[seo.librarySlug(id)], id);
  }
  assert.equal(seo.librarySlug("seed-donchian-20-10-coin"), "donchian-20-10");
  assert.equal(seo.librarySlug("seed-ema-20-50-ls-cds"), "ema-20-50-ls");
  assert.equal(seo.librarySlug("seed-bb-revert-cmd"), "bb-revert");
  for (const suffix of ["-uk", "-eu", "-jp", "-coin", "-fx", "-mcx", "-cds", "-cmd"]) assert.ok(ids.some((i) => i.endsWith(suffix)), `a sample for ${suffix}`);
  // facts only, and no data vendor in what a visitor reads
  for (const [, name] of seo.LIBRARY_SEEDS) assert.doesNotMatch(name, /yahoo|kite|zerodha|screener|finnhub|buy now|recommend/i, name);
  for (const text of Object.values(seo.LIBRARY_RULES)) assert.doesNotMatch(text, /yahoo|kite|zerodha|screener|finnhub|buy now|recommend|should/i, text);
});
