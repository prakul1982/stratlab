// IA-2 (owner, 30 Oct). Item 37: Market Watch's button on a laptop, two ways behind a temporary switch until the owner picks one:
// "menu" (the menu's market line is the Markets button, no floating button from 901 to 1599px) and "float" (the round button in a
// real 80px margin, 18px clear of the cards). The switch is localStorage "stratlab.mwButton" or ?mwButton= on any address.
// Run: npm run test:unit
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const M = await import("../src/lib/mwButton.ts");

// a page's storage and <body>, for applyMwButton
const store = new Map();
globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
globalThis.document = { body: { dataset: {} } };
afterEach(() => { store.clear(); globalThis.document.body.dataset = {}; });

test("item 37: the switch reads 'menu' or 'float', and anything else is no choice", () => {
  assert.equal(M.MW_BUTTON_KEY, "stratlab.mwButton");
  for (const [v, want] of [["menu", "menu"], ["float", "float"], ["MENU", "menu"], [" float ", "float"], ['"menu"', "menu"], ["", null], [null, null], [undefined, null], ["pill", null], ["true", null]])
    assert.equal(M.parseMwButton(v), want, String(v));
});

test("item 37: the default is today's floating button (with the margin fix) until the owner picks", () => {
  assert.equal(M.MW_BUTTON_DEFAULT, "float");
  assert.equal(M.pickMwButton("", null), "float");
  assert.equal(M.pickMwButton("?x=1", "nonsense"), "float");
  assert.equal(M.pickMwButton("", "menu"), "menu");
  // the address wins over the kept choice, so the owner can flip it on any page
  assert.equal(M.pickMwButton("?mwButton=float", "menu"), "float");
  assert.equal(M.pickMwButton("?a=1&mwButton=menu", "float"), "menu");
  assert.equal(M.pickMwButton("?mwButton=bogus", "menu"), "menu");
});

test("item 37: ?mwButton= is kept for the next page loads, and <body data-mw-button> says which way is on", () => {
  assert.equal(M.applyMwButton(""), "float");
  assert.equal(document.body.dataset.mwButton, "float");
  assert.equal(store.get("stratlab.mwButton"), undefined, "the default is not written: it changes when the owner picks");
  assert.equal(M.applyMwButton("?mwButton=menu"), "menu");
  assert.equal(store.get("stratlab.mwButton"), "menu");
  assert.equal(M.applyMwButton(""), "menu", "kept after the address loses it");
  assert.equal(document.body.dataset.mwButton, "menu");
  assert.equal(M.applyMwButton("?mwButton=float"), "float");
  assert.equal(M.applyMwButton(""), "float");
});

test("item 37: the Shell reads the switch, and the menu's market line becomes the Markets button in the 'menu' way", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /const mwButton = useMwButton\(loc\.search\);/);
  assert.match(shell, /<MarketsNow markets=\{markets\} opensWatch=\{mwButton === "menu"\} onGo=\{\(\) => setOpen\(false\)\} \/>/);
  const side = read("src/components/SideMenus.tsx");
  assert.match(side, /<button className="mkt-btn mkt-mw" aria-label="Open Market Watch" aria-describedby=\{id\} data-testid="markets-menu"/);
  assert.match(side, /onClick=\{\(\) => \{ onGo\?\.\(\); openMarkets\(\{ open: true \}\); \}\}>\n\s*<Markets size=\{16\} \/><span className="mkt-mw-word">Markets<\/span>/);
  const css = read("src/styles.css");
  assert.match(css, /\.mkt-btn\.mkt-mw \{ height: 36px;[^}]*border: 1px solid var\(--line-2\)/);
  assert.match(css, /\.mkt-btn\.mkt-mw:focus-visible \{ outline: 2px solid var\(--blue\)/);
  assert.match(css, /@media \(pointer: coarse\) \{[^]*?\.mkt-btn\.mkt-mw \{ height: 44px; \}/);
});

test("item 37: on a laptop the 'float' way keeps an 80px right margin with the button centred in it; the 'menu' way has no floating button there", () => {
  const css = read("src/components/watch/launcher.css");
  const block = css.match(/@media \(min-width: 901px\) and \(max-width: 1599px\) \{\n([^]*?)\n\}/)[1];
  // 80px margin, 44px button: (80 - 44) / 2 = 18px either side
  assert.match(block, /\.mw-launch\.app \{ width: 44px; min-height: 44px; padding: 0; justify-content: center; right: 18px; \}/);
  assert.match(block, /body:not\(\[data-mw-button="menu"\]\):not\(\.mw-docked\) \.shell > \.main \{ padding-right: 80px; \}/);
  // a menu folded away keeps the floating button: Market Watch is never out of reach
  assert.match(block, /body\[data-mw-button="menu"\] \.shell:not\(\.slim\) \.mw-launch\.app \{ display: none; \}/);
  // from 1600px the pill keeps its word in both ways (nothing above 1599px reads the switch)
  assert.doesNotMatch(css.replace(block, "").replace(/\/\*[^]*?\*\//g, ""), /data-mw-button/);
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
