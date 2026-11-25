// Lane admin90 (owner, 25 Nov: "can you do a admin cleanup and check"): rupee sums carry their dollar figure, a research run's twenty
// "theme unchanged" read once with a count, every Users header sorts, and the counts say when they were read.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a rupee sum shows its dollar figure beside it; ₹0 and other currencies as they are", async () => {
  const { withUsd, revenueText } = await import("../src/pages/admin/attention.ts");
  const fmt = (v, c) => `${c === "INR" ? "₹" : c + " "}${v.toLocaleString("en-IN")}`;
  assert.equal(withUsd(6990, "INR", fmt, 88), "₹6,990 (about $79)");
  assert.equal(withUsd(20, "INR", fmt, 88), "₹20 (about $1)");          // never "about $0" for money taken
  assert.equal(withUsd(0, "INR", fmt, 88), "₹0");
  assert.equal(withUsd(20, "USD", fmt, 88), "USD 20");
  assert.equal(revenueText({ USD: 20, INR: 1398 }, (v, c) => withUsd(v, c, fmt, 88)), "₹1,398 (about $16) · USD 20");
});

test("the research run's line names each post and result once, with how many", async () => {
  const { runLine } = await import("../src/pages/admin/blog.ts");
  const at = new Date(Date.now() - 3600 * 1000).toISOString();
  const made = [{ post: "classic strategies", slug: "a", result: "same" }, ...Array.from({ length: 20 }, (_, i) => ({ post: "theme", slug: `t${i}`, result: "same" })),
    { post: "theme", slug: "n", result: "new" }];
  const line = runLine({ at, made });
  assert.match(line, /: classic strategies unchanged, theme unchanged \(20 posts\), theme written\.$/);
  assert.doesNotMatch(line, /theme unchanged, theme unchanged/);
});

test("every Users header sorts, by its value; Overview's counts say when they were read", async () => {
  const { PLAN_RANK } = await import("../src/pages/admin/users.ts");
  assert.ok(PLAN_RANK.pro > PLAN_RANK.basic && PLAN_RANK.basic > PLAN_RANK.free);
  const users = read("src/pages/admin/UsersSection.tsx");
  assert.doesNotMatch(users, /<DataTable label="Users"[^\n]*sort=/);     // the table's own sort: every column with a header
  for (const key of ["email", "plan", "joined", "active"]) assert.match(users, new RegExp(`key: "${key}", header: "[^"]+",[^\\n]*sortValue:`));
  const ov = read("src/pages/admin/OverviewSection.tsx");
  assert.match(ov, /st\.counted_at \? `Counted \$\{fmtDateTime\(st\.counted_at/);
  assert.match(ov, /revenueText\(st\.revenue_30d\.by_currency, inr\)/);
});
