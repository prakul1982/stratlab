// Admin → Prices: the exchange-rate line names each rate's own read time (review rev6a, item 4). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { ratesRead } from "../src/pages/admin/prices.ts";

const ago = (t) => `at ${t.slice(0, 10)}`;

test("rev6a: the rates line moves with the newest read and names the rates kept from an older one", () => {
  assert.equal(ratesRead({}, ago), "Exchange rates not read yet: the built-in amounts are shown.");
  assert.equal(ratesRead({ USD: "2026-10-03T06:00", GBP: "2026-10-03T06:00" }, ago), "Exchange rates read at 2026-10-03.");
  assert.equal(ratesRead({ USD: "2026-10-03T06:00", EUR: "2026-10-02T06:00", AUD: "2026-10-01T06:00", JPY: "2026-10-01T06:00" }, ago),
    "Exchange rates read at 2026-10-03; AUD, JPY at 2026-10-01; EUR at 2026-10-02.");
});

test("rev6a: the US trades and dividends imports say how dates that read either way were read", async () => {
  const { readFileSync } = await import("node:fs");
  for (const f of ["UsTaxPage.tsx", "TaxToolsPage.tsx"]) {
    const page = readFileSync(new URL(`../src/pages/money/${f}`, import.meta.url), "utf8");
    assert.match(page, /r\.date_note \? ` \$\{r\.date_note\}`/);
  }
});

test("mo1: the US trades card says in one line which files work, names the realised-gains report, and shows the upload's own note", async () => {
  const { readFileSync } = await import("node:fs");
  const page = readFileSync(new URL("../src/pages/money/UsTaxPage.tsx", import.meta.url), "utf8");
  assert.match(page, /data-testid="us-upload-help">A trade list \(CSV or Excel\) from your broker, or a realised-gains tax report such as Vested's yearly tax report \(the \.xlsx\)\.<\/p>/);
  assert.equal((page.match(/realised-gains/g) ?? []).length, 1);                      // one explanation, not two
  assert.match(page, /\$\{r\.note \? ` \$\{r\.note\}` : ""\}/);
  assert.match(page, /accept="\.csv,\.xlsx,\.txt,text\/csv"/);                         // .xls is not read, so it is not offered
  assert.doesNotMatch(page, /Drive ?Wealth/i);
});
