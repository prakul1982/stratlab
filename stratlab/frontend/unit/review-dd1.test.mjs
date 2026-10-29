// Deep review DD (24 Oct 2026): the signed-in company pages' data — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DD-003: a BSE code of an NSE company opens its NSE page; a BSE-only company stays at its code", async () => {
  const { bseTwinMoved } = await import("../src/lib/researchFormat.ts");
  assert.equal(bseTwinMoved("500325", { symbol: "RELIANCE", exchange: "NSE" }), true);
  assert.equal(bseTwinMoved("543210", { symbol: "TINYCO", exchange: "BSE" }), false);
  assert.equal(bseTwinMoved("RELIANCE", { symbol: "RELIANCE", exchange: "NSE" }), false);
  assert.match(read("src/pages/Research.tsx"), /if \(bseTwinMoved\(sym, x\)\) \{ nav\(/);
});

test("DD-005: a market research doesn't cover is said so, never India's page opened silently", async () => {
  const { regionOf } = await import("../src/lib/researchFormat.ts");
  assert.equal(regionOf("in"), "IN");
  assert.equal(regionOf("US"), "US");
  assert.equal(regionOf("XX"), null);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /if \(!regionOf\(r\)\) return <NoSuchMarket/);
  assert.match(page, /Research covers India and the US/);
});

test("DD-010, DD-011: a first session is against the issue price, and a new listing's range is since listing", () => {
  const c = read("src/components/Research.tsx");
  assert.match(c, /q\.ref === "issue" \? "Issue price" : "Previous close"/);
  assert.match(c, /since \? `Since listing \(/);
  assert.match(read("src/pages/Research.tsx"), /since=\{c\.range52\.since\}/);
});

test("DD-012: a merged company's page says what became of it and offers nothing live", async () => {
  const { delistedLine } = await import("../src/lib/researchFormat.ts");
  const line = delistedLine("Housing Development Finance Corporation Ltd", { how: "merged", into: "HDFC Bank", on: "2023-07-13", last_price: 2724 }, () => "13 Jul 2023");
  assert.equal(line, "Housing Development Finance Corporation Ltd no longer trades: it was merged into HDFC Bank and delisted on 13 Jul 2023. "
    + "The figures below are its last reported ones. Its last price on record is ₹2,724.00.");
  assert.match(delistedLine("Xyz Ltd", { how: "delisted" }, (d) => d), /the exchange lists it as delisted\./);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /\{!c\.delisted && <StarButton/);
  assert.match(page, /\{!c\.delisted && <AlertButton/);
  assert.match(page, /\{!c\.delisted && <Card id="co-chart">/);
});

test("DD-013: a dividend declared before a bonus shows its amount in today's shares", () => {
  const c = read("src/components/CorpActions.tsx");
  assert.match(c, /<ul className="k-note cmp-foots" data-testid="div-now">/);       // (UI-CO item 1: a numbered note under the table, the mark beside the amount)
  assert.match(c, /dividends_12m\.adjusted \? " in today's shares" : ""/);
});

test("DD-018: a growth rate off a tiny base is n/m, on the page and in its bars", async () => {
  const { tinyBase, metricText } = await import("../src/lib/researchFormat.ts");
  assert.equal(tinyBase(1, 50, 3, 97), true);                      // TONBO: ₹1 cr of profit on ₹97 cr of sales
  assert.equal(tinyBase(4368, 99000, 3, 26974), false);            // a low year of a large business is no tiny base
  assert.equal(tinyBase(97, 361, 3), false);
  assert.equal(metricText({ label: "3Y CAGR", value: null, unit: "%±", text: "n/m" }, "INR"), "n/m");
  assert.equal(metricText({ label: "3Y CAGR", value: 55, unit: "%±" }, "INR"), "+55.0%");
  assert.match(read("src/components/Research.tsx"), /n\/m: from a small base/);
  assert.match(read("src/pages/DeepDive.tsx"), /nm=\{n\.growth_nm\?\.profit_cagr_3y\}/);
});

test("DD-030, DD-031: results bars name the fiscal quarter and say what the EPS counts", () => {
  const c = read("src/components/Research.tsx");
  assert.match(c, /r\.fiscal && <span className="k-note tbar-sub" data-testid="fiscal-quarter">/);
  assert.match(c, /EPS as the estimates count it: adjusted \(non-GAAP\)/);
  assert.match(read("src/pages/Research.tsx"), /<EarningsBars rows=\{c\.earnings\} basis=\{c\.earnings_basis\} \/>/);
});

test("DD-044: the chart's footer says splits and bonuses are adjusted for, regular dividends not", () => {
  const c = read("src/components/Research.tsx");
  assert.match(c, /Prices adjusted for splits and bonus issues, not for regular dividends\./);
  assert.doesNotMatch(c, /Prices as traded, not adjusted for dividends/);
});

test("DD-050: a report card target keeps its unit, and its cells agree when nothing is settled", () => {
  const d = read("src/pages/DeepDive.tsx");
  assert.match(d, /value=\{checked \? `\$\{c\.met\} of \$\{checked\}` : "None settled"\}/);
  assert.match(d, /label="Missed" value=\{checked \? String\(c\.missed\) : "–"\}/);
  assert.match(d, /\$\{unit === "%" \? "%" : ""\}/);
  assert.match(d, /"earnings releases" : "calls"/);
});

test("DD-070: At a glance never counts or deep-dives a saved symbol that is no listed company", () => {
  const p = read("src/pages/InvestorHome.tsx");
  assert.match(p, /\{!r\.unknown && <Link className="btn quiet sm" to=\{`\/research\/\$\{region\}\/\$\{encodeURIComponent\(r\.symbol\)\}\/deep`\}/);
  assert.match(p, /rows\.filter\(\(r\) => !r\.unknown\)\.length/);
});
