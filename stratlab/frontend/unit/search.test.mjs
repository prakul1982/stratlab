// Search's own matching (lib/features.ts, lib/helpTopics.ts): questions find the explanation already written for them,
// and the small words every question has don't pull in unrelated pages (F3-005). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { match } = await import("../src/lib/features.ts");
const { matchHelp, searchWords, HELP_TOPICS } = await import("../src/lib/helpTopics.ts");
const { HELP } = await import("../src/lib/help.ts");

test("a question keeps only the words that mean something", () => {
  assert.deepEqual(searchWords("What is walk-forward?"), ["walk", "forward"]);
  assert.deepEqual(searchWords("how does the Sharpe ratio work"), ["sharpe", "ratio"]);
  assert.deepEqual(searchWords("what is"), ["what", "is"]);          // nothing else left: the words as typed
  assert.deepEqual(searchWords("F&O lot size"), ["f&o", "lot", "size"]);
});

test("questions find their explanation", () => {
  assert.equal(matchHelp("what is walk-forward?")[0].key, "walkforward");
  assert.equal(matchHelp("What is a walk-forward test?")[0].key, "walkforward");
  assert.equal(matchHelp("what does max drawdown mean")[0].key, "worstFall");
  assert.equal(matchHelp("how is the sharpe ratio worked out?")[0].key, "sharpe");
  assert.equal(matchHelp("what is a trailing stop")[0].key, "trail");
  assert.equal(matchHelp("hdfc bank").length, 0);
  for (const t of HELP_TOPICS) assert.equal(t.text, HELP[t.key], `${t.key} has its (i) text`);
});

test("a question names a feature by its words, not by 'is' inside 'list'", () => {
  assert.equal(match("what is walk-forward?", 1)[0].id, "walkforward");
  assert.ok(!match("what is walk-forward?", 5).some((f) => f.to === "/research/watchlist"));
});
