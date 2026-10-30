// Item 34 (owner, 29 Oct): every price reads rupees first, the currency Razorpay charges, with the dollar figure beside it,
// "₹699 a month (about $8)", signed out or in, whatever the browser's locale; the dollar from the app's USD/INR rate, rounded,
// with a safe fixed rate when none is read. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { USD_INR_FALLBACK, aboutUsd, inrWithUsd, usdNote, usdRate } = await import("../src/lib/usdAbout.ts");
const { planPriceLine } = await import("../src/lib/planPrice.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

const INR = { symbol: "₹", name: "Indian rupee", basic: 699, pro: 1999, basic_year: 6999, pro_year: 19999, charged_in: "INR", yearly_charged_in: "INR" };
const paid = { mode: "paid", payments: true, yearly: true };

test("the dollar figure: whole dollars at the app's rate, always 'about', the fixed rate when none is read", () => {
  assert.equal(usdRate({ usd_inr: { rate: 95.21 } }), 95.21);
  for (const p of [null, undefined, {}, { usd_inr: null }, { usd_inr: { rate: 0 } }, { usd_inr: { rate: 9000 } }]) assert.equal(usdRate(p), USD_INR_FALLBACK);
  assert.equal(aboutUsd(699, 88), "about $8");
  assert.equal(aboutUsd(699, 95.21), "about $7");
  assert.equal(aboutUsd(19999, 88), "about $227");
  assert.equal(aboutUsd(50, 95), "about $1");                                  // a paid amount is never "about $0"
  assert.equal(inrWithUsd(699, 88, "month"), "₹699 a month (about $8)");     // the owner's own example
  assert.equal(inrWithUsd(6999, 95.21, "year"), "₹6,999 a year (about $74)");
  assert.equal(inrWithUsd(0, 88), "₹0");                                       // Free: no dollar figure
  assert.match(usdNote(95.21), /charged in rupees.*at ₹95\.21 to the dollar \(today's rate\)/);
  assert.match(usdNote(88, true), /at about ₹88 to the dollar;/);
});

test("a lock's price sentence is rupees first with the dollar beside each amount, whatever currencies the table has", () => {
  const p = { offer: paid, countries: { US: "USD" }, usd_inr: { rate: 88 }, currencies: { INR,
    USD: { symbol: "$", name: "US dollar", basic: 8, pro: 20, basic_year: 80, pro_year: 200, charged_in: "USD", yearly_charged_in: "USD" } } };
  assert.equal(planPriceLine("basic", p), "Basic is ₹699 a month (about $8) or ₹6,999 a year (about $80).");
  assert.equal(planPriceLine("pro", p), "Pro is ₹1,999 a month (about $23) or ₹19,999 a year (about $227).");
  assert.equal(planPriceLine("pro", { ...p, offer: { ...paid, yearly: false } }), "Pro is ₹1,999 a month (about $23).");
  // never dollars alone: a currency of its own in the table changes nothing
  assert.doesNotMatch(planPriceLine("basic", p), /^Basic is \$/);
});

test("no browser locale or saved choice picks the currency; checkout asks for the rupee plan as before", () => {
  const cur = read("src/lib/currency.ts");
  assert.doesNotMatch(cur, /resolvedOptions\(\)\.timeZone|navigator\.languages/);
  assert.match(cur, /try \{ localStorage\.removeItem\(KEY\); \} catch/);
  const plans = read("src/pages/PlansPage.tsx"), land = read("src/pages/Login.tsx");
  assert.match(plans, /body: \{ plan, period, currency: "INR" \}/);
  assert.match(plans, /\{price\.about && <span className="k-note" data-testid=\{`about-\$\{p\}`\}>\{price\.about\}<\/span>\}/);
  assert.match(plans, /<p className="k-small k-muted k-measure" data-testid="usd-note">\{usdNote\(rate, pricing\?\.usd_inr\?\.fallback\)\}<\/p>/);
  assert.match(land, /\{about && <span className="small muted" data-testid=\{`about-\$\{p\}`\}>\{about\}<\/span>\}/);
  for (const src of [plans, land]) assert.doesNotMatch(src, /aria-label="Prices in"|label="Prices in"|In India\? Show prices in ₹/);
  // the paywall sentences come from the same line (usePlanPrice / planPriceFor)
  assert.match(cur, /return planPriceLine\(plan, p\);/);
  assert.match(cur, /return shared\.then\(\(r\) => planPriceLine\(plan, r\)\)/);
});
