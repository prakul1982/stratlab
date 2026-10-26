// FX-1: the RC2A findings on the IPO pages, the lock text's price, the scans, the pulse, the US company page and the trade pages.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("RC2A-004: a closing time is shown only when the exchange's page gave one", async () => {
  const { clockText } = await import("../src/lib/ipoText.ts");
  assert.equal(clockText("17:00"), "5 PM");
  assert.equal(clockText("19:30"), "7:30 PM");
  assert.equal(clockText("09:00"), "9 AM");
  const list = read("src/pages/IposPage.tsx"), page = read("src/pages/IpoPage.tsx"), text = read("src/lib/ipoText.ts");
  assert.doesNotMatch(list + page + text, /5 PM IST/);
  assert.match(list, /r\.close_time && <span className="k-sub-line">\{clockText\(r\.close_time\)\} IST/);
  assert.match(page, /r\.close_time && <span className="k-note" data-testid="ipo-close-time">/);
});

test("RC2A-003: the key and value of the issue grid are one item, so a wrapping grid cannot pair a label with the next value", () => {
  const page = read("src/pages/IpoPage.tsx"), css = read("src/pages/ipo.css");
  assert.doesNotMatch(page, /<><dt>/);
  assert.equal((page.match(/<div(?: className="wide")?><dt>/g) ?? []).length >= 15, true);
  assert.match(css, /\.ipo-facts > div\.wide \{ grid-column: 1 \/ -1; \}/);
});

test("RC2A-002: the latest close is dated on the list", () => {
  assert.match(read("src/pages/IposPage.tsx"), /Close \$\{fmtDate\(p\.latest_date, \{ year: false \}\)\} · /);
});

test("RC2A-006: the list says when the bids were read, and the banner names its own read", () => {
  const list = read("src/pages/IposPage.tsx");
  assert.match(list, /data-testid="ipo-bids-read">Bids read /);
  assert.match(list, /At the list's read\{d\.problems_at/);
});

test("RC2A-011: alerts switched on with nowhere to send them say so, with the link", () => {
  const list = read("src/pages/IposPage.tsx");
  assert.match(list, /p\.allowed && p\.on && !p\.channels\.length && <p className="k-callout k-small" role="status" data-testid="ipo-no-channel">/);
  assert.ok(list.indexOf("<AlertsCard") < list.indexOf("<Aside rows"), "the settings sit above the folds");
  assert.match(list, /SME issues are left out of the alerts unless you tick the box above/);
});

test("RC2A-010: a lock names the rupee price a plan is charged, the local amount only as 'about'", async () => {
  const { planPriceLine } = await import("../src/lib/planPrice.ts");
  const paid = { mode: "paid", payments: true, yearly: true };
  const p = { offer: paid, countries: {}, currencies: {
    INR: { symbol: "₹", name: "Rupee", basic: 699, pro: 1999, basic_year: 6999, pro_year: 19999, charged_in: "INR", yearly_charged_in: "INR" },
    JPY: { symbol: "¥", name: "Yen", basic: 1150, pro: 3300, basic_year: 11500, pro_year: 33000, charged_in: "INR", yearly_charged_in: "INR",
      charge_about: { basic: 1155, pro: 3305, basic_year: 11550, pro_year: 33050 } },
    USD: { symbol: "$", name: "Dollar", basic: 8, pro: 24, basic_year: 80, pro_year: 240, charged_in: "USD", yearly_charged_in: "USD" } } };
  assert.equal(planPriceLine("basic", p, "JPY"), "Basic is ₹699 a month or ₹6,999 a year, paid in rupees (about ¥1,155 or ¥11,550 at today's rate).");
  assert.equal(planPriceLine("basic", p, "USD"), "Basic is $8 a month or $80 a year.");
  assert.equal(planPriceLine("basic", p, "INR"), "Basic is ₹699 a month or ₹6,999 a year.");
});

test("RC2A-021, 022: a scan says which price its rows hold", () => {
  const scans = read("src/pages/ResearchScans.tsx");
  assert.match(scans, /On today's last price, session still going/);
  assert.match(scans, /On the last whole session/);
  assert.match(scans, /data-testid="scan-whole-session"/);
  assert.match(scans, /list of \$\{s\.as_of\}/);
});

test("RC2A-024: the pulse reads its cards again when the mood was written on newer levels", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /ai\.levels_at > cardsAt\) reloadCards\(\)/);
  assert.match(r, /data-testid="pulse-mood-older"/);
});

test("RC2A-027: a US company's page has holders above 5% and its flagged filings", () => {
  const r = read("src/pages/Research.tsx"), u = read("src/components/UsFilings.tsx");
  assert.match(r, /region === "US" && !c\.delisted && <UsFilingsCards symbol=\{c\.symbol\} \/>/);
  assert.match(r, /\{ id: "us-owners", label: "Holders above 5%" \}/);
  assert.match(u, /\/research\/us-company\//);
});

test("RC2A-028: a qualifier the company page gives a figure stays with it in the comparison", () => {
  assert.match(read("src/pages/Research.tsx"), /QUALIFIES\.test\(note\) && <span className="k-sub-line" data-testid="cmp-note">/);
});

test("RC2A-031: the start dialog says when the session will enter", async () => {
  const { startWhenText } = await import("../src/lib/options.ts");
  const t = { entry: "09:30", lastEntry: "14:45" };
  const wed = (hm) => new Date(`2026-10-28T${hm}:00+05:30`);
  assert.match(startWhenText(t, null, wed("09:55")), /^now if prices are live, because today's window is open \(09:30 to 14:45\)/);
  assert.equal(startWhenText(t, null, wed("08:00")), "at 09:30 on market days");
  assert.equal(startWhenText(t, null, wed("16:00")), "at 09:30 on market days");
  assert.equal(startWhenText(t, null, new Date("2026-10-31T10:00:00+05:30")), "at 09:30 on market days");        // a Saturday
  assert.match(startWhenText(t, { name: "My rules" }, wed("10:00")), /^whenever "My rules" signals a trade/);
});

test("RC2A-032, 037: an options session with fills never waits for 'the first prices'; one figure is not shown twice; the rules wrap cleanly", () => {
  const s = read("src/pages/OptionsSession.tsx"), css = read("src/styles.css");
  assert.match(s, /orders\.length > 0 \|\| p \? \{ text: "Reading the latest prices"/);
  assert.match(s, /if \(running && p && !\(a\.today \?\? 0\) && !today\.length\) return null;/);
  assert.match(s, /eqSpan < a\.capital \* 0\.05/);
  assert.match(css, /\.rules-strip li:not\(:first-child\)::before \{ content: "·"/);
  assert.doesNotMatch(css, /\.rules-strip li:not\(:last-child\)::after/);
});

test("RC2A-034: the journal's verdict names the trades the tab shows", () => {
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /show === "practice" \? "your practice trades" : show === "all" && practice > 0 \? "your trades" : "your real trades"/);
  assert.match(j, /<span className="k-eyebrow">Verdict on \{whose\}<\/span>/);
});

test("RC2A-033: a paper session's page has no empty card and its rules come last", () => {
  const p = read("src/pages/PaperPage.tsx");
  assert.match(p, /\{closedTrades\.length > 0 && <Card label="Closed trades">/);
  assert.ok(p.indexOf('<Card label="Rules">') > p.indexOf('<Card label="Orders">'));
});

test("RC2A-029 (UI-FIX-1): a phone's segmented control shares its row, no label wraps, and one that does not fit stacks in equal widths", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(max-width: 480px\) \{\s*\.k-seg \{ display: flex; width: 100%; \}\s*\.k-seg button \{[^}]*white-space: nowrap/);
  assert.match(css, /\.k-seg\[data-stack="1"\] \{ display: flex; flex-direction: column; \}/);
  assert.match(css, /\.k-seg\[data-stack="2"\] \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
  const seg = read("src/components/kit/Seg.tsx");
  assert.match(seg, /setAttribute\("data-stack", "2"\)/);
  assert.match(seg, /setAttribute\("data-stack", "1"\)/);
});

test("RC2A-040, 041, 038, 039: events, the account chip, Trade home and the watchlist", () => {
  assert.match(read("src/pages/trade/EventsPage.tsx"), /kinds\.filter\(\(k\) => !none\(k\)\)\.map\(\(k\) => \(\{ value: k, label: v\.kinds\[k\] \}\)\)/);
  assert.match(read("src/pages/trade/EventsPage.tsx"), /className="k-two ev-pair"/);
  assert.match(read("src/components/SideMenus.tsx"), /<span className="acct-name">Account<\/span>/);
  const home = read("src/pages/SpaceHomes.tsx");
  assert.ok(home.indexOf("<MarketStrip />") < home.indexOf("<Top onSteps"), "today's market comes before the first-steps card");
  assert.match(read("src/pages/Research.tsx"), /<Card compact className="watch-add">/);
});

test("RC2A-042: the chosen segment is filled in dark, as the chosen pills are", () => {
  assert.match(read("src/styles.css"), /:root\[data-theme="dark"\] \.k-seg button\[aria-checked="true"\] \{ background: var\(--ink\); color: var\(--on-ink\); box-shadow: none; \}/);
});
