import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { frameOutliers, lintPage, type FrameRow, type LintResult, type PageFrame, type Violation } from "./ui-lint-rules";
import { seedWorld, session, WEB, type Route } from "./ui-lint-world";

// UI-LINT: finds the owner's kind of layout problems (dead space beside a short card, a floating "+ Custom", a squeezed hint, two
// highlighted menu items, a figure said three times on a card, uneven rows, and (CK-2) what a visual review found by eye: a hole inside any
// box, a fixed pill over content, an (i) glued to its label, a stat row mixing words and numbers, a page whose frame differs, a clipped
// sideways row on a phone, a wrapped badge, a far-away end control...) on every page, automatically.
//
// It fills the pages with a Pro user's data (ui-lint-world.ts), visits every route at 1440x900, 1280x800 and 390x844 in the dark
// theme, measures the drawn page against the rules in ui-lint-rules.ts, and writes report.md, report.json and a screenshot per
// page and width with the offenders outlined. It is REPORT-ONLY (always passes) unless UI_LINT_STRICT=1, in which case any
// violation not in ui-lint.allow.json fails the run. It is its own project (playwright.config.ts) so the default runs skip it:
//   npm run build && npm run ui-lint
// Env: UI_LINT_OUT (output folder), UI_LINT_STRICT=1, UI_LINT_LIGHT=1 (also 1440 in the light theme), UI_LINT_ROUTES=<regex>,
//      UI_LINT_WIDTHS=1440,390, UI_LINT_LANES=6 (pages measured at once), UI_LINT_SHOTS=0 (no screenshots),
//      UI_LINT_PANEL=1 (Market Watch open, docked, on the desktop widths).
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(process.env.UI_LINT_OUT ?? resolve(HERE, "../test-results/ui-lint"));
const STRICT = process.env.UI_LINT_STRICT === "1";
const LANES = Number(process.env.UI_LINT_LANES ?? 6);

// 360 (a small Android) and 430 (a big iPhone) are measured only when asked for (UI_LINT_WIDTHS=360,430): the default run keeps its three.
const SIZES = [
  { width: 1440, height: 900, touch: false },
  { width: 1280, height: 800, touch: false },
  { width: 390, height: 844, touch: true },
  { width: 360, height: 780, touch: true },
  { width: 430, height: 932, touch: true },
].filter((s) => process.env.UI_LINT_WIDTHS ? process.env.UI_LINT_WIDTHS.split(",").includes(String(s.width)) : s.width >= 390 && s.width !== 430);
const PASSES: { size: (typeof SIZES)[number]; theme: "dark" | "light" }[] = [
  ...SIZES.map((size) => ({ size, theme: "dark" as const })),
  ...(process.env.UI_LINT_LIGHT === "1" ? [{ size: SIZES[0] ?? { width: 1440, height: 900, touch: false }, theme: "light" as const }] : []),
];

export const RULES: Record<string, string> = {
  R1: "Dead space beside a short card: cards/columns in one row, one with > 60px and > 25% of the row height empty under its content",
  R2: "Sparse wide card: a card wider than 900px (and 140px+ tall) whose content covers < 55% of its inner width; a row of 2+ tiles that fills < 60% of the row",
  R3: "Floating control: a button/chip not level with the first row of a chip group wrapped over 2+ rows beside it, or an end control > 48px from its row",
  R4: "Text wrapping inside a button, chip, segmented option or tab (2+ lines)",
  R5: "Uneven row: a control > 25% (and 16px) off the row's median height; fields/stats whose control/value sits > 3px off its neighbours'; a stretched segmented option",
  R6: "Squeezed hint: a field hint < 40% of its row wide and 3+ lines, in a row of 2+ fields",
  R7: "Double highlight: 2+ highlighted active items in one menu, or 2+ selected options in one segmented group",
  R8: "Repeated figure: the same money/percent string 3+ times in one card (tables and charts left out)",
  R9: "Orphan row: a grid of 4+ equal cards/stats whose last line holds one item alone",
  R10: "Overflow and clipping: the page scrolls sideways, text cut off by a clipping box, two text lines overlapping",
  R11: "Tiny tap target on a phone (< 32px tall)",
  R12: "Caption clutter: a small 'Dots: ...' / 'Colours: ...' caption under a list or menu",
  R13: "Empty inside a box: any bordered/filled box 140px+ tall (a card inside a card too) with an empty band > 70px and > 25% of its height, at the bottom or between two blocks of content",
  R14: "Overlay on content: a fixed/sticky box (not the menu, a dialog or a toast) covering text or a control in the page, scrolled to the top, middle or bottom",
  R15: "Icon glued to its label: an (i) or icon button < 3px from the text beside it, or overlapping it",
  R16: "Uneven stat row: a word among numbers, a value wrapped over 2+ lines, or labels of different heights, in one row of figures",
  R17: "Page frame: a page whose title top/left or rightmost card edge differs (> 2px) from the one most pages share at that width",
  R18: "Clipped scroller on a phone: a sideways row with an item cut by the edge, or a table showing fewer than all its columns",
  R19: "Wrapped badge: a pill/badge/tag/chip whose text runs on 2+ lines",
  R20: "Orphan end control: a lone control at the end of a row of text, > 250px from where the text ends",
  R21: "Gap under the page header: > 56px of nothing between the page header and the first card",
  R22: "Row tags out of column: rows of [tag][name] whose name starts at x's that differ by > 4px",
  R23: "Header wrap parity: cards side by side whose headers differ by > 12px because one header's controls wrapped",
  R24: "Faint checkbox: an unchecked checkbox/radio whose border and fill are both < 3:1 against what is behind it",
  R25: "Same sentence twice: one sentence (30+ characters) said twice in one card (table rows left out)",
};

interface Row extends Violation { page: string; label: string; width: number; theme: string; shot?: string; allowed?: string }
interface Allow { page: string; rule: string; element: string; reason: string }

const slug = (s: string) => s.replace(/^https?:\/\/[^/]+/, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "") || "home";

function allowlist(): Allow[] {
  const f = resolve(HERE, "ui-lint.allow.json");
  if (!existsSync(f)) return [];
  try { return (JSON.parse(readFileSync(f, "utf8")).allow ?? []) as Allow[]; } catch { return []; }
}
/** An allowlist entry names the page ("*" for every page), the rule, and a piece of the element's label; a reason is required. */
const allowedBy = (a: Allow[], r: Pick<Row, "page" | "rule" | "element">) =>
  a.find((x) => x.reason && x.rule === r.rule && (x.page === "*" || x.page === r.page) && r.element.includes(x.element))?.reason;

async function newContext(browser: Browser, size: (typeof SIZES)[number], theme: "dark" | "light", signedIn: boolean, spaces: Record<string, string>): Promise<BrowserContext> {
  const ctx = await browser.newContext({ viewport: { width: size.width, height: size.height }, hasTouch: size.touch, isMobile: size.touch, colorScheme: theme });
  await ctx.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  // UI_LINT_PANEL=1 (MW-1): every page measured with Market Watch open, docked to the right edge (a phone's is a sheet: it is not opened)
  const panel = process.env.UI_LINT_PANEL === "1" && size.width > 900;
  await ctx.addInitScript(([s, signedIn, theme, spaces, panel]) => {
    if (signedIn) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    if (signedIn && panel) localStorage.setItem(`stratlab.watch.layout.${(s as { user: { id: string } }).user.id}`, JSON.stringify({ open: true, mode: "dock", w: 380 }));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab-theme", theme as string);
    // the menu follows the page's own space (Trade's menu lists the notebooks, and so on), as it does for a person who came through it
    const space = (spaces as Record<string, string>)[location.pathname];
    if (space) localStorage.setItem("stratlab.space", space); else localStorage.removeItem("stratlab.space");
  }, [session, signedIn, theme, spaces, panel] as const);
  return ctx;
}

/** Opens a route, waits for it to be drawn, measures it, and (when it has violations) saves a shot with the offenders outlined. */
async function measure(page: Page, r: Route, size: (typeof SIZES)[number], theme: string, shots: string): Promise<{ rows: Row[]; note?: string; frame?: PageFrame | null }> {
  await page.goto(WEB + r.path);
  // (with Market Watch open the page is never network-idle: its prices refresh every few seconds, so it gets a short wait instead)
  if (process.env.UI_LINT_PANEL === "1" && size.width > 900) await page.waitForTimeout(1200);
  else await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => undefined);
  let note: string | undefined;
  await expect(page.locator(".spinner")).toHaveCount(0, { timeout: 15_000 }).catch(() => { note = "still loading after 15s"; });
  // a card still reading its data shows a skeleton (role=status, aria-busy): measuring that would report the loading state, not the page
  await expect(page.locator("[aria-busy=true]")).toHaveCount(0, { timeout: 10_000 }).catch(() => { note = note ?? "a skeleton was still showing after 10s"; });
  await page.evaluate(() => document.fonts.ready).catch(() => undefined);
  await page.waitForTimeout(350);
  // a person opens the folded parts (rules, glossaries, "more" sections) to use them: measure them open, so a problem inside one counts
  const opened = await page.evaluate(() => { const d = Array.from(document.querySelectorAll("details:not([open])")); d.forEach((x) => x.setAttribute("open", "")); return d.length; });
  if (opened) await page.waitForTimeout(250);
  const body = (await page.locator("body").innerText().catch(() => "")).slice(0, 4000);
  if (/page (isn.t|is not) here|page not found|404/i.test(body.slice(0, 400)) && !/404/.test(r.path)) note = note ?? "the page shows not-found";
  let res: LintResult;
  try { res = await page.evaluate(lintPage, { phone: size.width <= 500, mark: process.env.UI_LINT_SHOTS !== "0" }); }
  catch (e) { return { rows: [], note: `lint failed: ${String(e).slice(0, 200)}` }; }
  const rows: Row[] = res.violations.map((v) => ({ ...v, page: r.path, label: r.label, width: size.width, theme }));
  if (rows.length && process.env.UI_LINT_SHOTS !== "0") {
    const file = `${slug(r.label)}-${size.width}${theme === "light" ? "-light" : ""}.jpg`;
    const h = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
    await page.screenshot({ path: resolve(shots, file), type: "jpeg", quality: 60, fullPage: true, clip: { x: 0, y: 0, width: size.width, height: Math.min(h, 6000) } }).catch(() => undefined);
    for (const x of rows) x.shot = `shots/${file}`;
  }
  return { rows, note, frame: res.frame };
}

function report(rows: Row[], routes: Route[], notes: string[], seconds: number, allow: Allow[], total: number): string {
  const live = rows.filter((r) => !r.allowed);
  const byRule: Record<string, number> = {};
  for (const r of live) byRule[r.rule] = (byRule[r.rule] ?? 0) + 1;
  const widths = Array.from(new Set(PASSES.map((p) => `${p.size.width}${p.theme === "light" ? " light" : ""}`))).join(", ");
  const md: string[] = [`# UI-LINT report`, "", `${routes.length} routes x widths ${widths} (dark unless marked) in ${Math.round(seconds)} s. ${live.length} violations (${rows.length - live.length} allowed by ui-lint.allow.json: ${allow.length} entries).`, "",
    "## Rules and counts", "", "| rule | violations | what it finds |", "|---|---:|---|", ...Object.entries(RULES).map(([k, v]) => `| ${k} | ${byRule[k] ?? 0} | ${v} |`), ""];
  if (notes.length) md.push("## Notes", "", ...notes.map((n) => `- ${n}`), "");
  // the same element + rule on many pages is usually one component: list those once
  const groups = new Map<string, { rule: string; key: string; pages: Set<string>; sample: Row }>();
  for (const r of live) {
    const k = `${r.rule}|${r.key}|${r.detail.replace(/\d+/g, "#").slice(0, 60)}`;
    const g = groups.get(k) ?? { rule: r.rule, key: r.key, pages: new Set<string>(), sample: r };
    g.pages.add(r.label);
    groups.set(k, g);
  }
  const shared = [...groups.values()].filter((g) => g.pages.size >= 3).sort((a, b) => b.pages.size - a.pages.size);
  if (shared.length) {
    md.push("## Seen on 3+ pages (probably one shared component)", "");
    for (const g of shared) md.push(`- ${g.rule} \`${g.key}\` on ${g.pages.size} pages (e.g. ${[...g.pages].slice(0, 3).join(", ")}): ${g.sample.detail}`);
    md.push("");
  }
  md.push("## By page", "");
  for (const route of routes) {
    const here = live.filter((r) => r.label === route.label);
    if (!here.length) continue;
    md.push(`### ${route.label}`, "");
    for (const rule of Object.keys(RULES)) {
      const mine = here.filter((r) => r.rule === rule);
      if (!mine.length) continue;
      const merged = new Map<string, { row: Row; widths: number[] }>();
      for (const r of mine) { const k = `${r.element}|${r.detail.replace(/\d+/g, "#")}`; const m = merged.get(k) ?? { row: r, widths: [] }; m.widths.push(r.width); merged.set(k, m); }
      for (const { row, widths: w } of merged.values()) md.push(`- **${rule}** @${[...new Set(w)].join("/")}: \`${row.element}\` - ${row.detail}${row.shot ? ` ([shot](${row.shot}))` : ""}`);
    }
    md.push("");
  }
  return md.join("\n");
}

test("rules fire on known-bad layouts and stay quiet on good ones", async ({ page }) => {
  // tiny fixture pages: each pair is the owner's complaint and its fix (the real pages are checked below)
  const css = `<style>*{box-sizing:border-box}body{font:14px/20px sans-serif;margin:0;padding:20px;width:1200px}
    .k-card{border:1px solid #888;border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:12px;background:#fff}
    .row{display:flex;gap:16px;align-items:flex-start}.row>*{flex:1}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
    .k-chip{height:32px;padding:0 12px;border:1px solid #888;border-radius:99px;background:#fff}.chips{display:flex;flex-wrap:wrap;gap:8px;width:300px}
    .k-field{display:flex;flex-direction:column;gap:6px}.k-form{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;align-items:start}
    .k-field-msg{font-size:12px;line-height:16px}.k-stat-v{font-size:24px}.k-seg{display:inline-flex}.k-seg button{height:32px;padding:0 14px}
    nav a{display:block;padding:6px 10px}nav a.active{background:#ccd}.tall{height:300px}
    .info-btn{display:inline-grid;place-items:center;width:18px;height:18px;border:1px solid #888;border-radius:50%;padding:0;font-size:11px;background:#fff}
    .k-stats{display:flex;gap:16px}.k-stat{display:flex;flex-direction:column;gap:2px;width:150px}.k-stat-k{font-size:12px;line-height:16px}.k-stat-v{font-size:24px;line-height:28px}
    .badge{display:inline-block;border-radius:99px;background:#dde;padding:3px 10px;font-size:12px;line-height:16px}</style>`;
  const fire = async (html: string, phone = false) => { await page.setContent(css + html); return (await page.evaluate(lintPage, { phone, mark: false })).violations.map((v) => v.rule); };
  const chips = (n: number) => Array.from({ length: n }, (_, i) => `<button class="k-chip">Chip number ${i}</button>`).join("");
  // R1 dead space: two cards of very different heights side by side (the Positioning FII/DII gap)
  expect(await fire(`<div class="row"><div class="k-card tall">Long card<p>x</p></div><div class="k-card">Short</div></div>`), "R1 short card beside a tall one").toContain("R1");
  expect(await fire(`<div class="row"><div class="k-card tall" style="height:260px">A<p>${"line ".repeat(200)}</p></div><div class="k-card" style="height:260px">B<p>${"line ".repeat(200)}</p></div></div>`), "R1 two full cards").not.toContain("R1");
  // R1 with the short card stretched by the row: its border is as tall, but it is empty inside
  expect(await fire(`<div class="row" style="align-items:stretch"><div class="k-card" style="min-height:400px"><p>${"line ".repeat(500)}</p></div><div class="k-card">Short</div></div>`), "R1 stretched short card").toContain("R1");
  // R2 sparse wide card
  expect(await fire(`<div class="k-card" style="width:1100px;height:200px"><h3>Two figures</h3><div style="display:flex;gap:30px"><b class="k-stat-v">12</b><b class="k-stat-v">34</b></div></div>`), "R2 wide card with two figures").toContain("R2");
  // the old Positioning FII/DII card: two stats side by side in the left of a wide card, under a long caption that stretches the union
  expect(await fire(`<div class="k-card" style="width:1100px;height:200px"><h3>Flows</h3><div style="display:flex;gap:200px;width:700px"><div><small>FII</small><br><b class="k-stat-v">₹4,120 cr</b></div><div><small>DII</small><br><b class="k-stat-v">₹3,310 cr</b></div></div><p style="width:1000px">${"A long caption that runs most of the way across the card. ".repeat(3)}</p></div>`), "R2 two stats in the left 72%").toContain("R2");
  // a long column of lines squeezed into the left third (the corporate actions list) is sparse; one headline or a short note is not
  expect(await fire(`<div class="k-card" style="width:1100px;height:400px"><h3>Coming up</h3>${Array.from({ length: 8 }, (_, i) => `<div>Ex-date ${i + 1} Nov: TCS ₹11 a share</div>`).join("")}</div>`), "R2 long list in the left third").toContain("R2");
  expect(await fire(`<div class="k-card" style="width:1100px;height:160px"><h3>Market headlines</h3><div>Nifty trades higher at 25,337</div><small>Economic Times · 2 hours ago</small></div>`), "R2 one headline").not.toContain("R2");
  expect(await fire(`<div class="k-card" style="width:1100px;height:160px"><h3>Profile</h3><div style="display:grid;grid-template-columns:repeat(3,1fr)"><div><small>Email</small><br><b>owner@example.com</b></div><div><small>Signed in with</small><br><b>Google</b></div><div><small>Plan</small><br><b>Pro</b></div></div></div>`), "R2 three facts spread across").not.toContain("R2");
  expect(await fire(`<div class="k-card" style="width:1100px;height:200px"><h3>Table</h3><table style="width:100%"><tr><td>a</td><td>b</td></tr></table></div>`), "R2 full-width table").not.toContain("R2");
  // R3 "+ Custom" centred beside two wrapped rows of chips, and as the last chip
  expect(await fire(`<div style="display:flex;align-items:center;gap:8px"><div class="chips">${chips(6)}</div><button class="k-chip">+ Custom</button></div>`), "R3 floating + Custom").toContain("R3");
  expect(await fire(`<div class="chips">${chips(6)}<button class="k-chip">+ Custom</button></div>`), "R3 + Custom as a chip").not.toContain("R3");
  // R3 the end control far from the rest of its row is floating; with a title between ("‹ Prev   October 2026   Next ›") it is not
  expect(await fire(`<div style="display:flex;gap:8px;align-items:center;width:600px"><button class="k-chip">A</button><button class="k-chip">B</button><button class="k-chip">C</button><span style="flex:1"></span><button class="k-chip">Far</button></div>`), "R3 end control floating").toContain("R3");
  expect(await fire(`<div style="display:flex;gap:8px;align-items:center;width:600px"><button class="k-chip">‹ Prev</button><b style="width:200px;text-align:center">October 2026</b><button class="k-chip">Next ›</button><button class="k-chip">Today</button></div>`), "R3 title between").not.toContain("R3");
  // R4 a label wrapping inside a segmented button
  expect(await fire(`<div class="k-seg"><button style="width:60px">New (default)</button><button>Old</button></div>`), "R4 wrapped label").toContain("R4");
  expect(await fire(`<div class="k-seg"><button>New (default)</button><button>Old</button></div>`), "R4 one-line label").not.toContain("R4");
  // R5 labels of different heights push the controls out of line
  expect(await fire(`<div class="k-form"><div class="k-field"><label>A label that is long enough to wrap onto a second line here</label><input></div><div class="k-field"><label>Short</label><input></div><div class="k-field" style="width:150px"><label>Another very long label for wrapping</label><input></div></div>`), "R5 controls at different y").toContain("R5");
  // R6 a four-line hint squeezed under one box of a row of boxes
  expect(await fire(`<div class="k-form" style="grid-template-columns:200px 200px 200px 600px"><div class="k-field"><label>Costs</label><select><option>Automatic</option></select><span class="k-field-msg">Automatic uses intraday (MIS) when the rules close the same day, otherwise delivery, so the costs follow what the trade was.</span></div><div class="k-field"><label>B</label><input></div><div class="k-field"><label>C</label><input></div></div>`), "R6 squeezed hint").toContain("R6");
  // R7 two menu items highlighted at once
  expect(await fire(`<nav><a class="active" href="#">Notebooks</a><a class="active" href="#">My notebook</a><a href="#">Library</a></nav>`), "R7 two active").toContain("R7");
  expect(await fire(`<nav><a class="active" href="#">Notebooks</a><a href="#">My notebook</a></nav>`), "R7 one active").not.toContain("R7");
  // R8 the same figure three times on a card
  expect(await fire(`<div class="k-card"><b>₹77,61,298</b><p>Your gain is ₹77,61,298</p><div>Total ₹77,61,298</div></div>`), "R8 repeated figure").toContain("R8");
  expect(await fire(`<div class="k-card"><b>₹77,61,298</b><p>Your gain is ₹12,000</p></div>`), "R8 distinct figures").not.toContain("R8");
  // R9 four cards and one alone
  const cells = (n: number) => Array.from({ length: n }, (_, i) => `<div class="k-card" style="height:90px">Card ${i}</div>`).join("");
  expect(await fire(`<div class="grid">${cells(5)}</div>`), "R9 4+1").toContain("R9");
  expect(await fire(`<div class="grid">${cells(8)}</div>`), "R9 4+4").not.toContain("R9");
  // R10 clipped text
  expect(await fire(`<div style="width:100px;overflow:hidden;white-space:nowrap">A sentence much longer than its box allows</div>`), "R10 clipped text").toContain("R10");
  // R1 lowered (CK-2): the Invest home's "Results today" held one line in a card stretched to 207px by "Coming up" beside it: 86px (41%) empty
  const lines = (n: number) => Array.from({ length: n }, (_, i) => `<p style="margin:0">Line ${i + 1} of the card</p>`).join("");
  expect(await fire(`<div class="row" style="align-items:stretch"><div class="k-card" style="min-height:207px"><h3 style="margin:0">Coming up</h3>${lines(7)}</div><div class="k-card"><h3 style="margin:0">Results today</h3>${lines(2)}</div></div>`), "R1 86px / 41% hole").toContain("R1");
  expect(await fire(`<div class="row" style="align-items:stretch"><div class="k-card" style="min-height:207px"><h3 style="margin:0">Coming up</h3>${lines(7)}</div><div class="k-card"><h3 style="margin:0">Results today</h3>${lines(6)}</div></div>`), "R1 nearly full").not.toContain("R1");
  // R13 empty inside a box: the home page's "Paper sessions", a short card stretched by its row inside a wrapper (R1 sees the wrapper's card as content)
  expect(await fire(`<div class="row" style="align-items:stretch"><div><div class="k-card" style="height:287px"><h3 style="margin:0">Paper sessions</h3><b class="k-stat-v">1 running</b><p style="margin:0">One line</p></div></div><div class="k-card" style="height:287px">${lines(12)}</div></div>`), "R13 hole inside a nested card").toContain("R13");
  expect(await fire(`<div class="k-card" style="height:287px"><h3 style="margin:0">Equity</h3><svg width="400" height="210"><rect width="400" height="210" fill="#ccc"/></svg></div>`), "R13 card filled by a chart").not.toContain("R13");
  expect(await fire(`<div class="k-card" style="height:287px;justify-content:center;align-items:center"><span>Nothing here yet</span></div>`), "R13 a message centred in its box").not.toContain("R13");
  // R13 a short card stretched beside a taller one with its notes pinned to the bottom edge: the hole is in the middle (Money's My Holdings, the events week card)
  expect(await fire(`<div class="k-card" style="height:300px"><h3 style="margin:0">The next seven days</h3><p style="margin:0">Tue 27 Oct · Monthly F&amp;O expiry</p><p style="margin:0;margin-top:auto">Results this week: 1</p></div>`), "R13 notes pinned to the bottom edge").toContain("R13");
  expect(await fire(`<div class="k-card" style="height:150px"><h3 style="margin:0">The next seven days</h3><p style="margin:0">Tue 27 Oct · Monthly F&amp;O expiry</p><p style="margin:0">Results this week: 1</p></div>`), "R13 notes directly under the list").not.toContain("R13");
  // R2 (CK-2) two tiles in the left half of a four-column grid leave the right half of the row empty (Invest's "More you can do"); sharing the row they do not
  const tile = (n: string) => `<div class="k-card" style="height:100px">${n}</div>`;
  expect(await fire(`<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;width:1000px">${tile("Compare two companies")}${tile("Company deep dive")}</div>`), "R2 two tiles in half the row").toContain("R2");
  expect(await fire(`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;width:1000px">${tile("Compare two companies")}${tile("Company deep dive")}</div>`), "R2 two tiles sharing the row").not.toContain("R2");
  // R14 a fixed pill over a control (the notebook's "Lab notes" over a rule's delete button), checked at the scroll's top, middle and bottom
  const pill = `<div style="position:fixed;right:10px;bottom:10px;width:120px;height:40px;border:1px solid #888;border-radius:20px;background:#fff">Lab notes</div>`;
  expect(await fire(`<main style="position:relative;height:1600px;width:1240px"><button style="position:absolute;left:1330px;top:860px;width:40px;height:30px">x</button>${pill}</main>`), "R14 pill over a button").toContain("R14");
  expect(await fire(`<main style="position:relative;height:1600px;width:1240px"><button style="position:absolute;left:100px;top:860px;width:40px;height:30px">x</button><p style="margin:0;width:600px">Some text in the column</p>${pill}</main>`), "R14 pill in the margin").not.toContain("R14");
  // R15 an (i) glued to the header text beside it ("ⓘOf shares issued" in a right-aligned column head)
  expect(await fire(`<table><tr><th style="text-align:right"><button class="info-btn">i</button>Of shares issued</th></tr></table>`), "R15 (i) touching its text").toContain("R15");
  expect(await fire(`<table><tr><th style="text-align:right"><button class="info-btn" style="margin-right:6px">i</button>Of shares issued</th></tr></table>`), "R15 (i) with a gap").not.toContain("R15");
  // R16 a stat row: a word among numbers ("None yet"), a value wrapped over two lines, a three-line label beside a one-line one
  const stat = (k: string, v: string) => `<div class="k-stat"><span class="k-stat-k">${k}</span><b class="k-stat-v">${v}</b></div>`;
  expect(await fire(`<div class="k-stats">${stat("Open value", "$10,120")}${stat("Today", "$120")}${stat("Since the start", "$320")}${stat("Worst day", "None yet")}</div>`), "R16 word among numbers").toContain("R16");
  expect(await fire(`<div class="k-stats">${stat("Open value", "$10,120")}${stat("Today", "$120")}${stat("Since the start", "$320")}${stat("Period", "49 months, 1,499 candles")}</div>`), "R16 wrapped value").toContain("R16");
  expect(await fire(`<div class="k-stats">${stat("Ratio", "0.94")}${stat("Stocks up 4% or more, down 4% or more on the day, and the rest", "12")}${stat("Up", "196")}</div>`), "R16 three-line label").toContain("R16");
  expect(await fire(`<div class="k-stats">${stat("Open value", "$10,120")}${stat("Today", "$120")}${stat("Since the start", "$320")}${stat("Period", "49 months")}${stat("Worst day", "−$40")}</div>`), "R16 a row of figures").not.toContain("R16");
  // R17 page frame: every page but one shows its title at y 112 and its cards to x 1384; the odd one (the notebook's /new, 1224) is reported
  const frameOf = async (h1Top: number, right: number) => { await page.setContent(css + `<main style="padding:0;margin:0"><div style="height:${h1Top - 6}px"></div><h1 style="margin:0;line-height:20px">T</h1><div class="k-card" style="margin:20px 0 0 300px;width:${right - 300}px;height:100px">c</div></main>`); return (await page.evaluate(lintPage, { phone: false, mark: false })).frame!; };
  const frames = [await frameOf(112, 1384), await frameOf(112, 1384), await frameOf(112, 1384), await frameOf(112, 1224), await frameOf(86, 1384)];
  const odd = frameOutliers(frames.map((frame) => ({ group: "app", frame })), 3).map((o) => o.index);
  expect(odd, "R17 the narrow page and the high title are the odd ones").toEqual([3, 4]);
  expect(frameOutliers(frames.slice(0, 3).map((frame) => ({ group: "app", frame })), 3), "R17 pages that agree").toEqual([]);
  // R18 on a phone: a row of chips cut at the edge; a table showing 2 of 4 columns (and a grid that scrolls on purpose)
  const bar = (wrapIt: boolean) => `<div class="k-chipbar" style="display:flex;gap:6px;width:300px;${wrapIt ? "flex-wrap:wrap" : "overflow-x:auto"}">${["3M", "6M", "1Y", "2Y", "All"].map((c) => `<button class="k-chip" style="flex:none;width:80px">${c}</button>`).join("")}</div>`;
  expect(await fire(bar(false), true), "R18 chips cut by the edge").toContain("R18");
  expect(await fire(bar(true), true), "R18 chips wrapped").not.toContain("R18");
  const tbl = (attr: string) => `<div ${attr} style="overflow-x:auto;width:300px"><table style="width:700px"><thead><tr><th>Stock</th><th>Price</th><th>Shares</th><th>Gain</th></tr></thead><tbody><tr><td>TCS</td><td>3,000</td><td>10</td><td>+400</td></tr></tbody></table></div>`;
  expect(await fire(tbl(""), true), "R18 table shows fewer columns").toContain("R18");
  expect(await fire(tbl("data-grid"), true), "R18 a grid read across").not.toContain("R18");
  // R19 a status badge that wraps to three lines (the IPO list's "Social Stock Exchange raise, not an IPO")
  expect(await fire(`<span class="badge" style="width:110px">Social Stock Exchange raise, not an IPO</span>`), "R19 wrapped badge").toContain("R19");
  expect(await fire(`<span class="badge">Fund raise</span>`), "R19 one-line badge").not.toContain("R19");
  // R20 a delete "×" far from the end of its rule's text
  const rule = (far: boolean) => `<div style="display:flex;align-items:center;width:1000px"><span>Buys when EMA 10 crosses above EMA 30</span><button class="k-chip" style="width:32px;padding:0;${far ? "margin-left:auto" : "margin-left:8px"}">×</button></div>`;
  expect(await fire(rule(true)), "R20 far × ").toContain("R20");
  expect(await fire(rule(false)), "R20 × beside the text").not.toContain("R20");
  expect(await fire(`<div style="display:flex;align-items:center;width:1000px"><h3 style="margin:0">Coming up</h3><button class="k-chip" style="margin-left:auto">Market events</button></div>`), "R20 a card head's action").not.toContain("R20");
  // R21 a blank band between the page title and the first card (the notebook page's 65px)
  const head = (gap: number) => `<main><h1 style="margin:0;font-size:28px;line-height:34px">Notebook</h1><p style="margin:0">What it tests</p><div class="k-card" style="margin-top:${gap}px;height:100px">About</div></main>`;
  expect(await fire(head(80)), "R21 blank band").toContain("R21");
  expect(await fire(head(24)), "R21 normal gap").not.toContain("R21");
  // R22 change rows whose tags differ in width push the name to a different x ("Leaving F&O", "Lot size", "Expiry or session")
  const tagRow = (tag: string, fixed: boolean) => `<div style="display:flex;gap:8px;align-items:center"><span class="badge" style="${fixed ? "width:140px" : ""}">${tag}</span><a href="#">RELIANCE</a></div>`;
  expect(await fire(`<div>${["Leaving F&O", "Lot size", "Expiry or session"].map((t) => tagRow(t, false)).join("")}</div>`), "R22 names out of column").toContain("R22");
  expect(await fire(`<div>${["Leaving F&O", "Lot size", "Expiry or session"].map((t) => tagRow(t, true)).join("")}</div>`), "R22 names in a column").not.toContain("R22");
  // R23 two cards side by side, the header of one wraps its button under the title (the breadth page's two chart cards)
  const cardHead = (title: string) => `<div class="k-card" style="width:300px"><div class="k-card-head" style="display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between"><h3 style="margin:0">${title}</h3><button class="k-chip">Table</button></div><p>Chart</p></div>`;
  expect(await fire(`<div style="display:flex;gap:16px;align-items:flex-start">${cardHead("Share above the 50- and 200-day averages")}${cardHead("Advance/decline line")}</div>`), "R23 one header wraps").toContain("R23");
  expect(await fire(`<div style="display:flex;gap:16px;align-items:flex-start">${cardHead("Advances")}${cardHead("Advance/decline line")}</div>`), "R23 both headers one line").not.toContain("R23");
  // R24 an unchecked box that is a dark grey square on a dark card (about 1.6:1)
  const box = (border: string, fill: string) => `<div style="background:#2a2a28;padding:20px"><input type="checkbox" style="appearance:none;-webkit-appearance:none;width:18px;height:18px;margin:0;border:1.5px solid ${border};background:${fill};border-radius:4px"></div>`;
  expect(await fire(box("#3c3c39", "#3c3c39")), "R24 faint box").toContain("R24");
  expect(await fire(box("#a8a8a2", "transparent")), "R24 visible box").not.toContain("R24");
  // R25 one sentence twice in one entry (a filing's title printed again as its body)
  expect(await fire(`<div class="k-card"><div><b>Disclosure of creation of pledge by promoter</b><p style="margin:0">Disclosure of creation of pledge by promoter.</p></div></div>`), "R25 title said again").toContain("R25");
  expect(await fire(`<div class="k-card"><div style="display:flex;gap:20px"><small class="k-stat-d">last 12 months vs the 12 before</small><small class="k-stat-d">last 12 months vs the 12 before</small></div></div>`), "R25 same caption on two stats").not.toContain("R25");
  // R12 caption under a list
  expect(await fire(`<ul><li>One</li><li>Two</li></ul><p style="font-size:12px">Dots: each notebook's last verdict.</p>`), "R12 caption").toContain("R12");
});

test("every route, three widths: UI layout problems, reported (UI_LINT_STRICT=1 fails on them)", async ({ browser, request }) => {
  test.setTimeout(30 * 60_000);
  const t0 = Date.now();
  const world = await seedWorld(request);
  let routes = world.routes;
  if (process.env.UI_LINT_ROUTES) routes = routes.filter((r) => new RegExp(process.env.UI_LINT_ROUTES!).test(r.label));
  rmSync(OUT, { recursive: true, force: true });
  const shots = resolve(OUT, "shots");
  mkdirSync(shots, { recursive: true });

  // every (route x pass) is one task; LANES pages are measured at once, each lane keeping one browser window per width and sign-in state
  const spaces: Record<string, string> = {};
  for (const r of routes) if (r.space) spaces[r.path.split(/[?#]/)[0]] = r.space;
  const tasks = routes.flatMap((r) => PASSES.map((p) => ({ r, ...p })));
  let next = 0;
  const rows: Row[] = [];
  const frames: (FrameRow & { r: Route; width: number; theme: string })[] = [];
  const notes = [...world.notes];
  await Promise.all(Array.from({ length: LANES }, async () => {
    const pages = new Map<string, Page>();
    const ctxs: BrowserContext[] = [];
    for (;;) {
      const t = tasks[next++];
      if (!t) break;
      const k = `${t.size.width}|${t.theme}|${t.r.signedIn}`;
      let page = pages.get(k);
      if (!page) { const ctx = await newContext(browser, t.size, t.theme, t.r.signedIn, spaces); ctxs.push(ctx); page = await ctx.newPage(); pages.set(k, page); }
      try {
        const m = await measure(page, t.r, t.size, t.theme, shots);
        rows.push(...m.rows);
        if (m.frame) frames.push({ group: `${t.size.width}|${t.theme}|${t.r.signedIn}|${t.r.path.startsWith("/admin") ? "admin" : "app"}`, frame: m.frame, r: t.r, width: t.size.width, theme: t.theme });
        if (m.note) notes.push(`${t.r.label} @ ${t.size.width}: ${m.note}`);
      } catch (e) { notes.push(`${t.r.label} @ ${t.size.width}: ${String(e).slice(0, 160)}`); }
    }
    for (const c of ctxs) await c.close();
  }));

  // R17 compares pages with each other, so it is decided once every page has been measured
  for (const o of frameOutliers(frames)) { const f = frames[o.index]; rows.push({ rule: "R17", element: "page frame", key: "page-frame", detail: o.detail, page: f.r.path, label: f.r.label, width: f.width, theme: f.theme }); }
  const allow = allowlist();
  for (const r of rows) r.allowed = allowedBy(allow, r);
  rows.sort((a, b) => routes.findIndex((x) => x.label === a.label) - routes.findIndex((x) => x.label === b.label) || a.rule.localeCompare(b.rule, "en", { numeric: true }) || b.width - a.width);
  const seconds = (Date.now() - t0) / 1000;
  const live = rows.filter((r) => !r.allowed);
  const perRule = Object.fromEntries(Object.keys(RULES).map((k) => [k, live.filter((r) => r.rule === k).length]));
  writeFileSync(resolve(OUT, "report.json"), JSON.stringify({ seconds: Math.round(seconds), routes: routes.length, widths: PASSES.map((p) => `${p.size.width}${p.theme === "light" ? "-light" : ""}`), perRule, notes, violations: rows }, null, 1));
  writeFileSync(resolve(OUT, "report.md"), report(rows, routes, notes, seconds, allow, tasks.length));
  console.log(`ui-lint: ${live.length} violations on ${routes.length} routes in ${Math.round(seconds)} s -> ${resolve(OUT, "report.md")}`, perRule);
  if (STRICT) expect(live.map((r) => `${r.label} @${r.width} ${r.rule} ${r.element}: ${r.detail}`), "UI layout violations (add a reasoned entry to e2e/ui-lint.allow.json to accept one)").toEqual([]);
});
