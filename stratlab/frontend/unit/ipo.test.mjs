// IPOs (Invest → IPOs): the helpers the two pages use, where the section is registered (menu, search, All features, deep links,
// plan gates), and the rules the pages keep (kit components, no vendor names, no advice words).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const ipo = await import("../src/lib/ipoText.ts");

test("a price band, a single price and a US range are written in their own currency", () => {
  assert.equal(ipo.bandText({ low: 153, high: 162, currency: "INR" }), "₹153 to ₹162");
  assert.equal(ipo.bandText({ low: 94, high: 94, currency: "INR" }), "₹94");
  assert.equal(ipo.bandText({ low: 14, high: 16, currency: "USD" }), "$14.00 to $16.00");
  assert.equal(ipo.bandText({ price: 16, currency: "USD" }), "$16.00");
  assert.equal(ipo.bandText({ currency: "INR" }), "–");
});

test("an issue's size is in rupees crore in India and in dollars in the US", () => {
  assert.equal(ipo.sizeText({ size: 275.4, currency: "INR", market: "IN" }), "₹275 cr");
  assert.equal(ipo.sizeText({ size: 150000000, currency: "USD", market: "US" }), "$150 million");
  assert.equal(ipo.sizeText({ size: 1500000000, currency: "USD", market: "US" }), "$1.5 billion");
  assert.equal(ipo.sizeText({ currency: "INR", market: "IN" }), "–");
});

test("dates: a span, an expected day and one not yet published", () => {
  assert.equal(ipo.spanText("2026-10-28", "2026-10-30"), "28 Oct to 30 Oct 2026");
  assert.equal(ipo.spanText("2026-10-28", "2026-10-28"), "28 Oct 2026");
  assert.equal(ipo.expectedText("2026-11-04", true), "4 Nov 2026 (expected)");
  assert.equal(ipo.expectedText("2026-11-04", false), "4 Nov 2026");
  assert.equal(ipo.expectedText(null, false), "Not published yet");
});

test("bids are counted in times, with the decimals a small count needs", () => {
  assert.equal(ipo.timesText(46.06), "46.06 times");
  assert.equal(ipo.timesText(12.34), "12.34 times");
  assert.equal(ipo.timesText(5.91), "5.91 times");
  assert.equal(ipo.timesText(135.9), "136 times");
  assert.equal(ipo.timesText(null), "–");
});

test("a change against the issue price keeps its sign and names the price", () => {
  assert.equal(ipo.againstIssue(9.2, { price: 586, currency: "INR" }), "+9.2% on ₹586.00");
  assert.equal(ipo.againstIssue(-4.4, { price: 16, currency: "USD" }), "−4.4% on $16.00");
  assert.equal(ipo.againstIssue(null, { price: 16, currency: "USD" }), "–");
});

test("the US has no Open tab: it has no public bidding window", () => {
  assert.deepEqual(ipo.tabsFor("IN").map((t) => t.value), ["upcoming", "open", "closed", "listed"]);
  assert.deepEqual(ipo.tabsFor("US").map((t) => t.value), ["upcoming", "closed", "listed"]);
  assert.match(ipo.TAB_LINE.US.upcoming, /no public bidding window/);
  assert.doesNotMatch(ipo.TAB_LINE.IN.open, /5 PM/);          // no time is written that the exchange's page did not give (RC2A-004)
});

test("the section is in the menu, ⌘K and All features, and its pages are app addresses", async () => {
  const { ALL_PAGES, locate, NAV } = await import("../src/lib/nav.ts");
  const at = ALL_PAGES.find((x) => x.page.to === "/invest/ipos");
  assert.ok(at && at.space === "invest" && at.group.id === "company-news");
  assert.equal(locate("/invest/ipos/in-bonfig").page.to, "/invest/ipos");                        // an issue's page is part of the IPOs page
  assert.match(at.page.words, /drhp/); assert.match(at.page.words, /price band/); assert.match(at.page.words, /subscription/);
  assert.equal(at.page.flag, "ipo_alerts");
  assert.ok(NAV.invest.groups.find((g) => g.id === "company-news").pages.some((p) => p.to === "/invest/ipos"));
  const { isAppPath } = await import("../src/lib/deepLinks.ts");
  assert.ok(isAppPath("/invest/ipos") && isAppPath("/invest/ipos/us-1273626-119431"));
  const { match } = await import("../src/lib/features.ts");
  assert.ok(match("initial public offering").some((f) => f.to === "/invest/ipos") || match("ipo").some((f) => f.to === "/invest/ipos"));
});

test("alerts and the summary are on Basic, and the pages say so where they lock", async () => {
  const { planOf, FLAGS } = await import("../src/lib/plans.ts");
  assert.equal(planOf("ipo_summary"), "basic");
  assert.equal(planOf("ipo_alerts"), "basic");
  assert.ok(FLAGS.some(([f]) => f === "ipo_alerts") && FLAGS.some(([f]) => f === "ipo_summary"));
  const { gateFor } = await import("../src/lib/gates.ts");
  assert.deepEqual(gateFor("/invest/ipos"), { feature: "ipo_alerts", whole: false });
  assert.deepEqual(gateFor("/invest/ipos/in-bonfig"), { feature: "ipo_summary", whole: false });
  const list = read("src/pages/IposPage.tsx"), one = read("src/pages/IpoPage.tsx");
  assert.match(list, /<PlanNote plan="basic">IPO alerts are on the/);                                // the one lock note, not a hand-made one
  assert.match(one, /<PlanNote plan="basic">The summary of the offer document is on the/);
  assert.match(one, /LockedPreview/);
});

test("the pages are built from the kit and keep the product rules", () => {
  for (const f of ["src/pages/IposPage.tsx", "src/pages/IpoPage.tsx", "src/lib/ipo.ts", "src/lib/ipoText.ts"]) {
    const src = read(f);
    assert.doesNotMatch(src, /<table|style=\{\{/, `${f} builds its own table or inline style`);
    assert.doesNotMatch(src, /yahoo|finnhub|screener|nasdaq\.com|edgar|kite connect/i, `${f} names a data vendor`);
    assert.doesNotMatch(src.replace(/Facts, not advice/g, ""), /\b(buy|sell|accumulate|undervalued|grey market|gmp|apply now|should you)\b/i, `${f} has advice words`);
  }
  const list = read("src/pages/IposPage.tsx");
  assert.match(list, /DataTable stack/); assert.match(list, /<Seg label="Market"/); assert.match(list, /useLiveRefresh/);
  assert.match(list, /no Open tab/);
  const one = read("src/pages/IpoPage.tsx");
  assert.match(one, /useLiveRefresh\(d\?\.ipo\.stage === "open"/);                                 // the bids move while the issue is open
  assert.match(one, /The document's words/);                                                          // each summary statement shows its quote
});

test("an issue that did not go ahead says which way, and has no stage of its own among the tabs (MEM1 B)", () => {
  assert.deepEqual(ipo.tabsFor("IN").map((t) => t.value), ["upcoming", "open", "closed", "listed"]);
  assert.equal(ipo.badgeOf({ stage: "withdrawn", issue_status: "postponed" }).word, "Postponed");
  assert.equal(ipo.badgeOf({ stage: "withdrawn", issue_status: "cancelled" }).word, "Cancelled");
  assert.equal(ipo.badgeOf({ stage: "withdrawn" }).word, "Withdrawn");
  assert.equal(ipo.badgeOf({ stage: "social" }).word, "Fund raise");   // VR1-121: a short badge; "not an IPO" is in the section title and the issue note
  assert.equal(ipo.badgeOf({ stage: "closed" }).word, "Closed, not listed yet");
  const page = read("src/pages/IposPage.tsx");
  assert.match(page, /d\.tabs\.withdrawn/);
  assert.match(page, /d\.tabs\.social/);
  assert.match(read("src/pages/IpoPage.tsx"), /badgeOf\(r\)/);
});

test("a size with a part in rupees and a part in shares shows both parts, then the total at the top of the band (MEM1 B)", () => {
  const parts = { fresh_cr: 500, ofs: 10000000 };
  assert.equal(ipo.partsText(parts), "Fresh ₹500 cr + offer for sale of 1,00,00,000 shares");
  assert.equal(ipo.partsText({ ofs_cr: 200, fresh: 5000000 }), "Fresh 50,00,000 shares + offer for sale of ₹200 cr");
  // no band yet: no total, so the parts stand where the size would be; the rupee part alone is never the size
  assert.equal(ipo.sizeText({ currency: "INR", market: "IN", size_parts: parts }), "Fresh ₹500 cr + offer for sale of 1,00,00,000 shares");
  // the band known: the server's total shows as the size, the parts under it
  assert.equal(ipo.sizeText({ size: 600, currency: "INR", market: "IN", size_parts: parts }), "₹600 cr");
  assert.match(read("src/pages/IpoPage.tsx"), /partsText\(r\.size_parts\)\}, \$\{r\.size_basis\}/);
});
