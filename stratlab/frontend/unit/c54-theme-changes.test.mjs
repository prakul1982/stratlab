// c54 (R53 review, the live Metals deck: "“Aluminium” removed (14 companies)" and nothing more): a lost layer says where its companies went
// and why it was not kept; a move says the placement's reason for where the company is now.
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

test("c54: a removed layer with where its companies went and why; a move with its reason", async () => {
  const C = await import("../src/lib/themeChanges.ts");
  const entry = {
    at: "2026-11-14T06:00:00+00:00", d: "2026-11-14", cause: "rules", counts: { removed: 0, added: 0, moved: 1, layers: 1, restated: 0 },
    removed: [], added: [], restated: [],
    moved: [{ symbol: "INTC", name: "Intel Corp", from: "Chip equipment and subsystem suppliers", to: "Makers of their own products",
              why: "its own words don't say it sells what “Chip equipment and subsystem suppliers” is" }],
    layers: [{ kind: "removed", from: ["Aluminium"], to: [], n: 14, went: { Other: 11, "Steel and alloy pipe and tube makers": 3 },
               why: "none restored: 2 of its 14 companies' own words or official industry still say what it sells, fewer than 3" }],
  };
  const rows = C.changeRows(entry, "₹ crore");
  assert.equal(rows[0].detail, "Chip equipment and subsystem suppliers → Makers of their own products: its own words don't say it sells what “Chip equipment and subsystem suppliers” is");
  assert.equal(rows[1].detail, "Aluminium (14 companies: 11 to Other, 3 to Steel and alloy pipe and tube makers), none restored: 2 of its 14 companies' own words or official industry still say what it sells, fewer than 3");
  assert.equal(C.removedDetail({ kind: "removed", from: ["Pipes"], to: [], n: 6 }), "Pipes (6 companies)");     // an older entry: as before
});
