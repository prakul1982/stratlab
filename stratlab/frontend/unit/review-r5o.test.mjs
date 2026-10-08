// Round 5, the owner's review (R5O-…): the frontend side of the fixes.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a failed /me shows Retry, never a spinner that waits forever (R5O-002)", () => {
  const main = read("src/main.tsx");
  assert.match(main, /StratLab couldn't load your account: \{meError\}<\/span><AccountRetry \/>/);
  assert.doesNotMatch(main, /if \(!me\) return <Loading label="Checking access" \/>/);
  assert.match(main, /<AccountWait label="Checking access" \/>/);
  const wait = read("src/components/AccountWait.tsx");
  assert.match(wait, /if \(!meError\) return <Skeleton/);
  assert.match(wait, /label: busy \? "Trying again…" : "Retry"/);
  for (const p of ["src/pages/AdminPage.tsx", "src/pages/AccountPage.tsx", "src/pages/SettingsPage.tsx"])
    assert.match(read(p), /<AccountWait label=/, p);
  // one quiet second try on a 502/503/504 or no answer before the error shows
  assert.match(read("src/lib/app.tsx"), /e\.status !== 503 && e\.status !== 502 && e\.status !== 504\) throw e;/);
});

test("notebook defaults invent nothing, and the sell question stays (R5O-010)", () => {
  const rules = read("src/lib/rules.ts");
  assert.match(rules, /const DEFAULT_RISK: Risk = \{[^}]*tgt: 0,/);
  assert.match(read("src/components/IdeaComposer.tsx"), /strategy: withDefaultExit\(strategy, out\.mentioned \|\| \[\]\)/);
  assert.match(read("src/components/ImportStrategy.tsx"), /\{ \.\.\.s\.risk, sl: 0, tgt: 0, \.\.\.\(out\.risk \|\| \{\}\) \}/);
  const page = read("src/pages/NotebookPage.tsx");
  assert.match(page, /body: \{ gaps: g \}/);                       // the questions are saved with the notebook
  assert.match(page, /body: \{ clearGaps: true \}/);
  assert.match(page, /No sell rule is set:/);
  assert.match(page, /const DEFAULT_DAILY_DAYS = 1825;/);         // "years of real prices": 5 years by default
  assert.doesNotMatch(page, /useState\("365"\)/);
  const r = read("src/components/Rules.tsx");
  // the exit's add button opens a picker, and sits under the block's rules like the entry's
  assert.doesNotMatch(r, /addBtn\("exit"/);
  assert.match(r, /<Pop title=\{label\} label=\{`\+ \$\{label\}`\} cls="add-rule" plain>/);
  const exitBlock = r.slice(r.indexOf('<Block title="Exit"'), r.indexOf('<Block title="Size and candles">'));
  assert.ok(exitBlock.indexOf('exitPick("exit"') > exitBlock.indexOf('title="Target"'), "add button under the stop and target line");
  const gaps = read("src/components/Gaps.tsx");
  assert.match(gaps, /label: hasExit \? "No target, let the sell rule decide" : "No target", rec: true/);
});

test("the theme map says a company without a checked ticker isn't listed, not 'private' (R5O-008)", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /\{co\.name\} \(not listed\)/);
  assert.doesNotMatch(r, /\(private\)/);
});
