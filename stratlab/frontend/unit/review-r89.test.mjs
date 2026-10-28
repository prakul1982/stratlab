// Round 89 (23 Oct 2026): leftovers from rounds 86–88 — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R88-007: the landing FAQ answers what it costs and how to cancel, in the refunds page's words", async () => {
  const { FAQ, faqText } = await import("../src/content/faq.ts");
  const cost = FAQ.find((f) => f.q === "What does it cost, and can I cancel?");
  assert.ok(cost);
  const a = faqText(cost);
  assert.match(a, /The Free plan costs nothing/);
  assert.match(a, /Account → Plan and usage/);                     // the section's real name, as /refunds says it
  assert.match(read("src/content/legal.ts"), /Account → Plan and usage → Cancel subscription/);
  assert.match(a, /stratlab\.studio\/plans/);
  assert.match(a, /stratlab\.studio\/refunds/);
  assert.doesNotMatch(a, /₹\d|\$\d/);                               // no price written here to go stale; the Plans page has them
});

test("R88-009: the Free card says ₹0 always, not per month or year, on the Plans page and the landing page", () => {
  for (const f of ["src/pages/PlansPage.tsx", "src/pages/Login.tsx"]) assert.match(read(f), /p === "free" \? " always"/, f);
});

test("R86-015: a company's price move keeps its decimals, as the price beside it does", async () => {
  const { signedMove } = await import("../src/lib/format.ts");
  assert.equal(signedMove(2), "+2.00");
  assert.equal(signedMove(0.7), "+0.70");
  assert.equal(signedMove(-1234.5, 2, "US"), "−1,234.50");
  assert.equal(signedMove(-123456.5), "−1,23,456.50");             // India's grouping
  assert.equal(signedMove(0.001), "0.00");                          // rounds to nothing: no sign
  assert.equal(signedMove(null), "–");
  assert.match(read("src/components/Research.tsx"), /signedMove\(q\.change, 2\)/);
});

test("R86-005: a scan running a few seconds says the day's first scan is the slow one", () => {
  const src = read("src/pages/ResearchScans.tsx");
  assert.match(src, /setTimeout\(\(\) => setShow\(true\), 3000\)/);
  assert.match(src, /The day's first scan of a list reads each stock's daily chart, so a long list can take 20 seconds or more\. Scans after that take a second or two\./);
  assert.match(src, /<ScanElapsed count=\{cur\?\.count\} \/><\/p><SlowFirstScan \/>/);
});

test("R86-004: in a phone-wide window the filter chips and the chart's tool buttons are 44px, as on a touch screen", () => {
  const css = read("src/styles.css");
  const phone = css.indexOf("@media (max-width: 640px) { .k-chip { height: 44px; } }");
  assert.ok(phone > css.indexOf(".k-chip { flex: none; height: 32px;"));                 // after the 32px rule it overrides
  const chart = read("src/charts/price/priceChart.css");
  assert.match(chart, /@media \(max-width: 640px\) \{\s*\.pc-btn, \.pc-sel, \.pc-seg \.pc-btn \{ min-height: 44px; \}\s*\.pc-btn\.icon \{ width: 44px; \}/);
  // nothing under 44px in a touch rule (R13S-011: a 40px rule after the touch screen's 44px one shrank the iPad's buttons)
  assert.ok(!chart.includes("@media (max-width: 640px), (pointer: coarse)"));
  assert.ok(!css.includes(".k-chip { height: 40px; }"));
});

test("R89-002: the US prints count as settling for 50 minutes after a traded close, and the rotation page says provisional then", async () => {
  const { usSettling, SETTLE_US_MIN } = await import("../src/lib/marketHours.ts");
  const US = { id: "US", tz: "America/New_York", status: "live", hours: { open: "09:30", close: "16:00", days: "Mon–Fri" }, holidays: [] };
  const IN = { id: "IN", tz: "Asia/Kolkata", status: "live", hours: { open: "09:15", close: "15:30", days: "Mon–Fri" }, holidays: [] };
  assert.equal(SETTLE_US_MIN, 50);
  assert.equal(usSettling(US, new Date("2026-10-23T20:20:00Z")), true);        // 16:20 ET, Fri
  assert.equal(usSettling(US, new Date("2026-10-23T20:55:00Z")), false);       // 16:55 ET: final
  assert.equal(usSettling(US, new Date("2026-10-23T19:50:00Z")), false);       // still open
  assert.equal(usSettling(US, new Date("2026-10-24T20:20:00Z")), false);       // Saturday: nothing traded
  assert.equal(usSettling({ ...US, holidays: ["2026-10-23"] }, new Date("2026-10-23T20:20:00Z")), false);
  assert.equal(usSettling(IN, new Date("2026-10-23T10:10:00Z")), false);       // only the US settles
  assert.equal(usSettling(null), false);
  const src = read("src/pages/ResearchScans.tsx");
  assert.match(src, /asOfLabel=\{provisional \? "Provisional closes \(prints still settling\) up to" : "Closes up to"\}/);
  assert.match(src, /region === "US" && !!out\?\.as_of && out\.as_of\.slice\(0, 10\) === dayIn\(now, marketTz\("US"\)\)/);
  assert.match(read("src/pages/MineHome.tsx"), /usSettling\(id === "US"/);
});

test("R89-003: the tile's long 'closing prints settling' words wrap inside the tile; 'on 16 Oct' stays together", () => {
  assert.match(read("src/pages/MineHome.tsx"), /className=\{w\.includes\("settling"\) \? "k-note" : "k-note nowrap"\} data-testid="mine-mkt-when"/);
});

test("R89-005: the previous close shows after the close and while prints settle, not only while the market trades", () => {
  const src = read("src/components/Research.tsx");
  // (a new listing's first session says "Issue price" there instead, DD-010)
  assert.match(src, /\{!preOpen && q\.change != null && <span className="k-note" data-testid="price-prev">\{q\.ref === "issue" \? "Issue price" : "Previous close"\} \{price\(q\.price - q\.change, currency\)\}/);
  assert.doesNotMatch(src, /!closed && !preOpen && !settling && q\.change != null && <span className="k-note" data-testid="price-prev">/);
});

test("R89-006: a price scale whose margin reaches under zero labels no gridline below zero; percent and signed studies keep theirs", async () => {
  const { ValueScale } = await import("../src/charts/price/scales.ts");
  const s = new ValueScale();
  s.top = 0; s.height = 400;
  s.fit(0.1, 350, 0.1, 0.22);                         // AAPL monthly since 1980, with the volume band under it
  assert.ok(s.lo < 0);                                 // the margin itself still reaches below zero (the bars keep their room)
  const t = s.ticks();
  assert.ok(t.length >= 3 && t.every((v) => v >= 0), String(t));
  const m = new ValueScale();
  m.top = 0; m.height = 400;
  m.fit(-2, 3);                                         // MACD: a signed study keeps its negative lines
  assert.ok(m.ticks().some((v) => v < 0));
  const p = new ValueScale();
  p.mode = "percent"; p.base = 100; p.top = 0; p.height = 400;
  p.fit(90, 120);                                       // percent mode: −10% is a real line
  assert.ok(p.ticks().some((v) => v < 100));
});

test("R90-005: the watchlist's price column says last session whenever the tab's market is shut, not only when a quote is dated", () => {
  const src = read("src/pages/Research.tsx");
  assert.match(src, /const shut = \(\(\) => \{ const m = markets\.find\(\(x\) => x\.id === region\); return m \? !marketState\(m\)\.open : false; \}\)\(\);/);
  assert.match(src, /header: `Price · \$\{shut \|\| Object\.values\(quotes \?\? \{\}\)\.some\(\(q\) => sessionOf\(q, marketTz\(region\)\)\) \? "last session" : "today"\}`/);
});

test("R90-008/010/012: a US company's move says its day after the close; Pulse and the money calendar say what their dates are", () => {
  assert.match(read("src/components/Research.tsx"), /closed && \(q\.change_day \|\| quoteDay\) \? `on \$\{fmtDate\(\(q\.change_day \|\| quoteDay\)!, \{ year: false \}\)\}` : since/);
  assert.match(read("src/pages/Research.tsx"), /title=\{pulseClosedDay\(data\?\.indices\) \? "How the market felt at the last close" : "How the market feels today"\}/);
  assert.match(read("src/pages/money/MoneyCalendarPage.tsx"), /asOfLabel="As of"/);
});

test("R90-011: a running paper session's card says Market closed when its market is shut", () => {
  const src = read("src/pages/PaperPage.tsx");
  assert.match(src, /markets\.find\(\(x\) => x\.id === r\.instrument\.market\) \?\? optionsMarket\(markets, r\.instrument\.exchange\); return !!m && !marketState\(m\)\.open;/);
  assert.match(src, /\{r\.status === "running" && shut\(r\) && <span className="k-note" data-testid="sess-market-shut">Market closed<\/span>\}/);
});

test("R90-014/R91-006: the feature check says when it ran; the library says what its dates are", () => {
  assert.match(read("src/pages/admin/PlatformPanel.tsx"), /\{r\.auto \? "Automatic check" : "Ran"\} \{fmtDateTime\(r\.at, \{ weekday: true, tz: IST, zone: true \}\)\} \(\{ago\(r\.at\)\}\)/);
  assert.match(read("src/pages/PublicLibrary.tsx"), /Each entry's dates are the prices its latest test covered\./);
});

test("R92-002/003/005: the notebook says what its plan won't run before Run; a phone chip row shows its chosen chip; a shut market hides a stale wait", () => {
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /\{planBlock && <div data-testid="run-plan-block"><PlanNote>\{planBlock\}<\/PlanNote><\/div>\}/);   // the plan note since DP2-022
  assert.match(nb, /if \(planBlock\) \{ plansToast\(planBlock\); return; \}/);
  const chips = read("src/components/kit/ChipBar.tsx");
  assert.match(chips, /querySelector<HTMLElement>\('\[aria-pressed="true"\]'\)/);
  assert.match(chips, /\$\{atEnd \? " end" : ""\}/);
  const css = read("src/styles.css");
  assert.match(css, /\.k-chipbar\.end \{ mask-image: none; -webkit-mask-image: none; \}/);
  assert.match(css, /\.k-custom select\.k-input \{ padding-right: 36px; \}/);
  assert.match(read("src/pages/OptionsSession.tsx"), /!\(feed === closed && \/\^Waiting for \(live prices\|the option chain\)\/\.test\(snap\.note\)\)/);
});

test("R93-004: a weekly brief's headline shows the day it ran", () => {
  assert.match(read("src/pages/NewsPage.tsx"), /\{it\.day && <span className="k-note" data-testid="news-item-day">\{it\.day\}: <\/span>\}<ItemText/);
});

test("R95: phone tap targets, a dated first axis tick, charts measured again after first paint", async () => {
  assert.match(read("src/components/Rotation.tsx"), /const hitR = \(phone: boolean\) => \(COARSE \|\| phone \? 22 : 12\);/);
  assert.match(read("src/styles.css"), /\.fo-row \.link \{ display: inline-flex; justify-content: center; min-width: 32px; \}/);
  assert.match(read("src/components/chart/core.ts"), /window\.setTimeout\(measure, 250\)/);
  const { timeTicks } = await import("../src/charts/price/scales.ts");
  const day = (m, d) => Date.UTC(2026, m, d);
  const walls = [day(8, 18), day(8, 21), day(8, 22), day(9, 1), day(9, 2), day(9, 14)];
  const ticks = timeTicks(walls, 0, walls.length - 1, (i) => i * 100, 84);
  assert.equal(ticks[0].label, "21 Sep");
  assert.ok(ticks.some((t) => t.label === "Oct"));
});

test("R92-001: a lock says what the plan costs, in the visitor's currency, while plans can be bought", async () => {
  const offer = await import("../src/lib/offer.ts");
  const { planPriceLine } = await import("../src/lib/planPrice.ts");
  const paid = { mode: "paid", payments: true, yearly: true, promo_until: null, free_now: {}, free_trial_days: null };
  const p = { offer: paid, countries: {}, currencies: {
    INR: { symbol: "₹", name: "Rupee", basic: 699, pro: 1999, basic_year: 6999, pro_year: 19999, charged_in: "INR", yearly_charged_in: "INR" },
    SAR: { symbol: "SAR ", name: "Riyal", basic: 27, pro: 78, basic_year: 274, pro_year: 783, charged_in: "INR", yearly_charged_in: "INR", converted: true } } };
  assert.equal(planPriceLine("basic", p, "INR"), "Basic is ₹699 a month or ₹6,999 a year.");
  assert.equal(planPriceLine("pro", p, "SAR"), "Pro is ₹1,999 a month or ₹19,999 a year, paid in rupees (about SAR 78 or SAR 783 at today's rate)."); // the rupee price is the charge (DK-001, RC2A-010)
  assert.equal(planPriceLine("pro", { ...p, offer: { ...paid, yearly: false } }, "INR"), "Pro is ₹1,999 a month.");
  assert.equal(planPriceLine("pro", p, "XYZ"), null);
  // the price, and the lock's own button says "See plans" (DP2-022: never said twice)
  assert.equal(offer.unlockHint(paid, undefined, "Basic is ₹699 a month or ₹6,999 a year."), "Basic is ₹699 a month or ₹6,999 a year.");
  assert.equal(offer.unlockHint({ ...paid, payments: false, mode: "early" }, "a@b.c", "Basic is ₹699 a month."), "Paid plans open soon; ask us at a@b.c for early access.");
  assert.match(read("src/components/kit/Notice.tsx"), /const price = usePlanPrice\(plan \?\? named\);/);
  assert.match(read("src/components/PageLock.tsx"), /unlockHint\(me\.offer, CFG\.CONTACT_EMAIL \|\| EARLY_ACCESS_EMAIL, price\)/);
});

test("Refunds (owner, 25 Oct): one 7-day window for every payment, monthly or yearly", () => {
  assert.match(read("src/content/legal.ts"), /Ask within 7 days of any payment, monthly or yearly, and we refund it in full\./);
  assert.match(read("src/content/faq.ts"), /refunded in full if you ask within 7 days of it/);
});

test("MS1-004: a finding's age reads in whole days, and the panel shows it beside the monthly check", async () => {
  const { openDays, openFor } = await import("../src/lib/format.ts");
  const now = Date.parse("2026-10-25T12:00:00Z");
  assert.equal(openDays("2026-10-25T01:00:00Z", now), 0);
  assert.equal(openDays("2026-10-22T11:00:00Z", now), 3);
  assert.equal(openDays(null, now), null);
  assert.equal(openDays("not a time", now), null);
  assert.equal(openFor(0), "found today");
  assert.equal(openFor(1), "open 1 day");
  assert.equal(openFor(19), "open 19 days");
  const panel = read("src/pages/admin/AuditPanel.tsx");
  assert.match(panel, /Full re-check on the 1st of each month/);
  assert.match(panel, /send\(\{ monthly: on \}\)/);
  assert.match(panel, /i\.level !== "fact" && openDays\(i\.since \?\? r\.at\) != null/);        // a fact has no age: nothing is wrong
  assert.match(panel, /Problems standing:/);
});

test("MO-4a: the notebook is one centred column and the Lab notes float, with the notes card's behaviour kept", () => {
  const page = read("src/pages/NotebookPage.tsx");
  assert.doesNotMatch(page, /className="nb-grid"/);                                   // no second column beside the notebook
  assert.doesNotMatch(page, /<aside/);
  assert.match(page, /<LabNotes ref=\{notesRef\} value=\{nb\.notes \?\? ""\} onChange=\{\(v\) => patch\(\{ notes: v \}\)\} \/>/);   // the same autosave patch, same field
  assert.match(page, /action === "note"\) notesRef\.current\?\.focus\(\)/);           // a suggestion to write a note opens the panel
  const notes = read("src/components/LabNotes.tsx");
  assert.match(notes, /placeholder="What did you notice\? What do you want to try next\?"/);
  assert.match(notes, /maxLength=\{4000\}/);
  assert.match(notes, /info=\{HELP\.labNotes\}/);
  assert.match(notes, /aria-expanded=\{open\} aria-controls=\{PANEL\}/);
  assert.match(notes, /<Card label="Lab notes">/);                                    // a labelled region
  assert.match(notes, /e\.key === "Escape" && !e\.defaultPrevented/);
  assert.match(notes, /button\.current\?\.focus\(\)/);                                // focus back to the button on close
  assert.match(notes, /area\.current\?\.focus\(\)/);                                  // and into the notes on open
  assert.match(notes, /try \{ localStorage\.setItem\(KEY/);                           // remembered per device, never throws
  assert.match(notes, /try \{ return localStorage\.getItem\(KEY\) === "1"; \} catch/);
  assert.match(notes, /ln-dot/);                                                      // a dot when there are notes
});

test("MO-4a: the floating notes clear the safe areas, sit under dialogs and toasts, and are a bottom sheet on a phone", () => {
  const css = read("src/styles.css");
  const dock = css.match(/\.ln-dock \{[^}]*\}/)[0];
  assert.match(dock, /position: sticky/);                                              // VR1-050: a zero-height sticky box at the page's end, its tab drawn up from it

  const z = Number(dock.match(/z-index: (\d+)/)[1]);
  assert.ok(z < 40 && z > 30, "above the sticky top bar (30), below the menu drawer (40), dialogs (60) and toasts (70)");
  assert.match(css, /\.ln-panel \{ width: 380px;/);
  assert.match(css, /\.ln-panel\[hidden\] \{ display: none; \}/);
  assert.match(css, /\.ln-panel \.lab-note \{[^}]*max-height:/);                      // its own scroll, never taller than the screen
  const phone = css.slice(css.indexOf("@media (max-width: 640px) {\n  .ln-dock"));
  assert.match(phone, /\.ln-dock-in \{ right: -16px; left: -16px;/);
  assert.match(phone, /env\(safe-area-inset-bottom\)/);
  assert.match(phone, /env\(safe-area-inset-right\)/);
  assert.match(phone, /border-radius: 14px 14px 0 0/);
});

test("MO-4b: Positioning's cash and put-call cards stack, and a pair of cards in .k-two ends level", () => {
  const page = read("src/pages/PositioningPage.tsx");
  assert.doesNotMatch(page, /<div className="k-two">\s*<Cash/);
  assert.match(page, /<Cash s=\{s\} \/>\s*<PcrTable coverage=\{s\.coverage\} \/>/);
  const css = read("src/styles.css");
  assert.match(css, /\.k-two \{[^}]*align-items: stretch;/);
  assert.match(css, /\.mc-grid \{ align-items: stretch; \}/);                         // the Money calendar's columns end level too (RC2B-041)
  const sig = read("src/pages/trade/SignalsPage.tsx");
  assert.match(sig, /<div className="k-page">\s*<UrlCard ov=\{ov\} reload=\{load\} \/>\s*<HowTo \/>\s*<\/div>/);   // the short card shares its column
});

test("Owner 26 Oct: + Custom flows as the last chip where the row wraps; the cost choice's note sits under the row", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(min-width: 641px\) \{\s*\.k-chiprow \{ flex-wrap: wrap; align-items: flex-start; padding: 2px; \}\s*\.k-chiprow > \.k-chipbar \{ display: contents; \}/);
  const rules = read("src/components/Rules.tsx");
  assert.match(rules, /<Field label="Indian stock costs">/);
  assert.match(rules, /\{currency === "INR" && " Indian stock costs: Automatic uses intraday \(MIS\) costs/);
});

test("Owner 26 Oct: inside a notebook only the notebook is the selected menu entry; no dots caption", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /const here = at\?\.page\.to === p\.to && !\(p\.to === "\/notebooks" && path\.startsWith\("\/n\/"\)\);/);
  assert.doesNotMatch(shell, /Dots: each notebook's last verdict/);
});

test("DOC-2: the landing page names the newer tools, its lists keep full grid rows, and the UI checker guide lists every rule", () => {
  const login = read("src/pages/Login.tsx");
  const list = (name) => {
    const m = login.match(new RegExp(`const ${name}: \\[[^\\]]*\\]\\[\\] = \\[\\n([\\s\\S]*?)\\n\\];`));
    assert.ok(m, name);
    return (m[1].match(/^  \["/gm) ?? []).length;
  };
  assert.equal(list("RESEARCH") % 4, 0);                 // four research tools a row (landing.spec.ts)
  assert.equal(list("TOOLS") % 4, 0);
  assert.equal(list("ALERTS") % 3, 0);                   // three alerts a row
  assert.equal(list("PORTFOLIO") % 2, 0);                // Money's cards in pairs
  for (const t of ["IPOs", "Business updates", "Named holders", "Closing auction", "Market events", "Chart replay", "Forward test", "Test a SIP", "Rates after tax"])
    assert.match(login, new RegExp(`\\["${t}",`), t);
  assert.match(login, /Trade · Invest · Money · Ten markets/);
  assert.doesNotMatch(login, /Yahoo|Screener|Finnhub|Kite|Zerodha Kite/);        // no data vendor named on the page
  // docs/UI_CHECKER.md names every rule the checker has, R1 to R25
  const rules = read("e2e/ui-lint.spec.ts").match(/^  R\d+: /gm) ?? [];
  const doc = readFileSync(new URL("../../../docs/UI_CHECKER.md", import.meta.url), "utf8");
  assert.equal(rules.length, 25);
  for (let i = 1; i <= rules.length; i++) assert.match(doc, new RegExp(`\\| R${i} \\|`), `R${i}`);
});

// ---------- PUB-1: the public pages look like one product ----------
test("PUB-1: the policies use the public frame (header with the site's links, footer with the explore links), not a header of their own", () => {
  const page = read("src/pages/LegalPage.tsx"), css = read("src/styles.css");
  assert.match(page, /<PublicFrame className="legal">/);
  assert.doesNotMatch(page, /legal-head|<Logo|SkipLink/);                                           // the frame brings the logo, the skip link and the header
  assert.match(page, /<nav className="legal-tabs" aria-label="Policies">/);                        // the other policies stay one tap away
  assert.match(css, /\.pub-main\.legal \{ max-width: 800px; \}/);
  assert.match(css, /\.legal-body \.h3 \{[^}]*font: 600 21px\/1\.25 var\(--serif\)/);               // a heading for each part, not a bold line of body text
  assert.match(css, /@media \(max-width: 640px\) \{ \.legal-tabs a \{ min-height: 44px; \} \}/);   // a tap target on a phone
  assert.doesNotMatch(css, /\.legal-head/);
});

test("PUB-1: the server-drawn public pages carry the app's own fonts, header height and colour tokens", async () => {
  const { PUBLIC_FONTS } = await import("../scripts/publicFonts.mjs");
  const files = PUBLIC_FONTS.map(([f]) => f);
  for (const f of ["fraunces-latin-600-normal.woff2", "ibm-plex-sans-latin-500-normal.woff2"]) assert.ok(files.includes(f), `${f} is published for the API's pages`);
  const py = readFileSync(new URL("../../backend/app/stock_pages.py", import.meta.url), "utf8");
  const style = py.slice(py.indexOf('STYLE = """'), py.indexOf('"""', py.indexOf('STYLE = """') + 12));
  for (const f of files) assert.ok(style.includes(`/fonts/${f}`), `${f} is asked for by the pages`);        // the pages ask for every font the build publishes, and no other
  const css = read("src/styles.css");
  for (const token of ["--paper", "--card", "--ink", "--muted", "--line", "--blue", "--orange"]) {                // one palette: the pages' light values are the app's
    const app = css.match(new RegExp(`${token}: (#[0-9A-Fa-f]{6})`))?.[1], srv = style.match(new RegExp(`${token}:(#[0-9A-Fa-f]{6})`))?.[1];
    assert.equal(srv?.toLowerCase(), app?.toLowerCase(), token);
  }
  assert.match(style, /\.nav\{display:flex;align-items:center;padding:18px clamp\(16px,4vw,48px\);border-bottom:1px solid var\(--line\)\}/);   // the app's public header: full width, 18px
  assert.match(style, /\.brand svg\{height:40px/);                                                                // the logo at the app's size
  assert.match(css, /\.pub-nav \{[^}]*padding: 18px clamp\(16px, 4vw, 48px\)/);
});
