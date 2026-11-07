// R19 (owner, 7 Nov): saved searches and AI reads. The pure parts: the page each saved item opens, the snapshot a theme read and a filter
// read make, when a theme read is finished enough to keep, "Last updated", and the one line an Update says. Plus the wiring: one shared
// component on every page that has a search or AI read worth keeping, none of it in the landing chunk.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const S = () => import("../src/lib/savedSnap.ts");

const co = (ticker, name, cap, base = true) => ({ ticker, name, cap, base });
const map = (over = {}) => ({
  sector: "India defence", summary: "", market_size: "", cagr: null, cagr_note: "", etfs: [], core: "", clusters: [], screen: [], tailwinds: [], risks: [], generated_at: 1,
  value_chain: [{ layer: "Platforms", description: "", companies: [co("HAL", "Hindustan Aeronautics", 300000), co("BEL", "Bharat Electronics", 200000)] },
    { layer: "Shipyards", description: "", companies: [co("MAZDOCK", "Mazagon Dock", null, false)] }],
  sub_themes: [{ name: "Electronics", detail: "", companies: [co("BEL", "Bharat Electronics", 200000), co("DATAPATTNS", "Data Patterns", 15000, false)] }],
  placements: { checked: true, pending: 0, left_out: 0, placed: 4 }, ai: null, ...over,
});

test("each saved item opens its own page with its own parameters, symbols made safe for the address", async () => {
  const { savedUrl } = await S();
  assert.equal(savedUrl({ kind: "theme", params: { q: "India defence", region: "IN" } }), "/research/themes?region=IN&q=India+defence");
  assert.equal(savedUrl({ kind: "filings", params: { region: "IN", view: "all", flag: "pledge", range: "30" } }), "/research/filings?region=IN&view=all&flag=pledge&range=30");
  assert.equal(savedUrl({ kind: "company_ai", params: { region: "IN", symbol: "M&M" } }), "/research/IN/M%26M");
  assert.equal(savedUrl({ kind: "deep_dive", params: { region: "US", symbol: "AAPL" } }), "/research/US/AAPL/deep");
  assert.equal(savedUrl({ kind: "compare", params: { region: "IN", a: "TCS", b: "INFY" } }), "/research/compare?region=IN&a=TCS&b=INFY");
});

test("a theme read's snapshot is every company once with its market value, and the key figures", async () => {
  const { themeSnap } = await S();
  const s = themeSnap(map());
  assert.deepEqual(Object.keys(s.rows), ["HAL", "BEL", "MAZDOCK", "DATAPATTNS"]);
  assert.deepEqual(s.rows.HAL, ["Hindustan Aeronautics", 300000]);
  assert.deepEqual(s.rows.MAZDOCK, ["Mazagon Dock", null]);
  assert.deepEqual(s.figures, { companies: 4, market_value: 515000, added: 2 });
});

test("a theme read still being written is not kept as the saved read (its companies would look added or removed)", async () => {
  const { themeReady } = await S();
  assert.equal(themeReady(map()), true);
  assert.equal(themeReady(map({ ai: { state: "working", message: "" } })), false);
  assert.equal(themeReady(map({ ai: { state: "failed", message: "x" } })), false);
  assert.equal(themeReady(map({ placements: { checked: false, pending: 3, left_out: 0, placed: 1 } })), false);
  assert.equal(themeReady(map({ placements: { checked: false, pending: 0, left_out: 0, placed: 1, industries_by: "pending" } })), false);
});

test("a filter read's snapshot is its filings by id; an AI read's is when it was written", async () => {
  const { filingsSnap, readSnap } = await S();
  const s = filingsSnap({ total: 140, companies: 60, items: [{ id: "f1", symbol: "ABC", label: "Promoter pledge" }] });
  assert.deepEqual(s, { rows: { f1: ["ABC: Promoter pledge", null] }, figures: { filings: 140, companies: 60 } });
  assert.deepEqual(readSnap(1762400000), { rows: {}, figures: { written: 1762400000 } });
});

test("Last updated: an AI read by when it was written, a search by when it was last read", async () => {
  const { lastUpdated } = await S();
  assert.equal(lastUpdated({ read_at: "2026-11-06T10:00:00+00:00", figures: {}, params: {} }), "6 Nov 2026");
  assert.equal(lastUpdated({ read_at: null, figures: {}, params: {} }), "Not read yet");
  assert.equal(lastUpdated({ read_at: "2026-11-07T10:00:00+00:00", figures: { written: Date.UTC(2026, 10, 5, 9) / 1000 }, params: {} }), "5 Nov 2026");
});

test("an Update says what changed in one plain line, facts only", async () => {
  const { changeLine } = await S();
  const ch = (o) => ({ added: [], added_count: 0, removed: [], removed_count: 0, moves: [], figures: [], same: false, ...o });
  assert.equal(changeLine(null, "theme"), "Read kept. The next Update says what changed since this read.");
  assert.equal(changeLine(ch({ same: true }), "theme"), "No change since the saved read.");
  assert.equal(changeLine(ch({ added_count: 2, removed_count: 1, figures: [{ name: "market_value", before: 100, after: 120, change: 20, pct: 20 }] }), "theme"),
    "2 companies added; 1 company removed; market value +20.0%.");
  assert.equal(changeLine(ch({ added_count: 1 }), "filings"), "1 filing new.");
  assert.equal(changeLine(ch({ figures: [{ name: "written", before: 1, after: 2, change: 1, pct: 100 }] }), "company_ai"), "The read was written again.");
  for (const line of [changeLine(ch({ added_count: 3 }), "theme"), changeLine(ch({ removed_count: 3 }), "filings")]) {
    assert.doesNotMatch(line, /\b(buy|sell|should|recommend|opportunit)/i);
  }
});

test("figures are written the app's way", async () => {
  const { figureText, figureName, savedWhat } = await S();
  assert.match(figureText("market_value", 515000, "IN"), /^₹.*cr$/);
  assert.equal(figureText("companies", 1234, "IN"), "1,234");
  assert.equal(figureText("filings", null, "IN"), "–");
  assert.equal(figureName("market_value"), "Market value of the companies");
  assert.equal(savedWhat({ kind: "compare", params: { region: "US", a: "AAPL", b: "MSFT" } }), "US · AAPL vs MSFT");
  assert.equal(savedWhat({ kind: "theme", params: { region: "IN", q: "India defence" } }), "India · India defence");
  assert.equal(savedWhat({ kind: "theme", name: "India defence", params: { region: "IN", q: "India defence" } }), "India");
});

test("one shared Save button and list on every page with a search or AI read worth keeping, signed-in code only", () => {
  for (const [file, kind] of [["src/pages/ThemesPage.tsx", "theme"], ["src/pages/ResearchScans.tsx", "filings"], ["src/components/Research.tsx", "company_ai"],
    ["src/pages/Research.tsx", "compare"], ["src/pages/DeepDive.tsx", "deep_dive"]]) {
    const src = read(file);
    assert.match(src, new RegExp(`<SaveButton kind="${kind}"`), file);
    assert.match(src, /from "\.\.?\/(components\/)?SavedSearches"/, file);
  }
  assert.match(read("src/pages/ThemesPage.tsx"), /<SavedList kind="theme"/);
  assert.match(read("src/pages/ResearchScans.tsx"), /<SavedList kind="filings"/);
  assert.match(read("src/pages/MineHome.tsx"), /saved: <SavedList/);
  // nothing the landing chunk loads imports it
  for (const f of ["src/entry.tsx", "src/components/Icons.tsx", "src/lib/share.ts"]) assert.doesNotMatch(read(f), /SavedSearches|lib\/saved/, f);
  // the list header says how many of the limit are used; a full list says so on the button
  const comp = read("src/components/SavedSearches.tsx");
  assert.match(comp, /\{count\} of \{limit\} saved/);
  assert.match(comp, /Saved list full \(\{limit\}\): remove one to save/);
  assert.match(comp, /<Working label=/);
});

test("My space shows the saved card only once there is something saved", async () => {
  const { CARDS, cleanLayout, slotSpans } = await import("../src/lib/mineLayout.ts");
  assert.ok(CARDS.some((c) => c.id === "saved"));
  assert.ok(cleanLayout({ order: ["networth"], hidden: [] }).order.includes("saved"));       // added to a layout kept from before
  assert.equal(slotSpans(["markets", "saved"]).saved, 12);
});
