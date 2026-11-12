// The customer and supplier map (lane b2): the card's sections in their order, the lock line, the facts line and the CSV rows,
// and where the card, the theme panel and the Admin queue are wired in. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const L = await import("../src/lib/companyLinks.ts");

const row = (o) => ({ id: "x", group: "names_customers", relation: "Names as customers", name: "Bharat Electronics Limited", symbol: "BEL", region: "IN",
  basis: "Order win", amount: "Rs 450 crore", quote: "received an order worth Rs 450 crore from Bharat Electronics Limited", said_on: "2026-11-10",
  doc_url: "https://nsearchives.nseindia.com/o.pdf", doc_title: "Receipt of order", method: "rule", as_filed: false, ...o });

test("the card's sections come in a fixed order and keep the server's order inside each", () => {
  assert.deepEqual(L.GROUPS.map((g) => g.title), ["Names as customers", "Named as a supplier by", "Names as suppliers", "Named as a customer by"]);
  const items = [row({ id: "a" }), row({ id: "b", group: "named_supplier_by" }), row({ id: "c" })];
  assert.deepEqual(L.inGroup(items, "names_customers").map((i) => i.id), ["a", "c"]);
  assert.deepEqual(L.inGroup(items, "names_suppliers"), []);
});

test("the lock line names how many links and the plan; the facts line and CSV say what the card says", () => {
  assert.equal(L.lockedText(1, "Basic"), "1 more link is on the Basic plan, each with its quote and source.");
  assert.equal(L.lockedText(4, "Basic"), "4 more links are on the Basic plan, each with its quote and source.");
  assert.equal(L.factsLine(row()), "Order win · Rs 450 crore");
  assert.equal(L.factsLine(row({ basis: "21% of sales", amount: null })), "21% of sales");
  const csv = L.csvRows([row({ symbol: null, as_filed: true })]);
  assert.equal(csv[0].length, L.CSV_HEAD.length);
  assert.deepEqual(csv[0].slice(0, 3), ["Names as customers", "Bharat Electronics Limited", ""]);
});

test("the card is on the company page, the theme panel on a theme, the queue on Admin's Data page; the plan copy names both features", () => {
  assert.match(read("src/pages/Research.tsx"), /<CompanyLinksCard region=\{region\} symbol=\{c\.symbol\} \/>/);
  assert.match(read("src/pages/ThemesPage.tsx"), /<ThemeLinksCard region=\{dive\.region\} theme=\{q\} \/>/);
  assert.match(read("src/pages/admin/DataSection.tsx"), /<SupplyQueuePanel \/>/);
  const card = read("src/components/CompanyLinks.tsx");
  assert.match(card, /PlanNote plan="basic"/);
  assert.match(card, /v\.csv &&/);                                    // the CSV only when the server says the plan has it
  assert.doesNotMatch(card, /dangerouslySetInnerHTML/);
  const plans = read("src/lib/plans.ts");
  assert.match(plans, /\["supply", "Customer and supplier links"\]/);
  assert.match(read("src/lib/gates.ts"), /supply: "company page", supply_pro: "themes"/);
  assert.match(read("src/lib/planFeatures.ts"), /latest 3 customer and supplier links/);
});
