// 24 Oct 2026, the deep audit of notebooks after a run (DA-022 .. DA-041): the verdict's chart and heatmap, trade cards on a
// phone, similar coins, the compare page, the notebook list, sharing, the library, the forward test and the trades export.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const C = await import("../src/lib/compare.ts");
const T = await import("../src/lib/tradeUi.ts");
const L = await import("../src/lib/libraryText.ts");

test("DA-022: the verdict's chart opens on the test's own candles and window, whatever was picked on another visit", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /tf=\{e\.tf as Tf\}/);
  assert.match(page, /openFrom=\{e\.series\.t\[0\] \?\? null\}/);
  assert.match(page, /rangesKeepTf/);
  const chart = read("src/charts/price/PriceChart.tsx");
  assert.match(chart, /useState<Tf>\(props\.tf && offered\.includes\(props\.tf\) \? props\.tf/);      // never a saved timeframe (DD-041)
});

test("DA-026: a heat cell keeps at least half its colour on the dark card, in both ways of choosing dark", () => {
  const css = read("src/styles.css");
  assert.match(css, /:root \{ --series-1: #1F4FB5;[^}]*--heat-floor: 25%; \}/);
  assert.match(css, /:root\[data-theme="dark"\] \{ --series-1: #6A8EE4;[^}]*--heat-floor: 50%; \}/);
  assert.match(css, /:root:not\(\[data-theme\]\) \{ --series-1: #6A8EE4;[^}]*--heat-floor: 50%; \}/);
  assert.match(read("src/components/Charts.tsx"), /color-mix\(in srgb, var\(\$\{val > 0 \? "--series-1" : "--series-2"\}\) \$\{share\}, transparent\)/);
});

test("DA-027: on a phone the trades are short cards by default, every detail one tap away", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /usePersisted<"short" \| "full">\("stratlab\.tradeCards", "short"\)/);
  assert.match(page, /\{ value: "short", label: "Short cards" \}, \{ value: "full", label: "Every detail" \}/);
  assert.match(page, /columns=\{shownCols\}/);
});

test("DA-030: a similar instrument with a shorter history is marked and said not to be counted", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /Prices from \{fmtDate\(r\.from\)\}: not counted/);
  assert.match(page, /data-testid="basket-shorter"/);
});

test("DA-031: each run's line on the dates of both, read off its own points, nothing outside its window", () => {
  const pts = new Map([["2024-01-01", 0], ["2024-01-11", 10], ["2024-01-21", 30]]);
  assert.deepEqual(C.onDates(pts, ["2023-12-25", "2024-01-01", "2024-01-06", "2024-01-11", "2024-01-16", "2024-01-21", "2024-02-01"]),
    [null, 0, 5, 10, 20, 30, null]);
  assert.deepEqual(C.onDates(new Map(), ["2024-01-01"]), [null]);
  const page = read("src/pages/CompareExperiments.tsx");
  assert.match(page, /times=\{dates\} x=\{xs\}/);                      // placed by date
  assert.match(page, /\["Worst fall",/);
  assert.doesNotMatch(page, /\["Worst drop"/);
  assert.equal(T.checksCell(2, 4), "2 of 4");
  assert.equal(T.badgeLabel({ verdict: "edge", passed: 2, total: 4 }), "Passed 2 of 4 checks");
  // the axis's ticks are found by position in the window, so a numeric x with times still gets its dates
  assert.match(read("src/components/chart/XYChart.tsx"), /const ta = T\[Math\.max\(0, Math\.min\(n - 1, in0\)\)\], tb = T\[Math\.max\(0, Math\.min\(n - 1, in1\)\)\];/);
});

test("DA-032: a notebook card is titled by its name, with its question under it and a pin that says Pin; the sidebar's dots are explained", () => {
  const home = read("src/pages/Home.tsx");
  assert.match(home, /title=\{<Link to=\{`\/n\/\$\{n\.id\}`\} className="k-title-link">\{n\.name\}<\/Link>\}/);
  assert.match(home, /className="k-small k-muted nb-question" title=\{question\}/);
  assert.match(home, /\{n\.pinned \? "Pinned" : "Pin"\}/);
  assert.match(home, /Tested on \$\{inst\}/);
  assert.match(read("src/pages/trade/trade.css"), /\.k-cards\.nb-cards \{ align-items: stretch; \}/);
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /VERDICT_FACT\[n\.summary\.last_verdict\]/);
  assert.match(shell, /Dots: each notebook's last verdict\./);
});

test("DA-033: making a public link asks first and says what becomes public; the page then says the verdict is public", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /title="Make a public link\?"/);
  assert.match(page, /Your rules, capital, trades and notes stay private\./);
  assert.match(page, /\{ label: "Make a public link", run: pub\.askMake \}/);
  assert.match(page, /<PublicLinkNote pub=\{pub\} \/>/);
  assert.match(page, /<b>This verdict is public\.<\/b>/);
});

test("DA-034, DA-035: the shared page shows the shared address with its own card, and a gone link goes to the real 404 once", () => {
  const page = read("src/pages/PublicVerdict.tsx");
  assert.match(page, /history\.replaceState\(history\.state, "", shared/);
  assert.match(page, /\["property", "og:image"\], \["name", "twitter:image"\]/);
  assert.match(page, /e\.status === 404 && goneOnce\(token\)\) \{ location\.replace\(`\/v\/\$\{encodeURIComponent\(token\)\}`\)/);
  assert.match(page, /sessionStorage\.getItem\(k\)\) return false/);
});

test("DA-036: the share card has no ruled lines and its reason is whole sentences", () => {
  const card = read("src/components/shareImage.ts");
  assert.doesNotMatch(card, /for \(let y = 34; y < H; y \+= 34\)/);
  assert.match(card, /export function reasonLines\(/);
  assert.match(card, /const sentences = summaryLines\(reason\)/);
});

test("DA-037, DA-038: the library leads with the gap to buy and hold and says once what every card repeated", () => {
  const page = read("src/pages/LibraryPage.tsx");
  assert.match(page, /useState\("hold"\)/);
  assert.match(page, /\{ value: "hold", label: "Ahead of buy and hold", short: "Vs hold" \}, \{ value: "best", label: "Most checks passed", short: "Checks" \}/);
  assert.doesNotMatch(page, /trails\(e\) && <p className="k-note" data-testid="lib-checks-not-hold">/);
  assert.match(page, /data-testid="lib-list-notes"/);
  assert.match(L.LIBRARY_DATES, /A copy is tested again up to the latest prices, so its figures can differ\./);
  for (const p of ["src/lib/features.ts", "src/pages/Login.tsx"]) assert.doesNotMatch(read(p), /mega caps/, p);
});

test("DA-039, DA-040: the forward test says what it is for, lists India when it is offline, and offers the plans once", () => {
  const page = read("src/pages/trade/SignalsPage.tsx");
  assert.match(page, /lede="A forward test tries a strategy on days that have not happened yet: connect your TradingView or Chartink alerts/);
  assert.match(page, /m\.status === "live" \|\| m\.status === "offline"/);
  assert.match(page, /offlineLine\(market\.name, me\?\.data_note\)/);
  assert.match(page, /title="Connect a TradingView alert"/);
  assert.match(page, /<LockedPreview title="Forward test" actions=\{false\}/);
  assert.match(read("src/pages/trade/ReplayPage.tsx"), /<LockedPreview title="Chart replay" actions=\{false\}/);
});

test("DA-041: a run's trades download as CSV from its verdict, and the notebook's export says it is the rules", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /\/experiments\/\$\{e\.v\}\/trades\.csv`, \{ raw: true \}/);
  assert.match(page, /Download as CSV\{canExport \? "" : " \(Pro\)"\}/);
  assert.match(read("src/pages/NotebookPage.tsx"), /label: `Export the rules\$\{canExport \? "" : " \(Pro\)"\}`/);
  assert.match(read("src/lib/plans.ts"), /\["export", "Export a notebook's rules and trades"\]/);
});
