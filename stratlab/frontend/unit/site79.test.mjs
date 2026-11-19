import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// a .ts file's extensionless imports, as the build resolves them (as unit/fix16.test.mjs)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

// site79 (Release 79): unit checks of the fixes the browser specs (e2e/site79.spec.ts) prove on the pages.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE16B-001: /login and /signup's own HTML draws both ways in, with true words, and the script that keeps an early press", async () => {
  const { pageFiles } = await import("../scripts/seoPages.mjs");
  const files = Object.fromEntries(pageFiles(read("index.html")));
  for (const [file, heading, verb] of [["login/index.html", "Sign in to StratLab", "Sign in"], ["signup/index.html", "Sign up for StratLab", "Sign up"]]) {
    const html = files[file];
    assert.doesNotMatch(html, /signs in with your Google account/);
    assert.match(html, new RegExp(`<h1 class="serif lp-h1 lp-own-h1">${heading}</h1>`));
    assert.match(html, new RegExp(`<p class="serif lp-lede">${verb} with your Google account<span data-boot-or> or your email address</span>: no password to set up\\.</p>`));
    assert.match(html, /<button type="button" class="btn lp-cta" data-boot-google><svg[^]*?<\/svg>Continue with Google<\/button>/);
    assert.match(html, new RegExp(`<label for="boot-email" class="email-signin-label">${verb} with email</label>`));
    assert.match(html, /<button type="submit" class="btn outline">Email me a code<\/button>/);
    assert.match(html, /<script src="\/signin-early\.js" async><\/script>\n<\/body>/);
    // the classes the app draws on the same page, so nothing moves when it takes over
    assert.match(html, /class="lp-wrap lp-hero-grid lp-hero-solo lp-hero-login"/);
    assert.match(html, /<header class="lp-nav" data-boot-head>/);
  }
  // the home page has no such script; its download is unchanged
  assert.doesNotMatch(files["index.html"], /<script src="\/signin-early\.js"/);
  const seo = read("src/content/seo.ts");
  assert.doesNotMatch(seo, /signs in with your Google account/);
  assert.match(seo, /Sign in to StratLab with your Google account or your email address: no password to set up\./);
});

test("LIVE16B-001: the early script keeps a press and the address, and takes the email way out when it is switched off", () => {
  const js = read("public/signin-early.js");
  assert.match(js, /if \(!on\) d\.documentElement\.setAttribute\("data-email-off", "1"\);/);
  assert.match(js, /e\.way = "google";/);
  assert.match(js, /e\.way = "email";/);
  const css = read("index.html");
  assert.match(css, /html\[data-email-off\] \.boot-login \[data-boot-email\], html\[data-email-off\] \.boot-login \[data-boot-or\] \{ display: none; \}/);
  // the app does the press once it draws
  assert.match(read("src/pages/Login.tsx"), /if \(e\.way === "google"\) \{ e\.way = undefined; go\(\); \}/);
  assert.match(read("src/components/EmailSignIn.tsx"), /if \(e\.way === "email" && emailSignInOn\(\)\) \{ e\.way = undefined; void send\(e\.email \?\? ""\); \}/);
});

test("LIVE16B-001: a plan card's email button carries its plan to the sign-in page and on to /plans", async () => {
  const src = read("src/lib/signin.ts");
  assert.match(src, /return plan \? `\/login\?plan=\$\{plan\}#email` : EMAIL_SIGNIN_PATH;/);
  const way = read("src/components/EmailWay.tsx");
  assert.match(way, /href=\{emailSignInPath\(next\)\}/);
  assert.match(way, /startEmailSignIn\(next, \(u\) => navigate\(u\)\)/);
  assert.match(read("src/pages/Login.tsx"), /if \(plan === "basic" \|\| plan === "pro"\) rememberNext\(`\/plans\?plan=\$\{plan\}`\);/);
  assert.match(read("src/pages/PlansPage.tsx"), /data-testid="plan-picked"/);
});

test("LIVE16B-003: Trade home's next F&O expiry is never one that ended earlier today", async () => {
  const { nextExpiry } = await import("../src/lib/expiry.ts");
  const ev = [{ kind: "expiry", date: "2026-11-19", time: "15:30", title: "SENSEX weekly expiry" },
    { kind: "expiry", date: "2026-11-23", time: "15:30", title: "Monthly F&O expiry" }];
  assert.equal(nextExpiry(ev, "2026-11-19", "14:10")?.title, "SENSEX weekly expiry");
  assert.equal(nextExpiry(ev, "2026-11-19", "19:53")?.title, "Monthly F&O expiry");
  assert.equal(nextExpiry(ev, "2026-11-19")?.title, "SENSEX weekly expiry");          // no clock given: as before
  assert.match(read("src/pages/SpaceHomes.tsx"), /nextExpiry\(ev\?\.events, today, istHm\(\)\)/);
});

test("LIVE16A-014: Mood's breadth count on a phone keeps its day beside the main figure", () => {
  assert.match(read("src/pages/PulseMood.tsx"), /numeric: true, brief: true, briefLabel: true, cell: \(r\) => \(r\.now == null/);
  assert.match(read("src/components/kit/DataTable.tsx"), /c\.brief && c\.briefLabel && "k-brief-label"/);
  assert.match(read("src/styles.css"), /\.k-tbl-wrap\.stack\.compact \.k-table td\.k-brief\.k-brief-label::before \{ display: inline; margin-right: 4px; \}/);
});

test("LIVE15B-012 / LIVE16B: the signed-in plans page holds the 'Prices in' switch's place while the prices load", () => {
  const src = read("src/pages/PlansPage.tsx");
  assert.match(src, /\(\(billing && yearlyOk\) \|\| usd \|\| pricingStatus === "loading"\) && \(/);
  assert.match(src, /\{\(usd \|\| pricingStatus === "loading"\) && <FieldGroup label="Prices in"><CurrencySwitch/);
});
