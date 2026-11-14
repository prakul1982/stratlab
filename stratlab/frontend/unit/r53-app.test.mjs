// Release 53, lane app53: whole-app fixes from the LIVE8A / LIVE8B reviews (frontend side).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE8B-002: a business-update chart puts each point at its month, so unread months are a stretch of the axis", async () => {
  const { monthIndex, monthOf, periodName } = await import("../src/lib/biz.ts");
  assert.equal(monthIndex("2026-06") - monthIndex("2025-10"), 8);       // Oct 2025 → Jun 2026 is eight months, not one step
  assert.equal(monthOf(monthIndex("2026-10")), "2026-10");
  assert.equal(monthOf(monthIndex("2026-01")), "2026-01");
  assert.ok(Number.isNaN(monthIndex("junk")));
  assert.equal(periodName(monthOf(monthIndex("2025-12"))), "Dec 2025");
  const chart = read("src/components/BizUpdates.tsx");
  assert.match(chart, /x: xs, xFormat/);
});

test("LIVE8B-006: the Free plan's change is a Limit / Now / From table on Account, one line on My space", async () => {
  const fc = await import("../src/lib/freeChange.ts");
  const NOTICE = { on: "2026-11-27T00:00:00+05:30", moves: ["The tax report's CSV and PDF downloads move to Basic"],
    rows: [{ key: "ai_reads_per_day", label: "Fresh AI reads a day", before: 60, after: 5 }, { key: "stock_alerts", label: "Stock alerts on at a time", before: 5, after: 3 },
      { key: "group_size", label: "Instruments in a group test", before: 10, after: 10 }] };
  assert.deepEqual(fc.changeRows(NOTICE), [["Fresh AI reads a day", "60", "5"], ["Stock alerts on at a time", "5", "3"]]);
  const comp = read("src/components/FreeChangeNotice.tsx");
  assert.match(comp, /<th scope="col">Limit<\/th>/);
  assert.match(comp, /From \{day\}/);
  assert.match(read("src/pages/MineHome.tsx"), /<FreeChangeNotice line \/>/);
});

test("LIVE8B-007 / LIVE8B-025: Account's kept limits are there from the plan before the counts come, with Plans' words", async () => {
  const acct = await import("../src/lib/account.ts");
  const rows = acct.plannedKept({ stock_alerts: 5, screens: 2, holdings: 30, mf_schemes: 5, networth_items: 5, journal_trades: 50, name: "Free" });
  assert.deepEqual(rows.map((r) => acct.keptRow(r)), [["Stock alerts on", "Up to 5"], ["Saved screens", "Up to 2"], ["Holdings kept", "Up to 30"],
    ["Mutual fund schemes kept", "Up to 5"], ["Net worth entries", "Up to 5"], ["Trades the journal keeps", "The last 50"]]);
  assert.deepEqual(acct.plannedKept(null), []);
  assert.match(read("src/pages/AccountPage.tsx"), /kept \?\? plannedKept\(/);
});

test("LIVE8B-004 / LIVE8A-017: the analytics question comes after the page, once it has drawn; a policy's footer waits for its words", () => {
  const shell = read("src/components/Shell.tsx"), card = read("src/components/Tracking.tsx"), css = read("src/styles.css");
  assert.ok(shell.indexOf("{ask}") > shell.indexOf('<main className="main" id="main"'));
  assert.match(card, /if \(guiding \|\| !settled\) return null;/);
  assert.match(card, /export const ASK_AFTER_LOAD_MS = 1200;/);
  assert.match(css, /\.shell > \.consent \{ grid-column: -2 \/ -1; grid-row: 2;/);
  assert.match(read("src/components/PublicFrame.tsx"), /\{foot && <footer/);
});

test("LIVE8B-011: a headline seven calendar days back but under seven days old never prints null", async () => {
  const { newsWhen } = await import("../src/lib/researchFormat.ts");
  const now = new Date("2026-11-14T02:40:00Z");                       // Sat 14 Nov, 08:10 IST
  const got = newsWhen("2026-11-07T10:00:00Z", now);                  // 7 Nov, 6 days 16 hours earlier
  assert.doesNotMatch(got, /null/);
  assert.match(got, /^7 Nov · 1 week old$/);
  assert.match(newsWhen("2026-11-11T10:00:00Z", now), /^11 Nov · 3 days old$/);
});

test("LIVE8B-013: a leg distance its box doesn't take is never echoed as a rule; the error sits under the row", async () => {
  const { legRule, offsetFits } = await import("../src/lib/options.ts");
  assert.equal(legRule({ side: "buy", opt: "CE", offset: 5000, lots: 1 }, "strikes"), "distance to fix");
  assert.equal(legRule({ side: "buy", opt: "CE", offset: 2.5, lots: 1 }, "strikes"), "distance to fix");
  assert.equal(legRule({ side: "buy", opt: "CE", offset: 5000, lots: 1 }, "points"), "5000 pts OTM");
  assert.equal(legRule({ side: "buy", opt: "CE", offset: 2, lots: 1 }, "strikes"), "2 strikes OTM");
  assert.equal(offsetFits(100, "strikes"), true);
  assert.equal(offsetFits(101, "strikes"), false);
  assert.match(read("src/pages/trade/options.css"), /\.k-leg-pick \.k-bad \{ flex-basis: 100%; order: 9; \}/);
});

test("LIVE8B-005: a loan's rate in the table is its statement rate when entered, the resets' rate named as expected", async () => {
  const { loanRateText } = await import("../src/lib/networth.ts");
  assert.equal(loanRateText(8.5, 7.5, 7.25), "7.25% a year on your statement; 7.5% expected after its resets (8.5% at the start)");
  assert.equal(loanRateText(8.5, 7.25, 7.25), "7.25% a year on your statement (8.5% at the start)");
  assert.equal(loanRateText(8.5, 7.5, null), "7.5% a year now (8.5% at the start)");
  assert.equal(loanRateText(8.5, null, null), "8.5% a year");
  assert.equal(loanRateText(8.5, 8.5, 8.5), "8.5% a year on your statement");
});

test("LIVE8B-014: an account with a Google sign-in is named Google; an email-link account is told how it gets back in", async () => {
  const acct = await import("../src/lib/account.ts");
  assert.equal(acct.accountMethod("email", ["email", "google"], null), "Google");
  assert.equal(acct.accountMethod("email", ["email"], null), "Email link");
  assert.equal(acct.accountMethod(undefined, undefined, "google"), "Google");
  assert.match(acct.EMAIL_LINK_NOTE, /Continue with Google, using this same email address/);
  assert.match(read("src/pages/AccountPage.tsx"), /method === "Email link" && <span className="k-sub-line" data-testid="email-link-note">\{EMAIL_LINK_NOTE\}<\/span>/);
});

test("LIVE8B-012: on a phone the peers come five at a time, quarters four a line; a bank's quarters say revenue", () => {
  assert.match(read("src/components/CompanyPeers.tsx"), /columns=\{cols\} foot=\{foot\} phonePage=\{6\}/);
  assert.match(read("src/styles-invest.css"), /\.inv-q \.k-tbl-wrap\.stack \.k-table tr \{ grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/);
  assert.match(read("src/components/Research.tsx"), /name: bank \? "Revenue" : "Sales"/);
});

test("LIVE8A-007: the Markets panel never paints a kept price from before its market's last session", async () => {
  const { keptQuotes, keepQuotes } = await import("../src/lib/watchQuotes.ts");
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  const now = Date.parse("2026-11-14T03:00:00Z");
  const q = (price, at) => ({ price, change: 0, change_pct: 0.32, prev_close: price, at, currency: "INR", stale: false });
  keepQuotes("u", { "IN:RELIANCE": q(1339.7, "2026-11-12T15:30:00+05:30"), "IN:TCS": q(2407.5, "2026-11-13T15:30:00+05:30"), "US:AAPL": q(356.27, "2026-11-13T16:00:00-05:00") }, now - 60_000, store);
  const since = (k) => (k.startsWith("IN:") ? "2026-11-13" : k.startsWith("US:") ? "2026-11-13" : null);
  const got = keptQuotes("u", now, store, since);
  assert.deepEqual(Object.keys(got).sort(), ["IN:TCS", "US:AAPL"]);
  assert.equal(Object.keys(keptQuotes("u", now, store)).length, 3);          // without a day to hold to, as before
  assert.match(read("src/components/watch/WatchPanel.tsx"), /keptQuotes\(me\?\.id \?\? "guest", Date\.now\(\), undefined, \(k\) => \{/);
});

test("LIVE8A-013: /sitemap and /index.html redirect; the public footer names the server pages' links; no sign-in on a not-found page", () => {
  const caddy = read("Caddyfile");
  assert.match(caddy, /^\tredir \/sitemap \/sitemap\.xml 301$/m);
  assert.match(caddy, /^\tredir \/index\.html \/ 301$/m);
  // before the app's own handling, beside the other redirects
  assert.ok(caddy.indexOf("redir /sitemap") < caddy.indexOf("handle @api"));
  const frame = read("src/components/PublicFrame.tsx");
  for (const l of ['href="/themes">Themes', 'href="/status">Data status']) assert.ok(frame.includes(l), l);
  const server = readFileSync(new URL("../../backend/app/stock_pages.py", import.meta.url), "utf8");
  assert.match(server, /\("\/themes", "Themes"\), \("\/blog", "Blog"\), \("\/pricing", "Plans"\),\s+\("\/status", "Data status"\)/);
  const gate = read("src/pages/Gate.tsx");
  const nf = gate.slice(gate.indexOf("export function NotFound"));
  assert.doesNotMatch(nf.slice(0, nf.indexOf("return signedIn")), /Continue with Google/);
});

test("LIVE8A-015: the overseas markets' rows name their session's date, never today", async () => {
  const { sessionWord } = await import("../src/lib/pulseMood.ts");
  const dayText = (iso) => `${Number(iso.slice(8))} Nov`;
  assert.equal(sessionWord("2026-11-13", "2026-11-13", dayText), "on 13 Nov");
  assert.equal(sessionWord(null, "2026-11-13", dayText), "–");
});

test("LIVE8B-015: a Key numbers group has a Basis or Usual range column only when one of its rows has one", () => {
  const r = read("src/components/Research.tsx");
  assert.match(r, /\.\.\.\(g\.items\.some\(\(m\) => m\.note && !mark\(m\)\) \? \[\{ key: "b", header: "Basis"/);
  assert.match(r, /\.\.\.\(g\.items\.some\(\(m\) => bandPosition\(m\.label, m\.value, industry\)\) \? \[\{ key: "r", header: "Usual range"/);
});

test("LIVE8B-027 / 029: one market open is named, not counted; the footer's Feedback is underlined like its links", async () => {
  const src = read("src/components/SideMenus.tsx");
  assert.match(src, /export const marketsOpenText = \(open: string\[\], total: number\): string => \(open\.length === 1 \? `\$\{open\[0\]\} open` : `\$\{open\.length\}\/\$\{total\} markets open`\);/);
  assert.match(src, /marketsOpenText\(rows\.filter\(\(r\) => r\.st\.open\)\.map/);
  assert.match(read("src/styles.css"), /\.legal-links \.legal-feedback \{[^}]*text-decoration: underline;/);
});

test("LIVE8B-021: positioning shares in one precision; the total row's net and split left blank", async () => {
  const { pct } = await import("../src/lib/positioning.ts");
  assert.equal(pct(61), "61.0%");
  assert.equal(pct(65.94), "65.9%");
  assert.equal(pct(null), "–");
  const page = read("src/pages/PositioningPage.tsx");
  assert.match(page, /r\.id === "total" && k\.endsWith\("_net"\) \? null/);
  assert.match(page, /r\.id === "total" \? null : <span data-testid=\{`split-\$\{r\.id\}`\}>/);
});

test("LIVE8B-017: the peers' growth column says its span", () => {
  assert.match(read("src/components/CompanyPeers.tsx"), /header: "Sales growth, 3 yrs"/);
});

test("LIVE8B-023: a US company's next results day says expected", () => {
  assert.match(read("src/pages/Research.tsx"), /\{region === "US" \? "Results expected" : "Results on"\} \{resultDay\(nextResults\)\}/);
});

test("LIVE8A-025: the results day chips don't repeat today and tomorrow by date", () => {
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /\.filter\(\(d\) => !nearDays\(region\)\.includes\(d\.date\)\)/);
  assert.match(page, /const nearDays = \(region: Region\): string\[\] =>/);
});

test("LIVE8A-021: the Plans row for a theme's supplier links says what its CSV is", () => {
  assert.match(read("src/lib/plans.ts"), /\["supply_pro", "Supplier links in a theme, CSV"\]/);
});
