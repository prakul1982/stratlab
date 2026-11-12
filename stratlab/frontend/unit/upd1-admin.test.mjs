// Lane upd1: Admin → Library dates an entry by the India day and says which kept decks are no longer the file people get; the blog list
// says which theme posts have figures from older rules and which the site answers "not found" for. Every value is fixed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("A store's entries are dated by the India day, not the UTC date's first ten characters", async () => {
  const { keptDay, keptSpan } = await import("../src/pages/admin/library.ts");
  // 20:00 UTC on 11 Nov is 01:30 on 12 Nov in India
  assert.equal(keptDay("2026-11-11T20:00:00+00:00"), "12 Nov");
  assert.equal(keptSpan("2026-11-11T20:00:00+00:00", "2026-11-12T10:00:00+00:00"), "12 Nov");
  assert.equal(keptSpan("2026-11-02T03:00:00+00:00", "2026-11-12T10:00:00+00:00"), "2 Nov – 12 Nov");
  assert.equal(keptSpan(null, "2026-11-12T10:00:00+00:00"), "–");
  assert.equal(keptDay("2026-11-12"), "12 Nov");                       // a plain day stays that day
});

test("A kept deck that is no longer served says why; one that is served says nothing", async () => {
  const { deckStaleText } = await import("../src/pages/admin/library.ts");
  assert.match(deckStaleText("older version"), /^Not served: made under older rules/);
  assert.match(deckStaleText("earlier day"), /^Not served: an earlier day's file/);
  assert.equal(deckStaleText(null), null);
  assert.equal(deckStaleText(undefined), null);
  const page = read("src/pages/admin/LibrarySection.tsx");
  assert.ok(page.includes("deckStaleText(d.stale)") && page.includes("Not served: kept under older rules"));
  assert.ok(!page.includes("iso.slice(0, 10)"));
});

test("The blog list notes a theme post with figures from older rules and a post the site doesn't show", () => {
  const panel = read("src/pages/admin/BlogPanel.tsx");
  assert.ok(panel.includes("p.stale_figures") && panel.includes("p.not_shown"));
  const ov = read("src/pages/admin/OverviewSection.tsx");
  assert.ok(ov.includes("signed in, or ran an experiment, an AI build or an AI read"));
});
