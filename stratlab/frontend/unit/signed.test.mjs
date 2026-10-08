// Signed figures: positive is green (k-up), negative red (k-down), zero and unknown stay plain, and the colour always
// agrees with the sign that is printed. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { signCls, signTone, signed, pct } from "../src/lib/format.ts";

test("positive maps to k-up, negative to k-down, zero to nothing", () => {
  assert.equal(signCls(5721), "k-up");
  assert.equal(signCls(-2579), "k-down");
  assert.equal(signCls(0), "");
  assert.equal(signCls(0.0001), "k-up");
  assert.equal(signCls(-1e-9), "k-down");
});

test("a missing or non-numeric value is never coloured", () => {
  assert.equal(signCls(null), "");
  assert.equal(signCls(undefined), "");
  assert.equal(signCls(NaN), "");
  assert.equal(signCls(Infinity), "", "an infinite value is not a figure");
});

test("given the text that is shown, a figure that rounds to nothing stays plain", () => {
  assert.equal(signCls(-0.02, pct(-0.02)), "", `"${pct(-0.02)}" has no sign, so it has no colour`);
  assert.equal(signCls(0.3, signed(0.3)), "", `"${signed(0.3)}" is zero`);
  assert.equal(signCls(-4.5, pct(-4.5)), "k-down");
  assert.equal(signCls(1234, signed(1234)), "k-up");
  assert.equal(signCls(-1, "−1"), "k-down");
});

test("words about a direction keep their colour (a bigger stake, a smaller one)", () => {
  assert.equal(signCls(1, "More shares"), "k-up");
  assert.equal(signCls(-1, "Fewer shares"), "k-down");
});

test("the colour agrees with the printed sign for every signed text", () => {
  for (const v of [-123456, -5, -0.4, 0, 0.4, 5, 123456]) {
    const text = signed(v, 1);
    const cls = signCls(v, text);
    if (text.startsWith("+")) assert.equal(cls, "k-up", text);
    else if (text.startsWith("−")) assert.equal(cls, "k-down", text);
    else assert.equal(cls, "", text);
  }
});

test("signTone and signCls agree, and the trade pages' upDown is signCls", () => {
  for (const v of [-3, 0, 3, null, undefined]) assert.equal(signTone(v) ? `k-${signTone(v)}` : "", signCls(v));
  assert.match(readFileSync(new URL("../src/lib/tradeUi.ts", import.meta.url), "utf8"), /export const upDown = .*signCls\(v\)/);
});

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
test("k-up and k-down are the kit's green and red", () => {
  assert.match(css, /\.k-up \{ color: var\(--up\); \}/);
  assert.match(css, /\.k-down \{ color: var\(--down\); \}/);
});

test("the Signed component writes the class signCls gives, and keeps the text (and so the sign) in the page", () => {
  const src = readFileSync(new URL("../src/components/kit/Signed.tsx", import.meta.url), "utf8");
  assert.match(src, /signCls\(value/);
  assert.match(src, /<span className=\{cls\}>\{text\}<\/span>/);
});

test("the positioning page's change and net cells are drawn with Signed", () => {
  const src = readFileSync(new URL("../src/pages/PositioningPage.tsx", import.meta.url), "utf8");
  assert.match(src, /<span className="k-sub-line"><Sgn v=\{v\} \/><\/span>/, "the change line under each cell");
  assert.match(src, /k\.endsWith\("_net"\) \? <Sgn v=/, "the net futures column");
  assert.match(src, /tone=\{signTone\(n\(fii, `fut_\$\{seg\}_net`\)\)\}/, "the headline net");
});
