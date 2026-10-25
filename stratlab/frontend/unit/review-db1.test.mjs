// Review DB (24 Oct 2026): the options builder, imports, paper sessions, chart replay and the journal — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DB-001: offline, the builder lists the recorded indices, prices on their last close and says so", async () => {
  const { recordedLine } = await import("../src/lib/options.ts");
  assert.match(recordedLine("Fri 23 Oct, 15:41 IST"), /^Priced on the last recorded option chain, as of Fri 23 Oct, 15:41 IST \(the last close\)/);
  assert.match(recordedLine("x"), /the broker's margin and paper trading need the live feed/);
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /api<Underlying\[\]>\("\/options\/recorded"\)/);
  assert.match(src, /disabled=\{pricing \|\| \(!!offline && !recordedUnd\)\}/);            // pricing on the recording
  assert.match(src, /disabled=\{starting \|\| !!offline/);                                 // never a session on it
  assert.match(src, /recorded chain as of \$\{recordedAt\(chain\.as_of\)\} \(last close\)/);
  assert.match(src, /p\.recorded \? "" : staleQuoteLine/);
});

test("DB-002: an import with notes can't start until they're read", () => {
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /\|\| timeIssues\.length > 0 \|\| notes\.length > 0\} onClick=\{\(\) => setConfirmStart\(true\)\}/);
  assert.match(src, /Check the import notes at the top and press Got it before you start\./);
});

test("DB-004: times out of order or out of hours are said", async () => {
  const { timingIssues } = await import("../src/lib/options.ts");
  const bad = timingIssues({ entry: "16:00", lastEntry: "08:00", squareoff: "09:00" }, "09:15", "15:40");
  assert.ok(bad.some((x) => x === "The entry time, 16:00, is outside the market's hours (09:15 to 15:40)."));
  assert.ok(bad.some((x) => /last entry \(08:00\) is before the first \(16:00\)/.test(x)));
  assert.ok(bad.some((x) => /square-off \(09:00\) has to come after the entries/.test(x)));
  assert.deepEqual(timingIssues({ entry: "09:30", lastEntry: "14:45", squareoff: "15:15" }, "09:15", "15:40"), []);
  assert.match(read("src/components/kit/TimeInput.tsx"), /onInvalid\?\.\(txt\)/);
  assert.match(read("src/pages/OptionsPage.tsx"), /isn't a time on the 24-hour clock/);
});

test("DB-005: the legs editor stacks into cards on a phone, the strike rule full width", () => {
  assert.match(read("src/pages/OptionsPage.tsx"), /<div className="opt-legs"><DataTable stack label="Legs"/);
  assert.match(read("src/pages/trade/options.css"), /\.opt-legs \.k-tbl-wrap\.stack \.k-table td\[data-label="Strike by"\] \{ grid-column: 1 \/ -1; \}/);
});

test("DB-006: the summary names the distance's unit", async () => {
  const { legRule, offsetsIn } = await import("../src/lib/options.ts");
  const leg = { side: "sell", opt: "CE", offset: 4, lots: 1 };
  assert.equal(legRule(leg, "strikes"), "4 strikes OTM");
  assert.equal(legRule({ ...leg, offset: 1 }, "strikes"), "1 strike OTM");
  assert.equal(legRule(offsetsIn([leg], "points", 50)[0], "points"), "200 pts OTM");
});

test("DB-007: a number past the range is held to it, and the range is said", async () => {
  const { clampTyped, rangeText } = await import("../src/lib/options.ts");
  assert.equal(clampTyped("999", 1, 50, true), 50);
  assert.equal(clampTyped("2.5", -100, 100, true), 3);
  assert.equal(clampTyped("-3", 1, 50, true), 1);
  assert.equal(clampTyped("abc", 1, 50, true), null);
  assert.equal(rangeText(1, 50, true), "A whole number, 1 to 50.");
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /<InNum label=\{`Leg \$\{i \+ 1\} lots`\} value=\{l\.lots\} min=\{1\} max=\{50\} whole/);
  assert.match(src, /Eight legs is the most a structure can have\./);
});

test("DB-008: each expiry choice shows its date, the fallback chips match the server's, the freeze limit shows the exchange's", async () => {
  const { expiryChoiceLabel, POPULAR_FALLBACK } = await import("../src/lib/options.ts");
  assert.equal(expiryChoiceLabel("Nearest", "2026-10-27", (d) => d.slice(5)), "Nearest · 10-27");
  assert.deepEqual(POPULAR_FALLBACK.slice(0, 5).map((u) => u.name), ["NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY"]);
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /has monthly expiries only, so Nearest and Monthly are the same day\./);
  assert.match(src, /placeholder=\{und\?\.freeze \? `\$\{und\.freeze\.toLocaleString\("en-IN"\)\}, the exchange's`/);
});

test("DB-009 and DB-010: export is said, the import names the options builder, the help's words match the toggle", () => {
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /It keeps the expiry as a choice/);
  assert.match(src, /kept from your last visit in this browser/);
  assert.doesNotMatch(read("src/pages/ImportPage.tsx") + read("src/components/ImportStrategy.tsx").replace(/\/\/.*$/gm, ""), /Options tab/);
  const help = read("src/lib/help.ts");
  assert.match(help, /optSize: "Fixed units trades/);
  assert.doesNotMatch(help, /As much as margin allows|Fixed lots/);
});

test("DB-020 and DB-021: one 'now' price, the chart says closed candles, fills and fees said truthfully", async () => {
  const { fillsLine } = await import("../src/lib/paperText.ts");
  const line = fillsLine({ slippage: 0.05, brokerage: 0 }, "0.1% exchange fee each way", "$0.00");
  assert.equal(line, "Orders fill at the close of the candle your rules act on, 0.05% worse for slippage (your setting), not at the live price, and pay 0.1% exchange fee each way. Unrealised P&L already counts the entry's costs.");
  assert.match(fillsLine({ slippage: 0, brokerage: 20 }, "STT, stamp duty, GST", "₹20.00"), /not at the live price, and pay STT, stamp duty, GST, plus brokerage of ₹20\.00 an order\./);
  assert.match(fillsLine({ slippage: 0, brokerage: 0 }, "Commission, SEC and FINRA fees", "$0.00"), /and pay commission, SEC and FINRA fees\./);
  assert.doesNotMatch(read("src/pages/NotebookPage.tsx"), /Orders fill at live prices/);
  const src = read("src/pages/PaperPage.tsx");
  assert.match(src, /closed ones only: the last closed/);
  assert.match(src, /the last price before the stop/);
});

test("DB-022: the equity curve starts at the capital, money to the cent, a rules card and closed trades", () => {
  const src = read("src/pages/PaperPage.tsx");
  assert.match(src, /\[\{ t: snap\.started_at, eq: a\.capital \}, \.\.\.snap\.equity_curve\]/);
  assert.match(src, /\["Cash", money\(a\.cash, cur, 2\)/);
  assert.match(src, /title=\{`Closed trades \(\$\{a\.trades\}\)`\}/);
  assert.match(src, /<CardHead level=\{3\} title="Orders" \/>/);
  assert.match(src, /data-testid="sess-rules"/);
});

test("DB-024: the session chart fills the card on a phone; the sidebar keeps the newest list of notebooks", () => {
  assert.match(read("src/pages/trade/paper.css"), /\.k-card\.sess-chart \.pc:not\(\.pc-full\) \{ margin-inline/);
  assert.match(read("src/lib/app.tsx"), /if \(n === nbSeq\.current\) \{ setNotebooks\(got\)/);
});

test("DB-030 and DB-031: random replay says why it can't start; the journal's rupees are said up front", () => {
  const src = read("src/pages/trade/ReplayPage.tsx");
  assert.match(src, /disabled=\{busy \|\| !indiaLive\}/);
  assert.match(src, /India's market data is offline right now, so it can't start/);
  assert.match(src, /data-testid="rp-problem"/);
  assert.match(src, /The journal keeps trades in rupees, so a replay in another currency isn't saved to it/);
  assert.match(src, /: <button type="button" className="btn" disabled=\{busy\} onClick=\{\(\) => finish\(false\)\}>/);
});

test("DB-032: a practice quantity is a plain number, above 0, and worth at most about ten million dollars", async () => {
  const { parseQty, qtyProblem, maxValue } = await import("../src/lib/replay.ts");
  const m = (v) => `$${v.toLocaleString("en-US")}`;
  assert.equal(parseQty("1e3"), null);
  assert.equal(parseQty("1,000.5"), 1000.5);
  assert.equal(qtyProblem("abc", 4590, "USD", m), "Enter a number, such as 10 or 0.5.");
  assert.equal(qtyProblem("0", 4590, "USD", m), "Enter a quantity above 0.");
  assert.match(qtyProblem("1000000000", 4590, "USD", m), /one practice order can be worth up to \$10,000,000/);
  assert.equal(qtyProblem("2", 4590, "USD", m), null);
  assert.equal(maxValue("INR"), 1e9);
  assert.match(read("src/pages/trade/ReplayPage.tsx"), /qtyText\(q, undefined, cur === "INR" \? "IN" : "US"\)/);
});

test("DB-041 to DB-044: the journal's minus, plurals, single-trade curve, stop side, saved toast and the market tab", () => {
  const src = read("src/pages/trade/JournalPage.tsx");
  assert.match(src, /const rText = \(v: number\) => `\$\{v > 0 \? "\+" : v < 0 \? "−" : ""\}/);
  assert.match(src, /\(\$\{trades\(r\.planned_n\)\}\)/);
  assert.match(src, /const first = s\.first && s\.equity\.length && s\.first < s\.equity\[0\]\.t \? \[\{ t: s\.first, v: 0 \}\] : \[\];/);
  assert.match(src, /planned stop goes \$\{dir === "long" \? "below" : "above"\} its entry/);
  assert.match(src, /"Saved\."\);/);
  assert.match(src, /if \(to !== j\.market\) \{ setMarket\(to\); setSegment\("all"\); \}/);
  assert.match(src, /const today = \[istToday\(\), local\]\.sort\(\)\[0\];/);
  assert.match(read("src/pages/trade/journal.css"), /\.j-verdict-head\.not_enough \{ font-size: clamp\(28px, 4vw, 40px\); \}/);
});
