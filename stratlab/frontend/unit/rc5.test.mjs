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
