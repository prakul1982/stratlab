// What the Holdings page sends for an edit, and how it names the dollar rate (review rev5a, B1 and item a). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dollarRate, editChange } from "../src/lib/holdingsEdit.ts";

const row = { symbol: "TCS", market: "IN", qty: 5, avg: 0 };      // an average of 0.004 shows as 0.00

test("B1: the edit form sends only the fields that changed, as one change", () => {
  assert.deepEqual(editChange(row, 5, 0), { op: "set", symbol: "TCS", market: "IN" });
  assert.deepEqual(editChange(row, 7, 0), { op: "set", symbol: "TCS", market: "IN", qty: 7 });
  assert.deepEqual(editChange(row, 5, 3100), { op: "set", symbol: "TCS", market: "IN", avg: 3100 });
  assert.deepEqual(editChange({ symbol: "AAPL", qty: 1, avg: 150 }, 1, null), { op: "set", symbol: "AAPL", market: "IN", avg: null });
});

test("B1: the page never sends the whole list it shows", () => {
  const page = readFileSync(new URL("../src/pages/HoldingsPage.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /body: \{ items \}/);
  assert.doesNotMatch(page, /current\(\)/);
  assert.match(page, /body: \{ changes \}/);
  assert.match(page, /op: "remove"/);
  assert.match(page, /op: "add"/);
});

test("item a: a dollar rate older than a day says its date", () => {
  const now = Date.parse("2026-10-12T06:00:00Z");
  assert.equal(dollarRate(88.2, "2026-10-12T01:00:00Z", now), "₹88.20 a dollar");
  assert.equal(dollarRate(88.2, null, now), "₹88.20 a dollar");
  assert.match(dollarRate(88.2, "2026-10-09T03:00:00Z", now), /^₹88\.20 a dollar \(the rate of 9 Oct 2026\)$/);
});

test("rev6a: a synced row's edit form says a typed quantity is kept and a typed average follows the broker's", async () => {
  const { syncedNote } = await import("../src/lib/holdingsEdit.ts");
  assert.equal(syncedNote("kite"), "Synced from Kite. A quantity you type is kept: the shares above Kite's are kept as your own, " +
    "through its next read. An average price typed alone is replaced by Kite's average on its next read.");
  assert.match(syncedNote("cas"), /^From your depository statement\. The next statement sets the quantity and average/);
  const page = readFileSync(new URL("../src/pages/HoldingsPage.tsx", import.meta.url), "utf8");
  assert.match(page, /row\.via && <p className="k-note" data-testid="synced-note">\{syncedNote\(row\.via\)\}/);
  assert.match(page, /r\.notes\?\.length/);
});
