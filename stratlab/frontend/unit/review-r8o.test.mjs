// Round 8 owner review of the live site (9 Oct 2026, India open): the app's side, each on the reviewer's example.
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

test("R8O-002: the daily cap is said plainly, with no Ask again beside it", async () => {
  const { aiLimited, aiReason, aiReadsUse } = await import("../src/lib/aiReason.ts");
  const cap = "You've used today's 60 fresh AI reads on your plan. Reads already written for a company or the market still open, and the count starts again at midnight India time.";
  assert.equal(aiLimited(cap), true);
  assert.equal(aiLimited("You've used 60 fresh AI reads today. Cached ones still work; try again tomorrow."), true);   // the old words too
  assert.match(aiReason(cap), /used up\. Reads already written still open, and the count starts again at midnight India time\./);
  assert.equal(aiLimited("The AI service is busy right now."), false);
  assert.equal(aiLimited(null), false);
  assert.equal(aiReadsUse(3, 60, null), "3 of 60 (starts again at midnight India time)");
  assert.equal(aiReadsUse(12, null, null), "12 (no daily cap on Pro)");
  assert.equal(aiReadsUse(12, null, "admin"), "12 (no daily cap for the site's admins)");
  // every place that offers "Ask again" hides it when the cap is the reason
  for (const f of ["src/components/Research.tsx", "src/pages/Research.tsx"]) {
    const src = read(f);
    const asks = src.match(/>\{(busy|asking) \? "Asking…" : "Ask again"\}/g) ?? [];
    const guarded = src.match(/\{!aiLimited\([^)]*\) && <button[\s\S]{0,200}?>\{(busy|asking) \? "Asking…" : "Ask again"\}/g) ?? [];
    assert.ok(asks.length > 0 && guarded.length === asks.length, f);
  }
});

test("R8O-002: Plans lists the fresh AI reads a day, from the same numbers as the server", async () => {
  const { LIMITS, NUMBERS, FEATURES } = await import("../src/lib/plans.ts");
  assert.equal(LIMITS.free.ai_reads_per_day, 60);
  assert.equal(LIMITS.basic.ai_reads_per_day, 60);
  assert.equal(LIMITS.pro.ai_reads_per_day, null);
  assert.ok(NUMBERS.some(([k, label]) => k === "ai_reads_per_day" && /market mood, never count/.test(label)));
  assert.ok(FEATURES.pro.some((f) => /up to 200 a day/.test(f) && /fresh AI reads/.test(f)));
  assert.match(read("src/pages/AccountPage.tsx"), /"Fresh AI reads today", aiReadsUse\(/);
});

test("R8O-007: a company page asks for its AI read behind the page and stops when it is left", async () => {
  const { AI_POLL_MS, AI_POLLS } = await import("../src/lib/research.ts");
  assert.ok(AI_POLL_MS * AI_POLLS >= 60_000 && AI_POLL_MS <= 5000);
  const src = read("src/lib/research.ts");
  assert.match(src, /\?background=true/);
  assert.match(src, /if \(!alive\(\)\) throw/);
  // the read mounts only once the company's numbers are on the page
  assert.match(read("src/pages/Research.tsx"), /if \(!c\) return \([\s\S]*<AIRead region=\{region\} symbol=\{c\.symbol\}/);
});

test("R8O-007: \"Opening…\" gives way to Reload after 15 s; Admin's reads go out together", async () => {
  const lg = read("src/components/LoadGuard.tsx");
  assert.match(lg, /export const OPEN_TIMEOUT_MS = 15_000;/);
  assert.match(lg, /data-testid="opening-slow"[\s\S]*location\.reload\(\)[\s\S]*Reload/);
  const main = read("src/main.tsx");
  assert.match(main, /<Suspense fallback=\{<><h1 className="sr-only">Opening the page<\/h1><Opening \/><\/>\}>/);
  assert.match(main, /if \(!ready\) return <main><h1 className="sr-only">Opening StratLab<\/h1><Opening label="Opening StratLab" \/><\/main>;/);
  assert.match(read("src/visitor/VisitorApp.tsx"), /<Opening label="Opening StratLab" \/>/);
  assert.match(main, /void firstPage\(location\.pathname\)\?\.\(\)/);
  const admin = read("src/pages/admin/AdminContext.tsx");
  assert.match(admin, /Promise\.all\(\[ovDone, libDone, reloadJobs\(\)\]\)/);
  assert.doesNotMatch(admin, /setOvState\(await api/);
});

test("R8O-009: the start-up and error shells have a main landmark and a heading", () => {
  const html = read("index.html");
  assert.match(html, /<html lang="en">/);
  assert.match(html, /<title>[^<]+<\/title>/);
  assert.match(html, /<div id="root">\s*<main>\s*<div class="boot[^"]*" data-boot>\s*<h1>/);
  assert.match(read("public/boot.js"), /createElement\("main"\)[\s\S]*createElement\("h1"\)/);
  assert.match(read("src/components/LoadGuard.tsx"), /<main><LoadFailed \/><\/main>/);
  // the closing auction's card headings follow the page's h1 (axe heading-order)
  assert.doesNotMatch(read("src/pages/trade/ClosingAuctionPage.tsx"), /level=\{3\}/);
});

test("R8O-009: a company's tab says its name from the first frame once it has been opened", async () => {
  const { titleFor, rememberName, knownName } = await import("../src/lib/title.ts");
  assert.equal(titleFor("/research/IN/POLYCAB"), "POLYCAB · StratLab");
  rememberName("IN", "POLYCAB", "Polycab India Ltd");
  assert.equal(knownName("in", "polycab"), "Polycab India Ltd");
  assert.equal(titleFor("/research/IN/POLYCAB"), "Polycab India Ltd (POLYCAB) · StratLab");
  assert.equal(titleFor("/research/IN/POLYCAB/deep"), "Polycab India Ltd (POLYCAB) deep dive · StratLab");
  // the app's shell sets the address's title before the sign-in is read
  assert.match(read("src/main.tsx"), /useLayoutEffect\(\(\) => \{ if \(!everyone && \(!ready \|\| session\)\) document\.title = titleFor\(loc\.pathname\); \}/);
});

test("R8O-006: a euro or pound price charged in rupees says that charge in its currency", async () => {
  const { aboutMoney, chargedLine, rupeesNote } = await import("../src/lib/currency.ts");
  const eur = { symbol: "€", name: "Euro", basic: 8, pro: 19, basic_year: 80, pro_year: 190, charged_in: "INR", yearly_charged_in: "INR", charge_about: { basic: 6.44 } };
  assert.equal(aboutMoney(eur, 6.44, "EUR"), "€6.44");
  assert.equal(aboutMoney(eur, 6.4, "EUR"), "€6.40");
  assert.equal(aboutMoney({ ...eur, symbol: "¥" }, 1234.4, "JPY"), "¥1,234");
  assert.equal(chargedLine("₹699", true, "month", "€6.44"), "Charged as ₹699 incl. GST (about €6.44 today) / month");
  assert.equal(chargedLine("₹699", false, "month", null), "Charged as ₹699 / month");
  const note = rupeesNote("EUR", { basic: "€6.44", pro: "€18.43" });
  assert.match(note, /about €6\.44 for Basic and €18\.43 for Pro at today's rate, not the EUR prices shown/);
  assert.doesNotMatch(note, /slightly/);
  assert.doesNotMatch(rupeesNote("SAR", null), /slightly/);
  assert.doesNotMatch(read("src/pages/PlansPage.tsx"), /can differ slightly/);
});

test("R7M-010: Plans' buy buttons are off under View as from the first frame, not only once /me answers", () => {
  const src = read("src/pages/PlansPage.tsx");
  assert.match(src, /const viewAs = me \? viewAsMe : readViewAs\(\);/);
  assert.match(src, /disabled=\{!!busy \|\| !!viewAs\}/);
  assert.match(src, /\(off while viewing as \{planName\(viewAs\)\}\)/);
});

test("R8O-008: the AI tile's denominator is said as System says it", async () => {
  const { aiTile } = await import("../src/pages/admin/attention.ts");
  const row = (label, result, extra = {}) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result, ...extra });
  const ai = [...["Groq", "Gemini", "OpenRouter", "Cloudflare", "NVIDIA"].map((l) => row(l, "working")),
    row("Cerebras", "quota", { answering: false }), row("SambaNova", "quota", { answering: false }), row("Hugging Face", "quota", { answering: false }),
    ...["Mistral", "Z.ai", "Vercel", "GitHub"].map((l) => row(l, "untested")),
    { label: "Anthropic", configured: false, in_use: false, model: null, last_error: null, result: null }];
  assert.equal(aiTile(ai).detail, "5 of 12 working (12 of 13 set up) · 3 out of credit · 4 not tried yet");
});

test("R8O-011: the live price feed says when the options sessions are more than one person's", async () => {
  const { feedTile } = await import("../src/pages/admin/attention.ts");
  const sv = (x) => ({ feed_connected: false, live_sessions: 0, india_sessions: 0, ...x });
  assert.equal(feedTile(sv({ options_sessions: 2, options_users: 2 })).detail, "Not needed: 2 options paper sessions running across 2 users on quotes read every few seconds");
  assert.equal(feedTile(sv({ options_sessions: 1, options_users: 1 })).detail, "Not needed: 1 options paper session running on quotes read every few seconds");
});

test("R8O-012: a chain from the live feed over two minutes old says its time, not \"live\"", async () => {
  const { chainWords, LIVE_CHAIN_FOR_MS } = await import("../src/lib/positioning.ts");
  const asOf = "2026-10-09T11:39:59+05:30";
  const t = Date.parse(asOf);
  assert.equal(LIVE_CHAIN_FOR_MS, 120_000);
  assert.equal(chainWords({ source: "live", as_of: asOf }, t + 30_000), "live chain");
  assert.equal(chainWords({ source: "live", as_of: asOf }, Date.parse("2026-10-09T11:49:08+05:30")), "chain at 11:39 IST");
  assert.equal(chainWords({ source: "live", at_close: true, as_of: asOf }, t + 3_600_000), "chain at the close");
  assert.equal(chainWords({ source: "recorded", as_of: asOf }, t), "recorded chain");
  assert.match(read("src/pages/PositioningPage.tsx"), /\{chainWords\(c\)\}, \{istTime\(c\.as_of\)\}/);
  assert.match(read("src/components/VixPanel.tsx"), /upperFirst\(chainWords\(ivNow\)\)/);
});

test("Small tap targets: My space's calendar links and the Trade home's Positioning link are 32px on a phone", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.mine-tl-i \.body a, \.tap-link \{ min-height: 32px; display: inline-flex; align-items: center; \}/);
  assert.match(read("src/pages/SpaceHomes.tsx"), /className="link tap-link" to="\/trade\/positioning"/);
});
