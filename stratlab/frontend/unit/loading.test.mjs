// Owner, 5 Nov: "put loading bar everywhere, it's a major issue, it creates confusion whether something is working or not". One moving
// bar along the top of the screen while any call to the server is out past a short wait, the same bar at the top of every card's loading
// placeholder, and work still running behind a page shown as that bar with one line (no warning boxes).
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("every call to the server drives the top loading bar, which the app draws on every signed-in page", () => {
  assert.match(read("src/lib/api.ts"), /export function api<T = any>\(path: string, opts: Opts = \{\}\): Promise<T> \{\n  callStarted\(\);\n  return send<T>\(path, opts\)\.finally\(callEnded\);/);
  assert.match(read("src/lib/inflight.ts"), /export function callStarted\(\): void \{ out \+= 1; watchers\.forEach\(\(f\) => f\(out\)\); \}/);
  const top = read("src/components/TopProgress.tsx");
  assert.match(top, /export const SHOW_AFTER_MS = (\d+);/);
  assert.ok(Number(top.match(/SHOW_AFTER_MS = (\d+)/)[1]) <= 400, "a wait shows the bar within 0.4 s");
  assert.match(top, /const stop = onCount\(on\);/);
  assert.match(read("src/components/Shell.tsx"), /<TopProgress \/>/);
  assert.match(read("src/styles.css"), /@media \(prefers-reduced-motion: reduce\) \{ \.top-progress > span \{/);
});

test("every card's loading placeholder starts with the moving bar; work still running is the bar and one line", () => {
  assert.match(read("src/components/kit/States.tsx"), /aria-busy="true" aria-label=\{label\}>\n\s+\{\/\*[^\n]*\*\/\}\n\s+<span className="k-working-bar" aria-hidden="true"><span \/><\/span>/);
  assert.match(read("src/components/kit/States.tsx"), /export function Working\(/);
  for (const f of ["src/pages/ThemesPage.tsx", "src/components/ThemeDive.tsx", "src/components/HoldingsActions.tsx", "src/pages/money/TaxToolsPage.tsx"])
    assert.match(read(f), /<Working /, f);
  assert.doesNotMatch(read("src/pages/ThemesPage.tsx"), /The AI is still sorting these companies/);
});
