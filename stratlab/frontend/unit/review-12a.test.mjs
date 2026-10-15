// The "live prices are offline" line shows only when a stock has no value (rev12a). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { unpricedNote } from "../src/lib/holdingsEdit.ts";

test("offline note: only with a stock that has no price", () => {
  assert.equal(unpricedNote(false, [{ value: 100 }, { value: 50 }]), false);
  assert.equal(unpricedNote(false, [{ value: 100 }, { value: null }]), true);
  assert.equal(unpricedNote(true, [{ value: null }]), false);
});
