// A11Y-1 (27 Oct 2026): accessibility review of the most-used pages: what was fixed, held in place.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");

test("A11Y-002: the big search box shows a real focus ring, not only a 1.1:1 glow", () => {
  const rule = css.match(/\.search-box:focus-within \{([^}]*)\}/)[1];
  assert.match(rule, /outline: 2px solid var\(--blue\)/);
  assert.doesNotMatch(rule, /blue-soft/);
});

test("A11Y-003: a script's scroll and a changing placeholder respect 'reduce motion'", async () => {
  const { scrollBehavior, prefersReducedMotion } = await import("../src/lib/motion.ts");
  assert.equal(prefersReducedMotion(), false);                         // no window in node
  assert.equal(scrollBehavior(), "smooth");
  globalThis.window = { matchMedia: (q) => ({ matches: /reduce/.test(q) }) };
  try {
    assert.equal(prefersReducedMotion(), true);
    assert.equal(scrollBehavior(), "auto");
  } finally { delete globalThis.window; }
  // nothing asks for "smooth" by hand any more
  for (const f of ["components/Explore", "components/IdeaComposer", "components/Shell", "components/kit/PageNav", "pages/Home", "pages/MarketPage", "pages/NewsPage", "pages/NotebookPage"]) {
    const src = read(`src/${f}.tsx`);
    assert.doesNotMatch(src, /behavior: "smooth"/, f);
    assert.match(src, /scrollBehavior\(\)/, f);
  }
  assert.match(read("src/lib/rotating.ts"), /prefersReducedMotion\(\)\) return/);
});

test("A11Y-004: on a phone or touch screen the (i), the logo link, drop-downs and small fields are 44px to hit", () => {
  const block = css.slice(css.indexOf("A11Y-004"));
  assert.match(block, /\.info-btn \{ --hit: 44px; \}/);
  assert.match(block, /\.brand \{ min-height: 44px; \}/);
  assert.match(block, /select \{ min-height: 44px; \}/);
  assert.match(block, /\.k-input\.sm, \.k-input\.k-in \{ height: 44px; \}/);
  // the (i)'s box and its focus ring follow --hit, so growing it moves nothing around it
  assert.match(css, /width: var\(--hit\); height: var\(--hit\); margin: calc\(\(var\(--i\) - var\(--hit\)\) \/ 2\)/);
  assert.match(css, /\.info-btn:focus-visible \{ outline-offset: calc\(\(var\(--i\) - var\(--hit\)\) \/ 2 \+ 2px\); \}/);
});

test("A11Y-005: a Field hands its own control the attributes that tie it to the error line under it", () => {
  const form = read("src/components/kit/Form.tsx");
  assert.match(form, /children\(fid, tie\)/);
  assert.match(form, /"aria-describedby": error \|\| shown \? msgId : undefined/);
  assert.match(read("src/components/kit/StockPicker.tsx"), /\{\.\.\.tie\}/);
  assert.match(read("src/components/AlertForm.tsx"), /\(id, tie\) => <StockPicker id=\{id\} tie=\{tie\}/);
  assert.match(read("src/pages/HoldingsPage.tsx"), /\(id, tie\) => <StockPicker key=\{`\$\{add\.market\}-\$\{boxes\}`\} id=\{id\} tie=\{tie\}/);
});

test("A11Y-006: each open scheme's blocks are regions named after the scheme, so two open folds don't share names", () => {
  const mf = read("src/pages/money/MutualFundsPage.tsx");
  for (const label of ["`Holding, ${s.name}`", "`Sales, ${name}`", "`31 Jan 2018 NAV, ${s.name}`"]) assert.ok(mf.includes(`aria-label={${label}}`), label);
  assert.match(mf, /<CostDetail q=\{costs\} id=\{s\.key\} name=\{s\.name\} \/>/);
  assert.match(mf, /<BehaviourDetail q=\{habits\} id=\{s\.key\} name=\{s\.name\} \/>/);
  assert.match(read("src/pages/money/FundCosts.tsx"), /`What it costs, \$\{name\}`/);
  assert.match(read("src/pages/money/FundBehaviour.tsx"), /`How you invested, \$\{name\}`/);
});

test("A11Y-007: a chart menu closed with Esc hands focus back to its button; the indicator settings take focus on opening", () => {
  const pc = read("src/charts/price/PriceChart.tsx");
  assert.match(pc, /querySelector<HTMLElement>\(":scope > button"\)/);
  assert.match(pc, /if \(edit\) editBox\.current\?\.querySelector<HTMLElement>\("input, button"\)\?\.focus\(\)/);
  assert.match(pc, /editBtn\.current\?\.focus\(\)/);
});

test("A11Y-008/009/010: a link in the (i) box, a note inside a filled button, and the palette's result list read and are named", () => {
  assert.match(css, /\.info-pop a, \.info-pop a:hover \{ color: var\(--on-ink\)/);
  assert.match(css, /\.btn:not\(\.quiet\):not\(\.outline\):not\(\.danger\) :is\(\.k-note, \.k-sub-line, \.muted\) \{ color: inherit; \}/);
  assert.match(read("src/components/SearchPalette.tsx"), /role="listbox" aria-label="Results"/);
});

test("A11Y-011: the drawings list holds only list items, and the phone sheet's group names are h2 (not an h4 that skips levels)", () => {
  const dt = read("src/charts/price/DrawToolbar.tsx");
  const list = dt.slice(dt.indexOf("function DrawList"), dt.indexOf("/** The vertical rail"));
  const inner = list.slice(list.indexOf('role="list"'), list.indexOf("</div>\n      )}") + 1);
  assert.doesNotMatch(inner, /<button type="button" className="btn quiet sm"/);   // "Remove all drawings" is outside the list
  assert.doesNotMatch(inner, /pc-note/);                                          // so is the empty note
  assert.match(list, /<button type="button" className="btn quiet sm" onClick=\{p\.onClearAll\}>Remove all drawings/);
  assert.doesNotMatch(dt, /<h4>/);
  assert.match(dt, /<h2>\{g\.name\}<\/h2>/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-sheet-body h2 \{/);
});

test("A11Y-012: on /plans (the page's own h1 above the cards) a plan's name is an h2; on the landing page, under its h2, an h3", () => {
  const login = read("src/pages/Login.tsx");
  assert.match(login, /const PlanHeading = top \? "h2" : "h3";/);
  assert.match(login, /<PlanHeading className="h2">\{PLAN_NAME\[p\]\}<\/PlanHeading>/);
});

test("A11Y-001: the library's and the list filters' search box draws its edge in --field-line and a 2px blue edge on focus", () => {
  const t = read("src/pages/trade/trade.css");
  assert.match(t, /\.k-search \{[^}]*border: 1px solid var\(--field-line\)/);
  assert.match(t, /\.k-search:focus-within \{ border-color: var\(--blue\); box-shadow: 0 0 0 1px var\(--blue\)/);
});
