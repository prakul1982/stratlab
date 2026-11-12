// Release 43: a theme's companies as a CSV is a download, so Basic and up (plans.py "theme_workbook", the theme's downloads). The server
// makes the file and answers 402 for Free (backend tests/test_theme_csv_gate.py); the page shows Free the plan note instead of asking.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("the theme's CSV comes from the server and is locked on Free with the Basic plan note", () => {
  const dive = read("src/components/ThemeDive.tsx");
  assert.match(dive, /<ThemeCsvButton region=\{region\} theme=\{theme\} dive=\{dive\} \/>/);
  assert.doesNotMatch(dive, /<CsvButton name=\{`theme /);                // no longer made in the browser for every plan
  const btn = read("src/components/ThemeChanges.tsx");
  const fn = btn.slice(btn.indexOf("export function ThemeCsvButton"));
  assert.match(fn, /features as Record<string, boolean> \| undefined\)\?\.theme_workbook === false/);
  assert.match(fn, /if \(off\) \{ setLocked\(true\); return; \}/);             // Free: the note, no request
  assert.match(fn, /\/research\/theme-dive\/companies\.csv\?region=\$\{region\}&q=\$\{encodeURIComponent\(theme\)\}/);
  assert.match(fn, /<PlanNote plan="basic">Downloading a theme's companies as a CSV is on the Basic plan/);
  // the comparison table's row for the theme's downloads says the CSV too
  assert.match(read("src/lib/planFeatures.ts"), /\["theme_workbook", "A theme as an Excel workbook: [^"]*, and its companies as a CSV", "basic"\]/);
});
