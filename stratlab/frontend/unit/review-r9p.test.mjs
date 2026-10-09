// Round 9 review of the live site (plan views, payments, emails, Safari): the app's side, each on the reviewer's example.
// Every clock here is a fixed instant. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

test("R9P-005: an admin viewing as Free or Basic sees the viewed plan's AI-reads cap, said as not enforced", async () => {
  const { aiReadsUse } = await import("../src/lib/aiReason.ts");
  assert.equal(aiReadsUse(35, null, "admin", 60), "35 of 60 (not enforced for you as an admin)");
  assert.equal(aiReadsUse(35, null, "admin", null), "35 (no daily cap for the site's admins)");     // viewing as Pro, or the owner's own Pro
  assert.equal(aiReadsUse(35, null, "admin"), "35 (no daily cap for the site's admins)");
  assert.equal(aiReadsUse(3, 60, null, 60), "3 of 60 (starts again at midnight India time)");        // anyone else: the enforced cap, as before
  assert.equal(aiReadsUse(12, null, null, null), "12 (no daily cap on Pro)");
  const src = read("src/pages/AccountPage.tsx");
  assert.match(src, /aiReadsUse\(u\.ai_reads_today, u\.ai_reads_limit \?\? null, u\.ai_reads_cap_for \?\? null, u\.ai_reads_plan_limit\)/);
});

test("R9P-005: Account's AI builds line carries Pro's daily cap, as the Plans card does", async () => {
  const { aiBuildsUse } = await import("../src/lib/account.ts");
  assert.equal(aiBuildsUse(5, 100, null), "5 of 100");
  assert.equal(aiBuildsUse(5, null, 200), "5 (unlimited; up to 200 a day)");
  assert.equal(aiBuildsUse(5, null, 200, true), "5 (unlimited; up to 200 a day, not enforced for you as an admin)");
  assert.equal(aiBuildsUse(5, null, null), "5 (unlimited)");
  const { FEATURES } = await import("../src/lib/plans.ts");
  assert.ok(FEATURES.pro.some((f) => /AI builds \(up to 200 a day\)/.test(f)));                    // the card the line has to match
  assert.match(read("src/pages/AccountPage.tsx"), /aiBuildsUse\(u\.ai_used, u\.ai_limit, u\.ai_builds_per_day, !!me\.is_admin\)/);
});

test("R9P-006: the confirm step names the rupee charge in the currency shown, from the same figure as the Plans cards", async () => {
  const { chargeAboutNote, checkoutDescription } = await import("../src/lib/offer.ts");
  const { aboutMoney, chargedLine } = await import("../src/lib/currency.ts");
  const usd = { symbol: "$", name: "US dollar", basic: 8, pro: 20, basic_year: 80, pro_year: 200, charged_in: "INR", yearly_charged_in: "INR", charge_about: { basic: 7.23 } };
  const about = aboutMoney(usd, usd.charge_about.basic, "USD");
  assert.equal(about, "$7.23");
  assert.equal(chargeAboutNote(true, "$8", about), " (about $7.23 today)");
  assert.equal(chargedLine("₹699", false, "month", about), "Charged as ₹699 (about $7.23 today) / month");       // the card says the same
  assert.equal(chargeAboutNote(true, "≈ SAR 27", null), " (about SAR 27 today)");                          // a converted price: its own figure
  assert.equal(chargeAboutNote(false, "$8", about), "");                                                    // charged in the currency shown, or INR
  assert.equal(chargeAboutNote(true, "$8", null), "");
  const src = read("src/pages/PlansPage.tsx");
  assert.match(src, /chargeAboutNote\(!!shown\.charged, shown\.shown, shown\.about\)/);
  // the headline prices are the owner's fixed ones and are not touched here
  assert.match(read("../backend/app/pricing.py"), /FIXED/);
});

test("R9P-007: Razorpay's own window says it renews", async () => {
  const { checkoutDescription } = await import("../src/lib/offer.ts");
  assert.equal(checkoutDescription("Basic", "₹699", "month"), "Basic plan, ₹699 / month. Renews every month until you cancel.");
  assert.equal(checkoutDescription("Pro", "$200", "year"), "Pro plan, $200 / year. Renews every year until you cancel.");
  assert.match(read("src/pages/PlansPage.tsx"), /description: checkoutDescription\(/);
});

test("R9P-008: a failed import() of the app's own chunk on first load gets the Reload card", () => {
  const entry = read("src/entry.tsx");
  assert.match(entry, /start\(\)\.catch\(\(\) => \{ if \(window\.__stratlabRecover\) window\.__stratlabRecover\(\); else window\.__stratlabShowLoadError\?\.\(\); \}\);/);
  assert.doesNotMatch(entry, /^void start\(\);/m);
  const boot = read("public/boot.js");
  assert.match(boot, /addEventListener\("unhandledrejection"/);
  assert.ok(boot.includes("importing a module script") && boot.includes("load failed"));
});

test("R9P-008: boot.js reloads once, then shows the card, when the main chunk's import rejects while the start-up text is showing", () => {
  const listeners = {};
  let reloads = 0, shown = 0, boot = true;
  const store = new Map();
  const root = { querySelector: (q) => (boot && /data-boot/.test(q) ? {} : null), textContent: "", appendChild: () => { shown += 1; } };
  const el = () => ({ setAttribute() {}, appendChild() {}, addEventListener() {}, className: "", style: {} });
  const sandbox = {
    window: { addEventListener: (t, f) => { listeners[t] = f; }, location: { reload: () => { reloads += 1; } } },
    document: { getElementById: () => root, createElement: el, documentElement: { dataset: {} } },
    sessionStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    localStorage: { getItem: () => null }, setTimeout: () => 0, Date, Number, String, location: { reload: () => { reloads += 1; } },
  };
  new Function(...Object.keys(sandbox), read("public/boot.js"))(...Object.values(sandbox));
  const safari = { reason: new TypeError("Importing a module script failed.") };
  listeners.unhandledrejection(safari);
  assert.equal(reloads, 1);                                           // the first failure: one automatic reload
  listeners.unhandledrejection(safari);
  assert.equal(reloads, 1);
  assert.equal(shown, 1);                                             // the second, within a minute: the Reload card
  boot = false;
  listeners.unhandledrejection({ reason: new TypeError("Failed to fetch") });
  assert.equal(shown, 1);                                             // once the app has drawn, a failed request is its own to report
  boot = true;
  listeners.unhandledrejection({ reason: new Error("something else") });
  assert.equal(shown, 1);
});

test("R7M-008 leftover: the AI tile has one denominator, not 12 beside 12 of 13", async () => {
  const { aiTile } = await import("../src/pages/admin/attention.ts");
  const row = (label, result, extra = {}) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result, ...extra });
  const ai = [...["Groq", "Gemini", "OpenRouter", "Cloudflare"].map((l) => row(l, "working")),
    row("Cerebras", "quota", { answering: false }), row("SambaNova", "quota", { answering: false }),
    ...["Mistral", "Z.ai", "Vercel", "GitHub", "NVIDIA", "Hugging Face"].map((l) => row(l, "untested")),
    { label: "Anthropic", configured: false, in_use: false, model: null, last_error: null, result: null }];
  assert.equal(aiTile(ai).detail, "4 working of 12 set up (13 known) · 2 out of credit · 6 not tried yet");
  assert.equal(aiTile(ai.slice(0, 12)).detail, "4 of 12 working · 2 out of credit · 6 not tried yet");     // every provider has a key: as before
});
