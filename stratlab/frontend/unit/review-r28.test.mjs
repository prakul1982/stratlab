// Round 28, India after the close: the final live breadth title, the sector table's day, My Stocks prices with their sign,
// and the journal's date line. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { liveTag, liveTitle, sectorColumnLabel } from "../src/lib/breadthLive.ts";
import { itemCurrency } from "../src/lib/newsPrice.ts";
import { price } from "../src/lib/format.ts";
import { journalSavedNote } from "../src/lib/journalTax.ts";

test("after the close the live card says final at the newest point's time", () => {
  assert.equal(liveTitle({ as_of: "15:30", state: "final" }), "Today, final at 15:30");
  assert.equal(liveTitle({ as_of: "10:45", state: "live" }), "Today, live as of 10:45");
  assert.equal(liveTag({ state: "final" }).text, "Final");
});

test("the sector table's newest column names its day", () => {
  const short = (iso) => `${Number(iso.slice(8))} Oct`;
  assert.equal(sectorColumnLabel({ label: "Today", day: "2026-10-14" }, short), "Latest · 14 Oct");
  assert.equal(sectorColumnLabel({ label: "1 week ago", day: "2026-10-08" }, short), "1 week ago");
});

test("My Stocks prices carry their currency sign", () => {
  assert.equal(price(925.4, itemCurrency("IN"), 2), "₹925.40");
  assert.equal(price(341.27, itemCurrency("US"), 2), "$341.27");
  assert.equal(price(123456.5, itemCurrency("IN"), 2), "₹1,23,456.50");
});

test("the journal's date line says it is the journal's own date", () => {
  const fmt = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7);
  const t = journalSavedNote("2026-10-15", "2026-10-09T10:00:00Z", fmt);
  assert.match(t, /journal last changed 09\/10/);
  assert.match(t, /tax report has its own date/);
  assert.equal(journalSavedNote("2026-10-15", null, fmt), "Worked out as of 15/10.");
});

test("Money home says when the files were uploaded and how far the trades go, not 'Trades as of' the upload time", async () => {
  const { uploadedLine } = await import("../src/lib/journalTax.ts");
  const fmt = (iso) => ({ "2026-10-04T09:05:00+00:00": "4 Oct 2026", "2025-06-27": "27 Jun 2025" })[iso];
  assert.equal(uploadedLine("2026-10-04T09:05:00+00:00", "2025-06-27", fmt), "Uploaded 4 Oct 2026 · trades up to 27 Jun 2025");
  assert.equal(uploadedLine(null, "2025-06-27", fmt), "Trades up to 27 Jun 2025");
  assert.equal(uploadedLine("2026-10-04T09:05:00+00:00", null, fmt), "Uploaded 4 Oct 2026");
});
