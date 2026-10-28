// The welcome question says what StratLab is before where things are, in the landing page's own sentence.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("the welcome pop-up opens with the landing page's 'What StratLab is' sentence", () => {
  const src = read("src/components/LevelPrompt.tsx");
  assert.match(src, /import \{ INTRO_LINE \} from "\.\.\/content\/intro";/);
  const what = src.indexOf('<p className="welcome-what">{INTRO_LINE}</p>');
  assert.ok(what > 0 && what < src.indexOf("StratLab has four spaces"));       // first, before the spaces line
  assert.match(read("src/content/intro.ts"), /paper trading only \(never real orders\) and facts, not tips/);
  assert.match(read("src/styles.css"), /\.welcome-what \{ margin: 0;/);
});
