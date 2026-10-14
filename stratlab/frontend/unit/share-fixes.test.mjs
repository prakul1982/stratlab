// The share card and public page count the checks run; updating a library entry starts from what it says. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { checksRun, libraryDraft } from "../src/lib/shareText.ts";

const checks = (s) => s.map((status) => ({ status }));

test("a verdict's checks run are its own total, not the four listed", () => {
  assert.equal(checksRun({ total: 3, checks: checks(["pass", "skip", "pass", "fail"]) }), 3);      // a group skips "nearby"
  assert.equal(checksRun({ checks: checks(["pass", "skip", "pass", "warn"]) }), 3);
  assert.equal(checksRun({ total: 4, checks: checks(["pass", "pass", "pass", "pass"]) }), 4);
  assert.equal(checksRun({ total: 0, checks: [] }), 0);
});

test("updating a library entry starts from its description and author", () => {
  assert.deepEqual(libraryDraft({ description: "A plain cross.", author: "Prakul" }, "Saved"), { desc: "A plain cross.", author: "Prakul" });
  assert.deepEqual(libraryDraft({ description: "", author: "A StratLab user" }, "Saved"), { desc: "", author: "Saved" });
  assert.deepEqual(libraryDraft(null, "Saved"), { desc: "", author: "Saved" });
});
