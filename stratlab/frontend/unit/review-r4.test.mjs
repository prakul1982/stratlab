// Round 4, builder A: the one financial-year rule, tab titles for every public page, the sidebar's lock, the welcome
// question's rule, and the pieces of markup the review looked at (page widths, hints, chips).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { openFy, askedFy, fyLink, yearHasTrades, movedYearNote } = await import("../src/lib/fy.ts");
const { signedOutTitle, titleFor, PUBLIC_TITLES } = await import("../src/lib/title.ts");
const { landingSection, isAppPath } = await import("../src/lib/deepLinks.ts");
const { welcomePending, askWelcome } = await import("../src/lib/onboarding.ts");
const { featureTag } = await import("../src/lib/offer.ts");
const { PAGE_GATES } = await import("../src/lib/gates.ts");

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("a year a link asks for is the year a page opens on, data or not (R4-007)", () => {
  const years = [2026, 2025, 2024];
  const has = (fy) => fy === 2024;
  assert.deepEqual(openFy(years, 2026, has, null, 2026), { fy: 2026, from: null });            // "as in tax tools": that year, as asked
  assert.deepEqual(openFy(years, 2026, has, 2024, 2025), { fy: 2025, from: null });            // a link beats the year last picked
  assert.deepEqual(openFy(years, 2026, has, null, 2019), { fy: 2024, from: 2025 });             // a year the page doesn't list is ignored
  assert.deepEqual(openFy(years, 2026, has, null, null), { fy: 2024, from: 2025 });             // else the rule: filing year, then the latest with data
  assert.deepEqual(openFy(years, 2026, (fy) => fy !== 2024, null, null), { fy: 2025, from: null });
  assert.equal(movedYearNote(2025, 2024, 2026, "sales"), "No sales in FY 2025-26, the year being filed, so this is FY 2024-25, the latest year with sales.");
});

test("a year in an address is read and written the same way (R4-007)", () => {
  assert.equal(askedFy("2025"), 2025);
  for (const bad of [null, undefined, "", "abc", "25", "2025.5", "99999"]) assert.equal(askedFy(bad), null, String(bad));
  assert.equal(fyLink("/money/tax-tools", 2026), "/money/tax-tools?fy=2026");
  assert.equal(fyLink("/money/tax-tools?tab=advance", 2026), "/money/tax-tools?tab=advance&fy=2026");
});

test("the Money home card and the tax report call the same years empty (R4-007)", () => {
  assert.equal(yearHasTrades({ count: 0, intraday: { count: 0 }, business: { segments: [] } }), false);
  assert.equal(yearHasTrades({ count: 5, intraday: { count: 0 }, business: { segments: [] } }), true);
  assert.equal(yearHasTrades({ count: 0, intraday: { count: 2 }, business: { segments: [] } }), true);
  assert.equal(yearHasTrades({ count: 0, intraday: { count: 0 }, business: { segments: [{}] } }), true);
  assert.equal(yearHasTrades({ count: 0, units: {} }), true);
});

test("every Money and tax page opens its year through openFy, and links carry the year (R4-007)", () => {
  for (const f of ["pages/TaxReportPage.tsx", "pages/money/TaxToolsPage.tsx", "pages/money/ItrExportPage.tsx", "pages/money/UsTaxPage.tsx", "pages/money/MutualFundsPage.tsx", "pages/SpaceHomes.tsx"]) {
    const s = read(f);
    assert.match(s, /movedYearNote|openFy/, `${f} doesn't use the shared rule`);
    assert.doesNotMatch(s, /\bpickFy\(/, `${f} opens on a year by its own rule`);
  }
  for (const f of ["pages/TaxReportPage.tsx", "pages/money/TaxToolsPage.tsx", "pages/money/UsTaxPage.tsx", "pages/money/MutualFundsPage.tsx"]) assert.match(read(f), /useAskedFy\(\)/, `${f} ignores ?fy=`);
  assert.match(read("pages/money/ItrExportPage.tsx"), /useAskedFy\(\)/);
  assert.match(read("components/HoldingsActions.tsx"), /fyLink\("\/money\/tax-tools", y\.fy\)[^]*as in tax tools/, "'as in tax tools' is a link that carries its year");
  assert.match(read("pages/SpaceHomes.tsx"), /fyLink\("\/tax-report", year\.fy\)/, "the Money home card's link carries its year");
});

test("every public page has a tab title of its own, and a page nothing is at says so (R4-017)", () => {
  assert.equal(signedOutTitle("/terms"), "Terms · StratLab");
  assert.equal(signedOutTitle("/privacy"), "Privacy · StratLab");
  assert.equal(signedOutTitle("/refunds"), "Refunds · StratLab");
  assert.equal(signedOutTitle("/contact"), "Contact · StratLab");
  assert.equal(signedOutTitle("/login"), "Sign in · StratLab");
  assert.equal(signedOutTitle("/signup"), "Sign up · StratLab");
  assert.equal(signedOutTitle("/about"), "About · StratLab");
  assert.equal(signedOutTitle("/nowhere"), "Page not found · StratLab");
  assert.equal(signedOutTitle("/holdings"), "Sign in · Holdings · StratLab");        // an app address still says what it waits for
  const titles = Object.values(PUBLIC_TITLES);
  assert.equal(new Set(titles).size, titles.length, "two public pages share a title");
  assert.equal(titleFor("/nowhere"), "StratLab: test it, research it, track it", "the signed-in default is unchanged: NotFound titles itself");
});

test("/login, /signup and /about are real addresses, not dead routes (R4-017)", () => {
  assert.equal(landingSection("/login"), null);
  assert.equal(landingSection("/signup"), null);
  assert.equal(landingSection("/about"), "about");
  for (const p of ["/login", "/signup", "/about"]) assert.ok(isAppPath(p), `${p} has no route`);
  assert.match(read("pages/Login.tsx"), /<div id="about" className="lp-wrap/, "the landing page has the place /about scrolls to (not a section[id]: the landing test lists those)");
  const main = read("main.tsx");
  for (const [from, to] of [["/login", "/"], ["/signup", "/"], ["/about", "/features"]]) assert.match(main, new RegExp(`path="${from}" element=\\{<Navigate to="${to}" replace />\\}`), `${from} signed in`);
});

test("the menu locks only a page that is locked whole; a part-paid page is described, not locked (R4-006)", () => {
  const shell = read("components/Shell.tsx");
  assert.match(shell, /const locked = off && gate!\.whole;/);
  assert.match(shell, /off \? `\$\{p\.line\} \(\$\{gate!\.whole \? "" : "part of it "\}on the/, "the part is still in the link's title");
  // the pages the review named are part-paid, so they carry no lock
  for (const p of ["/money/net-worth", "/money/mutual-funds"]) assert.equal(PAGE_GATES[p].whole, false, p);
  // a card for a part-paid page says "for part", not "🔒"
  const part = featureTag("basic", null, { canUse: false, part: true });
  assert.equal(part.locked, false);
  assert.equal(part.label, "Basic for part");
  assert.equal(featureTag("basic", null, { canUse: false }).label, "🔒 Basic");
  assert.equal(featureTag("basic", null, { canUse: true, part: true, paid: "basic" }).label, "Basic");
  // the two pages say what is free, where the numbers are
  assert.match(read("pages/money/NetWorthPage.tsx"), /of \{view\.limit\} free entries used/);
  assert.match(read("pages/money/MutualFundsPage.tsx"), /of \{view\.limit\} free schemes used/);
});

test("the welcome question is for an empty account only, and never starts on a choice (R4-101)", () => {
  const empty = { prefs: { level: null, focus: null }, onboarding: { welcome: null, tour: null } };
  assert.equal(welcomePending(empty), true);
  assert.equal(welcomePending({ ...empty, established: false }), true);
  assert.equal(welcomePending({ ...empty, established: true }), false, "an established account is never asked");
  assert.equal(askWelcome({ ...empty, established: true }, "/mine"), false);
  assert.equal(askWelcome(empty, "/mine"), true);
  assert.equal(welcomePending({ prefs: { level: "some", focus: "both" }, onboarding: { welcome: null, tour: null } }), false);
  assert.match(read("components/LevelPrompt.tsx"), /<Modal title="What brings you here\?" startOnClose/);
  assert.match(read("components/kit/Dialog.tsx"), /initial: startOnClose \? \(\) => box\.current\?\.querySelector<HTMLElement>\("\[data-close\]"\)/);
});

test("pages that were narrower than the rest use the standard width (R4-018)", () => {
  for (const f of ["pages/ImportPage.tsx", "pages/OptionsPage.tsx"]) assert.doesNotMatch(read(f), /k-narrow/, f);
});

test("a rule under a box shows after interaction; titles don't repeat their field; chips have an off state (R4-021)", () => {
  const form = read("components/kit/Form.tsx");
  assert.match(form, /rule\?: string/);
  assert.match(form, /const shown = hint \?\? \(rule && touched \? rule : undefined\)/);
  assert.match(read("pages/HoldingsPage.tsx"), /rule="More than 0"/);
  assert.match(read("pages/HoldingsPage.tsx"), /<Field wide label=\{add\.market === "IN" \? "NSE symbol or BSE code"/);
  const lending = read("pages/StockLendingPage.tsx");
  assert.doesNotMatch(lending, /CardHead title="Look up a stock"/);
  assert.match(lending, /Field label="Look up a stock"/);
  assert.match(read("pages/EtfGapsPage.tsx"), /placeholder="e\.g\. NIFTYBEES"/);
  const css = read("styles.css");
  assert.match(css, /\.k-chipset \.k-chip\[aria-pressed="true"\]::before \{ content: "✓"/);
  assert.match(css, /\.k-chipset \.k-chip\[aria-pressed="false"\] \{[^}]*border-style: dashed/);
  assert.match(read("pages/OptionsPage.tsx"), /<ChipBar wrap label="Underlying"/);
  assert.match(css, /\.k-chipbar:not\(\.wrap\) \{ flex-wrap: nowrap/);
  assert.match(read("pages/admin/admin.css"), /\.adm-menu \{ position: static; flex-direction: row; flex-wrap: wrap/);
});

test("the sidebar shows which edge has more behind it, and its scrollbar on hover (R4-016)", () => {
  assert.match(read("components/Shell.tsx"), /<nav ref=\{sideScroll\} className="side-groups" aria-label="Main" data-fade=\{fade\}>/);
  const css = read("styles.css");
  for (const edge of ["top", "bottom", "both"]) assert.match(css, new RegExp(`\\.side-groups\\[data-fade="${edge}"\\] \\{ -webkit-mask-image`));
  assert.match(css, /\.side-groups:hover[^{]*\{ scrollbar-color: var\(--dash\) transparent; \}/);
});

test("Settings words its test line from the boxes that are there (R4-020)", () => {
  const s = read("components/AlertSettings.tsx");
  assert.match(s, /ch\.telegram && "save a Telegram chat ID"/);
  assert.match(s, /ch\.email && "save an email address and confirm it"/);
  assert.match(s, /ch\.push && "turn on phone notifications"/);
  assert.match(s, /disabled=\{!!testWhy\} title=\{testWhy \?\? undefined\}/);
});
