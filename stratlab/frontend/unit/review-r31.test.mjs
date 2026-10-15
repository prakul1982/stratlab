// Round 31 (blind live review): the Ctrl K ranking of a question, the phone experiments table, the library's loading state.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const { matchHelp } = await import("../src/lib/helpTopics.ts");
const { firstForQuestion } = await import("../src/lib/paletteRank.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("R31-001: 'what is a Stage 2 stock' is not answered by an article sharing one word", () => {
  assert.ok(matchHelp("what is a Stage 2 stock", 3).length > 0, "the loose match still exists");
  assert.equal(matchHelp("what is a Stage 2 stock", 3, true).length, 0);
  assert.equal(firstForQuestion(true, matchHelp("what is a Stage 2 stock", 1, true).length), "ai");
});

test("R31-001: a clear match still leads; a plain name does not reorder", () => {
  const n = matchHelp("what is a walk-forward test?", 1, true).length;
  assert.equal(firstForQuestion(true, n), n ? "help" : "ai");
  assert.equal(firstForQuestion(false, 1), null);
  assert.equal(firstForQuestion(true, 0), "ai");
});

test("R31-004: the library shows a loading skeleton while its code downloads", () => {
  assert.match(read("src/visitor/VisitorApp.tsx"), /view\.kind === "library" \? <main[^>]*><h1 className="sr-only">[^<]*<\/h1><Skeleton/);
});

test("R31-003: no developer wording on user pages", () => {
  for (const f of ["src/lib/api.ts", "src/lib/http.ts"]) assert.doesNotMatch(read(f), /new ApiError\("[^"]*config\.js/);
});

test("R31-009: the header Sign in is a real link", () => {
  assert.match(read("src/components/PublicFrame.tsx"), /<a className="btn outline sm" href="\/" onClick[^\n]*>Sign in<\/a>/);
});

test("R31-007: the notebook experiments table puts Overall right after Run, so a phone sees it without scrolling", () => {
  const src = read("src/pages/NotebookPage.tsx");
  const keys = [...src.matchAll(/\{ key: "(v|what|ret|unseen|verdict)", header:/g)].map((m) => m[1]);
  assert.deepEqual(keys.slice(0, 3), ["v", "ret", "what"]);
});
