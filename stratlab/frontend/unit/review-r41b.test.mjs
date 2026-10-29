// 16-17 Oct live reviews, small fixes (fix41b). Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const { compareGap } = await import("../src/lib/legacyRun.ts");
const { notebookTitle, withBrand } = await import("../src/lib/title.ts");
const { greetingAt, hourIn } = await import("../src/lib/greeting.ts");
const { MOVES_LABEL, MOVES_TITLE } = await import("../src/lib/breadthLive.ts");
const { holderRowName } = await import("../src/lib/researchFormat.ts");

test("the sign-in modal links Terms and Privacy under the Google button", () => {
  const src = read("src/pages/Login.tsx");
  assert.match(src, /By continuing you agree to the <Link className="link" to="\/terms">Terms<\/Link> and <Link className="link" to="\/privacy">Privacy policy<\/Link>/);
  assert.ok(src.indexOf("By continuing you agree to the") > src.indexOf("<Dialog title="), "inside the dialog");
});

test("the Terms say rupees for now, as the Plans page does, and anything else only where the Plans page says so", () => {
  const legal = read("src/content/legal.ts");
  assert.doesNotMatch(legal, /or in your own currency where the Plans page says so/);
  assert.match(legal, /in Indian rupees for now, and in another currency only where the Plans page says so/);
  assert.match(legal, /"\/terms": "16 October 2026"/);          // the date the wording changed
});

test("a run page and the compare page have their own tab titles, not the notebook's", () => {
  assert.equal(withBrand(notebookTitle("52wkLowVolBuy")), "52wkLowVolBuy · StratLab");
  assert.equal(withBrand(notebookTitle("52wkLowVolBuy", "Run v2")), "Run v2 · 52wkLowVolBuy · StratLab");
  assert.equal(withBrand(notebookTitle("52wkLowVolBuy", "Compare runs")), "Compare runs · 52wkLowVolBuy · StratLab");
  assert.equal(notebookTitle(undefined, "Run v2"), null);          // nothing until the notebook has loaded
  assert.match(read("src/pages/ExperimentPage.tsx"), /useNotebook\(id, `Run v\$\{v\}`\)/);
  assert.match(read("src/pages/CompareExperiments.tsx"), /useNotebook\(id, "Compare runs"\)/);
});

test("the compare page counts hidden runs apart from the ones that can be compared", () => {
  assert.equal(compareGap(1, 1), "Comparing needs two runs of this notebook whose figures are shown. One run can be compared; 1 more is hidden because its figures don't add up. Change one thing and run it again.");
  assert.match(compareGap(1, 3), /One run can be compared; 3 more are hidden because their figures don't add up/);
  assert.match(compareGap(0, 2), /No run can be compared yet; 2 are hidden because their figures don't add up/);
  assert.equal(compareGap(1, 0), "Comparing needs two runs of this notebook. It has one so far: change one thing and run it again.");
  assert.equal(compareGap(0, 0), "Comparing needs two runs of this notebook. It has none yet.");
});

test("the My space greeting follows the hour: Hello in the small hours, never Good morning at 00:20", () => {
  assert.equal(greetingAt(0), "Hello");
  assert.equal(greetingAt(4), "Hello");
  assert.equal(greetingAt(5), "Good morning");
  assert.equal(greetingAt(11), "Good morning");
  assert.equal(greetingAt(12), "Good afternoon");
  assert.equal(greetingAt(16), "Good afternoon");
  assert.equal(greetingAt(17), "Good evening");
  assert.equal(greetingAt(21), "Good evening");
  assert.equal(greetingAt(22), "Hello");
  assert.equal(greetingAt(23), "Hello");
  const at = new Date("2026-10-16T18:50:00Z");                    // 00:20 IST on the 17th
  assert.equal(greetingAt(hourIn("Asia/Kolkata", at)), "Hello");
  assert.equal(greetingAt(hourIn("UTC", at)), "Good evening");     // the same instant in another zone
});

test("the whole promoter group is not labelled like the largest named holder", () => {
  assert.equal(holderRowName("Promoters"), "Promoter group total");
  assert.equal(holderRowName("FIIs"), "FIIs");
  assert.match(read("src/components/Research.tsx"), /cell: \(r\) => holderRowName\(r\.label\)/);
});

test("the breadth big-move counts say what they count", () => {
  assert.equal(MOVES_LABEL, "Stocks up 4% or more / down 4% or more on the day");
  assert.equal(MOVES_TITLE, "Stocks up 4% or more and down 4% or more, each day");
  const page = read("src/pages/BreadthPage.tsx");
  assert.match(page, /lab\(MOVES_LABEL, help\.moves\)/);
  assert.match(page, /<Box title=\{MOVES_TITLE\}/);
});
