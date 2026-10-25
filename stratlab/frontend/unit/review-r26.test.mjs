// Round 26 (a signed-out visitor): the public pages' phone Menu, /login's heading order, /pricing's address, the closing
// heading's wrap. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const root = new URL("../", import.meta.url);
const read = (p) => fs.readFileSync(new URL(p, root), "utf8");
const seo = await import("../src/content/seo.ts");
const { seoFor } = await import("../src/lib/seo.ts");

test("R26-005: the library's frame has a Menu (details/summary) with Trade, Invest, Money, Plans and Companies, shown up to 640px", () => {
  const frame = read("src/components/PublicFrame.tsx");
  assert.match(frame, /<details className=\{`lp-menu pub-menu\$\{action \? " pub-menu-start" : ""\}`\} ref=\{menu\}>\s*<summary>Menu<\/summary>/);
  assert.match(frame, /useDetailsDismiss\(menu\)/);
  for (const label of ["Trade", "Invest", "Money", "Plans", "Companies"]) assert.match(frame, new RegExp(`, "${label}"\\]`), label);
  const css = read("src/styles.css");
  assert.match(css, /@media \(min-width: 641px\) \{ \.pub-nav \.pub-menu \{ display: none; \} \}/);
  assert.match(css, /\.pub-nav \.lp-menu nav \{[^}]*position: absolute/);
});

test("R26-004: /login's dialog (its h2) comes after the page's h1 in the DOM", () => {
  const src = read("src/pages/Login.tsx");
  assert.ok(src.indexOf("</main>") < src.indexOf("{way && ("), "the dialog is drawn after main");
  assert.ok(src.indexOf('<h1 className="serif lp-h1">') < src.indexOf("{way && ("));
});

test("R26-006, RC1-011: /pricing's canonical address is the plans page, and it is not in the sitemap", () => {
  assert.equal(seoFor("/pricing").canonical, "https://stratlab.studio/plans");
  assert.ok(!seo.sitemapPages().some((p) => p.path === "/pricing"));
  assert.ok(seo.sitemapPages().some((p) => p.path === "/faq"));
});

test("R26-003: /features and /upgrade say what they are for a signed-out visitor, not 'Sign in to open this page'", () => {
  assert.equal(seoFor("/features", "gate").description, seo.FEATURES_DESCRIPTION);
  assert.equal(seoFor("/upgrade", "gate").description, seo.pageMeta("/pricing").description);
});

test("R26-010: the closing heading balances its lines, so a phone has no one-word last line", () => {
  assert.match(read("src/styles.css"), /\.lp-final-h \{[^}]*text-wrap: balance/);
});
