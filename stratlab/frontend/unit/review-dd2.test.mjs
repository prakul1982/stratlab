// Deep review DD (24 Oct 2026): the signed-in company pages' screens — the market mood, one Invest home, the offline
// line, the company card, deals, news ages, alerts, the watchlist, the price chart, the deep dive and compare.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DD-001: the mood card leads with the mood and the main story, and says where the FII/DII figures come from", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /\{ai\.mood && <p className="inv-summary" data-testid="pulse-mood"><b>\{ai\.mood\}<\/b><\/p>\}/);
  assert.match(page, /\{ai\.flows_source && <p className="k-note" data-testid="pulse-flows-source">\{ai\.flows_source\}<\/p>\}/);
  assert.match(read("src/lib/research.ts"), /mood\?: string;[\s\S]*flows_source\?: string;/);
});

test("DD-002: one Invest home, no second company search box; Look up a company is the search", () => {
  const homes = read("src/pages/SpaceHomes.tsx");
  assert.match(homes, /<Head eyebrow="Invest · companies and markets" title="Invest home">/);
  assert.doesNotMatch(homes, /<CompanySearch|Jump to a company|Your research desk/);
  assert.match(homes, /<Link to=\{`\/research\?region=\$\{region\}`\} className="link">Look up a company<\/Link>/);
  const lookup = read("src/pages/Research.tsx");
  const home = lookup.slice(lookup.indexOf("export function ResearchHome"), lookup.indexOf("/* ================= One company"));
  assert.doesNotMatch(home, /Explore a theme/);
  assert.match(home, /<Link to="\/invest" className="link">Invest home<\/Link>/);
  assert.doesNotMatch(read("src/components/Explore.tsx"), /\/>Search everything<\/button>/);
});

test("DD-006, DC-002, DP2-036: the weekend line says when the market opens, on one short line", async () => {
  const { closedLine, nextOpenAt } = await import("../src/lib/dataBack.ts");
  const nse = { id: "IN", name: "India", venues: "", currency: "INR", symbol: "₹", tz: "Asia/Kolkata", status: "offline", max_days: null,
    hours: { open: "09:15", close: "15:30", days: "Mon–Fri" }, what: "", costs: "", brokerage: 0, holidays: [] };
  const sat = new Date("2026-10-24T06:00:00Z");                       // Saturday 11:30 IST
  assert.equal(nextOpenAt(nse, sat), "Mon 26 Oct, 09:15 IST");
  assert.equal(nextOpenAt({ ...nse, holidays: ["2026-10-26"] }, sat), "Tue 27 Oct, 09:15 IST");
  assert.equal(nextOpenAt(null, sat), null);
  const line = closedLine("weekend", "Mon 26 Oct, 09:15 IST");
  assert.equal(line.full, "Indian markets are closed for the weekend and open again Mon 26 Oct, 09:15 IST. Indian prices are the last close.");
  assert.equal(line.short, "Indian markets open Mon 26 Oct, 09:15 IST");
  assert.doesNotMatch(line.full, /reconnect|work as usual|data login/);
  const main = read("src/main.tsx");
  assert.match(main, /<DataBanner note=\{me\?\.data_note \?\? null\} market=\{markets\.find\(\(m\) => m\.id === "IN"\)\} \/>/);
  assert.doesNotMatch(main, /work as usual/);
  assert.match(read("src/styles.css"), /\.banner\.data-banner \{ padding: 6px 14px; font-size: 13\.5px; margin-bottom: 14px; flex-wrap: nowrap; \}/);
});

test("DD-019: the company card's buttons sit under the market value, beside the price column", () => {
  const css = read("src/styles-invest.css");
  assert.match(css, /\.inv-head > \.inv-head-price \{ grid-column: 2; grid-row: 1 \/ span 2; \}/);
  assert.match(css, /\.inv-head > \.inv-actions \{ grid-column: 1; grid-row: 2; align-self: start; \}/);
  assert.match(read("src/pages/Research.tsx"), /<div className="k-row inv-actions">/);
});

test("DD-020, DD-054: a bar's figure that won't fit is written short for the whole chart; the latest bars share a colour", () => {
  const bars = read("src/components/Research.tsx");
  assert.match(bars, /const tight = points\.some\(\(p\) => trendValue\(p\.v, unit\)\.length > \(points\.length >= DENSE_BARS \? 6 : 7\)\);/);
  for (const f of ["src/pages/Research.tsx", "src/pages/DeepDive.tsx"]) assert.doesNotMatch(read(f), /<TrendBars[^>]*tone="blue"/, f);
});

test("DD-021: a bulk or block deal's two sides are one row; no 0.00% after and no \"Other\"", async () => {
  const { pairDeals, afterText } = await import("../src/lib/dealRows.ts");
  const d = (who, side, kind = "block", qty = 1000, price = 50) => ({ id: who, kind, date: "2026-10-20", qty, price, side, who });
  const rows = pairDeals([d("Fund A", "sold"), d("Fund B", "bought"), d("Promoter", "bought", "insider"), d("C", "bought", "bulk", 5), d("D", "bought", "bulk", 5)]);
  assert.deepEqual(rows.map((r) => [r.who, r.from ?? null]), [["Fund B", "Fund A"], ["Promoter", null], ["C", null], ["D", null]]);
  assert.equal(afterText(0), null);
  assert.equal(afterText(0.004), "under 0.01% after");
  assert.equal(afterText(1.234), "1.23% after");
  assert.match(read("src/components/Deals.tsx"), /d\.relation && d\.relation !== "other" &&/);
});

test("DD-022: every headline's time reads the same way", async () => {
  const { newsWhen } = await import("../src/lib/researchFormat.ts");
  const now = new Date("2026-10-24T12:00:00Z");
  assert.equal(newsWhen("2026-10-24T11:20:00Z", now), "40 min ago");
  assert.equal(newsWhen("2026-10-24T07:00:00Z", now), "5 hours ago");
  assert.equal(newsWhen("2026-10-21T09:00:00Z", now), "21 Oct · 3 days old");
  assert.equal(newsWhen("2026-10-12T09:00:00Z", now), "12 Oct · 1 week old");
  assert.equal(newsWhen("2025-12-01T09:00:00Z", now), "1 Dec 2025 · 10 months old");
  assert.doesNotMatch(read("src/components/Research.tsx"), /ago\(n\.at\)/);
});

test("DD-024: the alert form offers only the kinds that fit the instrument", async () => {
  globalThis.window ??= {};                                           // lib/config reads the page's settings off window
  const { fittingConditions } = await import("../src/lib/alerts.ts");
  const keys = (r, f, keep) => fittingConditions(r, f, keep).map((c) => c.key);
  const stock = keys("IN", { etf: false, fo: false });
  assert.ok(!stock.some((k) => k.startsWith("etfgap") || k === "mwpl"));
  assert.ok(stock.includes("insider") && stock.includes("bizupdate"));
  const etf = keys("IN", { etf: true, fo: false });
  assert.ok(etf.includes("etfgap_either") && !etf.includes("insider") && !etf.includes("bizupdate"));
  assert.ok(keys("IN", { etf: false, fo: true }).includes("mwpl"));
  assert.ok(keys("IN", null).includes("etfgap_either"));               // not known yet: left in
  assert.ok(!keys("US", null).includes("insider"));
  assert.ok(keys("IN", { etf: false, fo: false }, "mwpl").includes("mwpl"));      // the alert being edited stays
  assert.match(read("src/components/AlertForm.tsx"), /alertsApi\.fits\(region, sym\)/);
});

test("DD-025: a removed company comes back with Undo, where it was", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /notify\(`\$\{w\.symbol\} removed from your watchlist\.`, \{ label: "Undo", run: \(\) => \{/);
  assert.match(page, /save\(\(cur\) => \(cur\.some\(same\) \? cur : \[\.\.\.cur\.slice\(0, at\), w, \.\.\.cur\.slice\(at\)\]\)\)/);
  assert.match(page, /onClick=\{\(\) => remove\(w\)\}><Trash size=\{16\} \/><\/button>/);
});

test("DD-040: each indicator pane adds height; the candles start under the legend", () => {
  const chart = read("src/charts/price/PriceChart.tsx");
  assert.match(chart, /export const PANE_ADD = 110;/);
  assert.match(chart, /const stageH = height \+ ownPanes \* PANE_ADD;/);
  assert.match(chart, /style=\{\{ \["--pc-h" as string\]: `\$\{stageH\}px` \}\}/);
  const engine = read("src/charts/price/engine.ts");
  assert.match(engine, /this\.price\.fit\(lo, hi, Math\.min\(0\.45, Math\.max\(0\.1, legendTop\)\), this\.volume \? 0\.22 : 0\.08\);/);
  assert.match(engine, /this\.invalidate\(taller\);/);
});

test("DD-041: the chart opens on the page's own timeframe; indicators are the symbol's own", () => {
  const chart = read("src/charts/price/PriceChart.tsx");
  assert.match(chart, /const \[tf, setTf\] = useState<Tf>\(props\.tf && offered\.includes\(props\.tf\) \? props\.tf : offered\.includes\("1d"\) \? "1d" : offered\[0\]\);/);
  assert.match(chart, /validStudies\(lay0\?\.studies \?\? \[\]\)/);
  assert.doesNotMatch(chart, /stratlab\.pc\.studies|lsSet\(LS\.studies/);
  assert.match(chart, /setMine\(validStudies\(l\?\.studies \?\? \[\]\)\);/);
  assert.doesNotMatch(chart, /l\.tf = st\.tf/);
});

test("DD-042: an unknown compare symbol is said in the box; the button is always pressable", () => {
  const chart = read("src/charts/price/PriceChart.tsx");
  assert.match(chart, /setCmpErr\(status && status >= 500 \? "Prices couldn't be read just now\. Try again in a moment\." : `No prices found for \$\{want\}\./);
  assert.match(chart, /<button type="submit" className="pc-btn primary" disabled=\{cmpBusy\}>/);
  assert.match(chart, /\{cmpErr && <span id="pc-cmp-err" className="pc-pop-err" role="alert">\{cmpErr\}<\/span>\}/);
});

test("DD-043: a lone bad monthly print is taken out; real moves stay", async () => {
  const { dropSpikes } = await import("../src/charts/price/transforms.ts");
  const bar = (i, o, h, l, c) => ({ t: i, w: i, o, h, l, c, v: 1, day: i });
  const wick = dropSpikes([bar(1, 50, 55, 45, 52), bar(2, 52, 218, 48, 51), bar(3, 51, 58, 47, 55)]);
  assert.equal(wick.length, 3);
  assert.equal(wick[1].h, 52);                                        // down to the body's top
  const body = dropSpikes([bar(1, 50, 55, 45, 52), bar(2, 200, 220, 190, 210), bar(3, 51, 58, 47, 55)]);
  assert.deepEqual(body.map((b) => b.t), [1, 3]);
  const real = [bar(1, 50, 55, 45, 52), bar(2, 52, 120, 50, 110), bar(3, 110, 130, 100, 125)];     // a doubling that holds
  assert.deepEqual(dropSpikes(real), real);
  assert.match(read("src/charts/price/PriceChart.tsx"), /t === "1mo" \? dropSpikes\(aggregate\(base, "month"\)\)/);
});

test("DD-045: a day on the time axis names its month; + Custom opens over the chart; the table is as tall as the chart", async () => {
  const { timeTicks } = await import("../src/charts/price/scales.ts");
  const day = (m, d) => Date.UTC(2026, m, d);
  const walls = [day(2, 2), day(2, 3), day(2, 7), day(2, 21), day(3, 1)];
  const ticks = timeTicks(walls, 0, walls.length - 1, (i) => i * 100, 84);
  assert.ok(ticks.every((t) => !/^\d{1,2}$/.test(t.label)), ticks.map((t) => t.label).join(","));
  assert.ok(ticks.some((t) => t.label === "21 Mar"));
  const css = read("src/charts/price/priceChart.css");
  assert.match(css, /\.pc-bar \.k-custom \{ position: absolute; z-index: 20;/);
  assert.match(css, /\.pc-table \{ max-height: max\(360px, var\(--pc-h, 420px\)\);/);
});

test("DD-046: the indicator menu is short, and the Stage says its 150-day average", async () => {
  const { STUDIES } = await import("../src/charts/price/studies.ts");
  const stage = STUDIES.find((s) => s.type === "stage");
  assert.equal(stage.name, "Stage (150-day average)");
  for (const s of STUDIES) assert.ok(s.about.length <= 70, `${s.type}: ${s.about}`);
  assert.match(read("src/charts/price/PriceChart.tsx"), /className="item" title=\{d\.detail\}/);
});

test("DD-051: the deep dive's tables are cards on a phone", () => {
  assert.match(read("src/components/BizUpdates.tsx"), /<DataTable label=\{`\$\{symbol\} business update figures`\} stack /);
  const deep = read("src/pages/DeepDive.tsx");
  assert.match(deep, /<DataTable label="The last eight quarters" stack /);
  assert.match(deep, /<DataTable label="Capex and cash by year" stack /);
  assert.match(read("src/styles.css"), /\.biz-updates \.k-tbl-wrap\.stack \.inv-clamp \{ display: none; \}/);
});

test("DD-054: the deep dive links to the company page's holders and deals instead of repeating them", () => {
  const deep = read("src/pages/DeepDive.tsx");
  assert.doesNotMatch(deep, /<DealsPanel|<NamedHoldersPanel/);
  assert.match(deep, /to=\{`\/research\/IN\/\$\{encodeURIComponent\(v\.symbol\)\}#deals`\}/);
});

test("DD-060, DD-061: compare lines its columns up, draws both prices, shows who owns each, and is kind about one company twice", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /<PriceChart region=\{region\} symbol=\{res\.a\.symbol\} currency=\{res\.a\.currency\} price=\{res\.a\.quote\?\.price\} compareWith=\{res\.b\.symbol\} \/>/);
  assert.match(page, /<div className="k-stack cmp-sections">/);
  assert.match(page, /data-testid="cmp-owners"/);
  assert.match(page, /const same = !!a && !!b && canonTicker\(region, a\) === canonTicker\(region, b\);/);
  assert.match(page, /\(e as ApiError\)\.code === "same_symbol"/);
  assert.match(read("src/styles-invest.css"), /\.cmp-sections \.k-table \{ table-layout: fixed;/);
});

test("DD-072: the watchlist list says the P/E, the 52-week position and the alerts on each company", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /\/research\/watchlist\/facts\?region=\$\{region\}&symbols=/);
  assert.match(page, /data-testid="watch-facts"/);
  assert.match(page, /alert\{alertCount\[w\.symbol\] === 1 \? "" : "s"\} on/);
});
