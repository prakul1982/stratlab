// CK-2 (26 Oct 2026): the UI checker learns what the visual review (VR-1) found by eye: new rules R13 to R25 (the review's "Checker gaps" G1 to G14)
// and a lower bar for R1, each with a self-check fixture in e2e/ui-lint.spec.ts; and the fixes the new rules found in the app.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const rules = read("e2e/ui-lint-rules.ts");
const spec = read("e2e/ui-lint.spec.ts");

test("CK-2: R1 now fires on a 60px / 25% hole (the Invest 'Results today' case, 86px / 41%)", () => {
  assert.match(rules, /if \(dead > 60 && dead \/ rowH > 0\.25\) add\("R1"/);
  assert.match(spec, /R1: "Dead space beside a short card: [^"]*> 60px and > 25%/);
  assert.match(spec, /"R1 86px \/ 41% hole"\)\.toContain\("R1"\)/);
});

test("CK-2: every new rule is listed, measured, coloured and checked on a bad case and a good one", () => {
  for (let n = 13; n <= 25; n++) {
    const r = `R${n}`;
    assert.match(rules, new RegExp(`//   ${r} `), `${r} is in the rule list at the top of ui-lint-rules.ts`);
    if (n !== 17) assert.ok(rules.includes(`"${r}"`), `${r} is added by the rules`);          // (R17 is decided across pages: frameOutliers)
    assert.ok(rules.includes(`${r}: "#`), `${r} has an outline colour`);
    assert.match(spec, new RegExp(`  ${r}: "`), `${r} is described in RULES`);
    if (n === 17) { assert.ok(spec.includes('"R17 the narrow page and the high title are the odd ones"') && spec.includes('"R17 pages that agree"')); continue; }
    assert.match(spec, new RegExp(`"${r} [^"]*"\\)\\.toContain\\("${r}"\\)`), `${r} fires on a bad fixture`);
    assert.match(spec, new RegExp(`"${r} [^"]*"\\)\\.not\\.toContain\\("${r}"\\)`), `${r} stays quiet on a good fixture`);
  }
});

test("CK-2: thresholds written in the rules", () => {
  assert.match(rules, /r\.height < 140 \|\| r\.width < 200/);                                   // R13: boxes 140px+ tall
  assert.match(rules, /const atBottom = empty > 70 && empty \/ r\.height > 0\.25/);                // R13: > 70px and > 25%
  assert.match(rules, /ow > 6 && oh > 6/);                                                       // R14: more than 6px each way
  assert.match(rules, /gap < 3 && gap > -80/);                                                   // R15: under 3px
  assert.match(rules, /x\.h > 1\.6 \* mh/);                                                      // R16: a wrapped value
  assert.match(rules, /Math\.abs\(r\.frame\.h1Top - m\.h1Top\) > 2/);                           // R17: the modal frame
  assert.match(rules, /e\.children\.length > 12/);                                               // R18: a long strip scrolls on purpose
  assert.match(rules, /gap > 250/);                                                              // R20: 250px from the text's end
  assert.match(rules, /gap > 56/);                                                               // R21: 56px under the header
  assert.match(rules, /Math\.max\(\.\.\.v\) - Math\.min\(\.\.\.v\) > 4/);                       // R22: 4px
  assert.match(rules, /R\(h\)\.height - min > 12/);                                              // R23: 12px
  assert.match(rules, /Math\.max\(\.\.\.seen\) < 3/);                                            // R24: 3:1
});

test("CK-2 (R17): the page frame is compared across pages, by the pure function the spec calls", async () => {
  const { frameOutliers } = await import("../e2e/ui-lint-rules.ts");
  const ok = { h1Top: 112, h1Left: 304, right: 1384 };
  const pages = [ok, ok, ok, ok, { ...ok, right: 1224 }, { ...ok, h1Top: 86 }, { ...ok, h1Left: 400 }].map((frame) => ({ group: "app", frame }));
  assert.deepEqual(frameOutliers(pages, 3).map((o) => o.index), [4, 5, 6]);
  assert.match(frameOutliers(pages, 3)[0].detail, /1224px/);
  // a group is judged on its own, and needs enough pages to know what most of them do
  assert.deepEqual(frameOutliers(pages.map((p, i) => ({ ...p, group: i === 4 ? "admin" : "app" })), 3).map((o) => o.index), [5, 6]);
  assert.deepEqual(frameOutliers(pages), []);
  assert.match(spec, /for \(const o of frameOutliers\(frames\)\)/);
  assert.match(spec, /\$\{t\.r\.path\.startsWith\("\/admin"\) \? "admin" : "app"\}/);
});

test("CK-2 (R1, R13, R2): no card is stretched beside a taller one with its notes pinned to the bottom; the hole is not moved, it is closed", () => {
  const css = read("src/styles.css");
  // the checker measures the biggest empty band inside a box (a pinned note leaves it in the middle), and a short list of tiles that leaves its row half empty
  assert.match(rules, /let reach = -Infinity, band = 0, from = 0;/);
  assert.match(rules, /const inMiddle = band > 70 && band \/ r\.height > 0\.25;/);
  assert.match(rules, /\(inner - used\) \/ inner > 0\.4\) add\("R2", p,/);
  assert.match(spec, /"R13 notes pinned to the bottom edge"\)\.toContain\("R13"\)/);
  assert.match(spec, /"R2 two tiles in half the row"\)\.toContain\("R2"\)/);
  // no stretch + bottom pin left behind
  assert.doesNotMatch(css, /explore-go \{ margin-top: auto/);
  assert.doesNotMatch(css, /\.money-panels > \.k-card > \.k-stack/);
  assert.doesNotMatch(read("src/pages/trade/events.css"), /ev-week-more \{ margin-top: auto/);
  // Invest's short tile list shares its row
  assert.match(css, /\.k-explore \.explore-grid \{ grid-template-columns: repeat\(auto-fit, minmax\(230px, 1fr\)\); \}/);   // VR2-001: the tiles of a row are as tall as each other (no align-items:start)
  assert.doesNotMatch(css, /\.k-explore \.explore-grid \{[^}]*align-items: start/);
  // Money home: the tax card's explanation is behind its (i); each card its own height
  const home = read("src/pages/SpaceHomes.tsx");
  assert.match(home, /<Panel title=\{year \? `Tax, \$\{year\.label\}` : "Tax this year"\} info=\{how\}/);
  assert.match(home, /<p className="tiny muted">\{year\?\.count \?/);
  assert.match(home, /An estimate to check with your CA\.<\/p>/);
  assert.match(home, /className="grid2 space-panels money-panels"/);
  // /trade/events: the week card full width (events side by side, the count lines beside them), the reminders card in two columns under it
  const ev = read("src/pages/trade/EventsPage.tsx");
  assert.match(ev, /<div className="ev-weekgrid">/);
  assert.match(ev, /<div className="ev-remind">/);
  assert.ok(ev.indexOf('className="ev-weekgrid"') < ev.indexOf("<RemindCard v={v} onSave={save} />"));
  const evc = read("src/pages/trade/events.css");
  assert.match(evc, /\.ev-weekgrid > \.ev-week \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(260px, 1fr\)\);/);
  assert.match(evc, /\.ev-remind \{ display: grid; grid-template-columns: minmax\(0, 1\.4fr\) minmax\(0, 1fr\);/);
  // the plans: each card its own height, its button under its list
  assert.match(css, /\.k-plans \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(260px, 1fr\)\); gap: var\(--s4\); align-items: stretch; \}/);
  const allow = JSON.parse(read("e2e/ui-lint.allow.json")).allow;
  assert.deepEqual(allow.map((x) => `${x.page} ${x.rule} ${x.element}`), ["/plans R1 k-plan"]);
  // the company page: the peers' tiles in equal rows, the news under them
  assert.match(read("src/pages/Research.tsx"), /<div className="k-stack">\s*\{c\.peers\.length > 0 && <Card><CardHead title="Similar companies"/);
  assert.match(read("src/pages/Research.tsx"), /className=\{`co-peers co-peers-\$\{c\.peers\.length === 4 \? 2 : Math\.min\(3, c\.peers\.length\)\}`\}/);
  assert.match(read("src/styles-invest.css"), /\.co-peers-3 \.inv-tiles \{ grid-template-columns: repeat\(3, minmax\(0, 1fr\)\); \}/);
});

test("CK-2 (R16), LIVE1B-009: the tax at the special rates is no headline figure beside the year's total; its qualifier is said under the table", () => {
  const t = read("src/pages/TaxReportPage.tsx");
  assert.doesNotMatch(t, /<Stat label=\{<>Tax on share gains/);
  assert.match(t, /Tax at these rates: \{inr\(y\.tax\)\} \(\{inr\(y\.tax_with_cess\)\} with 4% cess\), before the unused basic exemption, the 87A rebate and surcharge/);
});

test("CK-2 (R18): a table that would be cut on a phone is cards, a short chip row wraps", () => {
  const d = read("src/components/kit/DataTable.tsx");
  assert.match(d, /const stack = stackProp \?\? \(!grid && !scrollEnd && \(columns\.length >= 5 \|\| spill\)\);/);
  assert.match(d, /b\.scrollWidth > b\.clientWidth \+ 2\) setSpill\(true\)/);
  assert.match(d, /data-grid=\{grid \|\| scrollEnd \? "" : undefined\}/);
  assert.match(read("src/pages/OptionsPage.tsx"), /<DataTable grid label=\{greeks \? "Option chain, IV and Greeks"/);
  assert.match(read("src/pages/PositioningPage.tsx"), /<DataTable grid label=\{`\$\{name\} open interest, change and volume by strike/);
  assert.match(read("src/components/kit/ChipBar.tsx"), /const wrapRow = wrap \|\| all\.length <= 12;/);
});

test("CK-2 (R19, R20): tags that fit on a line, actions that follow their text", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(max-width: 520px\) \{ \.lp-money \{ grid-template-columns: minmax\(0, 1fr\); \} \}/);
  assert.match(css, /@media \(max-width: 520px\) \{ \.lp-illus \{ border-radius: 14px; \} \}/);
  assert.match(css, /\.nw-snaps li \{ justify-content: flex-start;/);
  assert.match(read("src/styles-invest.css"), /\.ai-read-off \{ justify-content: flex-start; \}/);
  // the admin's rows: the link to get a key ends the line about the variable; "Open Money" ends the sentence it belongs to
  assert.match(read("src/pages/admin/AIPanel.tsx"), /<span className="k-row">\s*<span className="k-small k-muted">Set <span className="adm-mono">[^]*<a className="btn quiet sm" href=\{safeHref\(p\.key_url\)\}/);
  assert.match(read("src/pages/admin/OverviewSection.tsx"), /<span title=\{x\.full\}>\{x\.text\}<\/span><Link className="link" to=\{x\.to\}>Open \{x\.label\} →<\/Link>/);
});
