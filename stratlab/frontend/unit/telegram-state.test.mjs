// The Telegram box in Alerts settings: which state it shows. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
const { telegramState } = await import("../src/lib/telegramState.ts");

test("telegram settings states", () => {
  assert.equal(telegramState(null, "", false), "none");
  assert.equal(telegramState(null, "123", false), "unsaved");
  assert.equal(telegramState("123", "456", true), "unsaved");       // a changed chat has to be confirmed again
  assert.equal(telegramState("123", "123", false), "confirm");      // saved, or saved before codes existed
  assert.equal(telegramState("@Name_1", " @name_1 ", true), "verified");
});
