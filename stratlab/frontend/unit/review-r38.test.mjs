// Round 38 (16 Oct live review): a legacy run in every list and comparison, "Latest YoY" naming its periods, a group
// trade cut to the pot's free cash, and the SIP test link on a group notebook.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const { splitLegacy, legacyNote } = await import("../src/lib/legacyRun.ts");
const { sipTestLink } = await import("../src/lib/sip.ts");
const { qtyNote } = await import("../src/lib/tradeUi.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

const trade = (entry_t, exit_t, why = "Stop") => ({ entry_t, exit_t, why });
const legacy = { v: 2, stats: { ret: -100, emptied_on: "2022-05-09" }, trades: [trade("2022-05-02", "2022-05-09", "Account emptied"), trade("2022-06-01", "2022-06-03")] };
const fine = { v: 3, stats: { ret: 4.2 }, trades: [trade("2022-06-01", "2022-06-03")] };

test("R38-001: a run whose figures contradict each other is listed with the reason, never compared or called Capital lost", () => {
  const { shown, legacy: hidden } = splitLegacy([legacy, fine]);
  assert.deepEqual(shown.map((e) => e.v), [3]);
  assert.deepEqual(hidden.map((e) => e.v), [2]);
  assert.match(legacyNote(legacy), /^Figures not shown: saved by an older version.*emptied on 2022-05-09.*contradict each other/);
  // the compare page charts and tabulates only the runs whose figures are shown; the rest are listed with the note
  const cmp = read("src/pages/CompareExperiments.tsx");
  assert.match(cmp, /const \{ shown: exps, legacy \} = splitLegacy\(nb\.experiments\)/);
  assert.match(cmp, /legacyNote\(e\)/);
  // the notebook's experiments table: "Not shown" in place of the return and verdict, never "Capital lost"
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /isLegacyEmptied\(e\) \? "Not shown" : <Signed value=\{e\.stats\.ret\}>\{lost\(e\.stats\.ret\)\}/);
  assert.match(nb, /isLegacyEmptied\(e\) \? "Not shown" : <VerdictBadge/);
  assert.match(read("src/pages/SpaceHomes.tsx"), /n\.summary\?\.last_legacy \?/);
});

test("R38-002: Latest YoY says it is the latest quarter against a year before, else the year", () => {
  assert.match(read("src/components/Research.tsx"), /"Latest YoY": "The latest reported quarter against the same quarter a year before; without quarterly results, the latest year/);
});

test("R38-003: a group trade sized to the cash left free says so beside its quantity", () => {
  assert.equal(qtyNote({ cash_short: true }), "Sized to the cash left free");
  assert.equal(qtyNote({}), null);
  assert.match(read("src/pages/ExperimentPage.tsx"), /qtyNote\(t\) && <span className="k-sub-line">\{qtyNote\(t\)\}<\/span>/);
});

test("R38-004: a notebook set to a group has no SIP test link (it pointed at RELIANCE)", () => {
  const reliance = { symbol: "RELIANCE", market: "IN", type: "EQ" };
  assert.equal(sipTestLink(reliance), "/money/sip-test?symbol=RELIANCE");
  assert.equal(sipTestLink(reliance, { id: "nifty50", members: [] }), null);
  assert.match(read("src/pages/NotebookPage.tsx"), /sipTestLink\(inst, group\) &&/);
  assert.doesNotMatch(read("src/lib/help.ts"), /as of 2025/);
});
