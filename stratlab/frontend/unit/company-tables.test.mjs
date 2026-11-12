// Lane c-f2: a company's Peers, Financial statements and Shareholding history. The helpers the cards use (lib/companyTables.ts), where
// the cards sit (company page and deep dive), the plan copies, and the rules the cards keep (kit pieces, no vendor names, no advice words).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const ct = await import("../src/lib/companyTables.ts");

test("a market value is written in the units its market says", () => {
  assert.equal(ct.capText(925, "IN"), "₹925 cr");
  assert.equal(ct.capText(151000, "IN"), "₹1.51 lakh cr");
  assert.equal(ct.capText(412300, "US"), "$412.3B");
  assert.equal(ct.capText(null, "US"), "–");
  assert.equal(ct.peText(28.04), "28.0×");
  assert.equal(ct.peText(null), "–");
});

test("a statement figure is written by its row's kind, with a real minus and a dash for none", () => {
  assert.equal(ct.cellText(123456, "money", "IN"), "1,23,456");
  assert.equal(ct.cellText(123456, "money", "US"), "123,456");
  assert.equal(ct.cellText(-5400, "money", "IN"), "−5,400");
  assert.equal(ct.cellText(2.5, "money", "IN"), "2.5");
  assert.equal(ct.cellText(17, "pct", "IN"), "17.0%");
  assert.equal(ct.cellText(-3.25, "pct", "IN"), "−3.3%");
  assert.equal(ct.cellText(89.74, "per_share", "IN"), "89.74");
  assert.equal(ct.cellText(0.2, "ratio", "IN"), "0.20");
  assert.equal(ct.cellText(45, "days", "IN"), "45");
  assert.equal(ct.cellText(null, "money", "IN"), "–");
  assert.equal(ct.cellText(NaN, "pct", "IN"), "–");
});

test("peers sort by a column with the missing figures last, and equal ones keep their order", () => {
  const r = (symbol, pe, net = 1) => ({ symbol, name: symbol, own: false, market_cap: 1, sales_growth: 1, ebitda: 1, net, ret: 1, pe });
  const rows = [r("A", 20), r("B", null), r("C", 10), r("D", 20)];
  assert.deepEqual(ct.sortPeers(rows, "pe", true).map((x) => x.symbol), ["A", "D", "C", "B"]);
  assert.deepEqual(ct.sortPeers(rows, "pe", false).map((x) => x.symbol), ["C", "A", "D", "B"]);
  assert.deepEqual(rows.map((x) => x.symbol), ["A", "B", "C", "D"]);          // the server's order is untouched
});

test("each quarter stacks to its filed shares, and the change over the quarters is in points", () => {
  const qs = [{ quarter: "Mar 2026", promoters: 50, fiis: 20, diis: 15, public: 14.98, shareholders: 10, pledge: null },
    { quarter: "Jun 2026", promoters: 49.5, fiis: 21.25, diis: null, public: 15, shareholders: 12, pledge: null }];
  const s = ct.stacks(qs, ["promoters", "fiis", "diis", "public"]);
  assert.deepEqual(s[0].parts.map((p) => [p.key, p.from, p.to]), [["promoters", 0, 50], ["fiis", 50, 70], ["diis", 70, 85], ["public", 85, 99.98]]);
  assert.deepEqual(s[1].parts.map((p) => p.key), ["promoters", "fiis", "public"]);       // a missing figure is left out, never guessed
  assert.equal(ct.changeOver(qs, "fiis"), 1.25);
  assert.equal(ct.changeOver(qs, "promoters"), -0.5);
  assert.equal(ct.changeOver(qs, "diis"), null);
  assert.equal(ct.changeOver(qs.slice(0, 1), "fiis"), null);
});

test("an Indian March year reads as its financial year; a download keeps its basis", () => {
  assert.equal(ct.yearLabel("Mar 2026", "IN"), "FY26");
  assert.equal(ct.yearLabel("Sep 2025", "US"), "Sep 2025");
  assert.equal(ct.yearLabel("Dec 2025", "IN"), "Dec 2025");
  assert.equal(ct.downloadPath("IN", "M&M", "statements.xlsx", "standalone"), "/research/company/IN/M%26M/statements.xlsx?basis=standalone");
  assert.equal(ct.downloadPath("US", "AAPL", "peers.csv"), "/research/company/US/AAPL/peers.csv");
});

test("the cards sit on the company page and the deep dive, and the page jumps to them", () => {
  const page = read("src/pages/Research.tsx"), dive = read("src/pages/DeepDive.tsx"), all = read("src/components/CompanyTables.tsx");
  assert.match(page, /<CompanyTables region=\{region\} symbol=\{c\.symbol\}/);
  assert.match(page, /id: "co-peers", label: "Peers"/);
  assert.match(page, /id: "co-statements", label: "Statements"/);
  assert.match(dive, /<CompanyTables region=\{region\} symbol=\{v\.symbol\} ids="dd" \/>/);
  for (const c of ["PeersCard", "StatementsCard", "ShareholdingCard"]) assert.match(all, new RegExp(`<${c} `));
});

test("the cards use the kit, say a lock with the plan note, and never name a vendor or give advice", () => {
  const files = ["src/components/CompanyPeers.tsx", "src/components/CompanyStatements.tsx", "src/components/ShareholdingHistory.tsx", "src/lib/companyTables.ts"];
  for (const f of files) {
    const src = read(f);
    assert.doesNotMatch(src, /screener|finnhub|yahoo|tickertape|moneycontrol/i, `${f} names a vendor`);
    assert.doesNotMatch(src, /\b(buy|sell|target price|rating|undervalued|overvalued|cheap|expensive)\b/i, `${f} has advice words`);
    assert.doesNotMatch(src, /<table|toLocaleString\(|toFixed\(\d\)\}%/, `${f} builds a table or a number by hand`);
  }
  for (const f of files.slice(0, 3)) {
    const src = read(f);
    assert.match(src, /from "\.\/kit"/);
    assert.match(src, /<PlanNote plan=\{v\.locked\.plan\}>\{v\.locked\.message\}<\/PlanNote>/, `${f} says its lock with the plan note`);
    assert.match(src, /<Skeleton /, `${f} has a loading state`);
    assert.match(src, /<ErrorState /, `${f} has an error state`);
  }
  assert.doesNotMatch(read("src/components/companyTables.css"), /#[0-9a-f]{3,6}\b/i, "colours are tokens");
});

test("the plan copies name the feature on the plan that adds it, and the downloads on Pro", async () => {
  const plans = await import("../src/lib/plans.ts");
  const gates = await import("../src/lib/gates.ts");
  // (the landing page's plans file has 58 bytes to spare under its 450 KB budget: one short row, and the downloads are Pro's export)
  assert.equal(plans.planOf("tables"), "basic");
  assert.equal(plans.planOf("export"), "pro");
  assert.ok(plans.FLAGS.some(([f]) => f === "tables"));
  assert.ok(gates.ELSEWHERE.tables && /company page/.test(gates.ELSEWHERE.export));
  const cards = read("src/lib/planFeatures.ts");
  assert.match(cards, /every peer and ten years of statements and shareholding/);
  assert.match(cards, /a company's statements to Excel/);
});
