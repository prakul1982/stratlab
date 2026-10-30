// The Markets button: a press made before the account has loaded opens the panel once the account's own layout is read, instead
// of being lost under the guest's key (it did nothing about one time in eight in the browser tests, VR7-008). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/components/watch/Launcher.tsx", import.meta.url), "utf8");

test("a press before the account loads is kept and applied under the person's own key", () => {
  assert.match(src, /if \(mode === "app" && !userId\) pending\.current = p;/);
  assert.match(src, /if \(userId && pending\.current\) \{ const p = pending\.current; pending\.current = null; patch\(\{ \.\.\.p, open: true \}\); \}/);
  assert.match(src, /\}, \[userId, patch\]\);/);
});
