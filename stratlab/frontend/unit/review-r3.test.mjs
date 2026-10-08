// Fixes from the third fresh-eyes review (round 3): data trust. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { focusParam, metricText, monthsOld, newsAge, scaleFor, staleQuarter } = await import("../src/lib/researchFormat.ts");
const { movedYearNote, openFy } = await import("../src/lib/fy.ts");

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("sales and profit share one unit, so a lakh-crore chart never sits beside a crore one (R3-005)", () => {
  const sales = [596679, 466307, 694673, 964693], profit = [-21, -133, 20, 122];
  assert.equal(scaleFor(sales, false).unit, "₹ lakh cr");               // alone, sales would read in lakh crore
  assert.equal(scaleFor([...sales, ...profit], false).unit, "₹ cr");     // together, both in crore
  const page = read("pages/Research.tsx");
  assert.match(page, /scaleFor\(\[\.\.\.t\.revenue, \.\.\.t\.profit\]/, "the company page scales both series together");
  assert.match(read("pages/DeepDive.tsx"), /scaleFor\(years\.flatMap\(\(y\) => \[y\.sales, y\.profit\]\)[^)]*\), profitS = salesS/, "so does the deep dive");
});

test("a percentage that isn't zero never reads as 0.0% (R3-005)", () => {
  assert.equal(metricText({ label: "Net margin", value: 0.0126, unit: "%" }, "INR"), "0.01%");
  assert.equal(metricText({ label: "Net margin", value: 9.67, unit: "%" }, "INR"), "9.7%");
  assert.equal(metricText({ label: "Net margin", value: 0, unit: "%" }, "INR"), "0.0%");
  assert.equal(metricText({ label: "Latest YoY", value: -0.02, unit: "%±" }, "INR"), "−0.02%");
});

test("compare writes each figure with its unit, as the company page does (R3-004)", () => {
  assert.equal(metricText({ label: "Debt", value: 369575, unit: "cr" }, "INR"), "₹3.7 lakh cr");
  const page = read("pages/Research.tsx");
  assert.match(page, /const show = \([^)]*\) => \(m \? metricText\(m, c\.currency\) : "–"\)/);
  assert.match(page, /No AI comparison right now/, "no AI comparison is said, not left out");
});

test("an empty focus is no parameter at all (R3-010)", () => {
  assert.equal(focusParam(""), "");
  assert.equal(focusParam("  "), "");
  assert.equal(focusParam("banks & IT"), "&focus=banks%20%26%20IT");
  const lib = read("lib/research.ts");
  assert.ok(!/focus=\$\{encodeURIComponent\(focus\)\}/.test(lib), "the market read never sends focus= with nothing after it");
});

test("results and holders older than the latest that can be out say how old they are (R3-006)", () => {
  const oct8 = new Date(Date.UTC(2026, 9, 8));
  assert.equal(staleQuarter("Jun 2026", 60, oct8), null);       // the September quarter isn't due yet
  assert.equal(staleQuarter("Jun 2025", 60, oct8), 16);
  assert.equal(monthsOld(16), "16 months old");
  assert.equal(monthsOld(30), "over 2 years old");
  assert.equal(staleQuarter("Jun 2026", 21, oct8), null);       // shareholding for September is due by 21 Oct
  assert.equal(staleQuarter("Mar 2026", 21, oct8), 7);
  assert.equal(staleQuarter("TTM", 60, oct8), null);
});

test("a headline over a week old says how old it is (R3-006)", () => {
  const now = new Date("2026-10-08T06:00:00Z");
  assert.equal(newsAge("2026-10-07T20:00:00Z", now), null);
  assert.equal(newsAge("2026-09-24T08:00:00Z", now), "1 week old");      // 13 days
  assert.equal(newsAge("2026-09-20T08:00:00Z", now), "2 weeks old");
  assert.equal(newsAge("2026-06-01T08:00:00Z", now), "4 months old");
  assert.equal(newsAge(null, now), null);
});

test("a tax page opens on the year being filed, or on the latest year with data when that one is empty (R3-011)", () => {
  const years = [2026, 2025, 2024, 2023];
  const has = (fy) => fy === 2024 || fy === 2023;
  assert.deepEqual(openFy(years, 2026, has, null), { fy: 2024, from: 2025 });
  assert.deepEqual(openFy(years, 2026, (fy) => fy === 2025 || fy === 2024, null), { fy: 2025, from: null });   // the filing year has trades
  assert.deepEqual(openFy(years, 2026, () => false, null), { fy: 2025, from: null });                           // nothing anywhere
  assert.deepEqual(openFy(years, 2026, has, 2023), { fy: 2023, from: null });                                    // a year picked by hand
  assert.equal(movedYearNote(2025, 2024, 2026, "trades"), "No trades in FY 2025-26, the year being filed, so this is FY 2024-25, the latest year with trades.");
});

test("a missing notebook is a not-found page with the way to the notebooks, never endless skeletons (R3-008)", () => {
  const page = read("pages/NotebookPage.tsx");
  assert.match(page, /Notebook not found/);
  assert.match(page, /to="\/notebooks">Go to notebooks/);
  for (const f of ["pages/NotebookPage.tsx", "pages/MarketPage.tsx", "pages/CompareExperiments.tsx", "pages/ExperimentPage.tsx"])
    assert.match(read(f), /if \(!nb && problem\) return <NotebookProblem/, f);
});

test("out of hours a company's price is the last close, labelled so (R3-003)", () => {
  const comp = read("components/Research.tsx");
  assert.match(comp, /\{closed && <span className="k-stat-k">Last close<\/span>\}/);
  assert.match(read("pages/Research.tsx"), /closed=\{c\.market_open === false\}/);
});
