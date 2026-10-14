// Round 14 review fixes (R14-007). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("the start-up text sits down the page with padding, not a top margin that moves the whole body when the app replaces it", () => {
  const rule = read("index.html").match(/^\.boot \{([^}]*)\}/m)?.[1] ?? "";
  assert.match(rule, /padding:\s*18vh 16px 0/);
  assert.doesNotMatch(rule, /margin:[^;]*18vh/);
});

test("the landing page's verdict-card placeholders are as tall as the cards that replace them", () => {
  const css = read("src/styles.css");
  assert.match(css, /^\.lp-skel-card \{ height: 207px;/m);
  assert.match(css, /\.lp-skel-card \{ height: 190px; \} \}/);
});
