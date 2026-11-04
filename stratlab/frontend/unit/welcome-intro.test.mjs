// The welcome question says what StratLab is before where things are, in one sentence (the landing page cut it, LIVE3-023: it lives here).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("the welcome pop-up opens with the one 'what StratLab is' sentence", () => {
  const src = read("src/components/LevelPrompt.tsx");
  assert.match(src, /import \{ INTRO_LINE \} from "\.\.\/content\/welcome";/);      // not in the landing page's download since it cut the sentence (LIVE3-023)
  const what = src.indexOf('<p className="welcome-what">{INTRO_LINE}</p>');
  assert.ok(what > 0 && what < src.indexOf("The others stay one tap away"));       // first, before the line about where things are
  assert.match(read("src/content/welcome.ts"), /paper trading only \(never real orders\) and facts, not tips/);
  assert.match(read("src/styles.css"), /\.welcome-what \{ margin: 0;/);
});

test("StratLab's Instagram is linked from the app's footers, the server pages' footer and the Organization data", () => {
  const url = "https://www.instagram.com/stratlab.studio/";
  assert.match(read("src/content/seo.ts"), new RegExp(`export const INSTAGRAM = "${url.replace(/[./]/g, "\\$&")}";`));
  assert.match(read("src/components/LegalLinks.tsx"), /<a className="muted" href=\{INSTAGRAM\} rel="me noopener">Instagram<\/a>/);
  assert.match(read("scripts/seoPages.mjs"), /sameAs: \[INSTAGRAM\]/);
  assert.ok(readFileSync(new URL("../../backend/app/stock_pages.py", import.meta.url), "utf8").includes(`INSTAGRAM = "${url}"`));
});
