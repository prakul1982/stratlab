// Round 68 (19 Oct 2026): a first-time visitor on Chrome and Safari, desktop and phone — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R68-004: the start-up error card's link button is readable, and the notices don't stack or empty the app's elements", () => {
  const html = read("index.html");
  // the button is ink with paper-coloured words (beats ".boot a { color: inherit }"), and the dark theme swaps the two (RC7-001: through
  // the --b-ink / --b-on-ink tokens, which the dark blocks redefine, so it is readable on the paper in both themes)
  assert.match(html, /\.boot-btn, \.boot a\.boot-btn \{[^}]*background: var\(--b-ink\); color: var\(--b-on-ink\);/);
  assert.match(html, /--b-ink: #EFE9DC;[^}]*--b-on-ink: #141311;/);
  assert.match(html, /body:has\(#root \[role="alert"\]\) > main > \.boot-now \{ display: none; \}/);
  const boot = read("public/boot.js");
  assert.match(boot, /k\.indexOf\("__reactContainer"\) === 0/);
  assert.match(boot, /if \(!keep && !owned\) root\.textContent = "";/);
  assert.match(boot, /root\.parentNode\.insertBefore\(main, root\)/);
  assert.match(boot, /\/\\\/config\\\.js\(\\\?\|\$\)\/\.test\(url\)/);                // config.js failing is a failed load
});

test("R68-005: the start-up page's policy links are tall enough to tap", () => {
  const html = read("index.html");
  assert.match(html, /\.boot-foot a \{ display: inline-block; padding: 12px 4px; \}/);
  assert.match(html, /<p class="boot-foot"><a href="\/terms">Terms<\/a>/);
});

test("R68-007: the landing examples can be paused with a button", () => {
  const src = read("src/pages/Login.tsx");
  assert.match(src, /className="lp-demo-pause" onClick=\{\(\) => setAuto\(\(a\) => !a\)\}/);
  assert.match(src, /auto \? "Pause the examples" : "Play the examples"/);
});

test("R68-009: during the launch offer the pricing line says whether plans are on sale, and the end in the visitor's time", async () => {
  const offer = await import("../src/lib/offer.ts");
  const promo = { mode: "promo", promo_until: "2026-10-22T11:50:00Z", payments: true };
  const ny = offer.pricingIntro(promo, {}, "landing", undefined, "America/New_York");
  assert.match(ny.lede, /until Thu 22 Oct at 5:20 pm IST \(Thu 22 Oct, 7:50 am your time\)\./);
  assert.match(ny.lede, /Basic and Pro are on sale now too/);
  const india = offer.pricingIntro(promo, {}, "landing", undefined, "Asia/Kolkata");
  assert.doesNotMatch(india.lede, /your time/);
  assert.match(offer.pricingIntro({ ...promo, payments: false }, {}, "landing", undefined, "Asia/Kolkata").lede, /aren't on sale yet/);
  assert.equal(offer.endsLocal("2026-10-22T11:50:00Z", "Europe/London"), "Thu 22 Oct, 12:50 pm your time");
});
