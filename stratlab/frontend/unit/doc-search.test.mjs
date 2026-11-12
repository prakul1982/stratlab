// Search inside filings and call transcripts (lane b1): the address of a search, the plan's filters, the extracts drawn as text with
// their marked words (never as HTML), and the page's entries from the palette, the company pages, the menu and the plan copy.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const D = await import("../src/lib/docSearch.ts");

test("a search's address round-trips, and the first page and India are left unnamed", () => {
  const q = { ...D.EMPTY, q: "order book", region: "US", symbols: ["AAPL", "NVDA"], kinds: ["annual_report"], sectors: ["Technology"], theme: "chips",
    from: "2026-01-01", to: "2026-06-30", page: 2 };
  const p = D.writeQuery(q);
  assert.equal(p.get("symbols"), "AAPL,NVDA");
  assert.deepEqual(D.readQuery(p), q);
  assert.equal(D.writeQuery({ ...D.EMPTY, q: "capex" }).toString(), "q=capex");
  assert.equal(D.readQuery(new URLSearchParams("q=x&page=-3&region=zz")).page, 1);
  assert.equal(D.readQuery(new URLSearchParams("region=zz")).region, "IN");
});

test("Free's search sends the words, the market and the companies only; Basic sends every filter", () => {
  const q = { ...D.EMPTY, q: "order book", symbols: ["TCS"], sectors: ["Banks"], kinds: ["transcript"], theme: "defence", from: "2026-01-01", page: 2 };
  const free = new URL(D.apiPath(q, false), "http://x");
  assert.equal(free.pathname, "/research/docs/search");
  assert.deepEqual([...free.searchParams.keys()].sort(), ["page", "q", "region", "symbols"]);
  const basic = new URL(D.apiPath(q, true), "http://x").searchParams;
  assert.equal(basic.get("sector"), "Banks"); assert.equal(basic.get("kind"), "transcript"); assert.equal(basic.get("theme"), "defence"); assert.equal(basic.get("frm"), "2026-01-01");
  assert.ok(!new URL(D.apiPath(q, true, "/research/docs/export"), "http://x").searchParams.has("page"));     // the CSV holds every page
  assert.deepEqual(D.lockedFilters(q), ["sector", "kind of document", "theme", "dates"]);
  assert.deepEqual(D.lockedFilters({ ...D.EMPTY, q: "x", symbols: ["TCS"] }), []);
});

test("an extract is read as text with its marked words: a document's markup stays text", () => {
  const parts = D.snippetParts("&lt;script&gt;alert(1)&lt;/script&gt; the <mark>order</mark> <mark>book</mark> &amp; more");
  assert.deepEqual(parts, [{ text: "<script>alert(1)</script> the ", hit: false }, { text: "order", hit: true }, { text: " ", hit: false },
    { text: "book", hit: true }, { text: " & more", hit: false }]);
  assert.deepEqual(D.snippetParts("<b>bold</b>"), [{ text: "<b>bold</b>", hit: false }]);     // only <mark> is read as markup
  const page = read("src/pages/DocSearchPage.tsx");
  assert.ok(!/dangerouslySetInnerHTML/.test(page), "the extracts are never put in as HTML");
});

test("the words under a hit and under the results say facts, the plan's limits and where the link opens", () => {
  assert.equal(D.whereLine({ page: 4, pages: 20, source: "NSE" }), "Page 4 of 20 · NSE copy");
  assert.equal(D.whereLine({ page: null, pages: null, source: "SEC" }), "SEC copy");
  assert.match(D.planLine({ hits: 3, days: 365, filters: false, export: false }), /first 3 results/);
  assert.match(D.planLine({ hits: null, days: 365, filters: true, export: false }), /Pro searches every year/);
  assert.equal(D.totalLine(1, false), "1 document");
  assert.equal(D.totalLine(400, true), "At least 400 documents");
  assert.equal(D.companySearch("US", "AAPL"), "/research/search?region=US&symbols=AAPL");
  const all = read("src/pages/DocSearchPage.tsx") + read("src/lib/docSearch.ts");
  assert.ok(!/\b(buy|sell|accumulate|avoid|cheap|expensive|undervalued|overvalued|recommend)\b/i.test(all.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "")));
});

test("the page is reachable: its route, the menu, the palette's \"Search filings for …\", both company pages and the gate", () => {
  assert.match(read("src/main.tsx"), /<Route path="\/research\/search" element={<DocSearchPage \/>} \/>/);
  assert.match(read("src/lib/nav.ts"), /page\("\/research\/search", "Search filings"[^\n]*flag: "doc_search" }/);
  assert.match(read("src/components/SearchPalette.tsx"), /Search filings for “/);
  assert.match(read("src/pages/Research.tsx"), /actions={<DocSearchLink region="IN" symbol={c\.symbol} \/>}/);
  assert.match(read("src/components/UsFilings.tsx"), /<DocSearchLink region="US" symbol={symbol} \/>/);
  assert.match(read("src/lib/gates.ts"), /"\/research\/search": { feature: "doc_search", whole: false }/);
});

test("the plan copy names the filings search on Basic and its every-year archive and CSV on Pro", async () => {
  const { LIMITS, FLAGS, planOf } = await import("../src/lib/plans.ts");
  const features = read("src/lib/planFeatures.ts");             // read as text: its import of ./plans needs the bundler's resolution
  const [f, b, p] = ["  free: [", "  basic: [", "  pro: ["].map((m) => features.indexOf(m));
  const FEATURES = { free: [features.slice(f, b)], basic: [features.slice(b, p)], pro: [features.slice(p)] };
  assert.equal(planOf("doc_search"), "basic");
  assert.equal(planOf("doc_search_all"), "pro");
  assert.ok(!LIMITS.basic.features.includes("doc_search_all") && LIMITS.pro.features.includes("doc_search"));
  assert.ok(FLAGS.some(([f, t]) => f === "doc_search" && /^Search filings/.test(t)));
  assert.ok(FEATURES.free.some((t) => /first 3 results of a filings search/.test(t)));
  assert.ok(FEATURES.basic.some((t) => /search inside filings and call transcripts/.test(t)));
  assert.ok(FEATURES.pro.some((t) => /every year of a company's filings, with the results as a CSV/.test(t)));
});
