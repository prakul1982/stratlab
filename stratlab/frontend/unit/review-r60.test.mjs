// Round 60 (19 Oct 2026): money data, payments, the visitor on desktop and Admin — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R60-002: the checks line counts as the library does, everywhere", async () => {
  const { checksLine, checksOf } = await import("../src/lib/tradeUi.ts");
  assert.equal(checksLine(3, 3), "3 of 4 checks run · all 3 passed");          // was "3 of 4 checks passed · 1 not run"
  assert.equal(checksLine(1, 3), "3 of 4 checks run · 1 passed");               // was "1 of 4 checks passed · 1 not run"
  assert.equal(checksLine(2, 4), "4 of 4 checks run · 2 passed");
  assert.equal(checksLine(0, 0), "No checks could be run");
  const e = { range: null, stats: { ret: 12 }, verdict: { verdict: "edge", passed: 3, total: 3, checks: [{ id: "nearby", status: "skip" }] } };
  assert.equal(checksOf(e), "3 of 4 checks run · all 3 passed · nearby settings not run");
});

test("R60-007: on a phone the homes' countdown is one line with a ×, still named Got it", () => {
  const src = read("src/components/PromoCountdown.tsx");
  assert.match(src, /aria-label="Got it"/);
  assert.match(src, /<span className="promo-short">Pro free for \{timeLeft\(end - now\)\}<\/span>/);
  assert.match(read("src/styles.css"), /\.k-notice\.promo-countdown \{ flex-wrap: nowrap;/);
});

test("R60-008/010/005: Net worth dates prices only over market prices; the next Kite login is always said; the FAQ finds the invite link", () => {
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /asOf=\{priced \? view\?\.as_of : undefined\}/);
  assert.match(read("src/pages/admin/attention.ts"), /\$\{next \? `\.\$\{next\}` : ""\}/);
  const faq = read("src/content/faq.ts");
  assert.ok(!faq.includes("Your invite link is in Account"));
  assert.match(faq, /Invite friends page, in the account menu/);
});

test("R60-012: the visitor's plans page loads the side-by-side tables without the account code", () => {
  const login = read("src/pages/Login.tsx");
  assert.match(login, /lazy\(\(\) => (?:importWithRetry\(\(\) => )?import\("\.\.\/components\/PlanCompare"\)/);
  assert.match(login, /\{plansOnly && <section className="lp-sec lp-compare">/);
  const cmp = read("src/components/PlanCompare.tsx");
  assert.ok(!/from "\.\/kit"/.test(cmp) && !/lib\/(app|api)"/.test(cmp), "PlanCompare must not pull the kit index or the account code");
  assert.match(read("src/pages/PlansPage.tsx"), /<PlanCompare plans=/);
});
