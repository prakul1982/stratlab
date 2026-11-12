// Owner-approved features of 12 Nov (lane f3): import a watchlist (pasted symbols or a file's column, each looked up with the symbol
// search, then "Add N to <list>" within the plan's limits) and "Report an error in this figure" (a flag beside the figures of the app's
// tables and key-number cards, opening a dialog filled in with the page, the figure, its value, period and source).
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const W = await import("../src/lib/watchImport.ts");
const F = await import("../src/lib/figureReport.ts");
const { ADMIN_TYPES, FEEDBACK_TYPES } = await import("../src/lib/feedback.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const server = (f) => readFileSync(new URL(`../../backend/app/${f}`, import.meta.url), "utf8");

const it = (market, symbol, name = symbol) => ({ id: `${market}:${symbol}`, market, symbol, name, kind: "stock" });

test("pasted symbols: lines, commas, semicolons or tabs, any case, each once, and the server's own cap", () => {
  assert.deepEqual(W.splitPasted("RELIANCE, TCS, HDFCBANK\nNVDA\n infosys \n\ntcs;\"INFY\"\tBRK.B"), ["RELIANCE", "TCS", "HDFCBANK", "NVDA", "infosys", "INFY", "BRK.B"]);
  assert.deepEqual(W.splitPasted("Tata   Consultancy Services\r\nHDFC Bank"), ["Tata Consultancy Services", "HDFC Bank"]);
  assert.equal(W.splitPasted(Array.from({ length: 400 }, (_, i) => `S${i}`).join(",")).length, W.IMPORT_MAX);
  assert.match(server("watch_import.py"), /MAX_QUERIES = WS\.HARD_SYMBOLS/);
  assert.match(server("watch_store.py"), new RegExp(`HARD_SYMBOLS = ${W.IMPORT_MAX}\\b`));
  assert.deepEqual(W.allQueries(["TCS"], ["tcs", "INFY"]), ["TCS", "INFY"]);
});

test("found rows add their match, a row to confirm adds the picked suggestion (the best first), skipped or missing rows add nothing", () => {
  const rows = [
    { query: "RELIANCE", status: "found", item: it("IN", "RELIANCE"), suggestions: [] },
    { query: "infosys", status: "confirm", item: null, suggestions: [it("IN", "INFY", "Infosys"), it("US", "INFY", "Infosys ADR")] },
    { query: "TCS", status: "found", item: it("IN", "TCS"), suggestions: [] },
    { query: "zzzq", status: "missing", item: null, suggestions: [] },
    { query: "reliance industries", status: "confirm", item: null, suggestions: [it("IN", "RELIANCE")] },
  ];
  assert.deepEqual(W.toAdd(rows, {}, new Set()).map((x) => x.id), ["IN:RELIANCE", "IN:INFY", "IN:TCS"]);       // the same company once
  assert.deepEqual(W.toAdd(rows, { infosys: "US:INFY" }, new Set(["IN:TCS"])).map((x) => x.id), ["IN:RELIANCE", "US:INFY"]);   // already on the list: left out
  assert.deepEqual(W.toAdd(rows, { infosys: "", RELIANCE: "" }, new Set()).map((x) => x.id), ["IN:TCS", "IN:RELIANCE"]);      // a later line confirming it still adds it
  assert.equal(W.summaryLine(rows), "2 found, 2 to confirm, 1 not found");
  assert.equal(W.summaryLine(rows.slice(0, 1)), "1 found");
});

test("the plan's limit is said plainly before anything is added, and the button says what it adds", () => {
  assert.equal(W.limitSaid({ cap: 20, used: 15, adding: 5, plan: "Free", list: "Watchlist" }), null);
  assert.equal(W.limitSaid({ cap: null, used: 900, adding: 50, plan: "Pro", list: "Watchlist" }), null);
  assert.equal(W.limitSaid({ cap: 20, used: 17, adding: 6, plan: "Free", list: "Watchlist", next: "Basic keeps 100" }),
    "Watchlist has 17 of the 20 symbols Free keeps in a list: 3 of these 6 fit, so the first 3 will be added and the other 3 left out. Basic keeps 100.");
  assert.equal(W.limitSaid({ cap: 20, used: 20, adding: 2, plan: "Free", list: "Watchlist", next: "Basic keeps 100" }),
    "Watchlist has 20 of the 20 symbols Free keeps in a list, so none of these can be added. Basic keeps 100.");
  assert.equal(W.room(20, 17, 6), 3);
  assert.equal(W.addLabel(5, 5, "Watchlist"), "Add 5 to Watchlist");
  assert.equal(W.addLabel(6, 3, "Tech"), "Add the first 3 to Tech");
  assert.equal(W.addLabel(2, 0, "Watchlist"), "Nothing to add to Watchlist");
});

test("the import opens from Market Watch and the watchlist page; a file is Basic and up, named the same in plans.py and the Plans copy", () => {
  const panel = read("src/components/watch/WatchPanel.tsx");
  assert.match(panel, /aria-label="Import symbols into a list"/);
  assert.match(panel, /import\("\.\/ImportWatchlist"\)/);                      // downloaded only when opened
  assert.match(read("src/pages/Research.tsx"), /Import a watchlist<\/button>/);
  const dlg = read("src/components/watch/ImportWatchlist.tsx");
  assert.match(dlg, /\/watch\/import\/resolve/);
  assert.match(dlg, /\/watch\/import\/file/);
  assert.match(dlg, /features\?\.watchlist_import !== false/);
  assert.match(server("plans.py"), /"watchlist_import"\}/);
  assert.match(read("src/lib/plans.ts"), /\["watchlist_import", "Watchlist import from a CSV or Excel file"\]/);
  assert.match(read("src/lib/planFeatures.ts"), /watchlist import from a file/);
  assert.match(W.FILE_LOCK, /Basic plan/);
});

test("the report flag is in the shared table and figure components, only inside a scope, and the dialog downloads when opened", () => {
  const table = read("src/components/kit/DataTable.tsx");
  assert.match(table, /useReportScope\(\)/);
  assert.match(table, /\{v\}\{more\}\{report\(r, v\)\}/);
  assert.match(read("src/components/kit/Stat.tsx"), /<ReportFigure label=\{textOf\(label\)\}/);
  const kit = read("src/components/kit/ReportFigure.tsx");
  assert.match(kit, /if \(!scope \|\| !label\.trim\(\)\) return null;/);
  assert.match(kit, /aria-label=\{`Report an error in \$\{name\}`\}/);
  assert.match(read("vite.config.ts"), /ShowLess\|ReportFigure\)\\\.tsx/);       // in the public kit's file, not the account kit's
  for (const [f, section] of [["src/pages/Research.tsx", 'section="Key numbers"'], ["src/pages/Research.tsx", 'section="Sales and profit, by year"'],
    ["src/pages/DeepDive.tsx", 'section="Growth and margins"'], ["src/components/ThemeDive.tsx", "section={`Theme layer: ${layer.layer}`}"],
    ["src/pages/ResultsPage.tsx", "section={`Results on ${resultDay(d)}`}"], ["src/pages/HeatmapPage.tsx", "section={`Heatmap: ${name}`}"]]) {
    assert.ok(read(f).includes(`<ReportScope ${section}`), `${f}: ${section}`);
  }
  assert.match(read("src/pages/HeatmapPage.tsx"), /Report it from the Table view/);
  const main = read("src/main.tsx");
  assert.match(main, /<FigureReports \/>/);
  assert.match(read("src/components/FigureReportHost.tsx"), /import\("\.\/FigureReportDialog"\)/);
  const dlg = read("src/components/FigureReportDialog.tsx");
  assert.match(dlg, /\/feedback\/figure/);
  assert.match(dlg, /Sign in to report/);
});

test("the dialog starts on the latest period of a table of periods, else the row's first figure", () => {
  assert.deepEqual(F.figureChoice([["FY24", "17.1%"], ["FY25", "17.8%"], ["FY26", "18.4%"]]), { index: 2, column: "FY26", value: "18.4%", period: "FY26" });
  assert.deepEqual(F.figureChoice([["Sales", "1,200"], ["Net profit", "140"]]), { index: 0, column: "Sales", value: "1,200", period: null });
  assert.deepEqual(F.figureChoice([["Sales", "1,200"], ["Net profit", "140"]], 1), { index: 1, column: "Net profit", value: "140", period: null });
  assert.deepEqual(F.figureChoice([["Value", "22.5%"]]), { index: 0, column: null, value: "22.5%", period: null });
  assert.deepEqual(F.figureChoice([]), { index: 0, column: null, value: null, period: null });
  for (const p of ["FY26", "Q2 FY27", "2025", "Mar 2026", "TTM", "2024-25"]) assert.ok(F.isPeriod(p), p);
  for (const p of ["Sales", "EBITDA margin", "Last 3 years"]) assert.ok(!F.isPeriod(p), p);
  assert.equal(F.pageName({ querySelector: () => ({ textContent: " Tata Consultancy Services " }), title: "x" }), "Tata Consultancy Services");
  assert.equal(F.pageName({ querySelector: () => null, title: "Heatmap | StratLab" }), "Heatmap");
});

test("Admin → Feedback lists data errors with their figure; the form keeps its three types; limits match the server", () => {
  assert.deepEqual(FEEDBACK_TYPES.map(([v]) => v), ["broken", "not_working", "idea"]);
  assert.deepEqual(ADMIN_TYPES.at(-1), ["data_error", "Data error"]);
  assert.ok(server("feedback.py").includes('"data_error": "Data error"'));
  const admin = read("src/pages/admin/FeedbackSection.tsx");
  assert.match(admin, /data-testid="feedback-figure"/);
  assert.match(admin, /Reporter told/);
  assert.match(read("src/components/FigureReportHost.tsx"), /\/feedback\/notes\/seen/);
});
