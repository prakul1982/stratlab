// Round 10 review of the owner's pages (9 Oct 2026): the app's side, each on the reviewer's example.
// Every clock here is a fixed instant. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

test("R10O-001: a provider's long error is one line on Overview, with the whole text for a tooltip", async () => {
  const { oneLine } = await import("../src/pages/admin/attention.ts");
  const long = "403: AI Gateway requires a valid credit card on file to service requests. Visit https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai%3Fmodal%3Dadd-credit-card%26x%3D"
    + "a".repeat(200) + " to add one.";
  const one = oneLine(long);
  assert.equal(one.text, "403: AI Gateway requires a valid credit card on file to service requests.");
  assert.equal(one.full, long);
  const url = oneLine("https://vercel.com/d?to=" + "x".repeat(300));
  assert.ok(url.text.length <= 120 && url.text.endsWith("…") && url.full.length > 300);
  assert.deepEqual(oneLine("not answering"), { text: "not answering" });
  const css = read("src/pages/admin/admin.css");
  assert.match(css, /\.adm-todo-t > span:last-child \{[^}]*overflow-wrap: anywhere/);
  assert.match(read("src/pages/admin/OverviewSection.tsx"), /<span title=\{x\.full\}>\{x\.text\}<\/span>/);
});

test("R10O-008: the PCR table says what its rows are with the market shut", async () => {
  const { pcrNote } = await import("../src/lib/positioning.ts");
  assert.match(pcrNote([{ name: "NIFTY", exchange: "NFO", source: "recorded", at_close: true }]), /market is shut.*recording of its last close/);
  assert.match(pcrNote([{ name: "NIFTY", exchange: "NFO", source: "recorded" }]), /live chain is offline, the newest recording/);
  assert.equal(pcrNote([{ name: "NIFTY", exchange: "NFO", source: "live" }]), "Live chains are read at most once a minute.");
  assert.match(read("src/pages/PositioningPage.tsx"), /data-testid="pcr-note">\{pcrNote\(rows\)\}/);
});

test("R10O-009: the company page asks lean and fills the news in behind the header", async () => {
  const { withMore } = await import("../src/lib/research.ts");
  const c = { symbol: "TCS", news: [], peers: ["INFY"], about: { wiki: null, profile: "IT services" }, sources: [{ source: "Screener", ok: true, error: null }], lazy: ["news", "about"] };
  const m = { news: [{ headline: "TCS wins a deal", url: "https://example.com/x", source: "x", at: null }], wiki: { title: "TCS", extract: "A company.", url: "https://example.com/w" },
    peers: ["INFY", "WIPRO"], sources: [{ source: "Screener", ok: true, error: null }, { source: "Google News", ok: false, error: "slow" }] };
  const out = withMore(c, m);
  assert.equal(out.news.length, 1);
  assert.equal(out.about.wiki.title, "TCS");
  assert.equal(out.about.profile, "IT services");
  assert.deepEqual(out.peers, ["INFY", "WIPRO"]);
  assert.equal(out.lazy, undefined);
  assert.deepEqual(out.sources.map((s) => s.source), ["Screener", "Google News"]);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /researchApi\.company\(region, sym, true\)/);
  assert.match(page, /researchApi\.companyMore\(region, sym\)/);
  assert.match(page, /c\.lazy\?\.length \? <Skeleton label="Loading the latest news"/);
  const api = read("src/lib/research.ts");
  assert.match(api, /\$\{lean \? "\?lean=1" : ""\}/);
});

test("R10O-012: one stock's old close is named, not made the list's date", async () => {
  const { staleNote } = await import("../src/lib/screens.ts");
  assert.equal(staleNote([{ symbol: "XYZ", price_at: "2026-10-02" }]), "One stock's close is from 2 Oct: XYZ.");
  assert.equal(staleNote([{ symbol: "A", price_at: "2026-10-02" }, { symbol: "B", price_at: "2026-10-01" }]),
    "2 stocks' closes are more than three days older than the rest: A (2 Oct), B (1 Oct).");
  assert.equal(staleNote([]), null);
  assert.equal(staleNote(undefined), null);
  const page = read("src/pages/Screens.tsx");
  assert.match(page, /data-testid="screens-stale"/);
});

test("R10O-011: a bank's financing margin row is left out when none of it can be shown", () => {
  const table = read("src/components/Research.tsx");
  assert.match(table, /r\.name === "Financing margin" && r\.cells\.every\(\(c\) => c === "–"\)/);
  assert.match(read("src/pages/DeepDive.tsx"), /n\.bank && n\.quarters\.slice\(-8\)\.every\(\(q\) => q\.opm == null\)/);
});

test("R10O-010: the rotation chart's date label is the last finished session the server sends", () => {
  // the server leaves a session still trading out of the candles; the page only prints the as_of it is given
  const page = read("src/pages/ResearchScans.tsx");
  assert.match(page, /asOfLabel="Closes up to"/);
  assert.match(page, /closes\{out\.as_of \? ` to \$\{fmtDate\(out\.as_of\)\}` : ""\}/);
});
