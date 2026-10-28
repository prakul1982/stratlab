// RC-6, the main review of the whole app as real people use it: what broke in the flows, the frontend's side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("an Indian symbol written with its exchange is the company's own symbol, in the address too (RC6-001, RC5-010)", async () => {
  const { register } = await import("node:module");
  register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
    try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
  globalThis.window = { STRATLAB_CONFIG: {}, location: { search: "" }, matchMedia: () => ({ matches: false, addEventListener() {} }) };
  let canonTicker;
  try { ({ canonTicker } = await import("../src/lib/research.ts")); } finally { delete globalThis.window; }
  for (const typed of ["TCS.NS", "tcs.bo", "TCS-EQ", "NSE:TCS", "nse : tcs", "BSE:TCS", "TCS"]) assert.equal(canonTicker("IN", typed), "TCS", typed);
  assert.equal(canonTicker("IN", "BAJAJ-AUTO"), "BAJAJ-AUTO");
  assert.equal(canonTicker("IN", "M&M"), "M&M");
  assert.equal(canonTicker("IN", "500325"), "500325");
  assert.equal(canonTicker("IN", ".NS"), ".NS");               // a lone affix is left as typed
  assert.equal(canonTicker("US", "BRK.B"), "BRK-B");           // the US rule is unchanged
  assert.equal(canonTicker("US", "aapl"), "AAPL");
});

test("a company that isn't in the chosen market offers the other market's match, not a dead end (RC6-002)", () => {
  const src = read("src/pages/Research.tsx");
  assert.match(src, /suggestions\(q, region === "IN" \? "US" : "IN"\)/);
  assert.match(src, /<span className="k-small k-muted">In \{region === "IN" \? "the United States" : "India"\}<\/span>/);
  // "an NSE symbol", not "a NSE symbol"
  assert.match(src, /isn't \$\{region === "IN" \? "an NSE symbol or BSE code" : "a US ticker"\} we know/);
});

test("a read that failed offers Try again as a button, not a line telling the person to reload (RC6-004)", () => {
  const news = read("src/components/NewslettersCard.tsx");
  assert.match(news, /<ErrorState title="Couldn't load your newsletter settings" action=\{\{ label: "Try again", onClick: \(\) => setTries\(\(n\) => n \+ 1\) \}\}>/);
  assert.match(news, /\}, \[tries\]\);/);
  const invite = read("src/pages/InvitePage.tsx");
  assert.match(invite, /<ErrorState title="Your invite link isn't available right now" action=\{\{ label: "Try again", onClick: \(\) => setTries\(\(n\) => n \+ 1\) \}\}>/);
  // a Try again button and a line saying to reload said it twice
  for (const f of ["src/pages/money/FundBehaviour.tsx", "src/pages/money/FundCosts.tsx"]) assert.doesNotMatch(read(f), /Reload the page to try again/);
  assert.doesNotMatch(read("src/components/NewslettersCard.tsx") + invite, /Reload the page to try again/);
});

test("the trend scan says its groups couldn't be loaded, with Try again, instead of an empty box and a toast (RC6-005)", () => {
  const src = read("src/pages/ResearchScans.tsx");
  assert.match(src, /const \[setsFailed, setSetsFailed\] = useState\(false\)/);
  assert.match(src, /\.catch\(\(\) => setSetsFailed\(true\)\);\n  \}, \[region, setsTry\]\);/);
  assert.match(src, /<ErrorState title="The groups to scan couldn't be loaded" action=\{\{ label: "Try again", onClick: \(\) => setSetsTry\(\(n\) => n \+ 1\) \}\}>/);
});

test("named holders whose first read fails offers Try again, where Dismiss left a page with nothing on it (RC6-006)", () => {
  const src = read("src/pages/HoldersPage.tsx");
  assert.match(src, /const \[readFailed, setReadFailed\] = useState\(false\)/);
  assert.match(src, /\}, \[q, off, tries\]\);/);
  assert.match(src, /<ErrorState title="Named holders couldn't be read" action=\{\{ label: "Try again", onClick: \(\) => setTries\(\(n\) => n \+ 1\) \}\}>/);
  // a failed action (follow, a name too short) keeps its Dismiss
  assert.match(src, /<ErrorState title="That didn't work" action=\{\{ label: "Dismiss"/);
});

test("a market value of a lakh crore or more has two decimals, as the company's public page writes it (RC6-008)", async () => {
  const { bigMoney } = await import("../src/lib/format.ts");
  assert.equal(bigMoney(18_945_500_000_000, "INR"), "₹18.95 lakh cr");     // was "₹18.9 lakh cr" beside the public page's ₹18.95 lakh crore
  assert.equal(bigMoney(11_035_200_000_000, "INR"), "₹11.04 lakh cr");     // was "₹11 lakh cr"
  assert.equal(bigMoney(1_510_000_000_000, "INR"), "₹1.51 lakh cr");
  assert.equal(bigMoney(999_999_000_000, "INR"), "₹1.00 lakh cr");      // 9,99,999 crore rounds up into the lakh-crore tier
  assert.equal(bigMoney(34_720_000_000, "INR"), "₹3,472 cr");              // the crore tier is unchanged
  assert.equal(bigMoney(4_870_000_000_000, "USD"), "$4.87T");
});

test("a refused file's reason stays on the page beside every upload, kept by one shared hook (RC6-010)", () => {
  const kit = read("src/components/kit/UploadButton.tsx");
  assert.match(kit, /export function useUploadProblem\(\)/);
  assert.match(kit, /e instanceof ApiError && \(e\.status === 400 \|\| e\.status === 422\) && e\.message/);
  // the server's refusal is kept; no connection, a plan limit or a server error stays a toast
  assert.match(kit, /return false;/);
  for (const f of ["src/pages/HoldingsPage.tsx", "src/pages/TaxReportPage.tsx", "src/pages/trade/JournalPage.tsx", "src/pages/money/TaxToolsPage.tsx",
    "src/pages/money/MutualFundsPage.tsx", "src/pages/money/UsTaxPage.tsx", "src/components/ConnectedAccounts.tsx"]) {
    const src = read(f);
    assert.match(src, /useUploadProblem\(\)/, f);
    assert.match(src, /if \(!refused\(e\)\) fail\(e\)|if \(!refused\(e\)\) fail\(e\);/, f);
    assert.match(src, /UploadProblem problem=\{problem\}|uploadError &&/, f);
  }
});

test("signing out also forgets the options structure being built, so the next person on the device isn't offered it (RC6-011)", async () => {
  const mk = () => { const m = new Map(); return { m, getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), key: (i) => [...m.keys()][i], get length() { return m.size; }, clear: () => m.clear() }; };
  const { register } = await import("node:module");
  register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
    try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
  const local = mk(), session = mk();
  globalThis.window = { STRATLAB_CONFIG: {}, location: { search: "" }, matchMedia: () => ({ matches: false, addEventListener() {} }) };
  globalThis.localStorage = local; globalThis.sessionStorage = session;
  try {
    const { OPTIONS_DRAFT, OPTIONS_NOTES } = await import("../src/lib/options.ts");
    const { clearLocalData } = await import("../src/lib/localData.ts");
    local.setItem(OPTIONS_DRAFT, "{\"underlying\":\"NIFTY\"}"); local.setItem(OPTIONS_NOTES, "[\"a leg changed\"]"); local.setItem("stratlab.theme", "dark");
    clearLocalData();
    assert.deepEqual([...local.m.keys()], ["stratlab.theme"]);
    assert.equal(OPTIONS_DRAFT, "stratlab.options.draft.v1");        // the page and the sign-out share one key
  } finally { delete globalThis.window; delete globalThis.localStorage; delete globalThis.sessionStorage; }
  assert.match(read("src/pages/OptionsPage.tsx"), /const DRAFT = OPTIONS_DRAFT, NOTES = OPTIONS_NOTES;/);
});

test("a P/E's note about a lifted quarter shows on the side-by-side page too (RC6-012)", () => {
  assert.match(read("src/pages/Research.tsx"), /const QUALIFIES = \/special\|like-for-like\|against a quarter\|other income\|n\\\/m\|not meaningful\/i;/);
});
