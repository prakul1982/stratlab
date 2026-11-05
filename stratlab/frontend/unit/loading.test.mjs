// Owner, 5 Nov: "put loading bar everywhere, it's a major issue, it creates confusion whether something is working or not": a moving bar
// at the top of every card's loading placeholder, and work still running behind a page shown as that bar with one line (no warning
// boxes). The bar along the top of the screen that came with it was taken out the same day ("remove the top one, keep the rest").
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("no bar along the top of the screen (owner, 5 Nov: \"remove the top one, keep the rest\"): a wait shows in its own card", () => {
  assert.doesNotMatch(read("src/components/Shell.tsx"), /TopProgress/);
  assert.doesNotMatch(read("src/styles.css"), /\.top-progress/);
});

test("every card's loading placeholder starts with the moving bar; work still running is the bar and one line", () => {
  assert.match(read("src/components/kit/States.tsx"), /aria-busy="true" aria-label=\{label\}>\n\s+\{\/\*[^\n]*\*\/\}\n\s+<span className="k-working-bar" aria-hidden="true"><span \/><\/span>/);
  assert.match(read("src/components/kit/States.tsx"), /export function Working\(/);
  for (const f of ["src/pages/ThemesPage.tsx", "src/components/ThemeDive.tsx", "src/components/HoldingsActions.tsx", "src/pages/money/TaxToolsPage.tsx"])
    assert.match(read(f), /<Working /, f);
  assert.doesNotMatch(read("src/pages/ThemesPage.tsx"), /The AI is still sorting these companies/);
});
