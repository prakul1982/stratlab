// MW-2 (owner, 9 Nov, with a screenshot of the Markets panel): "why is this only extendable from one top corner ... while adding
// something why is it so cluttered ... we need to redesign it". The panel is sized from every edge and corner and stays inside the
// window; one search field adds a symbol; a row is one line under column heads; the tabs say their lists' names in words ("1 6" was
// a list named "1" beside its count of 6); and "last close" names the last day the market traded, never a weekend day.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const W = await import("../src/lib/watch.ts");
const L = await import("../src/lib/watchLayout.ts");
const H = await import("../src/lib/marketHours.ts");

const market = (id, tz, open, close, extra = {}) => ({ id, name: id, venues: "", currency: "INR", symbol: "", tz, hours: open ? { open, close, days: "Mon–Fri" } : null,
  what: "", costs: "", brokerage: 0, status: "live", max_days: null, holidays: [], ...extra });
const IN = market("IN", "Asia/Kolkata", "09:15", "15:30");
const US = market("US", "America/New_York", "09:30", "16:00");
const at = (iso) => new Date(iso);

// ---------- 4. the last close's day ----------
test("the last trading day of a market is never a weekend day or one of its holidays", () => {
  // the owner's case: Sunday 8 Nov 2026, India shut since Friday
  assert.equal(H.lastTradingDay(IN, at("2026-11-08T14:00:00+05:30")), "2026-11-06");
  assert.equal(H.lastTradingDay(IN, at("2026-11-07T10:00:00+05:30")), "2026-11-06");            // Saturday
  assert.equal(H.lastTradingDay(IN, at("2026-11-09T08:00:00+05:30")), "2026-11-06");            // Monday before the open: still Friday's close
  assert.equal(H.lastTradingDay(IN, at("2026-11-09T09:15:00+05:30")), "2026-11-09");            // from the open it is today's session
  assert.equal(H.lastTradingDay(IN, at("2026-11-09T18:00:00+05:30")), "2026-11-09");            // after the close: today's close
  // a holiday is stepped over like a weekend day: Monday shut, read on the Monday and on Tuesday before the open
  const hol = { ...IN, holidays: ["2026-11-09"] };
  assert.equal(H.lastTradingDay(hol, at("2026-11-09T12:00:00+05:30")), "2026-11-06");
  assert.equal(H.lastTradingDay(hol, at("2026-11-10T08:00:00+05:30")), "2026-11-06");
  assert.equal(H.lastTradingDay({ ...IN, holidays: ["2026-11-06", "2026-11-09"] }, at("2026-11-10T08:00:00+05:30")), "2026-11-05");
  // the US in its own calendar: Sunday morning in India is still Saturday in New York, and the last session is Friday's
  assert.equal(H.lastTradingDay(US, at("2026-11-08T06:00:00+05:30")), "2026-11-06");
  assert.equal(H.lastTradingDay(US, at("2026-11-10T02:00:00+05:30")), "2026-11-09");            // Monday 15:30 in New York: Monday's session
  // forex and the global commodity futures: Saturday, and Sunday before the week opens, are Friday's
  const FX = market("FX", "America/New_York", null, null), CM = market("CMDTY", "America/New_York", null, null);
  assert.equal(H.lastTradingDay(FX, at("2026-11-07T12:00:00-05:00")), "2026-11-06");
  assert.equal(H.lastTradingDay(FX, at("2026-11-08T16:59:00-05:00")), "2026-11-06");
  assert.equal(H.lastTradingDay(FX, at("2026-11-08T17:00:00-05:00")), "2026-11-09");            // the week has opened: Monday's session
  assert.equal(H.lastTradingDay(CM, at("2026-11-08T17:30:00-05:00")), "2026-11-06");            // commodities open an hour later
  assert.equal(H.lastTradingDay(market("CRYPTO", "UTC", null, null), at("2026-11-08T12:00:00Z")), null);   // never shut
  // every day of a fortnight, every hour: never a Saturday or a Sunday
  for (let h = 0; h < 24 * 14; h++) {
    const now = new Date(Date.parse("2026-11-01T00:30:00Z") + h * 3_600_000);
    for (const m of [IN, US, FX, CM]) {
      const wd = new Date(`${H.lastTradingDay(m, now)}T12:00:00Z`).getUTCDay();
      assert.ok(wd >= 1 && wd <= 5, `${m.id} at ${now.toISOString()}: ${H.lastTradingDay(m, now)}`);
    }
  }
});

test("the panel's foot says the last trading day, never the day the prices were read (it said 'last close Sun')", () => {
  const readOnSunday = ["2026-11-08T08:30:00Z", "2026-11-08T08:31:10Z"];
  // with the market's own last day
  assert.equal(W.asOfLine(readOnSunday, "Asia/Kolkata", true, H.lastTradingDay(IN, at("2026-11-08T14:00:00+05:30"))), "Closed · last close Fri 6 Nov");
  assert.equal(W.asOfLine([], "Asia/Kolkata", true, "2026-11-06"), "Closed · last close Fri 6 Nov");     // said before any price has come
  // without it (a market the page has no days for): the price's own day, moved off the weekend
  assert.equal(W.asOfLine(readOnSunday, "Asia/Kolkata", true), "Closed · last close Fri 6 Nov");
  assert.equal(W.asOfLine(["2026-11-07T08:30:00Z"], "Asia/Kolkata", true), "Closed · last close Fri 6 Nov");
  assert.equal(W.asOfLine(["2026-11-07T03:00:00Z"], "America/New_York", true), "Closed · last close Fri 6 Nov");   // Friday 22:00 in New York
  for (let d = 1; d <= 14; d++) assert.doesNotMatch(W.asOfLine([Date.UTC(2026, 10, d, 9)], "Asia/Kolkata", true), /Sat|Sun/);
  // open markets still say the moment
  assert.equal(W.asOfLine(["2026-11-06T04:59:39Z"]), "Prices as of 10:29:39 IST");
  assert.equal(W.dayText("2026-11-06"), "Fri 6 Nov");
  // a list of two markets says the newer of their last days
  assert.equal(W.newestDay(["2026-11-06", null, "2026-11-09", undefined]), "2026-11-09");
  assert.equal(W.newestDay([null]), null);
  const p = read("src/components/watch/WatchPanel.tsx");
  assert.match(p, /const lastDay = allShut \? newestDay\(/);
  assert.match(p, /lastTradingDay\(m\)/);
  assert.match(p, /asOfLine\(\[[^\]]*\], allShut \? tzOf : undefined, allShut, lastDay\)/);
});

// ---------- 3. the tabs, the rows ----------
test("a tab says its list's name in words: a list named only a number reads 'List 1', and its count is not set beside it", () => {
  assert.equal(W.listName("1"), "List 1");
  assert.equal(W.listName(" 2 "), "List 2");
  assert.equal(W.listName("Banks"), "Banks");
  assert.equal(W.listName("2026 ideas"), "2026 ideas");
  assert.equal(W.listName(""), "List");
  assert.equal(W.countSaid(1), "1 symbol");
  assert.equal(W.countSaid(6), "6 symbols");
  const lists = [{ id: "default", name: "Watchlist", default: true, items: [{}, {}] }, { id: "a", name: "1", default: false, items: Array(6).fill({}) }, { id: "b", name: "2", default: false, items: [{}] }];
  assert.deepEqual(lists.map(W.tabTitle), ["Your Research watchlist: 2 symbols", "List 1: 6 symbols", "List 2: 1 symbol"]);
  const p = read("src/components/watch/WatchPanel.tsx");
  // the tab's words are the name; the count is in its tooltip and in the panel's foot, in words
  assert.match(p, /title=\{tabTitle\(l\)\}>\{l\.default \? l\.name : listName\(l\.name\)\}<\/button>/);
  assert.doesNotMatch(p, /<small aria-hidden="true">\{l\.items\.length\}<\/small>/);
  assert.match(p, /\{list \? countSaid\(used\) : ""\}/);
  assert.doesNotMatch(read("src/components/watch/watch.css"), /\.mw-tab small/);
});

test("a row is one line of symbol, last, change and change %, in columns shared with the heads; the heads sort the list", () => {
  const q = { price: 1520, change: 20, change_pct: 1.33, prev_close: 1500, at: null, currency: "INR", stale: false };
  assert.equal(W.changeAbsOf(q), 20);
  assert.equal(W.changeAbsOf(q, 1485), -15);                                   // a live tick against the previous close
  assert.equal(W.changeAbsOf({ ...q, prev_close: null }), 20);                 // no previous close: the quote's own figure
  assert.equal(W.changeAbsOf(undefined), null);
  assert.equal(W.changeAbsText(20, 1520, "INR", "IN", "INFY"), "+20.00");
  assert.equal(W.changeAbsText(-1234.5, 124350.75, "INR", "IN", "^NSEI"), "−1,234.50");
  assert.equal(W.changeAbsText(0.001, 1520, "INR", "IN", "INFY"), "0.00");     // no sign on nothing
  assert.equal(W.changeAbsText(0.35, 1520, "INR", "IN", "INFY"), "+0.35");     // the price's own decimals, not four for a change under one
  assert.equal(W.changeAbsText(-0.00012, 1.0852, "USD", "FX", "EURUSD=X"), "−0.00012");
  assert.equal(W.changeAbsText(-0.0004, 0.0721, "USD", "CRYPTO", "DOGE-USD"), "−0.0004");
  assert.equal(W.changeAbsText(null, 1520, "INR", "IN", "INFY"), "–");
  assert.equal(W.priceText(1520, "INR", "IN", "INFY"), "1,520.00");
  // the heads' presses
  assert.equal(W.nextSort("custom", "name"), "name");
  assert.equal(W.nextSort("name", "name"), "custom");
  assert.deepEqual(["custom", "change_desc", "change_asc"].map((s) => W.nextSort(s, "change")), ["change_desc", "change_asc", "custom"]);
  assert.equal(W.nextSort("name", "change"), "change_desc");
  const row = read("src/components/watch/WatchRow.tsx"), p = read("src/components/watch/WatchPanel.tsx"), css = read("src/components/watch/watch.css");
  for (const cls of ["mw-num mw-price", "mw-num mw-abs mw-c-abs", "mw-num mw-chg"]) assert.ok(row.includes(cls), cls);
  for (const head of [">Symbol{", ">Last<", ">Change<", ">Change %{"]) assert.ok(p.includes(head), head);
  assert.doesNotMatch(p, /<Select /);                                          // no sort picker in the bar
  assert.match(css, /\.mw-cols, \.mw-rows, \.mw-row, \.mw-open \{ display: grid; grid-template-columns: subgrid; \}/);
  assert.match(css, /\.mw-num \{[^}]*text-align: right;[^}]*font-variant-numeric: tabular-nums; \}/);
  assert.match(css, /@container mw \(max-width: 359px\) \{[^@]*\.mw-c-abs \{ display: none; \}/);
  // a narrow panel keeps the symbol's room: its note is a dot named in the foot, and the change has no arrow (its sign and colour stay)
  assert.match(css, /@container mw \(max-width: 439px\) \{[^@]*\.mw-arrow \{ display: none; \}[^@]*\.mw-legend \{ display: flex; \}/);
  assert.match(row, /<i className="mw-arrow">\{changeArrow\(change\)\}<\/i>\{text\}/);
  assert.match(p, /notes\.has\("Delayed"\) && <span><i className="mw-dot delayed" aria-hidden="true" \/>Delayed, up to 15 minutes<\/span>/);
  // under a finger (44px handles) the symbol keeps its room: the change in price gives way below 480px, the percent stays
  assert.match(css, /@media \(max-width: 900px\), \(pointer: coarse\) \{\n  @container mw \(max-width: 479px\) \{[^@]*\.mw-c-abs \{ display: none; \}/);
  // "Closed" is not said on every row of a list whose markets are all shut: the foot says it once
  assert.match(p, /open\[it\.market\] === false && !allShut \? "Closed" : null/);
  // the visitor's board is the same table
  assert.match(read("src/components/watch/PublicBoard.tsx"), /<div className="mw-table fixed plain no-abs">/);
});

// ---------- 2. adding a symbol ----------
test("the add search lists what a list can take, each once, with symbol, name and exchange, and says what is on the list", () => {
  const found = [
    { id: "IN:1", symbol: "INFY", name: "Infosys Limited", exchange: "NSE", type: "EQ", market: "IN" },
    { id: "IN:2", symbol: "INFY", name: "Infosys Limited", exchange: "BSE", type: "EQ", market: "IN" },          // the same company's other listing
    { id: "IN:3", symbol: "INFY26NOVFUT", name: "INFY", exchange: "NFO", type: "FUT", market: "IN", fno: true },  // a contract: not on a list
    { id: "IN:4", symbol: "NIFTY 50", name: "NIFTY 50", exchange: "NSE", type: "INDEX", market: "IN" },
    { id: "US:INFY", symbol: "INFY", name: "Infosys Ltd ADR", exchange: "US", type: "EQ", market: "US" },
    { id: "CRYPTO:BTC-USD", symbol: "BTC/USD", name: "Bitcoin / US Dollar", exchange: "Coinbase", type: "CRYPTO", market: "CRYPTO" },
    { id: "IN:5", symbol: "GOLDBEES", name: "Nippon India Gold BeES", exchange: "NSE", type: "EQ", market: "IN", etf: true },
  ];
  const rows = W.addRows(found, (id) => id === "IN:^NSEI");
  assert.deepEqual(rows.map((r) => [r.item.id, r.symbol, r.name, r.exchange, r.kind, r.on]), [
    ["IN:INFY", "INFY", "Infosys Limited", "NSE", "Stock", false],
    ["IN:^NSEI", "NIFTY 50", "", "NSE", "Index", true],
    ["US:INFY", "INFY", "Infosys Ltd ADR", "US", "Stock", false],
    ["CRYPTO:BTC-USD", "BTC/USD", "Bitcoin / US Dollar", "Crypto", "Crypto", false],
    ["IN:GOLDBEES", "GOLDBEES", "Nippon India Gold BeES", "NSE", "ETF", false],
  ]);
  assert.equal(W.addRows(found, () => false, 2).length, 2);
  assert.deepEqual(W.addRows([], () => false), []);
  // where it trades is the exchange or the market, never where the prices come from
  assert.deepEqual(["IN", "US", "UK", "EU", "JP", "FX", "CRYPTO", "MCX", "CDS", "CMDTY"].map((m) => W.exchangeOf({ market: m, exchange: m === "IN" ? "BSE" : "Coinbase" })),
    ["BSE", "US", "London", "Europe", "Tokyo", "Forex", "Crypto", "MCX", "NSE currency", "Global futures"]);
});

test("the search's keys go round its rows, and adding says in a line what came of it", () => {
  assert.equal(W.stepRow(-1, 3, "ArrowDown"), 0);
  assert.equal(W.stepRow(2, 3, "ArrowDown"), 0);
  assert.equal(W.stepRow(0, 3, "ArrowUp"), 2);
  assert.equal(W.stepRow(-1, 3, "ArrowUp"), 2);
  assert.equal(W.stepRow(1, 3, "Home"), 0);
  assert.equal(W.stepRow(1, 3, "End"), 2);
  assert.equal(W.stepRow(0, 0, "ArrowDown"), -1);
  const infy = { id: "IN:INFY", market: "IN", symbol: "INFY", name: "Infosys", kind: "stock" }, tcs = { ...infy, id: "IN:TCS", symbol: "TCS" };
  const mine = { name: "Watchlist", default: true, items: [infy] }, one = { name: "1", default: false, items: [infy] };
  assert.deepEqual(W.addOutcome(mine, tcs, null, null), { ok: true, text: "Added TCS to your watchlist." });
  assert.deepEqual(W.addOutcome(one, tcs, 20, null), { ok: true, text: "Added TCS to List 1." });
  assert.deepEqual(W.addOutcome(one, infy, null, null), { ok: false, text: "INFY is already on List 1." });
  assert.deepEqual(W.addOutcome(one, tcs, 1, "1 of 1 symbols on Free. Basic keeps 100."), { ok: false, text: "1 of 1 symbols on Free. Basic keeps 100." });
  assert.deepEqual(W.addOutcome(one, tcs, 1, null), { ok: false, text: "This list is full." });
  const add = read("src/components/watch/AddSymbol.tsx"), p = read("src/components/watch/WatchPanel.tsx");
  // one field over every market (no market named in the request), a listbox of options, Enter and Esc
  assert.match(add, /api<Instrument\[\]>\(`\/instruments\/search\?q=\$\{encodeURIComponent\(term\)\}`\)/);
  assert.match(add, /role="combobox" aria-expanded=\{s\.active\} aria-controls=\{s\.listId\} aria-autocomplete="list"/);
  assert.match(add, /role="listbox" aria-label="Search results"/);
  assert.match(add, /role="option" aria-selected=\{i === s\.on\}/);
  for (const k of ["ArrowDown", "ArrowUp", "Enter", "Escape"]) assert.ok(add.includes(`"${k}"`), k);
  assert.match(add, /role="status"/);
  assert.doesNotMatch(add, /InstrumentSearch|<Select|Popular|Yours/);          // no market picker, no rows of quick picks beside the field
  assert.match(p, /<AddField s=\{search\} disabled=\{!list\} \/>/);
  assert.doesNotMatch(p, /\+ Add symbol|setAdding/);
});

// ---------- 1. the panel's size and place ----------
test("a floating panel is resized from every edge and corner: that edge follows the pointer, the opposite one stays", () => {
  const fl = { ...L.DEFAULT_LAYOUT, mode: "float", w: 400, h: 500, x: 300, y: 200 };
  const box = (l) => [l.x, l.y, l.x + l.w, l.y + l.h];                         // left, top, right, bottom
  const by = (edge, dx, dy) => box(L.resized(fl, dx, dy, 1440, 900, edge));
  assert.deepEqual(L.EDGES.slice().sort(), ["e", "n", "ne", "nw", "s", "se", "sw", "w"]);
  assert.deepEqual(by("e", 50, 999), [300, 200, 750, 700]);                    // the right edge only; the pointer's rise is nothing to it
  assert.deepEqual(by("w", -50, 999), [250, 200, 700, 700]);
  assert.deepEqual(by("s", 999, 60), [300, 200, 700, 760]);
  assert.deepEqual(by("n", 999, -60), [300, 140, 700, 700]);
  assert.deepEqual(by("se", 50, 60), [300, 200, 750, 760]);
  assert.deepEqual(by("ne", 50, -60), [300, 140, 750, 700]);
  assert.deepEqual(by("sw", -50, 60), [250, 200, 700, 760]);
  assert.deepEqual(by("nw", -50, -60), [250, 140, 700, 700]);
  // sensible limits: never under 300 by 320, never over 720 wide or the window less its margin high
  for (const edge of L.EDGES) {
    const small = L.resized(fl, edge.includes("e") ? -2000 : 2000, edge.includes("s") ? -2000 : 2000, 1440, 900, edge);
    const big = L.resized(fl, edge.includes("e") ? 5000 : -5000, edge.includes("s") ? 5000 : -5000, 1440, 900, edge);
    for (const l of [small, big]) {
      assert.ok(l.w >= L.MIN_W && l.w <= L.MAX_W && l.h >= L.MIN_H && l.h <= 900 - 32, `${edge}: ${l.w}×${l.h}`);
      assert.ok(l.x >= 0 && l.y >= 0 && l.x + l.w <= 1440 && l.y + l.h <= 900, `${edge}: inside the window`);
    }
    // as wide as it may be: 720, or as far as the window's edge on that side (the left edge held, the panel's right is 700 from it)
    if (/[ew]/.test(edge)) { assert.equal(small.w, L.MIN_W, edge); assert.equal(big.w, edge.includes("e") ? L.MAX_W : 700, edge); }
    if (/[ns]/.test(edge)) assert.equal(small.h, L.MIN_H, edge);
    // the edge opposite the one held has not moved
    if (edge.includes("e")) assert.equal(big.x, 300); if (edge.includes("w")) assert.equal(big.x + big.w, 700);
    if (edge.includes("s")) assert.equal(big.y, 200); if (edge.includes("n")) assert.equal(big.y + big.h, 700);
  }
  // a panel still resting in its corner (no place of its own yet) is sized from where it is drawn
  const corner = L.resized({ ...L.DEFAULT_LAYOUT, mode: "float", w: 380, h: 560 }, -40, -40, 1440, 900, "nw");
  assert.deepEqual(box(corner), [1440 - 16 - 420, 900 - 16 - 600, 1440 - 16, 900 - 16]);
  // a docked panel has its left edge only
  assert.equal(L.resized({ ...L.DEFAULT_LAYOUT, mode: "dock", w: 400 }, -100, 300, 1920, 1080, "se").w, 500);
});

test("the panel is never off-screen after the window is resized, and its size and place are kept for the person", () => {
  const kept = { open: true, mode: "float", w: 700, h: 800, x: 1100, y: 250, list: null, sort: "custom", chart: null };       // saved on a 1920×1080 screen
  for (const [vw, vh] of [[1920, 1080], [1512, 860], [1280, 720], [1024, 600], [901, 500]]) {
    const l = L.clampLayout(kept, vw, vh);
    assert.ok(l.x >= 0 && l.y >= 0 && l.x + l.w <= vw && l.y + l.h <= vh, `${vw}×${vh}: ${JSON.stringify(l)}`);
    assert.ok(l.w >= L.MIN_W && l.h >= L.MIN_H);
    // dragged as far as it goes any way: still whole in the window
    for (const [dx, dy] of [[-9999, -9999], [9999, 9999], [9999, -9999]]) {
      const d = L.dragged(l, dx, dy, vw, vh);
      assert.ok(d.x >= 0 && d.y >= 0 && d.x + d.w <= vw && d.y + d.h <= vh);
    }
  }
  assert.deepEqual(L.clampLayout(kept, 1920, 1080), kept);                      // room for it: exactly as it was left
  const launcher = read("src/components/watch/Launcher.tsx"), p = read("src/components/watch/WatchPanel.tsx"), css = read("src/components/watch/watch.css");
  // kept on this device under the person's own key, and read again against the window each time its size changes
  assert.match(launcher, /usePersisted<PanelLayout>\(`\$\{LAYOUT_KEY\}\.\$\{mode === "app" \? userId \?\? "guest" : "visitor"\}`, DEFAULT_LAYOUT\)/);
  assert.match(launcher, /const layout = useMemo\(\(\) => clampLayout\(raw, vw, vh\), \[raw, vw, vh\]\)/);
  assert.match(launcher, /window\.addEventListener\("resize", on\)/);
  // the top bar's button on a phone goes by what is drawn: a sheet kept open but not shown at load opens on the first press
  assert.match(launcher, /const open = d\.open === "toggle" \? !\(layout\.open && asked\.current\) : d\.open !== false;/);
  // eight grips on a floating panel (the left one is the keyboard's), each for a finger too; the header drags it
  assert.match(p, /shape === "float" && EDGES\.filter\(\(edge\) => edge !== "w"\)\.map\(/);
  assert.match(p, /<div className="mw-head" onPointerDown=\{grab\("move"\)\}>/);
  assert.match(p, /el\.setPointerCapture\(id\)/);
  assert.match(p, /window\.addEventListener\("pointercancel", end\)/);
  // sized while it floats, it is the person's own floating panel: its height is no longer held to half the window
  assert.match(p, /patch\(shape === "dock" \? \{ w: l\.w \} : \{ w: l\.w, h: l\.h, x: l\.x, y: l\.y, mode: "float" \}\)/);
  for (const edge of L.EDGES) assert.match(css, new RegExp(`\\.mw-size\\.${edge}\\b`), edge);
  assert.match(css, /\.mw-size \{[^}]*touch-action: none;/);
  assert.match(css, /\.mw-float \.mw-head \{[^}]*touch-action: none;/);
  assert.match(css, /@media \(pointer: coarse\) \{ \.mw-size \{ --g: 16px; --c: 28px; \} \}/);
});
