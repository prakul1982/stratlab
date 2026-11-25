import test from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

// a .ts file's extensionless imports, as the build resolves them (as unit/site82.test.mjs)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

// site89b (Release 89 site items): unit checks of the Results page's "Usual move" basis.

test("a usual move says how many earlier results days it stands on, which ones, and how each is measured", async () => {
  const { usualTitle } = await import("../src/lib/resultsRows.ts");
  const t = usualTitle({ n: 3, dates: ["2026-08-27", "2026-05-28", "2026-03-05"], basis: "close before the results day to the close of the session after it" });
  assert.match(t, /^Average size of the move over 3 earlier results days \(Thu 27 Aug, Thu 28 May, Thu 5 Mar\): close before the results day/);
  assert.equal(usualTitle({ n: 2, dates: [] }), "Average size of the move over 2 earlier results days: close before the results day to the close of the session after it");
});
