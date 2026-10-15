import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("rev10b: the journal's note says how it pairs trades and the one charges difference left", async () => {
  const { journalVsTax } = await import("../src/lib/journalTax.ts");
  const text = journalVsTax(false).join(" ");
  assert.match(text, /from flat to flat/);
  assert.match(text, /average price of its purchases and of its sales/);
  assert.doesNotMatch(text, /The journal pairs each purchase with the sales that close it, first in, first out/);
  // the same rupees where the file lists charges, and the difference that remains said as it is
  assert.match(text, /the journal takes off the same rupees as the tax report/);
  assert.match(text, /Tradebook trades whose file has neither charges nor STT columns are charged here at the published rates, STT included, while the tax report takes off none for them/);
  assert.match(text, /A sale line that a tradebook also has is counted once, the way the tax report counts it/);
});

test("rev10b: US share sales are labelled apart from the Indian totals", async () => {
  const { gainLabel, usSharesNote } = await import("../src/lib/usGains.ts");
  assert.equal(gainLabel("st", false), "Short-term gains (net)");
  assert.equal(gainLabel("lt", true), "Long-term gains, Indian shares and funds (net)");
  const fmt = (v) => `₹${v}`;
  assert.equal(usSharesNote(500, -20, fmt), "US shares, not in these totals: short-term ₹500, long-term ₹-20 (net).");
  assert.equal(usSharesNote(null, undefined, fmt), null);
  const report = read("src/pages/TaxReportPage.tsx");
  assert.match(report, /label=\{gainLabel\("st", !!y\.foreign\)\}/);
  assert.match(report, /usSharesNote\(y\.foreign\.st\.net, y\.foreign\.lt\.net, inr\)/);
  const tools = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(tools, /usSharesNote\(ex\.realised_us_st_net, ex\.realised_us_lt_net, inr\)/);
});

test("rev10b: section 234B says whether it has stopped or is still growing", async () => {
  const { b234Note } = await import("../src/lib/advanceTax.ts");
  const fmt = (v) => `₹${v}`;
  assert.equal(b234Note({ months: 2, until: "2026-05-10", fully_paid: true, self_assessment: 100000, unpaid: 0 }, fmt), "2 months, to May 2026; paid in full, so it stops there");
  assert.equal(b234Note({ months: 7, until: "2026-10-15", to_today: true, unpaid: 50000, self_assessment: 50000 }, fmt),
    "7 months, to October 2026; ₹50000 still unpaid, so it goes up each month until paid");
  assert.equal(b234Note({ months: 4, until: "2026-07-31", unpaid: 100000 }, fmt), "4 months, to July 2026, as if the rest is paid by the return's due date");
  assert.match(read("src/pages/money/TaxToolsPage.tsx"), /<Stat label="Interest \(234B\)" value=\{inr\(s\.b234\.interest\)\} tone="down" note=\{b234Note\(s\.b234, inr\)\} \/>/);
});

test("rev10b: a failed reload of the US tax page shows an error with Try again, not the old figures under a toast", () => {
  const page = read("src/pages/money/UsTaxPage.tsx");
  assert.match(page, /\.catch\(\(e\) => \{ if \(n === seq\.current\) setReloadError\(\{ message: \(e as Error\)\.message, fy, cy \}\); \}\)/);
  assert.match(page, /<ErrorState title="These figures couldn't be updated" action=\{\{ label: "Try again", onClick: \(\) => load\(reloadError\.fy, reloadError\.cy\) \}\}>/);
  assert.match(page, /\{v && v\.trades\.length > 0 && y && !reloadError && \(/);
  assert.doesNotMatch(page, /if \(n === seq\.current\) fail\(e\)/);
});

test("rev10b: Schedule FA's missing-price line fits a lot sold in the year", () => {
  assert.match(read("src/pages/money/UsTaxPage.tsx"), /their peak value, and the closing value of shares still held on 31 December, are blank/);
});
