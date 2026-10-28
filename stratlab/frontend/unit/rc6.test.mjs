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
