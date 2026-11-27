// Lane conv101 (owner, 27 Nov: "I need to make money now"; the funnel report: 0 paying users, SEO pages untracked, nothing to try without an
// account, no moment that asks a free user to pay). The browser's side: who is left out of analytics, the proxy, the hero's proof, the
// upgrade prompt, the trust and cancel lines. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

/** A browser for the gate: navigator, window, localStorage and document, each test its own. */
function browser({ ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36", webdriver = false, dnt, gpc, brands } = {}) {
  const store = new Map();
  globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { userAgent: ua, webdriver, doNotTrack: dnt, globalPrivacyControl: gpc, userAgentData: brands ? { brands } : undefined } });
  globalThis.window = globalThis.window ?? globalThis;
  const added = [];
  globalThis.document = { body: { appendChild: (n) => added.push(n) }, createElement: () => ({ setAttribute() {}, style: {}, remove() {} }) };
  return { store, added };
}

const gate = await import("../src/lib/analyticsGate.ts");

test("T2: a person's browser is counted; Do Not Track, Global Privacy Control, robots and StratLab's own devices are not", () => {
  browser();
  assert.equal(gate.analyticsOff(), false);
  browser({ dnt: "1" });
  assert.equal(gate.analyticsOff(), true);
  browser({ gpc: true });
  assert.equal(gate.analyticsOff(), true);
  browser({ webdriver: true });
  assert.equal(gate.analyticsOff(), true, "navigator.webdriver: a test run");
  for (const ua of ["Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/141.0 Safari/537.36",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Mozilla/5.0 (compatible; AhrefsBot/7.0)",
    "Mozilla/5.0 (Linux; Android 11; moto g power) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36 Chrome-Lighthouse"]) {
    browser({ ua });
    assert.equal(gate.analyticsOff(), true, ua);
  }
  browser({ brands: [{ brand: "HeadlessChrome" }, { brand: "Chromium" }] });
  assert.equal(gate.analyticsOff(), true, "client hints naming HeadlessChrome");
  browser({ ua: "Mozilla/5.0 (Linux; Android 10; Cubot P40 Build/QP1A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Mobile Safari/537.36" });
  assert.equal(gate.analyticsOff(), false, "a phone whose maker's name ends in -bot is a person");
});

test("T2: ?internal=1 marks this device for good (one localStorage entry) and says so; ?internal=0 undoes it", () => {
  const b = browser();
  globalThis.window.setTimeout = () => 0;
  assert.equal(gate.readInternalSwitch("?internal=1"), "on");
  assert.equal(b.store.get(gate.INTERNAL_KEY), "1");
  assert.equal(b.added.length, 1, "a note on the page");
  assert.equal(gate.analyticsOff(), true);
  assert.equal(gate.readInternalSwitch("?internal=0"), "off");
  assert.equal(b.store.has(gate.INTERNAL_KEY), false);
  assert.equal(gate.analyticsOff(), false);
  assert.equal(gate.readInternalSwitch("?x=1"), null);
});

test("T2: an account the server marks as StratLab's own is left out, and marks the device; the client names no address", () => {
  const b = browser();
  gate.setAccountInternal(true);
  assert.equal(gate.analyticsOff(), true);
  assert.equal(b.store.get(gate.INTERNAL_KEY), "1");
  gate.setAccountInternal(false);
  gate.markInternal(false);
  for (const f of ["src/lib/analyticsGate.ts", "src/lib/analytics.ts", "src/lib/app.tsx"]) assert.doesNotMatch(read(f), /@(stratlab|gmail|example)\.|ADMIN_EMAILS/, f);
  assert.match(read("src/lib/app.tsx"), /internal: me\.internal === true/);
  assert.match(read("src/lib/analytics.ts"), /if \(o\.internal\) \{ setAccountInternal\(true\); return; \}/);
});

test("T1: ?from= on a link from a page the server draws is kept for the sign-up, one plain word only, 30 days", () => {
  browser();
  gate.rememberFrom("?market=IN&symbol=RELIANCE&from=stock");
  assert.equal(gate.signupFrom(), "stock");
  gate.rememberFrom("?from=<script>");
  assert.equal(gate.signupFrom(), "stock", "a word that isn't plain is ignored");
  localStorage.setItem("stratlab.from", JSON.stringify({ v: "theme", at: Date.now() - 31 * 86_400_000 }));
  assert.equal(gate.signupFrom(), null, "older than 30 days");
});

test("T3: a browser left out of analytics tells the server (X-Analytics: off), and the sign-up and checkout steps go to the server", () => {
  assert.match(read("src/lib/api.ts"), /\.\.\.\(analyticsOff\(\) \? \{ "X-Analytics": "off" \} : \{\}\)/);
  const app = read("src/lib/app.tsx");
  assert.match(app, /api<\{ first: boolean \}>\("\/analytics\/signup", \{ method: "POST", body: \{ from \} \}\)/);
  const plans = read("src/pages/PlansPage.tsx");
  assert.match(plans, /"\/billing\/checkout-event"/);
  assert.match(plans, /ondismiss: \(\) => \{ told\("dismissed"\)/);
  assert.match(plans, /told\("failed"\)/);
  assert.doesNotMatch(plans, /track\("checkout started"/, "checkout started is the server's now, so it isn't counted twice");
});

test("T4: PostHog goes through the site's own /ingest on Vercel and on the Railway web server, and config.js uses it", () => {
  const vercel = JSON.parse(read("vercel.json"));
  const r = Object.fromEntries(vercel.rewrites.map((x) => [x.source, x.destination]));
  assert.equal(r["/ingest/:path*"], "https://us.i.posthog.com/:path*");
  assert.equal(r["/ingest/static/:path*"], "https://us-assets.i.posthog.com/static/:path*");
  const order = vercel.rewrites.map((x) => x.source);
  assert.ok(order.indexOf("/ingest/static/:path*") < order.indexOf("/ingest/:path*"), "the static files' rule first");
  const caddy = read("Caddyfile");
  assert.match(caddy, /handle_path \/ingest\/\* \{\n\t\treverse_proxy https:\/\/us\.i\.posthog\.com/);
  assert.match(caddy, /handle_path \/ingest\/static\/\* \{/);
  assert.match(read("public/config.js"), /POSTHOG_HOST: "\/ingest"/);
  // the CSP needs nothing new for it: the site's own address is 'self'
  const csp = vercel.headers[0].headers.find((h) => h.key === "Content-Security-Policy").value;
  assert.match(csp, /connect-src 'self'/);
  // and the sample deck has a stable address on the site
  assert.equal(r["/sample-deck"], "https://stratlab-production-ca25.up.railway.app/sample-deck");
  assert.equal(r["/sample-deck.pdf"], "https://stratlab-production-ca25.up.railway.app/sample-deck.pdf");
  assert.equal(r["/pricing/sample-deck"], "https://stratlab-production-ca25.up.railway.app/pricing/sample-deck");
});

test("T1: the pages the server draws use the same rules as the app (the beacon's words for robots and the mark are the gate's)", () => {
  const pv = read("../backend/app/pv.js");
  assert.ok(pv.includes(gate.AUTOMATED_UA.source), "the same robot words");
  assert.ok(pv.includes(`"${gate.INTERNAL_KEY}"`), "the same mark");
  assert.match(pv, /n\.doNotTrack/);
  assert.match(pv, /globalPrivacyControl === true/);
  assert.match(pv, /n\.webdriver === true/);
  assert.match(pv, /fetch\("\/ingest\/i\/v0\/e\/"/);
  assert.match(pv, /location\.origin \+ location\.pathname/, "the address without its query or hash");
  assert.match(pv, /"ph_" \+ key \+ "_posthog"/, "the app's own anonymous ID, so a visit into the app is one visitor");
});

const { heroExample } = await import("../src/lib/landingExamples.ts");
const entry = (id, market, passed, total, ret, unseen, verdict = "edge") => ({ id, name: id, market, instrument: null, group: { name: "g" }, verdict: { verdict, passed, total }, stats: { ret, unseen } });

test("P4: the hero's no-sign-in proof opens one verdict that held up, by rule: all checks passed, money made after costs and on unseen years", () => {
  const rows = [entry("in-lost", "IN", 1, 3, -7, -15, "no_edge"), entry("in-thin", "IN", 3, 3, 46, 0.3), entry("us-a", "US", 3, 3, 49, 11.8),
    entry("us-b", "US", 3, 3, 34, 15.9), entry("coin-luck", "CRYPTO", 1, 3, 53, -4.5, "luck"), entry("us-2of3", "US", 2, 3, 73, 3)];
  assert.equal(heroExample(rows)?.id, "us-b", "India's passing one made under a point on unseen years; of the US ones, the most on unseen years");
  assert.equal(heroExample([entry("x", "IN", 1, 3, 5, 2, "luck")]), null, "none qualifies: the button opens the library");
  const login = read("src/pages/Login.tsx");
  assert.match(login, /See a verdict that held up, no sign-in/);
  assert.doesNotMatch(login, /See real results, no sign-in/);
  // the start-up frame says the same words, so nothing changes when the app draws
  assert.match(read("scripts/seoPages.mjs"), /HERO_PROOF = "See a verdict that held up, no sign-in"/);
});

const nudge = await import("../src/lib/upgradeNudge.ts");

test("P8: a Free account that has used 3 of its 5 backtests (or AI builds) this month is told once, with what Basic gives", () => {
  const seen = new Set();
  const base = { plan: "free", basic: { backtests: 100, ai: 100 }, seen: (k) => seen.has(k) };
  assert.equal(nudge.nudgeFor({ ...base, usage: { backtests_used: 2, backtests_limit: 5 } }), null, "2 of 5: not yet");
  const n = nudge.nudgeFor({ ...base, usage: { backtests_used: 3, backtests_limit: 5 } });
  assert.equal(n.kind, "backtests");
  assert.equal(n.text, "You've used 3 of your 5 free backtests this month (2 left). Basic gives 100 a month.");
  seen.add(n.key);
  assert.equal(nudge.nudgeFor({ ...base, usage: { backtests_used: 4, backtests_limit: 5 } }), null, "once a month");
  assert.equal(nudge.nudgeFor({ ...base, usage: { backtests_used: 5, backtests_limit: 5 } }), null, "at the limit the plan's own lock speaks");
  assert.equal(nudge.nudgeFor({ ...base, usage: { backtests_used: 3, backtests_limit: 5, ai_used: 3, ai_limit: 5 } })?.kind, "ai");
  assert.equal(nudge.nudgeFor({ ...base, plan: "pro", usage: { backtests_used: 3, backtests_limit: 5 } }), null, "the launch offer: nothing to sell");
  assert.equal(nudge.nudgeFor({ ...base, viewAs: "free", usage: { backtests_used: 3, backtests_limit: 5 } }), null, "the owner viewing as Free");
  assert.ok(n.key.endsWith(nudge.istMonth()));
});

test("P6, P7: the trust line is the Terms' own words; plan buttons name the plan and say cancel and refund terms the Refunds page gives", async () => {
  const { TRUST_LINE, CANCEL_NOTE } = await import("../src/content/trust.ts");
  assert.match(read("src/content/legal.ts"), /is not a SEBI-registered investment adviser or research analyst/);
  assert.match(TRUST_LINE, /not a SEBI-registered investment adviser or research analyst/);
  const legal = read("src/content/legal.ts");
  assert.match(legal, /Cancel any time from/);
  assert.match(legal, /Ask within 7 days of any payment, monthly or yearly, and we refund it in full/);
  assert.equal(CANCEL_NOTE, "Cancel any time · full refund if you ask within 7 days");
  const offer = await import("../src/lib/offer.ts");
  assert.deepEqual(offer.landingAction(null, "basic"), { label: "Continue with Google to get Basic", buy: true });
  assert.deepEqual(offer.landingAction(null, "pro"), { label: "Continue with Google to get Pro", buy: true });
  const login = read("src/pages/Login.tsx");
  assert.match(login, /data-testid="trust-line"/);
  assert.match(login, /data-testid=\{`cancel-note-\$\{p\}`\}/);
  assert.match(read("src/pages/PlansPage.tsx"), /data-testid=\{`cancel-note-\$\{p\}`\}/);
});

test("P9: the home page's title and description say what StratLab is, in the owner's one title pattern", async () => {
  const { HOME_TITLE, HOME_DESCRIPTION } = await import("../src/content/seo.ts");
  assert.equal(HOME_TITLE, "Backtest trading ideas on Indian and US stocks · StratLab");
  assert.ok(HOME_DESCRIPTION.length >= 120 && HOME_DESCRIPTION.length <= 160, `${HOME_DESCRIPTION.length}`);
  assert.match(HOME_DESCRIPTION, /plain words/);
  const html = read("index.html");
  assert.ok(html.includes(`<title>${HOME_TITLE}</title>`));
  assert.ok(html.includes(`content="${HOME_DESCRIPTION}"`));
});

test("P10: a visitor who isn't signed in gets no section menu and no way to close an open section", () => {
  const sec = read("src/components/kit/Section.tsx");
  assert.match(sec, /const guest = useUser\(\) === "guest";\n  if \(guest && \(!fold \|\| frame\.open\)\) return null;/);
  assert.match(sec, /\{!guest && <SectionMenu frame=\{frame\} \/>\}/);
});

test("P1: the guest tool loads only when opened, on the landing page and on /new", () => {
  const login = read("src/pages/Login.tsx");
  assert.match(login, /const GuestTry = lazy\(\(\) => importWithRetry\(\(\) => import\("\.\.\/components\/GuestTry"\)\)/);
  assert.match(login, /\{open \? <Suspense/);
  assert.doesNotMatch(login, /import \{ GuestTry \}/);
  assert.match(read("src/pages/Gate.tsx"), /const GuestTry = lazy\(\(\) => import\("\.\.\/components\/GuestTry"\)/);
  const tool = read("src/components/GuestTry.tsx");
  assert.match(tool, /publicPost<Result>\("\/public\/try"/);
  assert.doesNotMatch(tool, /\b(buy now|sell now|recommend)/i);
});
