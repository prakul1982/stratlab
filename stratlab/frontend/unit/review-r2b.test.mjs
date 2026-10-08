// Fixes from the second fresh-eyes review (round 2B). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { distinctTicks, niceTicks, flatZero } = await import("../src/lib/chartFormat.ts");

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const walk = (dir) => readdirSync(dir).flatMap((f) => (statSync(join(dir, f)).isDirectory() ? walk(join(dir, f)) : [join(dir, f)]));

test("an axis never repeats a label (R2B-006)", () => {
  const whole = (v) => String(Math.round(v));
  const [ticks, labels] = distinctTicks([0, 0.5, 1, 1.5], whole);
  assert.deepEqual(labels, ["0", "1", "2"].slice(0, labels.length));
  assert.equal(new Set(labels).size, labels.length);
  assert.equal(ticks.length, labels.length);
  const pct = (v) => `${Math.round(v)}%`;
  const [, l2] = distinctTicks(niceTicks(0, 0.0, 5).concat([5.2, 5.4]), pct);
  assert.equal(new Set(l2).size, l2.length);
  // distinct labels all stay
  assert.deepEqual(distinctTicks([0, 10, 20], whole)[1], ["0", "10", "20"]);
});

test("a chart that is all zeros says so (R2B-006)", () => {
  assert.equal(flatZero([0, 0, 0], [0, null]), true);
  assert.equal(flatZero([0, 1]), false);
  assert.equal(flatZero([]), true);
});

test("heat-table cells use their own class names, not the global heading classes (R2B-007)", () => {
  const page = read("pages/BreadthPage.tsx");
  assert.ok(!/inv-heat-cell h\$\{/.test(page), "a cell class like h2 would pick up the .h2 heading style");
  const css = read("styles-invest.css");
  assert.ok(!/\.inv-heat-cell\.h\d/.test(css));
  assert.ok(/\.inv-heat-cell\.heat9/.test(css));
});

test("one primary button colour: no blue buttons (R2B-015)", () => {
  const offenders = walk(new URL("../src", import.meta.url).pathname).filter((f) => /\.tsx$/.test(f) && /className="btn blue|"btn blue/.test(readFileSync(f, "utf8")));
  assert.deepEqual(offenders, []);
});

test("the welcome question picks no experience for the person (R2B-012)", () => {
  const src = read("components/LevelPrompt.tsx");
  assert.ok(/useState<Level \| "">\(level \?\? ""\)/.test(src));
  assert.ok(!/level \?\? "some"/.test(src));
});

test("the tour waits while another dialog is open (R2B-012)", () => {
  assert.ok(/paused=\{dialogs > 0\}/.test(read("components/Onboarding.tsx")));
  assert.ok(/coach: true/.test(read("components/kit/Coachmark.tsx")));
  assert.ok(/if \(paused\) return null/.test(read("components/Tour.tsx")));
});

test("a form's rows start together, so a hint never lifts a neighbour's label (R2B-014)", () => {
  const css = read("styles.css");
  const rule = css.split("\n").find((l) => l.startsWith(".k-form {")) ?? "";
  assert.ok(/align-items: start/.test(rule), rule);
});

test("a company's tab title is the name its heading shows (R2B-003)", () => {
  assert.ok(/useDocTitle\(c \? `\$\{c\.name \|\| c\.symbol\}/.test(read("pages/Research.tsx")));
});
