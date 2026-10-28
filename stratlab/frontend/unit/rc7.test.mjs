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

test("RC7-002: the welcome question's four choices come before the optional level question, and on a phone before the intro too", () => {
  const src = read("src/components/LevelPrompt.tsx");
  const at = (s) => { const i = src.indexOf(s); assert.ok(i > 0, s); return i; };
  assert.ok(at('className="welcome-what"') < at('className="k-muted welcome-note"'));
  assert.ok(at('className="k-muted welcome-note"') < at('className="k-stack welcome-choices"'));
  assert.ok(at('className="k-stack welcome-choices"') < at('className="k-stack snug welcome-level"'));
  // the owner's words are all still in the file, unchanged
  for (const w of ["How much have you done? · optional", "We'll open the one you pick.", "The others stay one tap away, and you can change this any time in Settings.", "Every space side by side, starting on My space."]) assert.ok(src.includes(w), w);
  const css = read("src/styles.css");
  const phone = css.slice(css.indexOf("@media (max-width: 520px) {\n  .welcome-choices"));
  assert.match(phone, /\.welcome-choices \{ order: 1; \}\s*\.welcome-what \{ order: 2; \}\s*\.welcome-note \{ order: 3; \}\s*\.welcome-level \{ order: 4; \}/);
});

test("RC7-003: every page title draws the slot the plan-lock note goes into, and the note is portalled into it", () => {
  const head = read("src/components/kit/PageHeader.tsx");
  assert.match(head, /<div className="page-lock-slot" ref=\{/);
  assert.ok(head.indexOf("</header>") < head.indexOf('className="page-lock-slot"'), "the slot is after the title block");
  const lock = read("src/components/PageLock.tsx");
  assert.match(lock, /createPortal\(note, slot\)/);
  assert.match(lock, /useLockSlot\(\)/);
});

test("RC7-004: the screens write a market value as the company's page does, for India and the US", async () => {
  const { screenCap } = await import("../src/lib/researchFormat.ts");
  const { bigMoney, CRORE } = await import("../src/lib/format.ts");
  for (const cr of [1894550, 1103520, 92248, 53696]) assert.equal(screenCap(cr, "IN"), bigMoney(cr * CRORE, "INR"));      // the company page's header
  assert.equal(screenCap(1894550, "IN"), "₹18.95 lakh cr");
  assert.equal(screenCap(92248, "IN"), "₹92,248 cr");
  assert.equal(screenCap(2764692, "US"), bigMoney(2764692 * 1e6, "USD"));
  assert.equal(screenCap(2764692, "US"), "$2.76T");
});

test("RC7-005: a P/E, a dividend yield and an EBITDA margin are written the same on the company page, the screens, the deep dive and the public page", async () => {
  const { metricText, marginText } = await import("../src/lib/researchFormat.ts");
  assert.equal(metricText({ label: "P/E", value: 22.8, unit: "x" }, "INR"), "22.8");          // the screens, watchlist, deep dive and public page: one decimal
  assert.equal(metricText({ label: "P/E", value: 128.456, unit: "x" }, "INR"), "128.5");
  assert.equal(metricText({ label: "Fwd P/E", value: 26.4, unit: "x" }, "USD"), "26.4");
  assert.equal(metricText({ label: "P/B", value: 2.247, unit: "x" }, "INR"), "2.25");          // a book multiple keeps two (it sits near 1)
  assert.equal(metricText({ label: "Div yield", value: 0.71, unit: "%" }, "INR"), "0.71%");    // the screens and the public page: two decimals
  assert.equal(metricText({ label: "Div yield", value: 0, unit: "%" }, "INR"), "0.00%");
  assert.equal(metricText({ label: "EBITDA margin", value: 17, unit: "%" }, "INR"), "17%");     // whole when the source gives it whole, as the public page writes it
  assert.equal(metricText({ label: "EBITDA margin", value: 17.54, unit: "%" }, "INR"), "17.5%");
  assert.equal(marginText(null), "–");
  assert.equal(marginText(-3), "−3%");
  const screens = read("src/pages/Screens.tsx"), deep = read("src/pages/DeepDive.tsx");
  assert.match(screens, /\{ id: "opm", label: "EBITDA margin", cell: \(r\) => marginText\(r\.opm\) \}/);
  assert.match(deep, /cell: \(q: \(typeof n\.quarters\)\[number\]\) => marginText\(q\.opm\)/);
});
