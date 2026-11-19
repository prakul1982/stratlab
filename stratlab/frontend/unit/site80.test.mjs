import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// a .ts file's extensionless imports, as the build resolves them (as unit/site79.test.mjs)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

// site80 (Release 80): unit checks of the fixes the browser specs (e2e/site80.spec.ts) prove on the pages.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE17B-001: the sign-in frame's script is read from the head, first and at high priority, and runs before the app's module", async () => {
  const { pageFiles } = await import("../scripts/seoPages.mjs");
  const files = Object.fromEntries(pageFiles(read("index.html")));
  for (const file of ["login/index.html", "signup/index.html"]) {
    const html = files[file];
    const early = html.indexOf('<script src="/signin-early.js" defer fetchpriority="high"></script>');
    assert.ok(early > 0 && early < html.indexOf("</head>"), "in the head");
    assert.ok(early < html.indexOf('<script type="module"'), "before the app's module, so it runs first (both deferred, in order)");
    assert.equal(html.match(/src="\/signin-early\.js"/g).length, 1);
    assert.doesNotMatch(html, /signin-early\.js" async/);
  }
  assert.doesNotMatch(files["index.html"], /src="\/signin-early\.js"/);       // the landing's download is unchanged
  // while the script is on its way the buttons look as they will, with a working cursor, never the grey of a button that can't be pressed
  const css = read("src/styles.css");
  assert.match(css, /\.boot-login \[data-boot-google\]:disabled, \.boot-login \[data-boot-email\] \.btn:disabled \{ opacity: 1; cursor: progress; \}/);
  assert.match(css, /\.boot-login\.boot-login \.btn\.lp-cta\[data-boot-google\]:disabled \{ background: var\(--ink\); border: 1px solid var\(--ink\); color: var\(--on-ink\); \}/);
});

test("LIVE17B-002: a plan card's email button has the form's code before it opens the sign-in page, which lands at the form", () => {
  const way = read("src/components/EmailWay.tsx");
  assert.match(way, /onPointerEnter=\{warm\} onFocus=\{warm\} onTouchStart=\{warm\}/);
  assert.match(way, /emailFormWithin\(EMAIL_FORM_WAIT_MS\)\.then\(\(\) => startEmailSignIn\(next, \(u\) => navigate\(u\)\)\)/);
  assert.match(read("src/pages/Login.tsx"), /const EmailNow = emailFormNow\(\)\?\.EmailSignIn;/);
  // at its box before the first paint, not after (a phone showed /plans' footer, then jumped)
  assert.match(read("src/components/EmailSignIn.tsx"), /useLayoutEffect\(\(\) => \{\n    if \(location\.hash !== "#email" \|\| !box\.current\) return;\n    box\.current\.scrollIntoView\(\{ block: "center", behavior: "instant" \}\);/);
  assert.match(read("src/pages/Login.tsx"), /\}, \[login\]\);/);
});

test("LIVE17B-002: the email form's code is asked for once and a wait for it is capped", async () => {
  const src = read("src/lib/emailForm.ts");
  assert.match(src, /if \(!asked\) \{/);
  assert.match(src, /Promise\.race\(\[loadEmailForm\(\)\.catch\(\(\) => undefined\), new Promise\(\(ok\) => setTimeout\(ok, ms\)\)\]\)/);
});

test("LIVE17A-001: prices found off the day's settled closes are never called closes", async () => {
  const { dayLine } = await import("../src/lib/heatmap.ts");
  const day = (d) => d;
  const settled = dayLine({ as_of: "2026-11-18" }, true, "lists", day, "ET");
  assert.equal(settled.lead, "Closes of ");
  const off = dayLine({ as_of: "2026-11-18", unsettled: true }, true, "lists", day, "ET");
  assert.equal(off.lead, "Prices read during the session of ");
  assert.equal(off.day, "2026-11-18");
  assert.match(off.tail, /the day's closes are being read again/);
  assert.equal(off.price, "Last price");
  assert.doesNotMatch(off.source, /closes/);
});

test("LIVE17B-003: a company page asks for its chart's candles with its first call", () => {
  const lazy = read("src/charts/price/lazy.tsx");
  // the year of daily candles PriceChart opens on (1Y, daily), through the same kept read the chart's own first load finds
  assert.match(lazy, /companyLoader\(region, symbol\)\("1d", \{ range: "1y" \}\)/);
  assert.match(read("src/charts/price/PriceChart.tsx"), /props\.range === undefined \? "1Y"/);
  assert.match(read("src/pages/Research.tsx"), /prefetchCompanyChart\(region, sym\);\n    \/\/ the price, header/);
});

test("LIVE16B-005: the analytics question waits for the page's calls to be back before it is drawn", () => {
  const src = read("src/components/Tracking.tsx");
  assert.match(src, /if \(callsInFlight\(\) > 0\) return;/);
  assert.match(src, /cap = window\.setTimeout\(done, ASK_MAX_WAIT_MS\);/);
  assert.match(src, /export const ASK_QUIET_MS = 600;/);
});

test("LIVE17B-006: with scripts off the sign-in page says its sentence once", async () => {
  const { pageFiles } = await import("../scripts/seoPages.mjs");
  const files = Object.fromEntries(pageFiles(read("index.html")));
  for (const file of ["login/index.html", "signup/index.html"]) {
    const html = files[file];
    const body = html.slice(html.indexOf("<body>"));
    assert.equal((body.match(/with your Google account/g) ?? []).length, 1, file);
    assert.doesNotMatch(body, /<p class="boot-text">/);
  }
});

test("LIVE17B-004: the tax report on a phone: one width of controls, the year unbroken, one figure as a line", () => {
  const src = read("src/pages/TaxReportPage.tsx"), css = read("src/styles.css");
  assert.match(src, /\{ value: "replace", label: "Start again with this file", short: "Start again" \}/);
  assert.equal((src.match(/className="tax-controls"/g) ?? []).length, 2);
  assert.match(src, /<CardHead title=\{<>Total tax estimate, <span className="nowrap">\{y\.label\}<\/span><\/>\}/);
  assert.match(src, /if \(phone && one\) return \(/);
  assert.match(src, /<Card compact label="The year's tax" className="tax-head-hold">/);      // the placeholder's height: nothing moves
  assert.match(css, /\.tax-controls > \.k-card-head > \.k-card-actions > \.k-seg, .*\.tax-controls \.k-row > \.k-upload \{ width: 100%; box-sizing: border-box; \}/s);
});

test("LIVE17A-010 / LIVE17B-007 / LIVE17B-005: Movers' settings, Positioning's shares and switches, Money's card titles on a phone", () => {
  assert.match(read("src/pages/movers.css"), /\.mv-controls > \.k-field \{ flex: 1 1 100%; \}/);
  const css = read("src/styles.css");
  assert.match(css, /\.pos-split \{ display: flex; flex-wrap: wrap; row-gap: 4px; max-width: 100%; \}/);
  assert.match(css, /#pos-part > \.k-card-head > \.k-card-actions > \.k-seg, #pos-part > \.k-card-head > \.k-card-actions > \.btn \{ width: 100%;/);
  assert.match(css, /\.space-home \.k-card-head:has\(> \.k-card-actions > a\.link\[data-money\]:only-child\) > \.k-card-actions \{ order: 3; flex: 1 1 100%; height: auto; \}/);
  assert.match(css, /\.lp-skel-amount\.lp-skel-amount-one \{ height: calc\(44px \* 1\.05\); \}/);
});
