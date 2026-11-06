// The MONEY lane (Instinct deep QA, 1–2 Nov): imports, holdings, first clicks and small money fixes — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("MONEY-2: a holdings file adds by default, and Start again asks first, naming the count it replaces", () => {
  const p = read("src/pages/HoldingsPage.tsx");
  assert.match(p, /useState<"replace" \| "add">\("add"\)/);
  // R15 #4 (changed on purpose): the choice shows once a file is picked, and is asked then
  assert.match(p, /if \(mode === "replace" && rows\.some\(\(r\) => !isUS\(r\)\)\) \{ setReplacing\(f\)/);
  assert.match(p, /title="Start again with this file\?" confirmLabel="Replace my holdings"/);
  assert.match(p, /This replaces your \{held\}/);
});

test("MONEY-6a: the holdings upload names what it saved, shows the accepted columns on a refusal, and never says failure over a save", () => {
  const p = read("src/pages/HoldingsPage.tsx");
  assert.match(p, /label="Stocks saved from this file"/);
  assert.match(p, /data-testid="holdings-format">A file of your own needs the columns <b>Symbol<\/b> \(or ISIN\), <b>Quantity<\/b> and <b>Average price<\/b>/);
  assert.match(p, /couldn't be opened here, so nothing was sent and your holdings are unchanged/);
  assert.match(p, /if \(!refused\(e\)\) \{ fail\(e\); load\(\); \}/);
});

test("MONEY-6b/6c: the dividends tab opens its year once per reply (no state set inside another's updater), keys rows uniquely and names the file read", () => {
  const p = read("src/pages/money/TaxToolsPage.tsx");
  assert.doesNotMatch(p, /setFy\(\(cur\) => \{[^}]*setMovedFrom/);
  assert.match(p, /show\(r\.dividends, true\)/);
  assert.match(p, /rowKey=\{\(c, i\) => `\$\{c\.country\}:\$\{c\.symbol\}:\$\{i\}`\}/);
  assert.match(p, /setNote\(`\$\{f\.name\}: \$\{r\.added\} dividend/);
  assert.match(p, /const savedFrom = `Saved from \$\{v\.files\.map\(\(f\) => f\.name\)\.join\(", "\)\}\.`/);
});

test("MONEY-3: files are saved by one helper (in the page while clicked, address kept, an empty file an error), and Enter on a picked stock sends its form", () => {
  const s = read("src/lib/share.ts");
  assert.match(s, /if \(!blob\.size\) throw new Error\("The file came back empty\. Try again\."\)/);
  assert.match(s, /document\.body\.appendChild\(a\);\n  a\.click\(\);\n  a\.remove\(\);\n  setTimeout\(\(\) => URL\.revokeObjectURL\(a\.href\), 60_000\)/);
  for (const p of ["src/pages/money/ItrExportPage.tsx", "src/pages/TaxReportPage.tsx", "src/pages/money/NetWorthPage.tsx", "src/pages/money/UsTaxPage.tsx"]) {
    const src = read(p);
    assert.match(src, /import \{ download as saveFile \} from "[./]+lib\/share";/, p);
    assert.doesNotMatch(src, /URL\.createObjectURL\(await r\.blob\(\)\)/, p);
  }
  assert.match(read("src/components/kit/StockPicker.tsx"), /if \(!typed && !open && text\.trim\(\) && !clearOnPick\) return;\n      e\.preventDefault\(\);/);
});

test("MONEY-4: a fold asked open later opens, and the stopped sessions are open when none is running", () => {
  assert.match(read("src/components/Earlier.tsx"), /useEffect\(\(\) => \{ if \(open\) setShown\(true\); \}, \[open\]\);/);
  assert.match(read("src/pages/PaperPage.tsx"), /<Earlier label="Stopped sessions" count=\{stopped\.length\} open=\{!current\.length \|\| /);
});

test("MONEY-5: money forms say what is needed up front; funds at cost wait for a NAV; dividends on one date basis; Schedule FA says its rate and dividend source", () => {
  const nw = read("src/pages/money/NetWorthPage.tsx");
  assert.match(nw, /data-testid="entry-needed">Every box is needed unless it says optional\.<\/p>/);
  assert.match(nw, /aria-required=\{!f\.optional \|\| undefined\}/);
  const mf = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(mf, /const base = t \? t\.invested_priced \?\? t\.invested : 0;/);
  assert.match(mf, /at cost from your statement: \$\{t\.no_nav === 1 \? "its value waits" : "their values wait"\} for a NAV/);
  assert.match(read("src/components/HoldingsActions.tsx"), /k: "Last 12 months \(estimated\)", v: inr\(data\.received_total\), n: "by record date"/);
  const us = read("src/pages/money/UsTaxPage.tsx");
  assert.match(us, /The initial value is the lot's cost at Rule 115's rate/);
  assert.match(us, /FA_INCOME_FROM\[r\.income_from\]/);
});
