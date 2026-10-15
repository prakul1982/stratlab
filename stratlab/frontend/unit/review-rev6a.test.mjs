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
