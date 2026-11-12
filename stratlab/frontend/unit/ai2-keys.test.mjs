// AI lane (12 Nov 2026): a second Claude key (ANTHROPIC_API_KEY_2) with its own monthly credit, asked first.
// Admin → AI shows both keys side by side. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Admin → AI shows both Claude keys, the month's budget across them and which one answers", () => {
  const panel = read("src/pages/admin/AIPanel.tsx");
  assert.match(panel, /<DataTable label="Claude keys this month"/);
  assert.match(panel, /Both Claude keys this month: /);
  assert.match(panel, /key \$\{c\.active_key\} answers now/);
  assert.match(panel, /<ClaudeKeys c=\{c\} \/>/);                                 // inside "Claude this month"
  assert.match(panel, /p\.keys\.filter\(\(k\) => k\.configured\)\.map\(keyLine\)/); // and on the Anthropic provider row
  // shown only once the second key is set: one key looks exactly as before
  assert.match(panel, /if \(!keys\.some\(\(k\) => k\.slot === 2 && k\.configured\)\) return null;/);
});

test("every key state the backend reports has words on the panel, and a key is named by its last characters only", () => {
  const panel = read("src/pages/admin/AIPanel.tsx");
  const spend = read("../backend/app/ai_spend.py");
  for (const s of ["active", "standby", "spent", "off", "unknown"]) {
    assert.match(spend, new RegExp(`s[12], t[12] = "${s}"`));
    assert.match(panel, new RegExp(`\\b${s}: "`));
  }
  assert.match(spend, /return "…" \+ key\[-4:\] if len\(key\) >= 12 else "set"/);  // at most the last four characters
  assert.doesNotMatch(panel, /x-api-key|apiKey/);
});
