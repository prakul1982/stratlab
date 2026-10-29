// VR3 (27 Oct 2026): the visual review of every page VR2 did not cover (group pages, Settings, Plans, Red flags, Deep dive, the Money
// and Invest tools...): what the pages and the CSS now say.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");

test("VR3-001, VR3-009: two or three cards of a group page or a file list share the whole row (the right third is not left empty)", async () => {
  const hook = read("src/lib/noOrphan.ts");
  assert.match(hook, /export function useNoOrphan<T extends HTMLElement>\(fill = false\)/);
  assert.match(hook, /fill && kids\.length >= 2 && kids\.length < fit \? kids\.length : fillCols\(kids\.length, fit\)/);
  assert.match(read("src/components/TileGrid.tsx"), /useNoOrphan<HTMLDivElement>\(fill\)/);
  assert.match(read("src/pages/NavPages.tsx"), /<TileGrid className="nav-cards" fill>/);
  assert.match(read("src/pages/SettingsPage.tsx"), /<TileGrid className="k-linkcards" fill>/);
  // the old behaviour for every other grid is untouched
  const { fillCols } = await import("../src/lib/noOrphan.ts");
  assert.equal(fillCols(5, 4), 3);
  assert.equal(fillCols(2, 4), 4);
});

test("VR3-002: 'Yours' and 'record date the same day' are not printed on every row of a list that is all the person's own", () => {
  const ca = read("src/components/CorpActions.tsx");
  assert.doesNotMatch(ca, /record date the same day/);
  assert.match(ca, /showMine = true/);
  assert.match(ca, /\{showMine && a\.mine && <Badge tone="plain" dot=\{false\}>Yours<\/Badge>\}/);
  const page = read("src/pages/CorpActionsPage.tsx");
  assert.match(page, /showMine=\{scope === "all"\}/);
  assert.match(page, /the record date \(on each row when it's another day\)/);
});

test("VR3-003: a company with nothing flagged is not told twice on its red-flags card", () => {
  const scans = read("src/pages/ResearchScans.tsx");
  assert.match(scans, /r\.summary\.red \+ r\.summary\.amber > 0 && <span className="k-small k-muted">Nothing flagged in the last/);
});

test("VR3-004: the Trend scan footnote adds only what its rule line leaves out", () => {
  const scans = read("src/pages/ResearchScans.tsx");
  assert.doesNotMatch(scans, /Stage uses the 150-day average and its 20-day slope; Supertrend uses 10 days/);
  assert.match(scans, /A rising average is one whose 20-day slope is up\./);
});

test("VR3-005: a long label wraps beside its value in a list of rows, the value stays on the right", () => {
  assert.match(css, /\.k-rows > div > span \{ color: var\(--muted\); flex: 1 1 8rem; min-width: 0; \}/);
  assert.match(css, /\.k-rows > div > b \{ font-weight: 600; text-align: right; \}/);
});

test("VR3-006: the watchlist's Remove sits at the top right of a phone card, not alone on a last row", () => {
  assert.match(read("src/pages/Research.tsx"), /\{ key: "r", header: "", action: true, corner: true, cell: \(w\) => <button className="btn quiet sm icon-only" aria-label=\{`Remove \$\{w\.symbol\} from your watchlist`\}/);
});

test("VR3-007: the saved-screen email box is level with the name box, its group named for assistive tools only", () => {
  const form = read("src/components/kit/Form.tsx");
  assert.match(form, /quietLabel\?: boolean/);
  assert.match(form, /k-label-quiet/);
  assert.match(read("src/pages/Screens.tsx"), /<FieldGroup label="Email" quietLabel>/);
  assert.match(css, /@media \(max-width: 640px\) \{ \.k-label-quiet \{ display: none; \} \}/);
});

test("VR3-008: 'Save this password for next time' has a line of its own under the password box", () => {
  assert.match(read("src/components/ConnectedAccounts.tsx"), /<div className="k-field wide"><CheckField label="Save this password for next time"/);
});

test("VR3-010: Deep dive's look-back box is as wide as its words and its button stays beside it", () => {
  const dd = read("src/pages/DeepDive.tsx");
  assert.equal((dd.match(/<div className="k-row dd-ask">/g) ?? []).length, 2);
  assert.match(css, /\.dd-ask > select\.k-input \{ width: auto; flex: none; min-width: 150px; \}/);
});

test("VR3-011: a checklist value with a sentence in it goes under its rule across the row", () => {
  assert.match(read("src/pages/DeepDive.tsx"), /className=\{`small num\$\{x\.value\.length > 32 \? " long" : ""\}`\}/);
  assert.match(css, /\.check-row > \.num\.long \{ grid-column: 1 \/ 3; grid-row: 2; text-align: left; \}/);
});

test("VR3-012: the Plans page says 'Basic and Pro aren't on sale yet' once (its heading line); the box only offers to tell", () => {
  const plans = read("src/pages/PlansPage.tsx");
  assert.doesNotMatch(plans, /Basic and Pro aren't on sale yet\. Press the button/);
  assert.match(plans, /Press the button and we'll tell you the day they open\./);
});

test("VR3-013: the landing page's six extra Money tools are two rows of three (VR3-014's space pictures went with LAND-2's intro)", () => {
  assert.match(read("src/pages/Login.tsx"), /lp-money-3/);
  assert.match(css, /\.lp-money\.lp-money-3 \{ grid-template-columns: repeat\(3, minmax\(0, 1fr\)\); \}/);
  assert.doesNotMatch(css, /lp-space-art|lp-space-big/);
});

test("VR3-015: the closing-auction status does not say 'Continuous trading' beside a badge that says it", async () => {
  const { PHASE_TEXT } = await import("../src/lib/closingAuction.ts");
  assert.doesNotMatch(PHASE_TEXT.before, /^Continuous trading/);
  assert.match(PHASE_TEXT.before, /the auction starts at 15:15/);
});

test("VR3-016: the plan tables do not repeat their heading as the first column's header", () => {
  assert.match(read("src/components/PlanCompare.tsx"), /header: <span className="sr-only">\{first\}<\/span>, wrap: true/);
});

test("VR3-017, VR3-019: the two run pickers have the width of their names; the US holder company box's hint fits it", () => {
  // LIVE1A-009: the two selects fill one card's width (a pair of columns), with what changed under them
  assert.match(read("src/pages/CompareExperiments.tsx"), /<FormGrid label="Pick two runs" pair>/);
  assert.match(css, /\.k-form\.k-form-pair \{ grid-template-columns: repeat\(auto-fit, minmax\(min\(260px, 100%\), 1fr\)\); \}/);
  assert.match(read("src/pages/HoldersPage.tsx"), /placeholder="Like AAPL or Apple"/);
});

test("VR3-018: the rotation chart's legend is shown only when there is no four-box key under the title", () => {
  assert.match(read("src/pages/ResearchScans.tsx"), /actions=\{rows\.length > 0 \? undefined : <div className="rot-legend" role="group" aria-label="Legend">/);
});
