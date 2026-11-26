// inv96 (owner, 26 Nov: "ok go ahead"): the Invest home's Coming up lists the person's own stocks' next dates (results, ex-dates with
// the record date, bonuses, splits), the Calendar's "My stocks" rows from the same two answers, and its "See calendar" opens the
// Calendar on My stocks in the market picked. With none, the market's events under a label saying why. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { myStockRows, resultRows, actionRows } = await import("../src/lib/calendarRows.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const res = [
  { region: "IN", symbol: "TCS", name: "Tata Consultancy Services", date: "2026-12-03", purpose: "Financial Results", when: null, mine: true },
  { region: "IN", symbol: "ITC", name: null, date: "2026-11-20", purpose: "", mine: true },          // gone by: not coming up
];
const acts = [
  { id: "a1", region: "IN", symbol: "RELIANCE", name: "Reliance Industries", ex_date: "2026-12-01", kind: "dividend", label: "Final dividend", amount: 5.5, currency: "INR", record_date: "2026-12-01", mine: true },
  { id: "a2", region: "IN", symbol: "M&M", name: "Mahindra & Mahindra", ex_date: "2026-12-03", kind: "bonus", label: "Bonus 1:1", amount: null, currency: "INR", record_date: null, mine: true },
  { id: "a3", region: "IN", symbol: "INFY", name: "Infosys", ex_date: "2027-01-20", kind: "split", label: "Split 1:2", amount: null, currency: "INR", record_date: null, mine: true },   // past the window
];

test("the person's stocks' dates: in date order, results before actions on a day, each company linking to its page", () => {
  const rows = myStockRows(res, acts, "2026-11-26", "2026-12-09");
  assert.deepEqual(rows.map((r) => [r.date, r.type, r.name]), [
    ["2026-12-01", "action", "Reliance Industries"], ["2026-12-03", "results", "Tata Consultancy Services"], ["2026-12-03", "action", "Mahindra & Mahindra"]]);
  assert.equal(rows[2].to, "/research/IN/M%26M");
  assert.equal(rows[2].symbol, "M&M");
  assert.match(rows[0].detail, /^Ex-date: Final dividend · ₹5\.50 a share · record date /);
  assert.equal(rows[1].detail, "Financial Results");
  assert.equal(rows[2].detail, "Ex-date: Bonus 1:1");
  // a company without a stored name shows its symbol; a results day with no purpose has no detail (the card says "Results")
  assert.equal(resultRows([{ ...res[1], date: "2026-11-27" }], "2026-11-26")[0].name, "ITC");
  assert.equal(actionRows(acts, "2026-11-30").length, 0);
});

test("the Calendar's My stocks and the Invest home's card read the same rows", () => {
  const cal = read("src/pages/CalendarPage.tsx");
  assert.match(cal, /parts\.push\(resultRows\(/);
  assert.match(cal, /parts\.push\(actionRows\(corp\.ahead, until\)\)/);
  const homes = read("src/pages/SpaceHomes.tsx");
  const card = homes.slice(homes.indexOf("function InvestComing"), homes.indexOf("function WatchPanel"));
  assert.match(card, /\/research\/results\?\$\{q\}/);
  assert.match(card, /\/research\/corp-actions\?\$\{q\}/);
  assert.match(card, /const q = `region=\$\{region\}&scope=mine`/);
  assert.match(card, /myStockRows\(/);
  assert.match(card, /\.slice\(0, 5\)/);
  // Date · Company · What, the company a link to its page
  // (the symbol, as the watchlist beside it names the stocks; the full name is the link's title)
  assert.match(card, /header: "Date"[\s\S]*header: "Company", rowHeader: true, cell: \(r\) => <Link className="link" to=\{r\.to\} title=\{r\.name\}>\{r\.symbol \?\? r\.name\}<\/Link>[\s\S]*header: "What"/);
  // See calendar: the Calendar on My stocks, in the market picked here
  assert.match(card, /<SeeCalendar to=\{withRegion\(calHref\("mine"\), region\)\} \/>/);
  // the wait holds the five-row table's height (cal94, LIVE12B-012)
  assert.match(card, /<div className="coming-skel"><PanelSkel/);
  // none: the market events under a label saying why, the label taking the fifth row's place
  assert.match(card, /Market events \(\{add\} to see their dates\)/);
  assert.match(card, /Market events \(nothing dated for your stocks this week or next\)/);
  assert.match(card, /region \}\)\.slice\(0, 4\)/);
});
