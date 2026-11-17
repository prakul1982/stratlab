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
