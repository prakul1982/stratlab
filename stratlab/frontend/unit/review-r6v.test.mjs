// Round 6 visitor review of the live site, the frontend's side: library pages with their own tags before any script,
// readable tested dates and no repeated universe, the same verdict words on card and page, a main landmark while a page
// loads, an admin address that promises nothing, Safari's phone overflow on the landing, the plan confirmation before
// the payment window, email links on the site's domain, and the error reporter left out of a visitor's page.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const seo = await import("../src/content/seo.ts");
const { libraryFiles } = await import("../scripts/seoPages.mjs");
const { testedRange, whereShown, CHECK_RESULT } = await import("../src/lib/libraryText.ts");
const links = await import("../src/lib/deepLinks.ts");
const { signedOutTitle } = await import("../src/lib/title.ts");

test("every StratLab library strategy gets its own HTML with its own title and address (R6V-012)", () => {
  const files = Object.fromEntries(libraryFiles(read("index.html")));
  assert.equal(Object.keys(files).length, seo.LIBRARY_SEEDS.length);
  const page = files["library/seed-supertrend-us/index.html"];
  assert.match(page, /<title>Supertrend flip · 20 US large caps: rules and verdict · StratLab<\/title>/);
  assert.match(page, /<link rel="canonical" href="https:\/\/stratlab\.studio\/library\/seed-supertrend-us">/);
  assert.match(page, /content="index, follow"/);
  assert.doesNotMatch(page, /<link rel="canonical" href="https:\/\/stratlab\.studio\/">/);
  for (const html of Object.values(files)) assert.doesNotMatch(html, /recommend|buy now|should buy/i);
  assert.match(read("scripts/seoPages.mjs"), /\[\.\.\.pageFiles\(template\), \.\.\.libraryFiles\(template\)\]/);
});

test("a library page says its dates as days and its universe once (R6V-004)", () => {
  assert.equal(testedRange({ from: "2021-10-11T00:00:00-04:00", to: "2026-10-06T00:00:00-04:00" }), "11 Oct 2021 to 6 Oct 2026");
  assert.equal(testedRange({ from: "2021-10-11T00:00:00+05:30", to: "2026-10-06T00:00:00+05:30" }), "11 Oct 2021 to 6 Oct 2026");
  assert.equal(testedRange(null), null);
  assert.equal(whereShown("Supertrend flip · 20 US large caps", "20 US large caps"), null);
  assert.equal(whereShown("Opening-range breakout", "25 most liquid F&O stocks"), "25 most liquid F&O stocks");
  const pub = read("src/pages/PublicLibrary.tsx");
  assert.match(pub, /Tested \$\{testedRange\(e\.range\)\}/);
  assert.doesNotMatch(pub, /Tested \$\{e\.range\.from\}/);
});

test("the page and the card use the server's words for the verdict, and show all four checks (R6V-005)", () => {
  const pub = read("src/pages/PublicLibrary.tsx");
  assert.match(pub, /e\.verdict\.fact_headline \?\? e\.verdict\.headline/);
  assert.match(pub, /e\.verdict\.fact_summary \?\? e\.verdict\.summary/);
  assert.match(pub, /<VerdictBadge v=\{e\.verdict\.verdict\} facts label=\{e\.verdict\.label\} \/>/);
  assert.match(read("src/pages/Login.tsx"), /e\.verdict\.fact_headline \?\? e\.verdict\.headline/);
  assert.deepEqual(Object.keys(CHECK_RESULT).sort(), ["fail", "not_passed", "pass", "skip", "warn"]);
  assert.equal(CHECK_RESULT.skip, "Not run");
});

test("a page still loading is a main landmark with a heading, and the boot error is too (R6V-013)", () => {
  // R8O-007: the spinner is Opening, which shows Loading and, after 15 s, the reload card (components/LoadGuard.tsx)
  assert.match(read("src/visitor/VisitorApp.tsx"), /<main id="main" tabIndex=\{-1\}><h1 className="sr-only">StratLab<\/h1><Opening/);
  assert.match(read("src/components/LoadGuard.tsx"), /if \(!slow\) return <Loading label=\{label\} \/>;/);
  const boot = read("public/boot.js");
  assert.match(boot, /createElement\("main"\)/);
  assert.match(boot, /root\.appendChild\(main\)/);
});

test("a visitor at an admin address is asked to sign in, with no promise of an admin page (R6V-013)", () => {
  assert.deepEqual(links.describePath("/admin"), { what: "StratLab", restricted: true });
  assert.equal(links.describePath("/admin/users").restricted, true);
  assert.equal(signedOutTitle("/admin"), "Sign in · StratLab");
  assert.match(read("src/pages/Gate.tsx"), /d\.restricted \? "Sign in to StratLab"/);
});

test("Safari's phone width: grid cells may shrink and a drawing never outgrows its card (R6V-006)", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.lp-checks > \*, \.lp-steps > \*, \.lp-tools > \*, \.lp-markets > \* \{ min-width: 0; \}/);
  assert.match(css, /\.lp-art \{ max-width: 100%; min-width: 0; overflow: hidden; \}/);
});

test("a purchase is confirmed with the plan, the period, GST and the renewal before the payment window (R6V-009)", () => {
  const plans = read("src/pages/PlansPage.tsx");
  assert.match(plans, /const ask = \(plan: "basic" \| "pro"\) => setSwitching\(plan\);/);
  assert.match(plans, /incl\. 18% GST/);
  assert.match(plans, /renews automatically/);
  assert.match(plans, /name: `StratLab · \$\{planName\(plan\)\}, \$\{period === "year" \? "yearly" : "monthly"\}`/);
  assert.match(plans, /Included in the \{planName\(paid as PlanId\)\} plan you were given/);
});

test("email links that the API answers go through the site's own domain (R6V-016)", () => {
  const vercel = JSON.parse(read("vercel.json"));
  const to = Object.fromEntries(vercel.rewrites.map((r) => [r.source, r.destination]));
  assert.match(to["/unsubscribe"], /^https:\/\/[^/]+\.railway\.app\/unsubscribe$/);
  assert.match(to["/email/confirm"], /^https:\/\/[^/]+\.railway\.app\/email\/confirm$/);
});

test("a visitor's page downloads the error reporter only when something breaks (R6V-018)", () => {
  assert.match(read("src/entry.tsx"), /startErrorReports\(\{ lazy: !account \}\)/);
  const s = read("src/lib/sentry.ts");
  assert.match(s, /addEventListener\("error", onError\)/);
  assert.match(s, /addEventListener\("unhandledrejection", onRejection\)/);
});
