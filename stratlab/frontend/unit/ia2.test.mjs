// IA-2 (owner, 30 Oct). Item 37 and 43: Market Watch's round button on a laptop sits in a real 80px margin, 18px clear of the cards (the owner
// picked this of the two ways shown; the menu-button way and its switch are gone). Item 36: the menu lists every page under its heading.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("items 37, 43: on a laptop the page column keeps an 80px right margin with the round button centred in it", () => {
  const css = read("src/components/watch/launcher.css");
  const block = css.match(/@media \(min-width: 901px\) and \(max-width: 1599px\) \{\n([^]*?)\n\}/)[1];
  // 80px margin, 44px button: (80 - 44) / 2 = 18px either side
  assert.match(block, /\.mw-launch\.app \{ width: 44px; min-height: 44px; padding: 0; justify-content: center; right: 18px; \}/);
  assert.match(block, /body:not\(\.mw-docked\) \.shell > \.main \{ padding-right: 80px; \}/);
});

test("item 43: the menu-button way is gone: no switch, no address word, no menu Markets button", () => {
  assert.throws(() => read("src/lib/mwButton.ts"));
  for (const f of ["src/components/Shell.tsx", "src/components/SideMenus.tsx", "src/components/watch/launcher.css", "src/styles.css"]) {
    assert.doesNotMatch(read(f), /mwButton|data-mw-button|mkt-mw|markets-menu/, f);
  }
  // the market line is the markets-now list again
  assert.match(read("src/components/Shell.tsx"), /<MarketsNow markets=\{markets\} \/>/);
  assert.match(read("src/components/SideMenus.tsx"), /<button ref=\{btn\} className="mkt-btn" aria-haspopup="dialog"/);
});

// Item 36 (owner, 30 Oct: "you have squeezed the menu bar too much"): the 14 headings stay and list their pages under them, the same
// pages as their tabs; the section you are in is open, the others fold behind a disclosure button, kept per person.
const { NAV } = await import("../src/lib/nav.ts");

test("item 36: the 14 headings stay; every heading with more than one page lists them, as its tabs do", () => {
  const ids = new Set(Object.values(NAV).flatMap((s) => s.groups.map((g) => g.id)));
  assert.equal(ids.size, 14);
  const shell = read("src/components/Shell.tsx");
  // the list is drawn from the heading's own pages (the tabs' list), through the same link the menu always used (locks, titles)
  assert.match(shell, /<div id=\{`side-sub-\$\{g\.id\}`\} className="side-list side-sub" hidden=\{!open\}>\n\s*\{g\.pages\.map\(\(p\) => \(/);
  assert.match(shell, /\{pageLink\(p, p\.label, true\)\}/);
  assert.match(read("src/components/HubTabs.tsx"), /\{at\.group\.pages\.map\(\(t\) => \{/);
  // one page: no list and no button
  assert.match(shell, /const many = g\.pages\.length > 1;/);
});

test("item 36: a disclosure button per section, the section you are in open, the person's choice kept per person", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /<button type="button" className="side-toggle" aria-expanded=\{open\} aria-controls=\{`side-sub-\$\{g\.id\}`\} aria-label=\{`\$\{g\.label\} pages`\}/);
  assert.match(shell, /const OPEN_KEY = "stratlab\.side\.open";/);
  assert.match(shell, /usePersisted<Record<string, boolean>>\(`\$\{OPEN_KEY\}\.\$\{me\?\.id \?\? "guest"\}`, NO_CHOICE\)/);
  assert.match(shell, /const isOpen = \(g: NavGroup\) => opened\[g\.id\] \?\? g\.id === current;/);
  // the heading still opens the section's first page; it is marked only when its own page shows, else only bold
  assert.match(shell, /const to = startOf\(g, sp\);/);
  assert.match(shell, /className=\{here \? "active" : inIt \? "in-section" : undefined\} aria-current=\{here \? "page" : undefined\}/);
  const css = read("src/styles.css");
  assert.match(css, /\.side-list a\.in-section \{ color: var\(--ink\); font-weight: 600; \}/);
  assert.match(css, /\.side-list\.side-sub a \{ height: 28px;/);
  assert.match(css, /@media \(pointer: coarse\) \{[^]*?\.side-list a, \.side-list\.side-sub a \{ height: 40px; \}/);
});
