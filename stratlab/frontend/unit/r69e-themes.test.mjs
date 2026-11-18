// r69e (R69 theme engine, LIVE13A): one date logic in a theme's head. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file (as review-fix11's)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE13A-003: the map's date and the check's date are each said as what they are, never 'Last updated 7 Nov' beside 'checked on 18 Nov'", async () => {
  const { mapStamp } = await import("../src/lib/themeFormat.ts");
  const day = (iso) => ({ "2026-11-07": "7 Nov 2026", "2026-11-18": "18 Nov 2026" })[iso] ?? iso;
  const made = Date.UTC(2026, 10, 7, 21, 33) / 1000;
  assert.equal(mapStamp(made, "2026-11-18T08:53:00+00:00", "7 Nov, 16:33 ET", day), "Map made 7 Nov 2026 · checked 18 Nov 2026");
  assert.equal(mapStamp(made, "2026-11-07T22:00:00+00:00", "7 Nov, 16:33 ET", day), "Last updated 7 Nov, 16:33 ET");
  assert.equal(mapStamp(made, null, "7 Nov, 16:33 ET", day), "Last updated 7 Nov, 16:33 ET");
  assert.equal(mapStamp(null, "2026-11-18T08:53:00+00:00", "", day), null);
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /label=\{mapStamp\(/);                          // the head's stamp reads the check's date (the older read's, else the stored one's)
  assert.match(page, /r\.older\?\.at \?\? r\.checked_at/);
  assert.match(read("src/components/StoredStamp.tsx"), /label \?\? `Last updated/);
});

test("LIVE13A-013/014: the sortable table's headers wrap to fit; a layer's company cell keeps a reading width; an empty layer is no chain row", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.k-tbl-wrap\.k-fit \.k-table th button\.k-th-sort \{ white-space: normal;/);
  assert.match(css, /\[id\^="layer-"\] \.k-tbl-wrap \.k-table tbody th\.k-wrap \{ min-width: 18rem; \}/);
  assert.match(read("src/components/ThemeDive.tsx"), /rows=\{dive\.chain\.rows\.filter\(\(x\) => x\.n > 0 \|\| \(x\.listed \?\? 0\) > 0\)\}/);
});

test("LIVE13A-002: 'Membership checked N of M' is followed by states that add up to N", async () => {
  const T = await import("../src/lib/theme.ts");
  const dive = { evidence: { A: "description_verified", B: "description_verified", C: "industry_code_supported" }, membership_check: { outside: {} } };
  const line = T.membershipLine(dive, ["A", "B", "C", "D", "E"]);
  assert.equal(line, "Membership checked 3 of 5: 2 description-verified · 1 industry-supported; 2 not checked");
  const [, n, rest] = line.match(/checked (\d+) of \d+: (.*);/);
  assert.equal(rest.match(/\d+/g).map(Number).reduce((a, b) => a + b, 0), Number(n));
});
