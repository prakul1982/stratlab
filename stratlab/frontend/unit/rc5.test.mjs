// RC-5, the main review of the whole app as real people use it: what broke in the flows, the frontend's side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a deep dive that fails to open offers Try again, like every other page's error (RC5-001)", () => {
  const src = read("src/pages/DeepDive.tsx");
  assert.match(src, /const \[tries, setTries\] = useState\(0\)/);
  // the reading starts again when the count changes
  assert.match(src, /\}, \[sym, region, tries\]\);/);
  assert.match(src, /<ErrorState title="The deep dive couldn't be opened" action=\{\{ label: "Try again", onClick: \(\) => setTries\(\(n\) => n \+ 1\) \}\}>/);
});

test("on a phone the tour waits for the menu to slide away before it points at the next thing (RC5-002)", () => {
  const src = read("src/components/Tour.tsx");
  // the step after the menu's own steps: the ring was placed where the menu's search button still was (on the page's heading)
  assert.match(src, /const \[sliding, setSliding\] = useState\(false\)/);
  assert.match(src, /const wasInMenu = useRef\(false\)/);
  assert.match(src, /if \(\(inMenu && !menuShown\) \|\| sliding\) return null;/);
  // it waits as long as the menu takes to come in
  assert.equal([...src.matchAll(/window\.setTimeout\(\(\) => set(MenuShown|Sliding)\((true|false)\), 320\)/g)].length, 2);
});

test("an IPO address no issue has says so and offers no Try again, which could never help (RC5-004)", () => {
  const src = read("src/pages/IpoPage.tsx");
  assert.match(src, /setGone\(e instanceof ApiError && e\.status === 404\)/);
  assert.match(src, /gone \? <ErrorState title="That IPO isn't on the list">/);
  // a read that fails for any other reason still offers it
  assert.match(src, /<ErrorState title="This IPO couldn't be read" action=\{\{ label: "Try again", onClick: \(\) => load\(\) \}\}>/);
});

test("the alerts summary reads in whole sentences, and the unconfirmed email is said once (RC5-005)", () => {
  const src = read("src/pages/AlertsPage.tsx");
  // was "Sent by This page only": a capital mid-sentence and a "by" that names no one
  assert.doesNotMatch(src, /Sent by <b>\{page\.channels\.length \?/);
  assert.match(src, /Shown <b>on this page only<\/b>/);
  assert.match(src, /Your email isn't confirmed, and no phone or Telegram is set up, so a fired alert is listed here and nowhere else\./);
  // the second note shows only when something else already receives the alerts
  assert.match(src, /\{page\.channels\.length > 0 && page\.email && !page\.email_confirmed && /);
});

test("a long message stays long enough to read, a short one as before (RC5-006)", async () => {
  const { register } = await import("node:module");
  register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
    try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
  const { toastMs } = await import("../src/lib/toastTime.ts");
  assert.equal(toastMs("Saved.", false), 4500);
  assert.equal(toastMs("Saved.", true), 9000);
  // the holdings upload's refusal, 190 characters: about 14 s, not 4.5
  const refusal = "We couldn't find the holdings in that file. It needs a column for the stock (symbol, ISIN or name) and one for the quantity. If your broker isn't listed, make a CSV with the columns Symbol, Quantity, Average price.";
  assert.ok(refusal.length > 190);
  assert.ok(toastMs(refusal, false) >= 12000 && toastMs(refusal, false) <= 15000, String(toastMs(refusal, false)));
  assert.equal(toastMs("x".repeat(2000), false), 15000);
  assert.match(fs.readFileSync(new URL("../src/lib/app.tsx", import.meta.url), "utf8"), /setTimeout\(\(\) => setToast\(null\), toastMs\(msg, !!action\)\)/);
});

test("with no connection the idea box says so, not that the AI builder is away (RC5-009)", () => {
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /err\.code === "network" \|\| err\.code === "no_backend"\s*\n\s*\? `\$\{err\.message\} The simple converter read your idea here/);
  assert.match(src, /Saving them as a notebook needs the connection\./);
  // the AI being away keeps its own words
  assert.match(src, /"The AI builder isn't available right now, so the simple converter read your idea/);
});

test("Paper trading starts a second session from its own page: an options strategy or a notebook (owner, 28 Oct)", () => {
  const src = read("src/pages/PaperPage.tsx");
  assert.match(src, /<CardHead title="Your sessions" actions=\{<NewSessionButtons \/>\} \/>/);
  assert.match(src, /<Link className="btn sm" to="\/options">Build an options strategy<\/Link>/);
  assert.match(src, /<Link className="btn quiet sm" to="\/notebooks">Paper trade a notebook<\/Link>/);
});
