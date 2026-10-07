// Build 3: one source for what's on sale (lib/offer.ts), the way back after sign-in (lib/returnTo.ts), what an address is
// (lib/deepLinks.ts), the first-run guide's rules (lib/onboarding.ts) and the AI assistant's address (lib/mcp.ts).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const offer = await import("../src/lib/offer.ts");
const back = await import("../src/lib/returnTo.ts");
const links = await import("../src/lib/deepLinks.ts");
const onb = await import("../src/lib/onboarding.ts");
const { mcpEndpoint } = await import("../src/lib/mcp.ts");
const { LIMITS } = await import("../src/lib/plans.ts");

const FREE_NOW_EARLY = { ...LIMITS.pro, backtests_per_month: 10, ai_builds_per_month: 10, live_limit: 1 };
delete FREE_NOW_EARLY.features;
const early = { mode: "early", payments: false, yearly: false, promo_until: null, free_now: FREE_NOW_EARLY, free_trial_days: 5 };
const paid = { mode: "paid", payments: true, yearly: true, promo_until: null, free_now: {}, free_trial_days: 5 };
const promo = { mode: "promo", payments: false, yearly: false, promo_until: "2099-10-31T00:00:00+00:00", free_now: FREE_NOW_EARLY, free_trial_days: 5 };

test("early access says so, with the limits that still apply, and sells nothing", () => {
  const i = offer.pricingIntro(early, LIMITS.pro, "landing");
  assert.equal(i.title, "Free during early access.");
  assert.match(i.lede, /^Paid plans aren't on sale yet\. Until they are, every feature is open to everyone on the Free plan, with 10 backtests a month, 10 AI strategy builds a month and paper trading for 5 market days\./);
  assert.doesNotMatch(i.lede, /Cancel any time/);
  assert.deepEqual(offer.landingAction(early, "pro"), { note: "Not on sale yet" });
  assert.deepEqual(offer.landingAction(early, "free"), { label: "Start free", buy: false });
  assert.equal(offer.canBuy(early), false);
  // the small print promises nothing that can't be bought: no invoices, no renewals, no yearly
  const small = offer.finePrint(early, { currency: "INR", approx: false, approxYear: false, year: { basic: "₹6,999", pro: "₹19,999" } }).join(" ");
  assert.equal(small, "Rupee prices include 18% GST.");
  // the Plans page says the same words as the landing page
  assert.equal(offer.pricingIntro(early, LIMITS.pro, "app").lede, i.lede);
});

test("payments on: plans can be bought, cancelled any time, yearly in the visitor's own currency", () => {
  assert.deepEqual(offer.landingAction(paid, "basic"), { label: "Start with Basic", buy: true });
  assert.match(offer.pricingIntro(paid, LIMITS.pro, "landing").lede, /Cancel any time\.$/);
  const usd = offer.finePrint(paid, { currency: "USD", approx: true, approxYear: true, year: { basic: "about $80", pro: "about $225" }, charged: { basic: "₹699", pro: "₹1,999" } });
  assert.ok(usd.some((l) => l.startsWith("Paid in rupees for now: a card is charged ₹699 (Basic) or ₹1,999 (Pro) a month")));
  assert.ok(usd.includes("Paying yearly: Basic about $80, Pro about $225, charged in rupees."));
  assert.ok(!usd.join(" ").includes("Paying yearly in rupees"), "a dollar visitor isn't shown a rupee-only yearly line");
  const inr = offer.finePrint(paid, { currency: "INR", approx: false, approxYear: false, year: { basic: "₹6,999", pro: "₹19,999" } });
  assert.deepEqual(inr.slice(0, 2), ["Rupee prices include 18% GST, and every payment gets a GST invoice.", "Paying yearly: Basic ₹6,999, Pro ₹19,999."]);
});

test("the launch offer names its end; an unknown offer promises nothing", () => {
  const i = offer.pricingIntro(promo, LIMITS.pro, "landing");
  assert.match(i.title, /^Every Pro feature, free until 31 Oct\.$/);
  assert.match(i.lede, /Paid plans aren't on sale yet/);
  assert.equal(offer.promoUntil(promo, Date.parse("2099-10-30")), promo.promo_until);
  assert.equal(offer.promoUntil(promo, Date.parse("2099-11-01")), null);
  assert.equal(offer.offerMode(null), "unknown");
  assert.deepEqual(offer.landingAction(null, "pro"), { note: "Choose a plan after you sign in" });
  assert.deepEqual(offer.finePrint(null, { currency: "EUR", approx: true, approxYear: true }), []);
});

test("a paid feature that's open today is tagged as open, and why", () => {
  assert.deepEqual(offer.featureTag("basic", early, { paid: "free", canUse: true }),
    { label: "Basic · open now", why: "A Basic feature, open to everyone until paid plans go on sale" });
  assert.equal(offer.featureTag("pro", promo, { paid: "free", canUse: true }).why, "A Pro feature, open to everyone during the launch offer");
  assert.equal(offer.featureTag("basic", paid, { paid: "free", canUse: false }).label, "Basic");
  assert.equal(offer.featureTag("basic", paid, { paid: "pro", canUse: true }).label, "Basic");     // paying for it: just the plan
});

test("the way back after sign-in: own pages only", () => {
  for (const ok of ["/research/IN/RELIANCE", "/n/abc?x=1#y", "/holdings", "/research/US/BRK.B/deep"]) assert.equal(back.safeNext(ok), ok, ok);
  for (const bad of ["//evil.com", "/\\evil.com", "https://evil.com/x", "javascript:alert(1)", "evil.com", "", null, 42, "/a\nb", "/%0a", "/" + "a".repeat(600)]) {
    const got = back.safeNext(bad);
    assert.ok(got === null || got === "/%0a", `${String(bad).slice(0, 30)} → ${got}`);
  }
  assert.equal(back.safeNext("/%0a"), "/%0a");                         // an encoded character stays a path on this site
  assert.equal(back.returnPathFor("/"), null);
  assert.equal(back.returnPathFor("/pricing"), null);
  assert.equal(back.returnPathFor("/research/IN/RELIANCE", "?tab=deals"), "/research/IN/RELIANCE?tab=deals");

  const mem = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), m }; };
  const s1 = mem(), s2 = mem();
  back.rememberNext("/holdings", 1000, [s1, s2]);
  assert.equal(back.takeNext(2000, [s1, s2]), "/holdings");
  assert.equal(back.takeNext(3000, [s1, s2]), null, "read once");
  back.rememberNext("//evil.com", 1000, [s1]);
  assert.equal(back.takeNext(2000, [s1]), null);
  back.rememberNext("/library", 0, [s1]);
  assert.equal(back.takeNext(2 * 3600 * 1000, [s1]), null, "an hour-old return is dropped");
  s1.setItem(back.NEXT_PAGE, "/tax-report");                            // the old plain form still works
  assert.equal(back.takeNext(5, [s1]), "/tax-report");
  s1.setItem(back.NEXT_PAGE, JSON.stringify({ to: "https://evil.com", at: 5 }));
  assert.equal(back.takeNext(5, [s1]), null);
});

test("every route in main.tsx is an app address, and nothing else is", () => {
  const main = fs.readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
  const routes = [...main.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((r) => r !== "*" && !r.startsWith("/verdict/"));
  assert.deepEqual([...new Set(routes)].sort(), [...links.APP_ROUTES].sort());
  for (const p of ["/research/IN/RELIANCE", "/n/x/e/3", "/admin/users", "/holdings/", "/tax-report?fy=2025"]) assert.ok(links.isAppPath(p), p);
  for (const p of ["/nonexistent", "/research/IN/RELIANCE/extra/more", "/holdingsx", "/n"]) assert.ok(!links.isAppPath(p), p);
  assert.equal(links.landingSection("/"), null);
  assert.equal(links.landingSection("/pricing"), "pricing");
  assert.equal(links.landingSection("/help"), "faq");
  assert.equal(links.landingSection("/holdings"), undefined);
});

test("a signed-out visitor is told what's at the address", () => {
  assert.deepEqual(links.describePath("/research/IN/reliance"), { what: "RELIANCE", company: { region: "IN", symbol: "RELIANCE", deep: false } });
  assert.equal(links.describePath("/research/US/NVDA/deep").what, "the deep dive on NVDA");
  assert.equal(links.describePath("/research/watchlist").company, undefined);
  assert.equal(links.describePath("/n/abc").what, "this notebook");
  assert.equal(links.describePath("/n/abc/e/2").what, "this experiment");
  assert.equal(links.describePath("/holdings").what, "Holdings");
  assert.equal(links.describePath("/library").what, "Strategy library");
  assert.equal(links.describePath("/tax-report").what, "Tax report");
  assert.equal(links.describePath("/nope"), null);
});

test("the welcome question: once per account, on a home page only; the tour only right after it", () => {
  const fresh = { prefs: { level: null, focus: null }, onboarding: { welcome: null, tour: null } };
  assert.ok(onb.askWelcome(fresh, "/"));
  assert.ok(onb.askWelcome(fresh, "/trade"));
  for (const deep of ["/holdings", "/research/IN/RELIANCE", "/tax-report", "/n/x"]) assert.ok(!onb.askWelcome(fresh, deep), deep);
  assert.ok(!onb.askWelcome({ prefs: { level: "some", focus: "trade" }, onboarding: { welcome: null, tour: null } }, "/"), "answered");
  assert.ok(!onb.askWelcome({ prefs: {}, onboarding: { welcome: "2026-10-07T00:00:00Z", tour: null } }, "/"), "closed on another device");
  assert.ok(!onb.askWelcome(null, "/"));
  assert.ok(onb.tourSeen({ onboarding: { tour: "skipped" } }, null));
  assert.ok(onb.tourSeen({ onboarding: { tour: null } }, "1"), "this browser's old flag still counts");
  assert.ok(!onb.tourSeen({ onboarding: { tour: null } }, null));
  assert.ok(onb.autoTour(true, false));
  assert.ok(!onb.autoTour(false, false), "never by itself later: Help opens it");
  assert.ok(!onb.autoTour(true, true));
});

test("the AI assistant's address comes from the server the page talks to", () => {
  assert.equal(mcpEndpoint("https://api.stratlab.studio", "https://stratlab.studio", "http://localhost:8000/mcp"), "https://api.stratlab.studio/mcp");
  assert.equal(mcpEndpoint("https://x.up.railway.app/", "https://stratlab.studio"), "https://x.up.railway.app/mcp");
  assert.equal(mcpEndpoint("/api", "https://stratlab.studio"), "https://stratlab.studio/api/mcp");
  assert.equal(mcpEndpoint("", "https://stratlab.studio"), "https://stratlab.studio/mcp");
  assert.equal(mcpEndpoint("javascript:alert(1)", "https://stratlab.studio", "https://srv/mcp"), "https://srv/mcp");
});
