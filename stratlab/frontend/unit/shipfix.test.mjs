// Ship fixes (29 Oct): what the merged tree needed so a policy page stays small. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R5V-020: the consent banner's file does not import the plans, so a policy page doesn't download them", () => {
  assert.doesNotMatch(read("src/lib/ads.ts"), /from "\.\/plans"/);
  assert.match(read("src/lib/houseAds.ts"), /import \{ LIMITS \} from "\.\/plans";/);
  assert.match(read("src/components/AdUnit.tsx"), /import \{ houseCard \} from "\.\.\/lib\/houseAds";/);
  const vite = read("vite.config.ts");
  assert.match(vite, /\{ name: "plans", test: \/src\[\\\\\/\]lib\[\\\\\/\]plans\\\.ts\$\/ \}/);
  assert.doesNotMatch(vite, /name: "common", test: [^\n]*\|plans\)/);
});

test("VR5-011: the plan table's Free column is wide enough at 390px for the trial note to be two lines", () => {
  assert.match(read("src/styles.css"), /@media \(min-width: 381px\) and \(max-width: 410px\) \{[^@]*\.k-compare \.k-table td:nth-child\(2\) \{ min-width: 74px; \}/);
});
