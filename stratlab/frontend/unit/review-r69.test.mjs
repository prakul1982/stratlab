// Round 69 (19 Oct 2026): every StratLab email as the owner gets it — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R69-002: Settings → Alerts says where the other alerts and reminders are turned on and off", () => {
  const src = read("src/components/AlertSettings.tsx");
  assert.match(src, /data-testid="alert-where"/);
  assert.match(src, /are each turned on or off on their own page; they all go to this email\./);
});
