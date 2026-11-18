// Lane fix16 (LIVE12B review of the live site): the landing's start-up frame, sign-in and plan wording, layout shifts on
// first paint, and figures that must agree with the exchange's completed sessions.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { pageFiles } = await import("../scripts/seoPages.mjs");
const { startupHtml } = await import("../src/lib/held.ts");
const template = read("index.html");

// ---------- LIVE12B-001: the landing's frame while its code downloads, not a plain text page ----------
test("LIVE12B-001: the home page's start-up block wears the landing's hero frame for a browser that runs scripts; crawlers still read every word", () => {
  const files = Object.fromEntries(pageFiles(template));
  const home = files["index.html"];
  assert.match(home, /<div class="boot boot-wait boot-hero" data-boot>\n<h1>Is your trading idea skill or luck\?<\/h1>/);
  // the crawler's paragraphs and company links are still in the HTML
  assert.match(home, /<p>Trade, the strategy lab: /);
  assert.match(home, /<li><a href="\/stocks\/in">India A–Z<\/a><\/li>/);
  // only with scripting on: everything but the heading is hidden, the heading at the landing's hero size, the header on the hero's edges
  const css = /@media \(scripting: enabled\) \{([\s\S]*?)\n\}/.exec(home)?.[1] ?? "";
  assert.match(css, /\.boot\.boot-hero > :not\(h1\) \{ display: none; \}/);
  assert.match(css, /\.boot\.boot-hero h1 \{[^}]*clamp\(44px, 6\.2vw, 80px\)/);
  assert.match(css, /\.boot\.boot-hero \{[^}]*max-width: 1180px/);
  assert.match(css, /html:has\(\.boot-hero\) \.boot-head \{[^}]*max-width: 1180px/);
  // the landing's hero sizes are the ones written here (styles.css .lp-h1, .lp-wrap)
  const app = read("src/styles.css");
  assert.match(app, /\.lp-h1 \{ font-size: clamp\(44px, 6\.2vw, 80px\); line-height: 1; font-weight: 400; letter-spacing: -\.035em; max-width: 12ch; \}/);
  assert.match(app, /\.lp-wrap \{ width: 100%; max-width: 1180px;/);
  // every other page keeps its plain block
  for (const [f, html] of Object.entries(files)) if (f !== "index.html") assert.doesNotMatch(html, /boot-hero" data-boot/, f);
});

test("LIVE12B-001: the words kept for the app to draw while the page's code downloads include the start-up header", () => {
  const head = { getAttribute: (n) => (n === "class" ? "boot-head" : null), outerHTML: '<header class="boot-head"><a href="/">StratLab</a></header>' };
  const main = { outerHTML: '<main><div class="boot boot-wait boot-hero" data-boot><h1>Is your trading idea skill or luck?</h1></div></main>', previousElementSibling: head };
  const el = { getAttribute: (n) => (n === "class" ? "boot boot-wait boot-hero" : null), closest: () => main };
  assert.equal(startupHtml({ querySelector: (s) => (s === "[data-boot]" ? el : null) }),
    '<header class="boot-head"><a href="/">StratLab</a></header><main><div class="boot boot-hero" data-boot><h1>Is your trading idea skill or luck?</h1></div></main>');
});

// ---------- LIVE12B-002: the plans' note says the US prices without the switch's label in the sentence ----------
test("LIVE12B-002: the plans note names the US prices and nothing of the 'Prices in' switch's label", async () => {
  const { usdNote } = await import("../src/lib/usdAbout.ts");
  const note = usdNote(93.31, false, { basic: 8, pro: 20 });
  assert.match(note, /\(Basic \$8 and Pro \$20 a month\); other dollar figures/);
  assert.doesNotMatch(note, /Prices in:|\$ USD/);
});

// ---------- LIVE12B-013: the next F&O expiry is either exchange's ----------
test("LIVE12B-013: Trade home's next F&O expiry is the nearest of NSE's and BSE's, SENSEX's included", async () => {
  const { nextExpiry } = await import("../src/lib/tradeUi.ts");
  const ev = [
    { kind: "expiry", date: "2026-11-17", title: "NIFTY weekly expiry" },
    { kind: "expiry", date: "2026-11-23", title: "Monthly F&O expiry" },
    { kind: "expiry", date: "2026-11-19", title: "SENSEX weekly expiry" },
    { kind: "rbi", date: "2026-11-18", title: "RBI policy" },
  ];
  assert.equal(nextExpiry(ev, "2026-11-18")?.title, "SENSEX weekly expiry");
  assert.equal(nextExpiry(ev, "2026-11-20")?.title, "Monthly F&O expiry");
  // the same day on both: NSE's first
  assert.equal(nextExpiry([...ev, { kind: "expiry", date: "2026-11-19", title: "NIFTY weekly expiry" }], "2026-11-18")?.title, "NIFTY weekly expiry");
  assert.equal(nextExpiry(null, "2026-11-18"), null);
  assert.doesNotMatch(read("src/pages/SpaceHomes.tsx"), /!e\.title\.startsWith\("SENSEX"\)/);
});

// ---------- LIVE12B-016: one numbered note for two figures with the same note ----------
test("LIVE12B-016: Key numbers' notes list each note once; Sales and Profit growth's 'Latest YoY' share one number", async () => {
  const { metricFoots } = await import("../src/lib/research.ts");
  const items = [
    { label: "Div yield", note: "₹112 a share in the last 12 months, including a ₹46 special dividend; 2.7% without it" },
    { label: "Latest YoY", note: "Sep 2026 vs Sep 2025" },          // Sales growth
    { label: "5Y CAGR", note: null },
    { label: "Latest YoY", note: "Sep 2026 vs Sep 2025" },          // Profit growth
  ];
  const foots = metricFoots(items, () => true);
  assert.deepEqual(foots.map((f) => `${f.n} ${f.label}: ${f.text}`), [
    "1 Div yield: ₹112 a share in the last 12 months, including a ₹46 special dividend; 2.7% without it",
    "2 Latest YoY: Sep 2026 vs Sep 2025",
  ]);
  assert.match(read("src/components/Research.tsx"), /const foot = metricFoots\(/);
});

// ---------- LIVE12B-019: a date box asking for a day ahead shows a day ahead as its example ----------
test("LIVE12B-019: the token's end date example is a day ahead, not 14 Aug 2025", async () => {
  const { aheadExample } = await import("../src/lib/dateInput.ts");
  assert.equal(aheadExample(90, new Date(2026, 10, 18)), "e.g. 16 Feb 2027");
  assert.match(read("src/components/ConnectedAccounts.tsx"), /<DateField label="Token ends on" optional value=\{expires\} onChange=\{setExpires\} placeholder=\{aheadExample\(90\)\}/);
  assert.match(read("src/pages/SettingsPage.tsx"), /`Imported once from \$\{sourceWords\(h\.source\)\}/);
  // the brokers' Connect buttons one width
  assert.match(read("src/components/ConnectedAccounts.tsx"), /className="btn broker-connect"[^\n]*>Connect \{b\.name\}<\/button>/);
  assert.match(read("src/styles.css"), /\.broker-connect \{ min-width: 10\.5rem; justify-content: center; \}/);
});

// ---------- LIVE12B-007: a Coming up row's line never repeats its title ----------
test("LIVE12B-007: a Coming up row whose line repeats its title shows no line", async () => {
  const { detailBeyond } = await import("../src/lib/mine.ts");
  assert.equal(detailBeyond("India GDP: Quarterly Estimates of GDP for Q2, FY 2026-27", "Quarterly Estimates of GDP for Q2, FY 2026-27."), "");
  assert.equal(detailBeyond("RBI policy", "The Monetary Policy Committee's decision, 10:00 IST."), "The Monetary Policy Committee's decision, 10:00 IST.");
  assert.equal(detailBeyond("Advance tax", ""), "");
});

// ---------- LIVE12B-010: a plan's price once a page ----------
test("LIVE12B-010: a later plan note with the same price leaves it to the first one on the page", () => {
  const n = read("src/components/kit/Notice.tsx");
  assert.match(n, /querySelectorAll<HTMLElement>\("\[data-plan-price\]"\)\)\.find\(\(e\) => e\.dataset\.planPrice === price\)/);
  assert.match(n, /<span ref=\{priced\} data-plan-price=\{price \?\? undefined\}>\{unlockHint\(me\?\.offer, CFG\.CONTACT_EMAIL \|\| undefined, again \? null : price\)\}<\/span>/);
});
