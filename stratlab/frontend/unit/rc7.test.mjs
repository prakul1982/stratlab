// RC-7 (round 3 of the main review): the account, errors and phone side, and the investor figures that said one fact two ways.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("RC7-001: the start-up error card wears the app's paper and ink in both themes, with the logo, and is never pale text on white", () => {
  const html = read("index.html");
  // the page itself has the paper colour (it was the browser's white, with #eee text when the device was dark)
  assert.match(html, /html, body \{ margin: 0; background: var\(--b-paper\); \}/);
  // the same values as the app's tokens, for light, for a dark device with no saved choice, and for a saved dark choice
  assert.match(html, /:root \{ --b-paper: #F5F1E8; --b-card: #FFFDF8; --b-ink: #1D1B17;/);
  assert.match(html, /@media \(prefers-color-scheme: dark\) \{ :root:not\(\[data-theme="light"\]\) \{ --b-paper: #141311; --b-card: #1F1D1A; --b-ink: #EFE9DC;/);
  assert.match(html, /:root\[data-theme="dark"\] \{ --b-paper: #141311; --b-card: #1F1D1A; --b-ink: #EFE9DC;/);
  const css = read("src/styles.css");
  for (const [name, v] of [["paper", "#F5F1E8"], ["card", "#FFFDF8"], ["ink", "#1D1B17"], ["paper", "#141311"], ["card", "#1F1D1A"], ["ink", "#EFE9DC"]]) assert.ok(css.includes(`--${name}: ${v}`), `${name} ${v} is the app's own`);
  // no text colour is written as a bare light grey on the unthemed page any more
  assert.doesNotMatch(html, /\.boot, \.boot-head a \{ color: #eee; \}/);
  const boot = read("public/boot.js");
  assert.match(boot, /brand\.className = "boot-brand"/);
  assert.match(boot, /logo\.onerror = function \(\) \{ logo\.style\.display = "none"; \}/);     // no connection and no copy: the name, not a broken picture
  assert.match(html, /\.boot\.boot-now \{ box-sizing: border-box; max-width: min\(520px, calc\(100% - 32px\)\);/);   // a 16px gutter on a phone
});

test("RC7-001: the service worker's offline page is the same card, in both themes, and the logo it shows is the kept copy", () => {
  const sw = read("public/sw.js");
  assert.match(sw, /@media \(prefers-color-scheme:dark\)\{:root\{--p:#141311;--c:#1F1D1A;--i:#EFE9DC;/);
  assert.match(sw, /<img src="\/favicon\.svg"/);
  assert.match(sw, /url\.pathname === "\/favicon\.svg"[\s\S]{0,200}caches\.match\("\/favicon\.svg"\)/);
  assert.match(sw, /data-testid="offline-reload">Reload<\/button>/);      // the button the tests and the page's own reload use
});
