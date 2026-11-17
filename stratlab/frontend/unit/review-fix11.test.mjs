// fix11 (17 Nov 2026): open LIVE10A / LIVE10B / CX2 findings. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10A-025: a weekly date axis ticks on Mondays, seven days apart; Flows places its days by date", async () => {
  const { timeTicks } = await import("../src/lib/chartFormat.ts");
  const ticks = timeTicks(Date.UTC(2026, 9, 6), Date.UTC(2026, 10, 16), 7, "Asia/Kolkata", true);
  assert.deepEqual(ticks.map((t) => t.label), ["12 Oct", "19 Oct", "26 Oct", "2 Nov", "9 Nov", "16 Nov"]);
  for (let k = 1; k < ticks.length; k++) assert.equal(ticks[k].t - ticks[k - 1].t, 7 * 86400000);
  assert.match(read("src/pages/FlowsPage.tsx"), /x=\{shown\.map\(\(p\) => Date\.parse\(`\$\{p\.day\.slice\(0, 10\)\}T00:00:00Z`\)\)\}/);
});

test("LIVE10A-036: Briefs reads the other market's list ahead and paints a list it has read at once", () => {
  const page = read("src/pages/NewsPage.tsx");
  assert.match(page, /const seen = new Map<string, IssueRow\[\]>\(\);/);
  assert.match(page, /setList\(had \? \{ tab, rows: had \} : null\);/);
  assert.match(page, /if \(tab !== "mine" && !seen\.has\(other\)\) readList\(other\)/);
});

test("LIVE10A-031/014: the Markets panel fades a price still from this device's earlier read; a shut market's row says Closed, not Delayed", () => {
  const panel = read("src/components/watch/WatchPanel.tsx");
  assert.match(panel, /setReadNow\(\(o\) => \(o\.has\(k\) \? o : new Set\(o\)\.add\(k\)\)\)/);
  assert.match(panel, /old=\{!readNow\.has\(it\.id\) && ticks\[it\.id\] == null && quotes\[it\.id\] != null && open\[it\.market\] !== false\}/);
  assert.match(panel, /open\[it\.market\] === false \? \(allShut \? null : "Closed"\) : quotes\[it\.id\]\?\.delayed \? "Delayed" : null/);
  assert.match(read("src/components/watch/WatchRow.tsx"), /\$\{p\.old \? " old" : ""\}/);
  assert.match(read("src/components/watch/watch.css"), /\.mw-row\.old \.mw-num \{ opacity: \.5;/);
});

test("LIVE10A-014: the Watchlist page names the lists made in the Markets panel, each opening the panel on that list", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /getLists\(\)\.then\(\(a\) => \{ if \(live\) setOthers\(a\.lists\.filter\(\(l\) => !l\.default\)\); \}\)/);
  assert.match(page, /<Card testId="watch-other-lists">/);
  assert.match(page, /onClick=\{\(\) => openMarkets\(\{ open: true, list: l\.id \}\)\}>Open in the Markets panel<\/button>/);
  assert.match(read("src/components/watch/Launcher.tsx"), /d\.list \? \{ list: d\.list, chart: null \} : \{\}/);
});

test("LIVE10A-032 / LIVE10B-023: a company page says how many of your alerts watch the stock, beside Set alert, read again after a save", () => {
  const form = read("src/components/AlertForm.tsx");
  assert.match(form, /setOn\(r\.active\.filter\(\(a\) => a\.region === region && a\.symbol === symbol\)\.length\)/);
  assert.match(form, /\{showOn && on > 0 && <Link className="k-chip" to="\/alerts" data-testid="alerts-on">\{on\} alert\{on === 1 \? "" : "s"\} on<\/Link>\}/);
  assert.match(form, /onClose=\{\(\) => \{ setOpen\(false\); setSeen\(\(n\) => n \+ 1\); \}\}/);
  assert.match(read("src/pages/Research.tsx"), /<AlertButton region=\{region\} symbol=\{c\.symbol\} showOn \/>/);
});

test("LIVE10A-028: /new holds the market chips' row and the search box while the markets are read", () => {
  assert.match(read("src/pages/Home.tsx"), /\{!markets\.length \? <div className="k-where-wait" role="status" aria-busy="true" aria-label="Reading the markets"><span className="lp-skel" \/><span className="lp-skel" \/><\/div>/);
  assert.match(read("src/styles.css"), /\.k-where-wait \.lp-skel \+ \.lp-skel \{ height: 44px; \}/);
});

test("LIVE10A-027: a phone's results row names the company under its symbol, on one line", () => {
  const css = read("src/styles-invest.css");
  assert.doesNotMatch(css, /\.k-tbl-wrap\.compact \.res-name \{ display: none; \}|\.k-tbl-wrap\.compact \.res-plain, \.k-tbl-wrap\.compact \.res-name/);
  assert.match(css, /\.k-tbl-wrap\.compact \.res-name \{ white-space: nowrap; \}/);
});

test("CX2: /home opens My space, sent to the app by every web server (it was \"Page not found\")", async () => {
  assert.match(read("src/main.tsx"), /<Route path="\/home" element=\{<Redirect to="\/mine" \/>\} \/>/);
  const { APP_ROUTES } = await import("../src/lib/deepLinks.ts");
  assert.ok(APP_ROUTES.includes("/home"));
  for (const f of ["Caddyfile", "vercel.json", "public/sw.js"]) assert.match(read(f), /mine\|all\|home\|features/, f);
});

test("CX2 / LIVE10A-020: the calendars say how many companies no size counts, whenever there are some", () => {
  const f = read("src/components/CalendarFilters.tsx");
  assert.match(f, /\{unknownSize > 0 && <span className="k-note k-muted" data-testid="cal-unsized">/);
  assert.doesNotMatch(f, /filters\.size\.length > 0 && unknownSize > 0/);
});

test("LIVE10A-004: a company checked against its own description whose passage isn't quoted never reads 'No description in its own words yet'", async () => {
  const { noWords, NO_WORDS, NOT_QUOTED } = await import("../src/lib/themeFormat.ts");
  assert.equal(noWords(false), NO_WORDS);
  assert.equal(noWords(true), NOT_QUOTED);
  assert.doesNotMatch(NOT_QUOTED, /No description/);
  assert.match(read("src/components/ThemeDive.tsx"), /noWords\(c\.base \? ev\?\.\(c\.ticker\) === "description_verified" : !!c\.verified\)/);
});

test("LIVE10A-012: a tall, narrow heatmap tile too thin for its symbol across names it down its length", async () => {
  const { tileWords } = await import("../src/lib/heatmap.ts");
  const width = (t) => t.length * 6.2;                         // roughly the 600-weight width of a 10px letter
  assert.deepEqual(tileWords("HINDALCO", "+1.2%", 40, 220, width), { px: 12, fig: false, vert: true });
  assert.equal(tileWords("HINDALCO", "+1.2%", 160, 100, width).vert, undefined);       // a wide tile names it across
  assert.deepEqual(tileWords("HINDALCO", "+1.2%", 10, 220, width), { px: 0, fig: false });   // too thin for a letter
  assert.match(read("src/components/chart/treemap.css"), /\.hm-tile\.vert \.hm-sym \{ writing-mode: vertical-rl;/);
});

test("LIVE10A-012: the heatmap reads its width before its first paint, so it is drawn at its own height, not its floor", () => {
  const t = read("src/components/chart/Treemap.tsx");
  assert.match(t, /useLayoutEffect\(\(\) => \{\n\s+const el = box\.current;\n\s+if \(!el\) return;\n\s+const read = \(\) => setWidth\(Math\.floor\(el\.clientWidth\)\);/);
});

test("LIVE10A-012: the heatmap's Stocks box holds its place while the first read is out", () => {
  const page = read("src/pages/HeatmapPage.tsx");
  assert.match(page, /\{!theme && \(!view \|\| view\.universes\.length > 0\) && \(/);
  assert.match(page, /<Select id=\{id\} value="" disabled onChange=\{\(\) => undefined\} options=\{\[\{ value: "", label: "Reading the groups…" \}\]\} \/>/);
});

test("LIVE10B-029/047, LIVE10A-013: a tiny deepest fall keeps its digits; the VIX tile's day never splits; an F&O change chip is in the page's letters", () => {
  assert.match(read("src/components/RiskOverview.tsx"), /num\(c\.max_drawdown_pct, c\.max_drawdown_pct && Math\.abs\(c\.max_drawdown_pct\) < 0\.1 \? 2 : 1\)/);
  assert.match(read("src/pages/SpaceHomes.tsx"), /\{vixDay \? <> · <span className="nowrap">\{vixDay\}<\/span><\/> : ""\}/);
  assert.match(read("src/styles.css"), /\.surv-badge\.fo-badge \{ white-space: nowrap; max-width: 100%; overflow: hidden; text-overflow: ellipsis; font-family: var\(--sans\); \}/);
});

test("LIVE10B-010: My space's net worth line is coloured by its own direction, first point to last", () => {
  assert.match(read("src/pages/MineHome.tsx"), /tone=\{whole\[whole\.length - 1\]\.net < whole\[0\]\.net \? "down" : "up"\} area height=\{64\} label="Net worth over time"/);
});

test("LIVE10B-043: Settings says a holdings import's day once, in India's time", () => {
  const page = read("src/pages/SettingsPage.tsx");
  assert.match(page, /note=\{h\?\.source && h\.updated_at \? noun\(h\.count, "stock", "stocks"\) : note\(h, noun\(h\?\.count, "stock", "stocks"\)\)\}/);
  assert.match(page, /on \$\{fmtDate\(h\.updated_at, \{ year: false, tz: "Asia\/Kolkata" \}\)\}/);
});
