import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { lintPage, type LintResult, type Violation } from "./ui-lint-rules";
import { seedWorld, session, WEB, type Route } from "./ui-lint-world";

// UI-LINT: finds the owner's kind of layout problems (dead space beside a short card, a floating "+ Custom", a squeezed hint, two
// highlighted menu items, a figure said three times on a card, uneven rows...) on every page, automatically.
//
// It fills the pages with a Pro user's data (ui-lint-world.ts), visits every route at 1440x900, 1280x800 and 390x844 in the dark
// theme, measures the drawn page against the rules in ui-lint-rules.ts, and writes report.md, report.json and a screenshot per
// page and width with the offenders outlined. It is REPORT-ONLY (always passes) unless UI_LINT_STRICT=1, in which case any
// violation not in ui-lint.allow.json fails the run. It is its own project (playwright.config.ts) so the default runs skip it:
//   npm run build && npm run ui-lint
// Env: UI_LINT_OUT (output folder), UI_LINT_STRICT=1, UI_LINT_LIGHT=1 (also 1440 in the light theme), UI_LINT_ROUTES=<regex>,
//      UI_LINT_WIDTHS=1440,390, UI_LINT_LANES=6 (pages measured at once), UI_LINT_SHOTS=0 (no screenshots).
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(process.env.UI_LINT_OUT ?? resolve(HERE, "../test-results/ui-lint"));
const STRICT = process.env.UI_LINT_STRICT === "1";
const LANES = Number(process.env.UI_LINT_LANES ?? 6);

const SIZES = [
  { width: 1440, height: 900, touch: false },
  { width: 1280, height: 800, touch: false },
  { width: 390, height: 844, touch: true },
].filter((s) => !process.env.UI_LINT_WIDTHS || process.env.UI_LINT_WIDTHS.split(",").includes(String(s.width)));
const PASSES: { size: (typeof SIZES)[number]; theme: "dark" | "light" }[] = [
  ...SIZES.map((size) => ({ size, theme: "dark" as const })),
  ...(process.env.UI_LINT_LIGHT === "1" ? [{ size: SIZES[0] ?? { width: 1440, height: 900, touch: false }, theme: "light" as const }] : []),
];

export const RULES: Record<string, string> = {
  R1: "Dead space beside a short card: cards/columns in one row, one with > 120px and > 30% of the row height empty under its content",
  R2: "Sparse wide card: a card wider than 900px (and 140px+ tall) whose content covers < 55% of its inner width",
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
  await ctx.addInitScript(([s, signedIn, theme, spaces]) => {
    if (signedIn) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab-theme", theme as string);
    // the menu follows the page's own space (Trade's menu lists the notebooks, and so on), as it does for a person who came through it
    const space = (spaces as Record<string, string>)[location.pathname];
    if (space) localStorage.setItem("stratlab.space", space); else localStorage.removeItem("stratlab.space");
  }, [session, signedIn, theme, spaces] as const);
  return ctx;
}

/** Opens a route, waits for it to be drawn, measures it, and (when it has violations) saves a shot with the offenders outlined. */
async function measure(page: Page, r: Route, size: (typeof SIZES)[number], theme: string, shots: string): Promise<{ rows: Row[]; note?: string }> {
  await page.goto(WEB + r.path);
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => undefined);
  let note: string | undefined;
  await expect(page.locator(".spinner")).toHaveCount(0, { timeout: 15_000 }).catch(() => { note = "still loading after 15s"; });
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
  return { rows, note };
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
    nav a{display:block;padding:6px 10px}nav a.active{background:#ccd}.tall{height:300px}</style>`;
  const fire = async (html: string) => { await page.setContent(css + html); return (await page.evaluate(lintPage, { phone: false, mark: false })).violations.map((v) => v.rule); };
  const chips = (n: number) => Array.from({ length: n }, (_, i) => `<button class="k-chip">Chip number ${i}</button>`).join("");
  // R1 dead space: two cards of very different heights side by side (the Positioning FII/DII gap)
  expect(await fire(`<div class="row"><div class="k-card tall">Long card<p>x</p></div><div class="k-card">Short</div></div>`), "R1 short card beside a tall one").toContain("R1");
  expect(await fire(`<div class="row"><div class="k-card tall" style="height:260px">A<p>${"line ".repeat(200)}</p></div><div class="k-card" style="height:260px">B<p>${"line ".repeat(200)}</p></div></div>`), "R1 two full cards").not.toContain("R1");
  // R1 with the short card stretched by the row: its border is as tall, but it is empty inside
  expect(await fire(`<div class="row" style="align-items:stretch"><div class="k-card" style="min-height:400px"><p>${"line ".repeat(500)}</p></div><div class="k-card">Short</div></div>`), "R1 stretched short card").toContain("R1");
  // R2 sparse wide card
  expect(await fire(`<div class="k-card" style="width:1100px;height:200px"><h3>Two figures</h3><div style="display:flex;gap:30px"><b>12</b><b>34</b></div></div>`), "R2 wide card with two figures").toContain("R2");
  expect(await fire(`<div class="k-card" style="width:1100px;height:200px"><h3>Table</h3><table style="width:100%"><tr><td>a</td><td>b</td></tr></table></div>`), "R2 full-width table").not.toContain("R2");
  // R3 "+ Custom" centred beside two wrapped rows of chips, and as the last chip
  expect(await fire(`<div style="display:flex;align-items:center;gap:8px"><div class="chips">${chips(6)}</div><button class="k-chip">+ Custom</button></div>`), "R3 floating + Custom").toContain("R3");
  expect(await fire(`<div class="chips">${chips(6)}<button class="k-chip">+ Custom</button></div>`), "R3 + Custom as a chip").not.toContain("R3");
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
        if (m.note) notes.push(`${t.r.label} @ ${t.size.width}: ${m.note}`);
      } catch (e) { notes.push(`${t.r.label} @ ${t.size.width}: ${String(e).slice(0, 160)}`); }
    }
    for (const c of ctxs) await c.close();
  }));

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
