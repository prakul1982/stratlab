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
