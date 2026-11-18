// r66e (R66 theme engine, LIVE12A): the theme page says when it shows an older read being checked again, and says once which companies
// have no line of their own words quoted. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file (as review-fix11's)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE12A-002: a theme served from its read under an earlier version of the checks says so, and that it is checked again", async () => {
  const { olderNote, DIVE_UPDATING } = await import("../src/lib/themeFormat.ts");
  const day = (iso) => (iso === "2026-11-07" ? "7 Nov 2026" : iso);
  assert.equal(olderNote(null, day), null);
  assert.equal(olderNote({ at: "2026-11-07T10:00:00+00:00", rechecking: true }, day),
    "This is the theme as it was checked on 7 Nov 2026, under an earlier version of StratLab's checks. It is being checked again now and fills in here when that is done.");
  assert.doesNotMatch(olderNote({ at: null, rechecking: false }, day), /being checked again/);
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /data-testid="theme-older"/);
  assert.match(page, /dive\.updating && <p className="k-note" data-testid="theme-dive-updating">\{DIVE_UPDATING\}/);
  assert.match(page, /r\?\.older\?\.rechecking/);                       // asked again, gently, while it is checked again
  assert.match(DIVE_UPDATING, /last stored read/);
});

test("LIVE12A-001: the companies with no line quoted are said once, not on every row", async () => {
  const { unquotedLine } = await import("../src/lib/themeFormat.ts");
  assert.equal(unquotedLine(0, 0), null);
  assert.equal(unquotedLine(30, 20).startsWith("No line of their own words is quoted for 50 companies here: 30 checked against their own description"), true);
  assert.match(unquotedLine(0, 1), /for 1 company here: 1 with no description in their own words yet\.$/);
  const dive = read("src/components/ThemeDive.tsx");
  assert.match(dive, /data-testid="theme-unquoted"/);
  assert.doesNotMatch(dive, /<span className="k-muted">\{noWords\(/);      // no longer the sentence in every empty cell
});
