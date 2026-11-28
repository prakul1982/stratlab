// Lane su1 (owner, 16 Nov): (1) sign-in by email beside Google, hidden until /config.js switches it on; (2) US dollar prices for US
// visitors on a visible "Prices in" switch, from the /pricing USD row, with the rupee charge said while checkout is in rupees.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const pc = await import("../src/lib/priceCurrency.ts");
const { configOn } = await import("../src/lib/flags.ts");
const { emailSignInProblem, emailLooksRight, codeDigits } = await import("../src/lib/signinError.ts");
const { emailLinkIn, withoutEmailLink } = await import("../src/lib/entry.ts");
const { planPriceLine } = await import("../src/lib/planPrice.ts");
const { aboutUsd } = await import("../src/lib/usdAbout.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

const USD = { symbol: "$", name: "US dollar", basic: 8, pro: 20, basic_year: 80, pro_year: 200, charged_in: "INR", yearly_charged_in: "INR" };
const USD_PLANS = { ...USD, charged_in: "USD", yearly_charged_in: "USD" };
const INR = { symbol: "₹", name: "Indian rupee", basic: 699, pro: 1999, basic_year: 6999, pro_year: 19999, charged_in: "INR", yearly_charged_in: "INR" };
const about = (v) => aboutUsd(v, 88);

test("config switches: only a clear 'on' turns a feature on", () => {
  for (const v of ["on", "ON", "true", "1", "yes", " on ", true]) assert.equal(configOn(v), true, String(v));
  for (const v of [undefined, null, "", "off", "false", "0", "no", false, 1, {}]) assert.equal(configOn(v), false, String(v));
});

test("the currency shown: the visitor's choice, else dollars for the US region and rupees elsewhere, said as automatic", () => {
  assert.deepEqual(pc.pickPriceCur(null, "US"), { cur: "USD", auto: true });
  assert.deepEqual(pc.pickPriceCur(null, "IN"), { cur: "INR", auto: true });
  assert.deepEqual(pc.pickPriceCur("INR", "US"), { cur: "INR", auto: false });       // a US visitor who chose rupees keeps rupees
  assert.deepEqual(pc.pickPriceCur("USD", "IN"), { cur: "USD", auto: false });
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  assert.equal(pc.savedPriceCur(store), null);
  pc.savePriceCur(store, "USD");
  assert.equal(mem.get("stratlab.price-currency"), "USD");
  assert.equal(pc.savedPriceCur(store), "USD");
  mem.set("stratlab.price-currency", "EUR");
  assert.equal(pc.savedPriceCur(store), null);                                          // anything else is no choice
  const broken = { getItem: () => { throw new Error("off"); }, setItem: () => { throw new Error("off"); } };
  assert.equal(pc.savedPriceCur(broken), null);
  pc.savePriceCur(broken, "INR");                                                      // storage off: no throw
  assert.match(pc.AUTO_USD_LINE, /American time zone\. Switch to ₹ any time\./);
});

test("the USD row is used only when every amount is there", () => {
  assert.deepEqual(pc.usdRowOf({ currencies: { USD, INR } }), USD);
  assert.equal(pc.usdRowOf(null), null);
  assert.equal(pc.usdRowOf({ currencies: { INR } }), null);
  assert.equal(pc.usdRowOf({ currencies: { USD: { ...USD, pro_year: 0 } } }), null);
  assert.equal(pc.usdRowOf({ currencies: { USD: { ...USD, basic: "8" } } }), null);
});

test("checkout charges dollars only when dollar checkout is on and the server has the USD plans for the period; else the rupee plan", () => {
  assert.equal(pc.checkoutCur("USD", USD_PLANS, "month", true), "USD");
  assert.equal(pc.checkoutCur("USD", USD_PLANS, "month", false), "INR");               // switched off in config.js: rupees
  assert.equal(pc.checkoutCur("USD", USD, "month", true), "INR");                      // no USD plans on the server: rupees
  assert.equal(pc.checkoutCur("USD", { ...USD_PLANS, yearly_charged_in: "INR" }, "year", true), "INR");
  assert.equal(pc.checkoutCur("USD", { ...USD_PLANS, yearly_charged_in: "INR" }, "month", true), "USD");
  assert.equal(pc.checkoutCur("INR", USD_PLANS, "month", true), "INR");
  assert.equal(pc.checkoutCur("USD", null, "month", true), "INR");
});

test("a card's price and its charge agree in every case", () => {
  // rupees: "₹699" with the US price beside it (updated on purpose, LIVE11B: beside a rupee price, StratLab's own US price when the table has one, not the rupees converted)
  assert.deepEqual(pc.cardPrice({ plan: "basic", period: "month", cur: "INR", inr: 699, usd: USD, checkoutOn: true, aboutUsd: about }),
    { shown: "₹699", about: "US price $8", charged: "₹699", chargedCur: "INR", usdShown: false });
  assert.equal(pc.cardPrice({ plan: "basic", period: "month", cur: "INR", inr: 699, usd: null, checkoutOn: true, aboutUsd: about }).about, "about $8");
  // dollars shown, checkout in rupees: "$8", with the rupee charge beside it, and the charge is the rupee amount
  assert.deepEqual(pc.cardPrice({ plan: "basic", period: "month", cur: "USD", inr: 699, usd: USD, checkoutOn: true, aboutUsd: about }),
    { shown: "$8", about: "Charged as ₹699 in rupees", charged: "₹699", chargedCur: "INR", usdShown: true });
  assert.deepEqual(pc.cardPrice({ plan: "pro", period: "year", cur: "USD", inr: 19999, usd: USD_PLANS, checkoutOn: false, aboutUsd: about }),
    { shown: "$200", about: "Charged as ₹19,999 in rupees", charged: "₹19,999", chargedCur: "INR", usdShown: true });
  // dollars charged: the dollar amount alone
  assert.deepEqual(pc.cardPrice({ plan: "pro", period: "month", cur: "USD", inr: 1999, usd: USD_PLANS, checkoutOn: true, aboutUsd: about }),
    { shown: "$20", about: null, charged: "$20", chargedCur: "USD", usdShown: true });
  // no USD row (the prices not read yet, or an old server): rupees, whatever was picked
  assert.equal(pc.cardPrice({ plan: "basic", period: "month", cur: "USD", inr: 699, usd: null, checkoutOn: true, aboutUsd: about }).shown, "₹699");
  // the card's charge is always what checkout asks for
  for (const usd of [USD, USD_PLANS]) for (const on of [true, false]) for (const period of ["month", "year"]) for (const cur of ["INR", "USD"]) {
    const c = pc.cardPrice({ plan: "basic", period, cur, inr: period === "year" ? 6999 : 699, usd, checkoutOn: on, aboutUsd: about });
    assert.equal(c.chargedCur, pc.checkoutCur(cur, usd, period, on), JSON.stringify({ usd: usd.charged_in, on, period, cur }));
  }
  assert.equal(pc.freePrice("USD", USD), "$0");
  assert.equal(pc.freePrice("USD", null), "₹0");
  assert.equal(pc.freePrice("INR", USD), "₹0");
  assert.equal(pc.dollarText(7.5), "$7.50");
  assert.match(pc.usdPricesNote(USD, "month", true), /shown for information: payment is in rupees for now/);
  assert.match(pc.usdPricesNote(USD_PLANS, "month", true), /charged in US dollars/);
});

test("a lock's price sentence follows the currency shown, with the rupee charge while checkout is in rupees", () => {
  const p = { offer: { mode: "paid", payments: true, yearly: true }, countries: { US: "USD" }, usd_inr: { rate: 88 }, currencies: { INR, USD } };
  assert.equal(planPriceLine("basic", p), "Basic is ₹699 a month (US price $8) or ₹6,999 a year (US price $80).");          // rupees, with the US price beside each (updated on purpose, LIVE11B: beside a rupee price, StratLab's own US price when the table has one, not the rupees converted)
  assert.equal(planPriceLine("basic", p, "USD", false), "Basic is $8 a month or $80 a year, charged as ₹699 or ₹6,999 in rupees.");
  assert.equal(planPriceLine("pro", { ...p, currencies: { INR, USD: USD_PLANS } }, "USD", true), "Pro is $20 a month or $200 a year.");
  assert.equal(planPriceLine("pro", { ...p, currencies: { INR, USD: USD_PLANS } }, "USD", false), "Pro is $20 a month or $200 a year, charged as ₹1,999 or ₹19,999 in rupees.");
  assert.equal(planPriceLine("pro", { ...p, currencies: { INR } }, "USD", true), "Pro is ₹1,999 a month (about $23) or ₹19,999 a year (about $227).");
});

test("the pages draw the switch, the card prices and the checkout from the same functions", () => {
  const plans = read("src/pages/PlansPage.tsx"), land = read("src/pages/Login.tsx");
  for (const src of [plans, land]) {
    assert.match(src, /const usd = usdRowOf\(pricing\), cur = usd \? pc\.cur : "INR", usdOn = usdCheckoutOn\(\);/);
    assert.match(src, /<CurrencySwitch cur=\{cur\} auto=\{pc\.auto\} onChange=\{pc\.choose\} \/>/);
    assert.match(src, /usdPricesNote\(usd, period, usdOn\)/);
  }
  assert.match(plans, /const currency = checkoutCur\(cur, usd, period, usdOn\);/);
  assert.match(plans, /body: \{ plan, period, currency, offer: offerFor\(plan, period\) \}/);     // (changed on purpose, price102)
  // the server answered in another currency than the page confirmed: no payment window
  assert.match(plans, /if \(d\.currency && d\.currency !== currency\) \{ notify\(/);
  assert.ok(plans.indexOf("d.currency !== currency") < plans.indexOf("await loadRazorpay()"));
  assert.match(read("src/lib/currency.ts"), /export const usdCheckoutOn = \(\): boolean => configOn\(CFG\.USD_CHECKOUT\);/);
});

test("email sign-in: the service's answers in plain words", () => {
  assert.match(emailSignInProblem({ status: 429, code: "over_email_send_rate_limit", message: "email rate limit exceeded" }, "send"), /^Too many sign-in emails/);
  assert.match(emailSignInProblem({ status: 429, message: "For security purposes, you can only request this after 42 seconds." }, "send"), /can be sent in 42 seconds/);
  assert.match(emailSignInProblem({ status: 403, code: "otp_expired", message: "Token has expired or is invalid" }, "verify"), /^That code didn't work/);
  assert.match(emailSignInProblem({ status: 400, code: "email_address_invalid", message: "Email address is invalid" }, "send"), /doesn't look right/);
  assert.match(emailSignInProblem({ status: 400, code: "email_provider_disabled", message: "Email logins are disabled" }, "send"), /isn't available right now\. Use Continue with Google/);
  assert.match(emailSignInProblem(new TypeError("Failed to fetch"), "send"), /Can't reach the sign-in service/);
  assert.match(emailSignInProblem({ status: 500, message: "boom" }, "send"), /^Couldn't send the sign-in email/);
  assert.match(emailSignInProblem(null, "verify"), /^Couldn't sign you in with that code/);
  for (const ok of ["a@b.co", "first.last+tag@example.com", " x@y.in "]) assert.equal(emailLooksRight(ok), true, ok);
  for (const bad of ["", "a@b", "a b@c.com", "@b.com", "a@@b.com", "a@b.c", `${"x".repeat(65)}@b.com`]) assert.equal(emailLooksRight(bad), false, bad);
  assert.equal(codeDigits(" 123 456 "), "123456");
  assert.equal(codeDigits("123-456"), "123456");
  assert.equal(codeDigits("12345678901234"), "1234567890");
});

test("the email's link signs in from any app: a hashed token of type email or magiclink, never signup", () => {
  assert.deepEqual(emailLinkIn("?token_hash=0123456789abcdef&type=email"), { token_hash: "0123456789abcdef", type: "email" });
  assert.deepEqual(emailLinkIn("?token_hash=0123456789abcdef&type=magiclink"), { token_hash: "0123456789abcdef", type: "magiclink" });
  assert.equal(emailLinkIn("?token_hash=0123456789abcdef&type=signup"), null);
  assert.equal(emailLinkIn("?token_hash=0123456789abcdef&type=recovery"), null);
  assert.equal(withoutEmailLink("https://x.test/?token_hash=0123456789abcdef&type=email"), "/");
});

test("email sign-in is drawn only while config.js switches it on, and ships switched off", () => {
  const signin = read("src/lib/signin.ts"), comp = read("src/components/EmailSignIn.tsx");
  assert.match(signin, /export const emailSignInOn = \(\): boolean => configOn\(CFG\.EMAIL_SIGNIN\);/);
  assert.match(comp, /if \(!emailSignInOn\(\)\) return null;/);
  // off: a "Sign in" button is Google's sign-in as before; on: the sign-in page with both ways in
  assert.match(signin, /if \(!emailSignInOn\(\)\) return signIn\(next\);[\s\S]{0,120}location\.assign\("\/login"\);/);
  assert.match(signin, /signInWithOtp\(\{ email, options: \{ emailRedirectTo: location\.origin \+ "\/", shouldCreateUser: true \} \}\)/);
  assert.match(signin, /verifyOtp\(\{ email, token, type: "email" \}\)/);
  // the sign-in page and the sign-in gate draw it under Continue with Google
  const land = read("src/pages/Login.tsx");
  // (updated on purpose, R61: the sign-in page's form knows whether the visitor came to sign up)
  // (updated on purpose, LIVE12B-008: the form sits in a slot that holds its place from the first frame)
  // (updated on purpose, LIVE16B-001: on the sign-in page the form's code is asked for at once and drawn straight away once here, so the
  // start-up frame's form is never swapped for an empty slot; the slot stays for when it is still on its way)
  // (updated on purpose, site80 LIVE17B-002: the form's code is kept in lib/emailForm, so a plan card's button asks for it before opening the page)
  assert.ok(land.indexOf("{login && emailSignInOn() && (EmailNow ? <EmailNow signup={signup} /> : <Suspense fallback={<i className=\"email-slot\" />}><EmailSignIn signup={signup} /></Suspense>)}") > land.indexOf("{cta()}"));
  const gate = read("src/pages/Gate.tsx");
  assert.ok(gate.indexOf("<EmailSignIn />") > gate.indexOf("<SignInButton />"));
  // a send can't be repeated for a minute (the sign-in service's own limit per address, and its hourly limit, still apply)
  assert.match(comp, /export const RESEND_WAIT = 60;/);
  assert.match(comp, /if \(busy \|\| wait > 0\) return;/);
  // (updated on purpose (owner, 17 Nov: the sign-in service's email templates and SMTP are set up, and the payment provider takes
  // international payments): the site ships with email sign-in and dollar checkout both on)
  const cfg = read("public/config.js");
  assert.match(cfg, /EMAIL_SIGNIN\s*:\s*"on"/);
  assert.match(cfg, /USD_CHECKOUT\s*:\s*"on"/);
});
