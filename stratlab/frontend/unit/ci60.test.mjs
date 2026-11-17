// Lane ci60: where Release 60's lanes met in the frontend.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Market today's volatility table: ▲/▼ in coloured text, no pills, as FII/DII beside it (LIVE9A-002 with R15 #16)", () => {
  const src = read("src/pages/PulseMood.tsx");
  const risk = src.slice(src.indexOf("export function RiskTable"), src.indexOf("export function GlobalTable"));
  assert.match(risk, /<Signed value=\{mv\.value\}>\{arrowed\(mv\.value, mv\.text\)\}<\/Signed>/);
  assert.doesNotMatch(risk, /<Delta /);
  assert.match(src, /function arrowed\(value: number, text: string\): ReactNode \{[\s\S]*?"▲" : "▼"/);
});

test("the Plans placeholders keep the room the lede and the fine print take on a laptop, US dollar note included (R5V-006 with su1)", () => {
  const css = read("src/styles.css");
  assert.match(css, /\n\.lp-skel-p \{ height: calc\(17px \* 1\.6 \* 3\);/);
  assert.match(css, /\n\.lp-skel-fine \{ height: calc\(13\.5px \* 1\.5 \* 4\);/);
});
