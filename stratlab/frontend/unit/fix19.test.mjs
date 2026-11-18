// Lane fix19 (owner, 18 Nov): one browser-tab title pattern everywhere, "Page · StratLab" (the landing page "StratLab");
// the sidebar's "More below" pill never covers a menu item; the analytics question in the app is a card in the page flow.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { ALL_GROUPS, ALL_PAGES, groupPath } = await import("../src/lib/nav.ts");
const title = await import("../src/lib/title.ts");
const seo = await import("../src/content/seo.ts");
const { AD_TITLE } = await import("../src/content/ad.ts");

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
// one part, then the brand: no second " · " inside the page's name
const ONE = /^[^·]+ · StratLab$/;

test("every tab title is 'Page · StratLab' with a one-part name, the landing page the brand alone (owner, 18 Nov)", () => {
  assert.equal(seo.withBrand("Briefs"), "Briefs · StratLab");
  assert.equal(seo.withBrand(), "StratLab");
  assert.equal(seo.HOME_TITLE, "StratLab");
  assert.equal(title.DEFAULT_TITLE, "StratLab");
  assert.equal(title.signedOutTitle("/"), "StratLab");
  // every menu page and every entry page, signed in and signed out
  for (const { page } of ALL_PAGES) {
    assert.match(title.titleFor(page.to), ONE, page.to);
    assert.equal(title.titleFor(page.to), `${page.label} · StratLab`, page.to);
    assert.match(title.signedOutTitle(page.to), /^(Sign in: [^·]+|[^·]+) · StratLab$/, page.to);
  }
  for (const { space, group } of ALL_GROUPS) assert.equal(title.titleFor(groupPath(space, group)), `${group.label} · StratLab`);
  // the pages LIVE13A-023 named: a renamed tab is titled like its neighbours
  assert.equal(title.titleFor("/invest/breadth"), "Breadth · StratLab");
  assert.equal(title.titleFor("/invest/movers"), "Movers · StratLab");
  assert.equal(title.titleFor("/research/rotation"), "Sectors · StratLab");
  // Plans: one name signed in and signed out, on each of its addresses
  for (const p of ["/plans", "/pricing", "/upgrade"]) assert.equal(title.signedOutTitle(p), "Plans · StratLab", p);
  assert.equal(title.titleFor("/plans"), "Plans · StratLab");
  // the public table, the ad landing, the admin sections, a notebook's run, a company
  for (const p of seo.PAGES.filter((x) => x.path !== "/")) assert.match(p.title, ONE, p.path);
  assert.equal(AD_TITLE, seo.withBrand("Try StratLab free"));
  for (const p of ["/admin", "/admin/users", "/admin/emails"]) assert.match(title.titleFor(p), ONE, p);
  assert.match(title.withBrand(title.notebookTitle("My notebook", "Run v2")), ONE);
  assert.equal(title.companyName("Reliance Industries", "RELIANCE"), "Reliance Industries (RELIANCE)");
  assert.equal(title.withBrand(title.companyName("Reliance Industries", "RELIANCE")), "Reliance Industries (RELIANCE) · StratLab");
  assert.equal(title.companyName("AAPL", "AAPL"), "AAPL");
  assert.equal(title.companyName(null, "AAPL"), "AAPL");
  // a library strategy's title keeps its short name only, so no universe after a second " · "
  assert.match(seo.libraryMeta("seed-golden-cross-in", "Golden cross · NIFTY 50 stocks").title, ONE);
  assert.match(seo.libraryTitle("Supertrend flip · 20 of the largest US companies", null, "Probably luck."), ONE);
});

test("no page writes its own ' · StratLab': the app's titles go through withBrand (content/seo.ts)", () => {
  const files = [];
  const walk = (d) => { for (const f of readdirSync(d)) { const p = join(d, f); if (statSync(p).isDirectory()) walk(p); else if (/\.(ts|tsx)$/.test(f)) files.push(p); } };
  walk(new URL("../src", import.meta.url).pathname);
  const allowed = new Set(["content/seo.ts", "content/ad.ts"]);
  for (const f of files) {
    const rel = f.split("/src/")[1];
    if (allowed.has(rel)) continue;
    // the code, not its comments
    const src = readFileSync(f, "utf8").split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).map((l) => l.replace(/\s\/\/ .*$/, "")).join("\n");
    assert.doesNotMatch(src, /document\.title = ["`'][^"`']*· StratLab/, rel);
    assert.doesNotMatch(src, /["`'][^"`'\n]*\S · StratLab["`']/, rel);
  }
  // the static page the landing is drawn from says the same as the app
  assert.match(read("index.html"), /<title>StratLab<\/title>/);
  assert.match(read("scripts/seoPages.mjs"), /title: withBrand\("Page not found"\)/);
});

test("the sidebar's More below pill has a row of its own under the menu's edge line, and 'below' means the last item is not in view", () => {
  const css = read("src/styles.css"), shell = read("src/components/Shell.tsx");
  assert.match(css, /\.side-more-row \{[^}]*border-top: 1px solid var\(--line-2\)/);
  assert.doesNotMatch(css.match(/\n\.side-more \{[^}]*\}/)[0], /z-index|position: (absolute|fixed)/);
  assert.match(shell, /<div className="side-more-row">\s*<button type="button" className="side-more"/);
  assert.match(shell, /const below = last \? last\.getBoundingClientRect\(\)\.bottom - el\.getBoundingClientRect\(\)\.bottom > 1/);
});

test("the analytics question is one small card in the page's flow that can be closed for the visit (owner, 18 Nov)", () => {
  const css = read("src/styles.css"), card = read("src/components/Tracking.tsx");
  const rule = css.match(/\n\.consent \{[^}]*\}/)[0];
  assert.match(rule, /position: relative/);
  assert.doesNotMatch(rule, /position: (fixed|sticky)|z-index/);
  assert.match(rule, /max-width: 640px/);
  assert.match(css, /\.shell > \.consent \{ grid-column: -2 \/ -1; grid-row: 2;[^}]*width: min\(640px,/);
  assert.match(card, /className="consent-x" aria-label="Not now"/);
  // closed, no answer is saved (nothing loads) and it stays away for the visit
  assert.match(card, /if \(guiding \|\| !settled \|\| later\) return null;/);
  assert.match(card, /sessionStorage\.setItem\(LATER_KEY, "1"\)/);
  const later = card.slice(card.indexOf("function askLater"));
  assert.doesNotMatch(later.slice(0, later.indexOf("\n}\n")), /writeChoice/);
});
