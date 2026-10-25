// Round 20 (the owner on Chrome, live): a failed sign-in check is not "signed out", the option chain says when the market is
// shut, the journal's date is its last trade, one provider count, Results' heading, phone tables and bar labels.
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const URL_ = "https://abc123.supabase.co";

test("R20-002: a saved sign-in with no session is 'couldn't check', only an empty store is signed out", async () => {
  const { hasSavedSession, sessionKeyFor } = await import("../src/lib/entry.ts");
  const key = sessionKeyFor(URL_);
  assert.equal(hasSavedSession(URL_, { getItem: (k) => (k === key ? "{\"access_token\":\"x\"}" : null) }), true);
  assert.equal(hasSavedSession(URL_, { getItem: () => null }), false);
  assert.equal(hasSavedSession(URL_, { getItem: () => { throw new Error("storage off"); } }), false);
  assert.equal(hasSavedSession(URL_, null), false);
});

test("R20-002: the app, the API calls and the gate never read a failed check as signed out", () => {
  const app = read("src/lib/app.tsx"), main = read("src/main.tsx"), api = read("src/lib/api.ts"), gate = read("src/pages/Gate.tsx");
  // the app asks again before deciding, and a saved sign-in with no session shows the load error with Reload
  assert.match(app, /export const sessionUnconfirmed = \(ready: boolean, session: Session \| null\): boolean =>/);
  assert.match(app, /SESSION_RETRY_MS/);
  assert.match(main, /if \(!session && sessionUnconfirmed\(ready, session\)\) return <main><LoadFailed what="your account" \/><\/main>;\s+if \(!session\) return <VisitorApp \/>;/);
  // a request is never sent without a token while a sign-in is saved (its 401 would sign the person out)
  assert.match(api, /if \(!token && hasSavedSession\(CFG\.SUPABASE_URL/);
  // the gate itself says "couldn't load" when the settings never loaded or a sign-in is saved
  assert.match(gate, /const unsure = !window\.STRATLAB_CONFIG \|\| hasSavedSession\(/);
  assert.match(gate, /if \(unsure\) return <main><LoadFailed what="your account" \/><\/main>;/);
  // the first-load path was already there: no config on an app address is the Reload card, never the visitor page
  assert.match(read("src/entry.tsx"), /if \(!\(await readConfig\(\)\) && !isPublicForAll\(path\)\) \{ window\.__stratlabShowLoadError\?\.\(\); return; \}/);
  assert.match(read("src/visitor/visitorMain.tsx"), /\(signedInNow\(\) \|\| !window\.STRATLAB_CONFIG\)\) location\.reload\(\)/);
});

test("R20-005: one count of working providers for Settings and Admin, and the detail stays with admins", async () => {
  const { aiCountText, serverRow, aiMissingRow } = await import("../src/lib/connection.ts");
  assert.equal(aiCountText(4, 10, 10), "4 of 10 working");
  assert.equal(aiCountText(4, 10, 12), "4 working of 10 set up (12 known)");
  assert.match(read("src/pages/admin/attention.ts"), /aiCountText\(working, keys\.length, ai\.length\)/);
  const settings = read("src/pages/SettingsPage.tsx");
  assert.match(settings, /set\.filter\(\(p\) => p\.result === "working"\)\.length/);       // Admin's own reading, not the one test
  assert.match(settings, /aiCountText\(working,/);
  assert.match(settings, /else if \(!me\.is_admin\) add\(\{ t: "AI strategy builder", s: "pass", d: "Online" \}\);/);   // a person: one generic line
  // a person's server line has no host; an admin's has it
  assert.equal(serverRow(true, false, "https://stratlab-production.up.railway.app").d, "Online");
  assert.equal(serverRow(true, true, "https://stratlab-production.up.railway.app").d, "stratlab-production.up.railway.app");
  assert.doesNotMatch(aiMissingRow(false).d, /GROQ|Railway/);
});

const IN = { id: "IN", name: "India", venues: "NSE", currency: "INR", symbol: "₹", tz: "Asia/Kolkata", hours: { open: "09:15", close: "15:30", days: "Mon-Fri" },
  what: "", costs: "", brokerage: 0, status: "live", max_days: null, holidays: [] };

test("R20-012: the option chain says live only while the exchange trades, else when it last traded", async () => {
  const { chainStamp } = await import("../src/lib/marketHours.ts");
  const times = ["2026-10-14T15:29:58", null, "2026-10-14T15:30:00+05:30"];     // the broker's feed sends no offset: IST
  assert.equal(chainStamp({ market: IN, times, now: new Date("2026-10-14T21:55:00Z") }), "as of Wed 14 Oct, 15:30 IST (market closed)");   // 03:25 IST on 15 Oct
  assert.equal(chainStamp({ market: IN, times, now: new Date("2026-10-15T05:00:00Z") }), "live");                    // 10:30 IST, open
  assert.equal(chainStamp({ market: IN, times: [], now: new Date("2026-10-14T21:55:00Z") }), "last prices (market closed)");
  assert.equal(chainStamp({ market: null, times, now: new Date("2026-10-14T21:55:00Z") }), "live");               // no market to judge by
  assert.match(read("src/pages/OptionsPage.tsx"), /bid \/ ask, IV and Greeks, \{chain \? stamp : offline \? "from the last recorded close" : stamp === "live" \? "live" : "market closed"\}/);
});

test("R20-013: the journal's badge is the newest trade's date, not today's", () => {
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /asOf=\{j\?\.trades\.map\(\(t\) => t\.exit_t\.slice\(0, 10\)\)\.sort\(\)\.pop\(\)\} asOfLabel="Trades up to"/);
  assert.doesNotMatch(j, /asOf=\{j\?\.as_of\}/);
});

test("R20-015: Results and Corporate actions say what is empty: this window, not 'yet', when stocks exist", () => {
  const r = read("src/pages/ResultsPage.tsx"), c = read("src/pages/CorpActionsPage.tsx");
  assert.match(r, /data\.mine_count \? "None of your stocks has a results date in these two weeks" : "No stocks to show results dates for yet"/);
  assert.match(c, /data\.mine_count \? "None of your stocks has an ex-date in this window" : "No stocks to show ex-dates for yet"/);
  assert.doesNotMatch(r, /has a results date yet/);
});

test("R20-018: the after-tax rate says what it leaves out", () => {
  const r = read("src/pages/money/RatesPage.tsx");
  assert.match(r, /slab with 4% cess and no surcharge, because no income is saved in your/);
  assert.match(r, /not profits from imported trade files/);
});

test("R20-019: the launch offer's end in Admin Users is in IST like the rest of the site", async () => {
  assert.match(read("src/pages/admin/UsersSection.tsx"), /<b>\{endsAt\(until\)\}<\/b>/);
  const { endsAt } = await import("../src/lib/offer.ts");
  assert.equal(endsAt("2026-10-22T11:50:59Z"), "Thu 22 Oct at 5:20 pm IST");
});

test("R20-008: a phone table's first column wraps inside 40vw so the next column's figures show", () => {
  const css = read("src/styles.css");
  assert.match(css, /:is\(thead th, tbody th, tbody td:not\(\.k-empty-row\), tfoot th\):first-child \{ white-space: normal; overflow-wrap: break-word; max-width: 40vw; min-width: 0; \}/);
});

test("R20-017: a bar's figure of six characters or more has a five-character form on a phone", async () => {
  const { trendShort, trendValue } = await import("../src/lib/researchFormat.ts");
  assert.equal(trendValue(31542, "₹ Cr"), "31,542");
  assert.equal(trendShort(31542, "₹ Cr"), "31.5k");
  assert.equal(trendShort(146882, "₹ Cr"), "147k");
  assert.equal(trendShort(40012, "₹ Cr"), "40k");                                    // never "40.0k" (a page check reads "0k" as a zero)
  assert.equal(trendShort(-28046, "₹ Cr"), "−28k");
  assert.equal(trendShort(4200, "₹ Cr"), null);
  assert.equal(trendShort(1234567, "USD"), null);
  assert.match(read("src/styles-invest.css"), /\.tbar-num:has\(\.tbar-short\) \.tbar-full \{ display: none; \}/);
});
