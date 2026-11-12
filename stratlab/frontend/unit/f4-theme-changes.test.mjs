// f4: a theme's change log ("What changed") and its workbook download, beside the deck downloads; the plans name both features.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const ENTRY = {
  at: "2026-11-12T06:00:00+00:00", d: "2026-11-12", cause: "refresh",
  counts: { removed: 1, added: 2, moved: 1, layers: 1, restated: 1 },
  removed: [{ symbol: "CELLB", name: "Cell B", layer: "Cells", why: "another business (filed under Solar Panels)" }],
  added: [{ symbol: "N1", name: "New One", layer: "Mining" }, { symbol: "N2", name: "New Two", layer: "Mining" }],
  moved: [{ symbol: "MINEB", name: "Mine B", from: "Mining", to: "Cells" }],
  layers: [{ kind: "renamed", from: ["Mining"], to: ["Metal mining"], n: 2 }],
  restated: [{ symbol: "MINEA", name: "Mine A", year: "Mar 2026", revenue: [150000, 160000], margin: [50, 50], measure: "EBITDA margin", what: ["revenue"] }],
};

test("f4: an entry's counts in one line, and each change as a row with its reason or detail", async () => {
  const C = await import("../src/lib/themeChanges.ts");
  assert.equal(C.countsLine(ENTRY.counts), "2 companies added, 1 company removed, 1 company moved between layers, 1 layer change, 1 company's figures restated");
  assert.equal(C.countsLine({ removed: 0, added: 0, moved: 0, layers: 0, restated: 0 }), "No change");
  const rows = C.changeRows(ENTRY, "₹ crore");
  assert.deepEqual(rows.map((r) => r.change), ["Removed", "Added", "Added", "Moved", "Layer renamed", "Figures restated"]);
  assert.equal(rows[0].detail, "From Cells: another business (filed under Solar Panels)");
  assert.equal(rows[3].detail, "Mining → Cells");
  assert.equal(rows[4].detail, "Mining → Metal mining (2 companies)");
  assert.equal(rows[5].detail, "Mar 2026: revenue 1,50,000 → 1,60,000 ₹ crore");          // Indian grouping for rupees
  const m = C.changeRows({ ...ENTRY, restated: [{ ...ENTRY.restated[0], margin: [12.0, -3.5], what: ["margin"] }] }, "₹ crore").at(-1);
  assert.equal(m.detail, "Mar 2026: EBITDA margin 12.0% → −3.5%");
  assert.equal(C.CAUSE_WORDS.rules, "Re-checked under new placement rules");
});

test("f4: the lock line says what Free sees and that Basic has the rest", async () => {
  const C = await import("../src/lib/themeChanges.ts");
  const line = C.changesLockLine({ full: false, since: "2026-11-01", entries: [{ ...ENTRY, hidden: 2 }], older: 3 });
  assert.match(line, /^The full change log, with 3 earlier refreshes, is on the Basic plan\./);
  assert.match(line, /Free shows the latest refresh's counts and its first 5 changes\./);
});

test("f4: the theme page shows 'What changed' and the downloads hold 'Workbook (XLSX)' beside the slides", () => {
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /<ChangesCard dive=\{dive\} \/>/);
  const dl = read("src/components/ThemeDive.tsx");
  assert.ok(dl.indexOf("<WorkbookButton") > dl.indexOf('"Slides (PowerPoint)"'));
  const comp = read("src/components/ThemeChanges.tsx");
  assert.match(comp, /Workbook \(XLSX\)/);
  assert.match(comp, /\/research\/theme-dive\/workbook\?/);
  assert.match(comp, /<PlanNote plan="basic">/);                 // the one lock wording, naming the plan
  assert.match(comp, /theme_workbook === false/);                // a plan without it is told before anything is asked of the server
});

test("f4: the plans name both features on Basic and up, in the table and on Basic's card", async () => {
  const F = await import("../src/lib/planFeatures.ts");
  assert.deepEqual(F.MORE_FLAGS.map(([f, , p]) => [f, p]), [["theme_changes", "basic"], ["theme_workbook", "basic"]]);
  for (const f of ["theme_changes", "theme_workbook"]) {
    assert.deepEqual(["free", "basic", "pro"].map((p) => F.hasMore(p, f)), [false, true, true]);
  }
  assert.ok(F.FEATURES.basic.some((l) => l.includes("theme change logs") && l.includes("theme's workbook in Excel")));
  assert.ok(!F.FEATURES.free.concat(F.FEATURES.pro).some((l) => /change log|workbook/.test(l)));
  assert.match(read("src/components/PlanCompare.tsx"), /MORE_FLAGS\.map/);
  assert.doesNotMatch(read("src/lib/plans.ts"), /theme_changes|theme_workbook/);       // the landing page's own copy stays as it was
});
