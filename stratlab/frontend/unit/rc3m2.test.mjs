// RC3-M2 (27 Oct 2026): the Money findings RC3-M left open, the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("RC3M-007: the ETFs and gold bonds card shows the indexed and 10% heads, and only the sales it can't index as not worked out", () => {
  const src = read("src/components/TaxUnits.tsx");
  assert.match(src, /head: "slab" \| "lt" \| "lt_idx" \| "lt_10" \| "exempt" \| "old"/);
  assert.match(src, /lt_idx: "Long term, 20% with indexation"/);
  assert.match(src, /lt_10: "Long term, 10% without indexation"/);
  assert.match(src, /old: "Old rules, not worked out"/);
  assert.match(src, /indexed_cost\?: number; taxed_gain\?: number/);
  assert.match(src, /units\.lt_idx && /);
  assert.match(src, /units\.lt_10 && /);
  assert.match(src, /but the cost can't be indexed \(bought before the index starts\), so not worked out/);
  assert.doesNotMatch(src, /Sold before 23 Jul 2024 under the old long-term rules \(indexation\), not worked out here/);
});

test("RC3M-009: Screens shows the note when the stored promoter and insider purchases don't reach back over the window", () => {
  assert.match(read("src/lib/screens.ts"), /insider_note\?: string \| null/);
  assert.match(read("src/pages/Screens.tsx"), /\{out\?\.insider_note && <p className="k-note" data-testid="screens-insider-note">\{out\.insider_note\}<\/p>\}/);
  assert.match(read("e2e/pages.spec.ts"), /no company can be shown as having had none/);
});

test("RC3M-010: a mutual fund's kind says when it was only guessed from the fund's name", () => {
  const src = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(src, /kind_basis\?: "category" \| "hint" \| "name"/);
  assert.match(src, /if \(s\.kind_set\) return "Set by you";/);
  assert.match(src, /s\.kind_basis === "name"\) return "Guessed from the fund's name; change it if it is wrong"/);
  assert.match(src, /data-testid="mf-kind-basis">\{kindBasis\(s\)\}/);
  assert.doesNotMatch(src, /\{s\.kind_set \? "Set by you" : "From the category"\}/);
});
