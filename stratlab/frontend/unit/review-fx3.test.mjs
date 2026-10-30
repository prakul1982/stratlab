// 26 Oct 2026 re-score, the rest of it (RC2B-027 .. RC2B-034): search without a typo's guess or a repeated row, the margin
// table's header, the ETF live row, named holders' US tab, the public addresses that draw their own part of the page, a tab
// that stays on one line, a rupee shortcut, and deleting your own account.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { match } = await import("../src/lib/features.ts");
const { gapAtLastTrade } = await import("../src/lib/etfGapMath.ts");
const { slimOf, isPlansPath, visitorView } = await import("../src/lib/deepLinks.ts");

test("RC2B-030: 'contact' is Contact us alone; a typo's guess is only for when nothing is found as typed", () => {
  const got = match("contact", 6).map((f) => f.title);
  assert.equal(got[0], "Contact us");
  assert.ok(!got.some((t) => /F&O changes/i.test(t)), got.join(", "));          // "contract" is one letter from "contact"
  assert.ok(match("setings", 5).some((f) => f.id === "settings"), "a typo still finds its page when nothing else does");
  assert.equal(match("zzzzqq", 5).length, 0);
});

test("RC2B-030: an intent's page is not listed again as a feature; a topic word puts the pages before a company named like it", () => {
  const pal = read("src/components/SearchPalette.tsx");
  assert.match(pal, /\.filter\(\(f\) => !\(intent\?\.to && resolve\(f\.to, loc\.pathname, null\) === intent\.to\)\)/);
  assert.match(pal, /const topicWord = words === 1 && feats\.length >= 2 && \(companies\[0\]\?\.match \?\? 9\) > 2;/);
  assert.match(pal, /!exactFeature && !intent && !topicWord\) first\("Companies"\)/);
  // "tax report" names one page at one address; the intent and the page of that name both point at /tax-report
  assert.equal(match("tax report", 6).filter((f) => f.to === "/tax-report").length, 1);
});

test("RC2B-027: a number column's (i) comes before its words, so the header ends where the figures do", () => {
  const t = read("src/components/kit/DataTable.tsx");
  assert.match(t, /\{c\.numeric && c\.info && info\(c\)\}/);
  assert.match(t, /\{!c\.numeric && c\.info && info\(c\)\}/);
  assert.ok(t.indexOf("c.numeric && c.info && info(c)") < t.indexOf('className="k-th-sort"'));
});

test("RC2B-029: the live row says what its price is against, and never changes the row's own gap", () => {
  const row = { symbol: "MONQ50", price: 213.66, nav: 118.3705, nav_date: "2026-10-23", nav_price_day: "2026-10-23", nav_gap: 86 };
  assert.equal(gapAtLastTrade(row, "2026-10-26"), 80.5);                           // the audit's 80.5% at ₹213.66
  assert.equal(gapAtLastTrade(row, "2026-10-23"), null);                            // the close's own day: the row's gap is it
  assert.equal(gapAtLastTrade({ ...row, nav_mismatch: true }, "2026-10-26"), null);
  assert.equal(gapAtLastTrade({ ...row, price: 400 }, "2026-10-26"), null);          // 3 or more times the NAV: another unit
  assert.equal(gapAtLastTrade({ ...row, nav_closed_day: true }, "2026-10-26"), null);
  assert.equal(gapAtLastTrade({ ...row, nav: null }, "2026-10-26"), null);
  assert.equal(gapAtLastTrade(row, null), null);
  const page = read("src/pages/EtfGapsPage.tsx");
  assert.match(page, /gapShort\(live\)\} the \{fmtDate\(r\.nav_date, \{ year: false \}\)\} NAV/);
  assert.match(page, /header: "Close vs NAV"/);                                      // the row's gap is still the close's
});

test("RC2B-032: /help, /faq, /about, /login and /pricing each draw their own part of the page", () => {
  assert.equal(slimOf("/help"), "faq");
  assert.equal(slimOf("/faq/"), "faq");
  assert.equal(slimOf("/about"), "about");
  assert.equal(slimOf("/login"), "login");
  assert.equal(slimOf("/signup"), "login");
  assert.equal(slimOf("/"), null);
  assert.equal(slimOf("/features"), null);                                          // the features address is the landing page at its Trade section
  assert.ok(isPlansPath("/plans") && isPlansPath("/pricing") && isPlansPath("/upgrade") && !isPlansPath("/"));
  assert.equal(visitorView("/pricing").kind, "landing");
  const login = read("src/pages/Login.tsx");
  assert.match(login, /\{\(full \|\| slim === "about"\) && <section className="lp-sec lp-spaces-sec"/);
  assert.match(login, /\{\(full \|\| slim === "faq"\) && <section id="faq"/);
  assert.match(login, /\{!slim && <Pricing/);
  assert.match(login, /\{full && <HeroDemo \/>\}/);
  assert.match(read("src/visitor/VisitorApp.tsx"), /slim=\{slimOf\(pathname\) \?\? undefined\}/);
});

test("RC2B-033: the example tabs stay on one line on a phone", () => {
  assert.match(read("src/styles.css"), /\.lp-demo-tabs button \{ flex: 1 1 auto; white-space: nowrap; padding: 0 10px; \}/);
});

test("RC2B-034, item 34: no visitor is shown another currency first, so there is nothing to switch back to rupees", () => {
  // changed on purpose by item 34 (owner, 29 Oct): the browser's country no longer picks dollars; every price is rupees with "about $"
  const cur = read("src/lib/currency.ts");
  assert.doesNotMatch(cur, /function country\(\)|offerRupees|pickCurrency/);
  assert.match(cur, /return \{ pricing: p, currency: "INR" as const, status, rate: usdRate\(p\) \};/);
  for (const f of ["src/pages/Login.tsx", "src/pages/PlansPage.tsx"]) assert.doesNotMatch(read(f), /In India\? Show prices in ₹|aria-label="Prices in"|label="Prices in"/, f);
});

test("DF-018: the US tab opens with the holder's name, then one company's filings", () => {
  const p = read("src/pages/HoldersPage.tsx");
  const holder = p.indexOf('<CardHead title="Search a holder" />', p.indexOf("function UsHolders"));
  const company = p.indexOf("Or one company's filings");
  assert.ok(holder > 0 && company > holder);
  assert.ok(p.indexOf('aria-label="Find a holder"') < p.indexOf('<Field label="Company" optional>'));
});

test("RC2B-031: Account has Delete my account, typed-email confirmed, and nothing says closing is done by request", () => {
  const a = read("src/pages/AccountPage.tsx");
  assert.match(a, /Delete my account…/);
  assert.match(a, /"\/me\/delete-account", \{ method: "POST", body: \{ confirm: typed \} \}/);
  assert.match(a, /confirmMatches\(typed, email\)/);
  assert.doesNotMatch(a, /done by us on request/);
  assert.match(a, /Invoices and the payment records behind them are kept, as tax law asks/);
  // the privacy page names the button the same way, with a new updated date
  const legal = read("src/content/legal.ts");
  assert.match(legal, /\\"Delete my account\\" to erase it and delete your sign-in account too/);
  assert.match(legal, /"\/privacy": "28 October 2026"/);
  assert.match(read("src/content/seo.ts"), /delete your data\.", index: true, updated: "2026-10-28"/);
  assert.match(read("../backend/app/site_pages.py"), /\("\/privacy", "2026-10-28"\)/);
});
