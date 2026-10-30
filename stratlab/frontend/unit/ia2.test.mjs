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
  assert.match(shell, /<button type="button" className="side-toggle" aria-expanded=\{open\} aria-controls=\{`side-sub-\$\{g\.id\}`\}/);
  assert.match(shell, /<span className="sr-only">\{g\.label\} pages<\/span>/);
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

// Item 38 (owner screenshot, 30 Oct): a theme's chart had its first two axis labels run together and its end-of-line names past the card.
const C = await import("../src/components/chart/core.ts");

test("item 38: an axis label held in from the plot's edge is measured where it is drawn, so the next one cannot run into it", () => {
  const w = C.textWidth("13 Oct 2023");
  // the first label at the plot's left edge is drawn from its point rightwards, not centred on it
  const first = C.placeLabel(40, w, 40, 900);
  assert.equal(first.anchor, "start");
  assert.equal(first.l, 40);
  assert.equal(first.r, 40 + w);
  // the second, 84px on: its centres were far enough apart for the old check, but its left edge sits inside the first label
  const second = C.placeLabel(124, C.textWidth("2 Feb 2024"), 40, 900);
  assert.ok((124 - 40) >= (w + C.textWidth("2 Feb 2024")) / 2 + 10, "the old centre-to-centre test let it through");
  assert.ok(second.l < first.r + 10, "the new test, on the drawn edges, leaves it out");
  // a label at the right edge is drawn leftwards from its point
  assert.deepEqual(C.placeLabel(900, 50, 40, 900), { anchor: "end", l: 850, r: 900 });
  assert.equal(C.labelWidth("abc", 11), C.textWidth("abc", 11), "without a canvas the rough width");
});

test("item 38: end-of-line labels get a column as wide as the longest one, or none when it would not fit (the legend names the lines)", () => {
  assert.equal(C.endColumn([], 1000), 0);
  assert.equal(C.endColumn([60, 80], 1000), 102);
  assert.equal(C.endColumn([200], 1000), 0, "too long for 140px: no end labels, never cut or past the card");
  assert.equal(C.endColumn([110], 600), 0, "more than a fifth of a narrow chart");
  // XYChart draws the short name at the end, the full one in the legend and tooltip; the theme's long line name has one
  const xy = read("src/components/chart/XYChart.tsx");
  assert.match(xy, /out\.push\(\{ label: s\.short \?\? s\.label, color: s\.color, v, y: 0 \}\)/);
  assert.match(xy, /const endW = endColumn\(endLabels\.map\(\(e\) => labelWidth\(e\.label, 12\)\), W\);/);
  assert.match(xy, /if \(prevT && at\.l < prevT\.r \+ 10\) return;/);
  assert.match(read("src/components/Charts.tsx"), /series=\{lines\.map\(\(l\) => \(\{ label: l\.label, short: l\.short,/);
  assert.match(read("src/components/ThemeDive.tsx"), /label: "Relative strength \(theme over index\)", short: "Rel\. strength"/);
});

// Item 39 (owner, 30 Oct: "these not colored"): every ▲/▼ change pill is green up and red down; there is no grey "neutral" pill any more.
test("item 39: the change pill always takes its direction's colour, and nothing asks for a grey one", async () => {
  const stat = read("src/components/kit/Stat.tsx");
  assert.match(stat, /export function Delta\(\{ value, children \}: \{ value: number \| null \| undefined; children: ReactNode \}\) \{/);
  assert.match(stat, /<span className=\{`k-delta \$\{dir\}`\}>\n\s*\{dir !== "flat" && <span aria-hidden="true">\{dir === "up" \? "▲" : "▼"\}<\/span>\}/);
  // an arrow is drawn only for "up" or "down", so an arrowed pill always has the class that colours it
  const css = read("src/styles.css");
  assert.match(css, /\.k-delta\.up \{ background: var\(--up-soft\); color: var\(--up\); \}/);
  assert.match(css, /\.k-delta\.down \{ background: var\(--down-soft\); color: var\(--down\); \}/);
  const { readdirSync, statSync } = await import("node:fs");
  const files = [];
  const walk = (d) => { for (const f of readdirSync(new URL(`../${d}`, import.meta.url))) { const p = `${d}/${f}`; if (statSync(new URL(`../${p}`, import.meta.url)).isDirectory()) walk(p); else if (/\.(tsx|ts)$/.test(f)) files.push(p); } };
  walk("src");
  for (const f of files) {
    const s = read(f);
    assert.doesNotMatch(s, /<Delta [^>]*tone=/, `${f}: a Delta with a tone`);
    // an arrow in a hand-made badge must carry the up/down colour too (the landing's sample card had a grey "Last close ▲ 1.33%")
    // (a chart's key to its buy and sell marks is not a change: "▲ buy ▼ sell")
    for (const m of s.matchAll(/className="([^"]*)"[^>]*>[^<{]*[▲▼]/g)) if (!/▲ buy/.test(m[0] + s.slice(m.index + m[0].length, m.index + m[0].length + 8))) assert.match(m[1], /\b(k-up|k-down|up|down|k-delta up|k-delta down)\b/, `${f}: "${m[0].slice(0, 60)}"`);
  }
});

