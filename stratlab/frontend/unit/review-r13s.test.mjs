// Round 13 Safari review (R13S): the app's side of the fixes. Every date here is a fixed instant; no weekday or time of
// day matters. Run: npm run test:unit
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

test("R13S-002: a feed that fails is said so, naming the companies, and never as 'no stocks'", async () => {
  const { unreadLine, unreadSymbols } = await import("../src/lib/filingsText.ts");
  const problems = ["TCS: The exchange feed isn't answering right now. Try again in a minute.", "INFY: The exchange is slow to answer for this one.", "TCS: again"];
  assert.deepEqual(unreadSymbols(problems), ["TCS", "INFY"]);
  assert.deepEqual(unreadSymbols(undefined), []);
  assert.equal(unreadLine(["TCS"]), "Couldn't read TCS's filings right now.");
  assert.equal(unreadLine(["TCS", "INFY"]), "Couldn't read the filings of TCS and INFY right now.");
  assert.equal(unreadLine(["A", "B", "C"]), "Couldn't read the filings of A, B and C right now.");
  assert.equal(unreadLine(["A", "B", "C", "D", "E"]), "Couldn't read the filings of A, B, C and 2 more right now.");
  assert.equal(unreadLine([]), "Couldn't read your companies' filings right now.");
  const home = read("src/pages/SpaceHomes.tsx");
  // the card tells a failed read from an empty list, and shows the plan note only once the plan is known
  assert.match(home, /const known = !!me;/);
  assert.match(home, /!known \? <PanelSkel label="Checking your plan" \/>/);
  assert.match(home, /failed \? <p className="small muted" data-testid="invest-redflags-failed">/);
  assert.match(home, /!data\.rows\.length && unread\.length \?/);
});

test("R13S-003: a plan note waits for the plan to be known", () => {
  for (const f of ["src/pages/InvestorHome.tsx", "src/pages/ResearchScans.tsx"]) {
    const src = read(f);
    assert.doesNotMatch(src, /\{!pro && <PlanNote>/, f);
    assert.match(src, /\{!pro && me && <PlanNote>/, f);
  }
  assert.match(read("src/pages/InvestorHome.tsx"), /\{\(pro \|\| !me\) && !rows && !error && <Card><Skeleton/);
});

test("R13S-004: Block and Re-rank ask first, say who blocked and when, and offer an Undo; nothing unblocks everything", async () => {
  const { blockedLine } = await import("../src/pages/admin/aiBlocks.ts");
  const at = Date.UTC(2026, 9, 9, 8, 35) / 1000;                                     // 9 Oct 2026, 14:05 IST
  assert.equal(blockedLine("owner@example.com", at), "Blocked by owner@example.com at 9 Oct 2026, 14:05 IST");
  assert.equal(blockedLine("owner@example.com", null), "Blocked by owner@example.com");
  assert.equal(blockedLine(null, at), "Blocked at 9 Oct 2026, 14:05 IST");
  assert.equal(blockedLine(null, null), "Blocked (who and when weren't recorded)");
  const panel = read("src/pages/admin/AIPanel.tsx");
  assert.match(panel, /setAsk\(\{ kind: "rerank"/);
  assert.match(panel, /setAsk\(\{ kind: "block", p: pp, model, blocked \}\)/);          // Block and Unblock both ask first
  assert.match(panel, /setAsk\(\{ kind: "pin", p: pp, model \}\)/);                   // so does Pin
  assert.match(panel, /label: "Undo", run: \(\) => void restoreRank\(r\.undo!\)/);
  assert.match(panel, /label: "Undo", run: \(\) => void setBlocked\(p, model, !blocked\)/);
  assert.doesNotMatch(panel, /unblock-all|Unblock all/i);
  const sig = read("src/pages/trade/SignalsPage.tsx");
  assert.match(sig, /setAsk\(ov\.hook \|\| fresh \? "new" : "first"\)/);
  assert.match(sig, /ask === "first" && <ConfirmDialog title="Make your URL\?"/);
});

test("R13S-005: on a phone or a touch screen every field is 16px or more, so Safari doesn't zoom", () => {
  const css = read("src/styles.css");
  const block = css.slice(css.indexOf("R13S-005"));
  assert.match(block, /@media \(max-width: 640px\), \(pointer: coarse\) \{[^}]*font-size: 16px/);
  assert.match(block, /\.field input, \.field select, \.field textarea, \.input, \.k-input \{ font-size: 16px; \}/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-pop input, \.pc-text, \.pc-risk input \{ min-height: 44px; font-size: 16px; \}/);
});

test("R13S-006 and R13S-008: the billing switch's label and a Trade tile's status wrap instead of spilling out or being cut", () => {
  const css = read("src/styles.css");
  // (UI-FIX-1: the billing switch's label now keeps to one line; its field takes two columns, and a phone's column is wide enough)
  assert.match(css, /\.k-form > \.k-field > \.k-seg button \{[^}]*white-space: nowrap/);
  const foot = css.split("\n").find((l) => l.startsWith(".space-card-foot {"));
  assert.ok(foot && !/white-space: nowrap/.test(foot) && !/overflow: hidden/.test(foot), foot);
});

test("R13S-007: a More menu that would run past the screen's edge opens to the other side", () => {
  const src = read("src/components/MoreMenu.tsx");
  assert.match(src, /document\.documentElement\.clientWidth - 8/);
  assert.match(src, /\(align === "right"\) !== flip \? " right" : ""/);
});

test("R13S-009 and R13S-010: dates in words are written the site's way, never as an ISO text", () => {
  assert.match(read("src/pages/Screens.tsx"), /List gathered as of \{asOf\(out\.index_at\) \?\? out\.index_at\}/);
  assert.match(read("src/pages/admin/AuditPanel.tsx"), /\(\$\{dayMonth\(n\.listed\)\}\)/);
  assert.match(read("src/pages/admin/RulesPanel.tsx"), /\$\{fmtDate\(c\.date\)\}: \$\{c\.subject\}/);
});

test("R13S-011: on a touch screen the measured controls are 44px", () => {
  const css = read("src/styles.css");
  const touch = css.slice(css.indexOf("R13S-011"));
  for (const re of [/\.k-seg button \{ min-height: 44px; \}/, /\.k-chip \{ height: 44px; \}/, /\.k-th-sort \{ min-height: 44px;/,
    /\.k-table td a, [^{]*\{ min-height: 44px; min-width: 44px;/, /\.k-tap \{ min-width: 44px; min-height: 44px;/]) assert.match(touch, re);
  const chart = read("src/charts/price/priceChart.css");
  assert.match(chart, /\.pc-btn, \.pc-sel, \.pc-seg \.pc-btn, \.pc-rail \.pc-btn\.icon \{ min-height: 44px; \}/);
  assert.match(read("src/pages/admin/admin.css"), /@media \(pointer: coarse\) \{ \.adm-link \{ min-height: var\(--ctl\); \} \}/);
  const rot = read("src/components/Rotation.tsx");
  assert.match(rot, /r=\{hitR\(phone\)\}/);          // 44px for a finger, and on a phone-width chart (R95-002)
  assert.match(rot, /matchMedia\("\(pointer: coarse\)"\)/);
});

test("R13S-013: the axe items listed in the review", () => {
  assert.match(read("src/charts/price/PriceChart.tsx"), /<div className="pc-legend" role="group" aria-label="Legend">/);
  assert.match(read("src/pages/ResearchScans.tsx"), /<div className="rot-legend" role="group" aria-label="Legend">/);
  const draw = read("src/charts/price/DrawToolbar.tsx");
  assert.doesNotMatch(draw, /Show all drawings" : "Hide all drawings"\} [^>]*pressed=/);          // a label that flips is not also a toggle
  assert.match(read("src/pages/trade/FoChangesPage.tsx"), /<CardHead title="Alert" \/>/);
  assert.match(read("src/pages/trade/ReplayPage.tsx"), /<CardHead title="Unfinished" \/>/);
  assert.match(read("src/pages/trade/SignalsPage.tsx"), /<CardHead level=\{2\} title="Your webhook URL"/);
  assert.match(read("src/pages/admin/AuditPanel.tsx"), /"Whole-market findings by area" : "Data audit findings by area"/);
  assert.match(read("src/pages/MarketPage.tsx"), /className="chip-row" role="group" [^>]*tabIndex=\{0\}/);
  assert.match(read("src/pages/ExperimentPage.tsx"), /<PageHeader eyebrow="Trade · Build and test" title="Experiment" \/><EmptyState title="That experiment wasn't found\."/);
  const sw = read("public/sw.js");
  assert.doesNotMatch(sw, /http-equiv/);
});

test("R13S-014: no key hints on a touch screen, and the selected drawing's bar sits at the foot on a tablet", () => {
  const css = read("src/charts/price/priceChart.css");
  assert.match(css, /@media \(hover: none\) and \(pointer: coarse\) \{ \.pc-pop button\.item\.row kbd \{ display: none; \} \}/);
  assert.match(css, /@media \(max-width: 1100px\), \(pointer: coarse\) \{\s*\.pc-selbar \{ top: auto; bottom: 30px;/);
});

test("R13S-015: the US 'sector' column is called what it is", () => {
  const src = read("src/pages/Screens.tsx");
  assert.match(src, /const sectorName = region === "US" \? "Industry \(SEC division\)" : "Sector";/);
  assert.match(src, /<Group title=\{sectorName\} help=\{help\.sector\}>/);
});

test("R13S-016: an impossible date says so; the other small fixes", async () => {
  const { parseDay, whyNotDay } = await import("../src/lib/dateInput.ts");
  assert.equal(parseDay("31/02/2026"), null);
  assert.equal(whyNotDay("31/02/2026"), "There is no 31 February 2026.");
  assert.equal(whyNotDay("30 Feb 2026"), "There is no 30 February 2026.");
  assert.equal(whyNotDay("29/02/2025"), "There is no 29 February 2025.");
  assert.equal(parseDay("29/02/2024"), "2024-02-29");
  assert.equal(whyNotDay("tomorrow"), "Write the date day first, like 14 Aug 2025 or 14/08/2025.");
  assert.equal(whyNotDay("12/13/2026"), "Write the date day first, like 14 Aug 2025 or 14/08/2025.");
  assert.match(read("src/components/ConnectedAccounts.tsx"), /placeholder=\{i\.has_password \? "Saved\. Type to replace it" : ""\}/);
  assert.match(read("src/components/ImportStrategy.tsx"), /<span className="k-drop-hint">Drop a strategy file here, or<\/span>/);
  assert.match(read("src/pages/trade/trade.css"), /@media \(hover: none\) and \(pointer: coarse\) \{ \.k-drop-hint \{ display: none; \} \}/);
  const breadth = read("src/pages/BreadthPage.tsx");
  assert.match(breadth, /const fmtInt = \(v: number\) => minus\(Math\.round\(v\)\.toLocaleString\("en-IN"\)\);/);
  assert.match(breadth, /const fmt1 = \(v: number\) => minus\(/);
});

test("R26-002: the library's search box and the notes box are 16px on a phone too, whatever order the sheets load in", () => {
  const css = read("src/styles.css");
  const block = css.slice(css.indexOf("R13S-005"));
  assert.match(block, /@media \(max-width: 640px\), \(pointer: coarse\) \{[^@]*body \.k-search input, body \.k-textarea \{ font-size: 16px; \}/);
  assert.match(read("src/pages/trade/trade.css"), /\.k-search input \{[^}]*font-size: var\(--t-body\)/);   // the 15px it overrides, with less weight than `body .k-search input`
});

test("R39: on a phone the plan switch's buttons and the footer's policy links are 44px tall, by padding and height", () => {
  const css = read("src/styles.css");
  const phone = css.slice(css.indexOf("R39:"), css.indexOf("/* VR5-005"));     // (VR6 added rules after it: this block only)
  assert.match(phone, /@media \(max-width: 640px\) \{[^@]*\.lp-period \.k-seg button \{ min-height: 44px; \}/);
  assert.match(phone, /\.lp-foot \.legal-links a \{[^}]*min-height: 44px; padding-block: 12px/);
  assert.doesNotMatch(phone, /font-size/);
  // the landing page's tabs, nav and footer landmarks stay as they are
  const lp = read("src/pages/Login.tsx");
  for (const re of [/role="tablist"/, /role="tab"/, /role="tabpanel"/, /aria-selected=\{k === i\}/, /<nav aria-label="Sections">/, /<footer className="lp-foot">/]) assert.match(lp, re);
});

test("round 39: on a phone, chips and small buttons are 44 px to tap; the desktop keeps its density", () => {
  const css = read("src/styles.css");
  const at = css.indexOf("round 39: tap heights on a phone");
  assert.ok(at > 0);
  const block = css.slice(at);
  assert.match(block, /@media \(max-width: 640px\) \{/);
  assert.match(block, /\.k-chip \{ height: 44px; \}/);
  assert.match(block, /\.btn\.sm, \.k-card-head \.btn\.sm[^{]*\{ min-height: 44px; \}/);
  assert.match(block, /\.side-toggle \{ width: 44px; height: 44px; \}/);
  assert.match(block, /\.space-switch button[^{]*\{ height: auto; min-height: 44px; \}/);
  // the desktop sizes are untouched
  assert.match(css, /\.k-chip \{ flex: none; height: 32px;/);
  assert.match(css, /\.side-toggle \{ flex: none; display: grid; place-items: center; width: 26px; height: 26px;/);
});
