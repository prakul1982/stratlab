// Review 5c: the Invest and Research screens. The watchlist's quotes past the 24th, a stale price dated "now", the at a
// glance card's market and its first 20, compare's "Ask again", the Invest home's US red flags and its links' market,
// search races, Ctrl K's deep dive and compare in either market, and the screener, scan and rotation kept in the address.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const backend = (p) => readFileSync(new URL(`../../backend/app/${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

const ui = await import("../src/lib/investUi.ts");
const fn = (src, name) => src.slice(src.indexOf(`export function ${name}`), src.indexOf("\nexport function", src.indexOf(`export function ${name}`) + 10));

/* ---------- 1. the watchlist's quotes after the 24th ---------- */

test("R5C-001: the watchlist asks for its quotes 24 at a time, in turn, so every stock gets one", async () => {
  // the server's cap is the page's batch size
  assert.match(backend("intel/routes.py"), /asked = \[s\.strip\(\)\.upper\(\) for s in symbols\.split\(","\) if s\.strip\(\)\]\[:24\]/);
  assert.equal(ui.QUOTE_BATCH, 24);
  assert.deepEqual(ui.batches([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  const syms = Array.from({ length: 60 }, (_, i) => `S${i}`);
  const asked = [], parts = [];
  let inFlight = 0, most = 0;
  const ask = async (part) => {
    inFlight++; most = Math.max(most, inFlight); asked.push(part);
    await new Promise((r) => setTimeout(r, 1));
    inFlight--;
    if (part.includes("S30")) throw new Error("500");                          // one batch fails
    return Object.fromEntries(part.filter((s) => s !== "S5").map((s) => [s, { price: 1 }]));
  };
  const out = await ui.quotesInBatches(ask, syms, (p) => parts.push(Object.keys(p).length));
  assert.deepEqual(asked.map((a) => a.length), [24, 24, 12]);
  assert.equal(most, 1, "one request at a time");
  assert.deepEqual(parts, [24, 48, 60]);                                      // rows fill in batch by batch
  assert.equal(Object.keys(out).length, 60);
  assert.deepEqual(out.S59, { price: 1 });                                    // after the 24th: a price, not "–"
  assert.equal(out.S5, null);                                                 // no price: null, said "–"
  assert.equal(out.S30, null);                                                // its batch failed; the next was still asked
  let live = true;
  const stopped = await ui.quotesInBatches(async (p) => { live = false; return Object.fromEntries(p.map((s) => [s, { price: 1 }])); }, syms, () => {}, () => live);
  assert.equal(Object.keys(stopped).length, 0, "a page that moved on takes nothing");
  const page = read("src/pages/Research.tsx");
  const watch = page.slice(page.indexOf("export function WatchlistPage"));
  assert.match(watch, /void quotesInBatches\(\(syms\) => researchApi\.quotes\(region, syms\), mine\.map\(\(w\) => w\.symbol\), \(soFar\) => setQuotes\(soFar\), \(\) => live\);/);
  assert.match(watch, /if \(quotes == null \|\| !\(w\.symbol in quotes\)\) return "…";/);
  assert.doesNotMatch(watch, /researchApi\.quotes\(region, mine\.map/);
});

/* ---------- 2. a stale India price dated "now" ---------- */

test("R5C-002: a price's day decides \"today\": an earlier session's says its day, one with no time says so", async () => {
  const { priceLabel } = await import("../src/lib/research.ts");
  const day = (d) => (d === "2026-10-08" ? "8 Oct" : d);
  assert.deepEqual(priceLabel({ market_open: true, quote_day: "2026-10-09" }, "2026-10-09", day), { label: null, since: "today" });
  assert.deepEqual(priceLabel({ market_open: true, quote_day: "2026-10-08" }, "2026-10-09", day), { label: "Not updated today yet", since: "on 8 Oct" });
  assert.deepEqual(priceLabel({ market_open: true, quote_day: null }, "2026-10-09", day), { label: "Time of this price unknown", since: "" });
  assert.deepEqual(priceLabel({ market_open: false, quote_day: null }, "2026-10-09", day), { label: "Last close", since: "on the day" });
  assert.deepEqual(priceLabel({ market_open: true }), { label: null, since: "today" });           // an answer without the field, as before
  const page = read("src/pages/Research.tsx");
  assert.match(page, /quoteDay=\{c\.quote_day\} today=\{dayIn\(new Date\(\), marketTz\(region\)\) \?\? undefined\}/);
  assert.match(page, /priceLabel\(c, today, dayText\)/);                                        // the compare page too
  const change = fn(read("src/components/Research.tsx"), "Change");
  assert.match(change, /quote_day: quoteDay \}/);
  assert.match(change, /\{closed && <span className="k-stat-k">Last close<\/span>\}/);
  assert.match(change, /\{!closed && !preOpen && !settling && label && <span className="k-stat-k" data-testid="price-when">\{label\}<\/span>\}/);
  // the server keeps the fallback quote's time and sends no "as of" without one
  const co = backend("intel/company.py");
  assert.match(co, /"prev_close", "volume", "at"\)\}/);
  assert.match(co, /quote = \{"price": s\["price"\], "at": None\}/);
  const routes = backend("intel/routes.py");
  assert.match(routes, /if t is None:\n        return None/);
  assert.match(routes, /"quote_day": quote_day\(r, c\)/);
  // the ETF badge's day is the quote's own trade day
  assert.match(page, /<EtfGapBadge symbol=\{c\.symbol\} price=\{c\.quote\?\.price\} day=\{c\.quote\?\.at \? dayIn\(c\.quote\.at\) : null\} \/>/);
});

/* ---------- 3 and 9. the at a glance card ---------- */

test("R5C-003: the at a glance page drops a late answer for the market it left", () => {
  const page = read("src/pages/InvestorHome.tsx");
  const effect = page.slice(page.indexOf("useEffect(() => {"), page.indexOf("}, [pro, region, tries]);"));
  assert.match(effect, /let live = true;/);
  assert.match(effect, /\.then\(\(x\) => \{ if \(!live\) return; setRows\(x\.rows\);/);
  assert.match(effect, /\.catch\(\(e\) => \{ if \(live\) setError\(\(e as Error\)\.message\); \}\)/);
  assert.match(effect, /return \(\) => \{ live = false; \};/);
  assert.doesNotMatch(page, /fail\(e\)/, "a failed load is the error card only, no toast as well");
});

test("R5C-009: the at a glance page says it shows 20 of N, with the full watchlist a link away", () => {
  const main = backend("main.py");
  assert.match(main, /syms = listed\[:investor\.MAX\]/);
  assert.match(main, /"total": len\(listed\)/);
  const page = read("src/pages/InvestorHome.tsx");
  assert.match(page, /Showing \{rows\.length\} of \{total\} \{place\} watchlist companies/);
  assert.match(page, /<Link className="link" to=\{`\/research\/watchlist\?region=\$\{region\}`\}>See all \{total\} on your watchlist<\/Link>/);
});

test("R5C-010: the at a glance titles open the company page; the deep dive is its own link", () => {
  const page = read("src/pages/InvestorHome.tsx");
  assert.match(page, /title=\{<Link className="link" to=\{`\/research\/\$\{region\}\/\$\{encodeURIComponent\(r\.symbol\)\}`\}>\{r\.name\}<\/Link>\}/);
  assert.match(page, /aria-label=\{`Deep dive into \$\{r\.name\}`\}>Deep dive →<\/Link>/);
  assert.equal((page.match(/\/deep`/g) ?? []).length, 1, "one deep dive link per card, said as one");
});

/* ---------- 4. compare's "Ask again" ---------- */

test("R5C-004: compare's Ask again answers only the pair it was asked for", () => {
  assert.equal(ui.pairKey("IN", "tcs", "INFY"), "IN|TCS|INFY");
  assert.notEqual(ui.pairKey("IN", "TCS", "INFY"), ui.pairKey("US", "TCS", "INFY"));
  const page = read("src/pages/Research.tsx");
  const cmp = page.slice(page.indexOf("export function ComparePage"), page.indexOf("/* ================= Watchlist"));
  assert.match(cmp, /const shownKey = pairKey\(region, a, b\);/);
  assert.match(cmp, /\.then\(\(x\) => \{ if \(pair\.current === key\) setRes\(/);
  assert.match(cmp, /\.finally\(\(\) => setAsking\(\(k\) => \(k === key \? null : k\)\)\);/);
  assert.match(cmp, /disabled=\{asking === shownKey\} onClick=\{askAgain\}>\{asking === shownKey \? "Asking…" : "Ask again"\}/);
  assert.match(cmp, /useEffect\(\(\) => \{\n    setAsking\(null\);/);
  // a market switch clears both companies
  assert.match(cmp, /p\.set\("region", r\); p\.delete\("a"\); p\.delete\("b"\); setParams\(p, \{ replace: true \}\);/);
  assert.match(cmp, /<RegionSwitch region=\{region\} setRegion=\{setRegion\} \/>/);
});

/* ---------- 5 and 6. the Invest home ---------- */

test("R5C-005: the US red flags card says where US red flags are and links there", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.doesNotMatch(src, /A US company's own page lists its SEC filings/);
  assert.match(src, /<Panel title="Red flags" right=\{<Link to="\/research\/filings\?region=US" className="link">US filings →<\/Link>\}>/);
  assert.match(src, /US red flags are read from the Form 8-K items S&P 500 companies file with the SEC/);
  // ...which the filings page's US tab is
  assert.match(read("src/pages/ResearchScans.tsx"), /What S&P 500 companies told the SEC in a Form 8-K/);
  assert.match(read("e2e/review-r9r.spec.ts"), /toHaveAttribute\("href", "\/research\/filings\?region=US"\)/);
});

test("R5C-006: every Invest home link opens its page on the market picked there", async () => {
  assert.equal(ui.withRegion("/research/results", "US"), "/research/results?region=US");
  assert.equal(ui.withRegion("/research/scan?set=nifty50", "IN"), "/research/scan?set=nifty50&region=IN");
  assert.deepEqual(ui.investStrip("US").map((t) => t.to), ["/research/screens?region=US", "/research/rotation?region=US", "/research/scan?region=US", "/research/corporate-actions?region=US"]);
  assert.equal(ui.investStrip("IN")[2].to, "/research/scan?set=nifty50&region=IN");
  const home = read("src/pages/SpaceHomes.tsx");
  assert.match(home, /const tools: Tool\[\] = investStrip\(region\)\.map\(\(t\) => \(\{ \.\.\.INVEST_STRIP\[t\.key\], to: t\.to \}\)\);/);
  assert.match(home, /<Link to=\{withRegion\("\/research\/investor", region\)\} className="link">At a glance →<\/Link>/);
  assert.match(home, /<Link to=\{withRegion\("\/research\/results", region\)\} className="link">Calendar →<\/Link>/);
  assert.match(home, /<Link to="\/research\/filings\?region=IN" className="link">All filings →<\/Link>/);
  const card = read("src/components/BreadthCard.tsx");
  assert.match(card, /`\/invest\/breadth\?group=\$\{encodeURIComponent\(d\.group\.id\)\}` : `\/invest\/breadth\?region=\$\{region\}`/);
  assert.match(card, /<Link to=\{page\} className="link">Charts →<\/Link>/);
  // the pages they open read the address: breadth by group or market, at a glance by market
  const { breadthStart } = await import("../src/lib/breadthPick.ts");
  assert.deepEqual(breadthStart(new URLSearchParams("group=sp500"), "IN"), { group: "sp500", range: "1y", picked: true, region: "US" });
  assert.equal(breadthStart(new URLSearchParams("region=US"), "IN").group, "sp500");
  assert.equal(breadthStart(new URLSearchParams("region=US"), "IN").region, "US");
  assert.equal(breadthStart(new URLSearchParams(""), "IN").group, "nifty500");
  assert.equal(breadthStart(new URLSearchParams("group=nope"), "IN").group, "nifty500");    // a group not offered: the market's own
  const breadth = read("src/pages/BreadthPage.tsx");
  assert.match(breadth, /const \[first\] = useState\(\(\) => breadthStart\(params, homeRegion\(\)\)\);/);
  assert.match(breadth, /n\.set\("group", g\); n\.delete\("region"\); return n; \}, \{ replace: true \}\);/);
  const glance = read("src/pages/InvestorHome.tsx");
  assert.match(glance, /const \[region, pick\] = useRegion\(\);/);
  assert.doesNotMatch(glance, /useState<Region>\(savedRegion\)/);
  for (const p of ["src/pages/Screens.tsx", "src/pages/ResultsPage.tsx"]) assert.match(read(p), /= useRegion\(\);/, p);
  assert.match(read("src/pages/CorpActionsPage.tsx"), /const fromUrl = params\.get\("region"\)\?\.toUpperCase\(\);/);
});

/* ---------- 7. search races ---------- */

test("R5C-007: a search answer for an earlier keystroke never replaces a newer one's", () => {
  const l = ui.makeLatest();
  const first = l.next(), second = l.next();
  assert.equal(l.latest(first), false);
  assert.equal(l.latest(second), true);
  l.reset();
  assert.equal(l.latest(second), false);                                      // a market switch drops what's on its way
  const box = read("src/components/CompanySearch.tsx");
  assert.match(box, /useEffect\(\(\) => \{ asked\.current\+\+; setQ\(""\); setRows\(null\); setActive\(0\); \}, \[region\]\);/);
  assert.match(box, /const n = \+\+asked\.current;/);
  assert.match(box, /if \(n === asked\.current\) \{ setRows\(r\); setActive\(0\); \}/);
  assert.match(box, /catch \(e\) \{ if \(n === asked\.current\) fail\(e\); \}/);
  const pal = read("src/components/SearchPalette.tsx");
  assert.match(pal, /\.then\(\(r\) => \{ if \(n === asked\.current\) setInsts\(r\.slice\(0, 8\)\); \}\)/);
});

/* ---------- 8. Ctrl K's deep dive and compare ---------- */

test("R5C-008: Ctrl K's deep dive and compare look in every market and use the company's own", async () => {
  const { pickCompany, compareTo } = await import("../src/lib/paletteRank.ts");
  const rows = [
    { symbol: "NIFTY 50", market: "IN", type: "INDEX" }, { symbol: "BTC-USD", market: "CRYPTO", type: "CRYPTO" },
    { symbol: "AAPL", market: "US", type: "EQ" }, { symbol: "APLAPOLLO", market: "IN", type: "EQ" }, { symbol: "TCS26OCTFUT", market: "IN", type: "FUT", fno: true },
  ];
  assert.equal(pickCompany(rows, "aapl").symbol, "AAPL");
  assert.equal(pickCompany(rows, "apple").symbol, "AAPL");                    // the search's first company, an index skipped
  assert.equal(pickCompany(rows, "aplapollo").market, "IN");
  assert.equal(pickCompany(rows.slice(0, 2), "nifty"), null);
  assert.equal(compareTo({ symbol: "AAPL", market: "US" }, { symbol: "MSFT", market: "US" }, "IN"), "/research/compare?region=US&a=AAPL&b=MSFT");
  assert.equal(compareTo({ symbol: "TCS", market: "IN" }, { symbol: "MSFT", market: "US" }, "IN"), "/research/compare?region=IN&a=TCS");
  assert.equal(compareTo(null, { symbol: "MSFT", market: "US" }, "IN"), "/research/compare?region=US&b=MSFT");
  assert.equal(compareTo(null, null, "US"), "/research/compare?region=US");
  const pal = read("src/components/SearchPalette.tsx");
  assert.doesNotMatch(pal, /findInstrument\(it\.deep, "IN"\)|findInstrument\(n, "IN"\)|compare\?region=IN\$/);
  assert.match(pal, /`\/research\/\$\{inst\.market\}\/\$\{encodeURIComponent\(inst\.symbol\)\}\/deep` : `\/research\?q=\$\{encodeURIComponent\(it\.deep\)\}`/);
  assert.match(pal, /\/instruments\/search\?q=\$\{encodeURIComponent\(name\.trim\(\)\.slice\(0, 40\)\)\}`\)/);          // no market
  // /research?q= opens with the name typed in the search box, its matches listed
  const page = read("src/pages/Research.tsx");
  assert.match(page, /const q = \(params\.get\("q"\) \?\? ""\)\.slice\(0, 40\);/);
  assert.match(page, /<OpenCompany key=\{q\} region=\{region\} autoFocus=\{typingFirst\(\)\} query=\{q \|\| undefined\} \/>/);
  const picker = read("src/components/kit/StockPicker.tsx");
  assert.match(picker, /const \[text, setText\] = useState\(search \|\| value\);\n  const \[typed, setTyped\] = useState\(!!search\);/);
});

/* ---------- 10. the screener in the address ---------- */

test("R5C-010: Find stocks keeps its conditions and sort in the address, and how many rows were loaded", async () => {
  const none = { sector: [], cap: [], stage: [], red_flags: null, insider_buy: null, insider_days: 90, surveillance: null, surv_lists: [], ranges: {} };
  const empty = ui.screenQuery({ filters: none, sort: "market_cap", desc: true }, none);
  assert.deepEqual(empty, { f: null, sort: null, dir: null });                // the default screen leaves the address alone
  const s = { filters: { ...none, sector: ["Energy"], stage: [2], red_flags: "no", insider_days: 30, ranges: { pe: { min: null, max: 20 }, roe: { min: 15, max: null }, opm: { min: null, max: null } } },
    sort: "pe", desc: false };
  const q = ui.screenQuery(s, none);
  assert.equal(q.sort, "pe"); assert.equal(q.dir, "asc");
  const back = ui.screenFromQuery(new URLSearchParams(Object.entries(q).filter(([, v]) => v)), none);
  assert.deepEqual(back.filters, { ...s.filters, ranges: { pe: { min: null, max: 20 }, roe: { min: 15, max: null } } });
  assert.equal(back.sort, "pe"); assert.equal(back.desc, false);
  assert.deepEqual(ui.screenFromQuery(new URLSearchParams("f=%7Bbroken&sort=x;y"), none), { filters: none, sort: "xy", desc: true });
  const p = new URLSearchParams("region=IN&f=1");
  assert.equal(ui.withParams(p, { f: "1" }), p, "nothing to write: the same object, so no address write");
  assert.equal(ui.withParams(p, { f: null }).toString(), "region=IN");
  const page = read("src/pages/Screens.tsx");
  assert.match(page, /const \[start\] = useState\(\(\) => screenFromQuery\(params, NO_FILTERS\)\);/);
  assert.match(page, /const next = withParams\(params, query\);\n    if \(next !== params\) setParams\(next, \{ replace: true \}\);/);
  assert.match(page, /const LOADED_KEY = "stratlab\.screens\.loaded";/);
  assert.match(page, /if \(restore\.current > shown && shown < r\.total && r\.rows\.length\) \{ runRef\.current\(shown\); return; \}/);
  assert.match(page, /rememberLoaded\(screenKey, shown\);/);
});

/* ---------- 11 and 12. the trend scan and the rotation in the address ---------- */

test("R5C-011: the trend scan keeps the group in the address", () => {
  const src = read("src/pages/ResearchScans.tsx");
  const scan = src.slice(src.indexOf("export function ScanPage"), src.indexOf("interface RotationOut"));
  assert.match(scan, /const \[setId, setSetId\] = useState\(\(\) => params\.get\("set"\) \|\| "watchlist"\);/);
  assert.match(scan, /const chooseSet = \(v: string\) => \{\n    setSetId\(v\); drop\(\);\n    const p = new URLSearchParams\(window\.location\.search\); p\.set\("set", v\); setParams\(p, \{ replace: true \}\);/);
  assert.match(scan, /<Select id=\{id\} value=\{setId\} onChange=\{chooseSet\}/);
});

test("R5C-012: the rotation keeps its group, the sector drilled into, the candle size and the trail in the address", () => {
  assert.deepEqual(ui.rotationFromQuery(new URLSearchParams("")), ui.ROTATION_DEFAULT);
  const st = ui.rotationFromQuery(new URLSearchParams("set=sector:NIFTY_IT&from=sectors&iv=daily&trail=9"));
  assert.deepEqual(st, { set: "sector:NIFTY_IT", from: "sectors", interval: "daily", tail: 9 });
  assert.deepEqual(ui.rotationQuery(st), { set: "sector:NIFTY_IT", from: "sectors", iv: "daily", trail: "9" });
  assert.deepEqual(ui.rotationQuery(ui.ROTATION_DEFAULT), { set: null, from: null, iv: null, trail: null });
  assert.equal(ui.rotationFromQuery(new URLSearchParams("trail=99")).tail, 4);
  assert.equal(ui.rotationQuery({ ...st, set: "watchlist" }).from, null);       // "from" only beside a sector's stocks
  const src = read("src/pages/ResearchScans.tsx");
  const rot = src.slice(src.indexOf("export function RotationPage"), src.indexOf("interface FilingsOverview"));
  assert.match(rot, /const \[start\] = useState\(\(\) => rotationFromQuery\(params\)\);/);
  for (const s of ["useState(start.set)", "useState<string | null>(start.from)", "useState<\"weekly\" | \"daily\">(start.interval)", "useState(start.tail)"]) assert.ok(rot.includes(s), s);
  assert.match(rot, /rotationQuery\(\{ set: setId, from: backTo, interval, tail: askTail \}\)/);
});

/* ---------- the smaller items ---------- */

test("R5C-013: the help says what the key-number marks and the earnings bars draw, with no strong or weak", async () => {
  const { HELP } = await import("../src/lib/help.ts");
  assert.doesNotMatch(HELP.researchMetrics, /blue|orange|strong|weak/i);
  assert.match(HELP.researchMetrics, /dark mark/);
  assert.doesNotMatch(HELP.researchEarnings, /blue|orange/i);
  assert.match(HELP.researchEarnings, /Green bars beat the estimate, red bars missed it\./);
  const css = read("src/styles-invest.css");
  assert.match(css, /\.inv-krail \.mark \{ fill: var\(--ink-2\); \}/);
  assert.match(css, /\.tbar-bar\.beat \{ fill: var\(--up\); \}/);
  assert.match(css, /\.tbar-bar\.neg \{ fill: var\(--down\); \}/);
});

test("R5C-014: the rotation chart is as wide as its card on a small phone", () => {
  assert.equal(ui.rotationWidth(254), 254);
  assert.ok(ui.rotationWidth(0) < 254 && ui.rotationWidth(100) < 254);
  assert.equal(ui.rotationWidth(820.6), 820);
  const src = read("src/components/Rotation.tsx");
  assert.match(src, /const W = rotationWidth\(width\)/);
  assert.doesNotMatch(src, /Math\.max\(300, width\)/);
});

test("R5C-015: a failed news read says the news couldn't be loaded, not that there are no headlines", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /\.catch\(\(\) => live && setC\(\(cur\) => \(cur \? \{ \.\.\.cur, lazy: undefined, news_failed: true \} : cur\)\)\);/);
  assert.match(page, /c\.news_failed && !c\.news\.length \? <p className="k-small k-muted" data-testid="news-failed">The news couldn't be loaded just now\./);
});

test("R5C-016: India's panels and the results line use the page's own symbol (ZOMATO's page is ETERNAL's)", () => {
  const page = read("src/pages/Research.tsx");
  for (const p of ["<FilingsPanel symbol={c.symbol} />", "<BizUpdatesPanel symbol={c.symbol}", "<NamedHoldersPanel symbol={c.symbol}", "<DealsPanel symbol={c.symbol} />"]) assert.ok(page.includes(p), p);
  assert.doesNotMatch(page, /Panel symbol=\{sym\}/);
  assert.match(page, /`\/research\/results\/\$\{region\}\/\$\{encodeURIComponent\(x\.symbol \|\| sym\)\}`/);
});

test("R5C-017: a brief's links to the app open in the app, whatever the address's form", () => {
  const here = { origin: "https://stratlab.studio", host: "stratlab.studio" };
  assert.equal(ui.inAppPath("https://stratlab.studio/research/IN/TCS?x=1#filings", here), "/research/IN/TCS?x=1#filings");
  assert.equal(ui.inAppPath("https://www.stratlab.studio/news", here), "/news");
  assert.equal(ui.inAppPath("https://stratlab.studio/stocks/in/tcs", here), null);            // a public page, not the app's
  assert.equal(ui.inAppPath("https://example.com/research/IN/TCS", here), null);               // another site
  assert.equal(ui.inAppPath("https://stratlab.studio/researchers", here), null);
  assert.equal(ui.inAppPath(null, here), null);
  const news = read("src/pages/NewsPage.tsx");
  assert.match(news, /const inApp = inAppPath\(href, window\.location\);\n  if \(inApp\) return <Link className="link" to=\{inApp\}>\{text\}<\/Link>;/);
  assert.doesNotMatch(news, /\.test\(href\)/);
});

test("R5C-018: \"Find a company by name\" is said only where there is a box to find one in", () => {
  for (const p of ["src/pages/ResultsPage.tsx", "src/pages/CorpActionsPage.tsx"]) {
    const src = read(p);
    assert.match(src, /And \{data\.more\} more\.\{scope === "all" \? " Find a company by name to narrow the list\." : ""\}/, p);
    assert.match(src, /\{scope === "all" && \(\n\s*<Field key=\{region\} label="Find a company">/, p);
  }
});
