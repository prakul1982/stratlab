// AI lane (4 Nov 2026): Claude on the owner's monthly credit. Admin → AI shows "Claude this month".
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Admin → AI shows Claude's spend against the monthly cap, in the owner's words, with a table by model", () => {
  const panel = read("src/pages/admin/AIPanel.tsx");
  assert.match(panel, /Claude this month: \{usd\(c\.usd\)\} of \{usd\(c\.cap_usd\)\} cap \(Sonnet until \{usd\(c\.sonnet_until_usd\)\}\)/);
  assert.match(panel, /<DataTable label="Claude spend by model this month"/);
  assert.match(panel, /read from the cache/);                                   // the cache hit share
  assert.match(panel, /the spend can't be read right now, so Claude isn't asked/); // an unreadable meter says so
  // shown once Claude has a key (or something was spent), from the /admin/ai JSON's `claude`
  assert.match(panel, /v\.claude && \(on\.some\(\(p\) => p\.name === "anthropic"\) \|\| \(v\.claude\.usd \?\? 0\) > 0\) && <ClaudeMonth c=\{v\.claude\} \/>/);
});

test("every tier the backend reports has words on the panel", () => {
  const panel = read("src/pages/admin/AIPanel.tsx");
  const tiers = read("../backend/app/ai_spend.py").match(/"tier": "off" if usd >= cap else "sonnet" if usd < until else "haiku"/);
  assert.ok(tiers);
  for (const t of ["sonnet", "haiku", "off"]) assert.match(panel, new RegExp(`\\b${t}: "`));
});
