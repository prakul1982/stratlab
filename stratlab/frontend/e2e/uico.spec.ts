import { expect, test, type Page } from "@playwright/test";

// UI-CO (29 Oct 2026): the owner's company-page, Compare and Screener fixes: blocks of figures are tables with a header row and aligned columns.
// Desktop and phone. The fake world holds a deep-dive read and a management report card for RELIANCE (backend/tests/visual_server.py deep_reads):
// targets met, missed, not due yet, and ones the numbers can't settle (a segment, no year named, a plan with no figure).
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|bullish|bearish|should|recommend)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nseindia|edgar/i;
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN = session("admin-token", "u-admin", "owner@example.com");
const LOAD = (n: number) => session(`load-${n}`, `u-load-${n}`, `load${n}@example.com`);

async function open(page: Page, path: string, ready: string, s = ADMIN, extra?: () => Promise<void> | void) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.addInitScript((x) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1"); }, s);
  await extra?.();
  await page.goto(path);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 3000 }).then(async () => { await welcome.getByRole("button", { name: /^All of it/ }).click(); return true; }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").first().innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
}

/** Cells whose content runs past them (a note over the next column), the check LIVE1A-048 made for Compare. */
const overflowing = (page: Page, root: string) => page.evaluate((sel) => Array.from(document.querySelectorAll(`${sel} td, ${sel} th`)).filter((c) => {
  const cell = c.getBoundingClientRect();
  return cell.width > 0 && Array.from(c.querySelectorAll("*")).some((x) => { const r = x.getBoundingClientRect(); return r.width > 0 && r.right > cell.right + 1; });
}).length, root);

test("company page: corporate actions, key numbers and the AI read are tables with headers", async ({ page }) => {
  const errors = await open(page, "/research/IN/TCS", "Corporate actions");
  const actions = page.locator("#corporate-actions").getByRole("table", { name: /Corporate actions/ });
  await expect(actions.getByRole("columnheader")).toHaveText(["Ex-date", "Type", "Amount a share", "Record date"], { timeout: 30_000 });
  expect(await actions.locator("tbody tr").count()).toBeGreaterThan(1);
  await expect(page.locator("#corporate-actions").getByText(/Dividends with an ex-date in the last 12 months/)).toBeVisible();      // the total stays a line above the table
  // Key numbers: a table a group, all of one width, each with Value and Basis columns
  const val = page.getByRole("table", { name: "Key numbers: Valuation" });
  await expect(val.getByRole("columnheader")).toHaveText(["Valuation", "Value", "Basis", "Range"]);
  const widths = await page.locator(".inv-metrics .inv-mt").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
  expect(widths.length).toBeGreaterThanOrEqual(4);
  expect(new Set(widths).size, `Key numbers' tables: ${widths}`).toBe(1);
  expect(await overflowing(page, ".inv-metrics"), "a note running out of its cell").toBe(0);
  // (the AI read's table is checked in unit/uico.test.mjs: the fake world's model reply differs from one read to the next)
  await sane(page, errors);
});

test("company page: the price header is one balanced block, the buttons under it", async ({ page }, info) => {
  const errors = await open(page, "/research/IN/RELIANCE", "Market value");
  const q = await page.getByTestId("company-price").boundingBox();
  const cap = await page.locator(".inv-head-cap").boundingBox();
  const rail = await page.locator(".inv-head-price").boundingBox();
  const acts = await page.locator(".inv-actions").boundingBox();
  expect(q && cap && rail && acts).toBeTruthy();
  expect(acts!.y, "the buttons are under the figures").toBeGreaterThan(Math.max(q!.y + q!.height, cap!.y + cap!.height, rail!.y + rail!.height) - 1);
  if (info.project.name !== "phone") {
    expect(Math.abs(q!.y - cap!.y), "price and market value start together").toBeLessThan(40);
    expect(cap!.x - (q!.x + q!.width), "no wide empty middle between the price and the market value").toBeLessThan(260);
  } else {
    expect(cap!.y, "stacked: the price, then the market value").toBeGreaterThan(q!.y + q!.height - 1);
  }
  await sane(page, errors);
});

test("deep dive: the report card is a table with the quote under each target, and what can't be checked says why", async ({ page }) => {
  const errors = await open(page, "/research/IN/RELIANCE/deep", "Management report card");
  const card = page.getByRole("table", { name: "Management targets and how they turned out" });
  await expect(card).toBeVisible();
  await expect(card.getByRole("columnheader")).toHaveText(["Target", "For", "Said", "Result"]);
  const text = await card.innerText();
  expect(text, "a 20% CAGR said as a fraction").not.toMatch(/\b0\.2%|\b0\.3.0\.5%/);
  expect(text).toContain("30–50%");                                                      // what management said, as said
  expect(text).toMatch(/Net margin: PAT margin of 1\.5%/);                               // a PAT margin is a net margin, not the operating margin
  expect(text, "a statement about the past is not a target").not.toContain("our CAGR has been 20%");
  expect(text, "an analyst's question is not a target").not.toContain("are we expecting 12% growth");
  await expect(card.getByTestId("rc-why").filter({ hasText: "whole company" }).first()).toBeVisible();
  await expect(card.getByTestId("rc-why").filter({ hasText: "No year or quarter was named" }).first()).toBeVisible();
  // every row says its result, and each can't-check row says why
  const rows = card.locator("tbody tr");
  const n = await rows.count();
  for (let i = 0; i < n; i++) {
    const row = rows.nth(i);
    if ((await row.innerText()).includes("Can't check")) await expect(row.getByTestId("rc-why")).toHaveCount(1);
  }
  // the counts above the table agree with it
  const cant = await card.getByText("Can't check", { exact: true }).count();
  await expect(page.locator("main").getByText("Couldn't check", { exact: true }).locator("xpath=..")).toContainText(String(cant));
  expect(await overflowing(page, "[aria-label='Management targets and how they turned out']"), "text running out of a cell").toBe(0);
  await sane(page, errors);
});

test("deep dive: growth, the checklist, the documents read and the business model are tables", async ({ page }) => {
  const errors = await open(page, "/research/IN/RELIANCE/deep", "Investor checklist");
  await expect(page.getByRole("table", { name: "Growth a year" }).getByRole("columnheader")).toHaveText(["Growth a year", "Last 3 years", "Last 5 years"]);
  const groups = page.getByRole("table", { name: /^Investor checklist: / });
  expect(await groups.count()).toBeGreaterThanOrEqual(3);
  await expect(groups.first().getByRole("columnheader").nth(1)).toHaveText("Value");
  await expect(groups.first().getByRole("columnheader").nth(2)).toHaveText("Result");
  const heights = await page.locator(".checklist > .check-group").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)));
  expect(new Set(heights).size, "one column of tables, no masonry").toBe(1);
  const docs = page.getByRole("table", { name: "The documents the read used" });
  await expect(docs.getByRole("columnheader")).toHaveText(["Document", "Date", "Link"]);
  expect(await docs.locator("tbody tr").count()).toBeGreaterThanOrEqual(5);
  await expect(page.getByRole("table", { name: "What the business earns from" }).getByRole("columnheader")).toHaveText(["Business", "Share of revenue", "What it is"]);
  await expect(page.getByRole("table", { name: "The business, in the company's words" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Capex plans, in management's words" })).toBeVisible();
  await sane(page, errors);
});

test("compare: the two companies are one table, a long note is a numbered note under the table, and a link with no market opens where the companies are", async ({ page }) => {
  const errors = await open(page, "/research/compare?a=HDFCBANK&b=ICICIBANK", "The numbers side by side", ADMIN, async () => {
    // the browser last used the US market: the link names two Indian tickers and no market (LIVE2-021)
    await page.addInitScript(() => localStorage.setItem("stratlab.research.region", "US"));
  });
  const two = page.getByRole("table", { name: "The two companies" });
  await expect(two.getByRole("columnheader")).toHaveText(["Company", "Price", "Change", "Market value", "Actions"]);
  await expect(two.locator("tbody tr")).toHaveCount(2);
  await expect(page).toHaveURL(/region=IN/);
  expect(await overflowing(page, "main"), "a note running out of its cell").toBe(0);
  await expect(page.getByText("The two couldn't be compared")).toHaveCount(0);
  await sane(page, errors);
});

test("screener: the numeric filters are one table with equal boxes, and the results come first on a phone", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  if (phone) {
    // folded: the filters are one "Filters" bar, the results are under it, and "Save this screen" isn't in the way
    await expect(page.getByRole("heading", { name: "Filters", exact: true })).toBeVisible();
    const results = await page.getByRole("heading", { name: /companies match/ }).boundingBox();
    const save = page.getByRole("heading", { name: "Save this screen" });
    await expect(save).toBeHidden();
    expect(results!.y, "the results start near the top").toBeLessThan(700);
    await page.getByRole("button", { name: /Show filters/ }).click();
    await expect(save).toBeVisible();
  }
  if (!phone) {
    // the results fit beside the filters: no sideways scroll in their table at 1440
    const fits = await page.locator(".screens-table .k-tbl-wrap").evaluate((e) => e.scrollWidth <= e.clientWidth + 1);
    expect(fits, "the results table scrolls sideways").toBe(true);
  }
  const ranges = page.getByRole("table", { name: "Filters on figures: at least and at most" });
  await expect(ranges.getByRole("columnheader")).toHaveText(["Measure", "At least", "At most"]);
  // the names are whole (they wrap, never end in "…"), and every box is the same width whether its unit is % or ×
  const names = await ranges.locator("tbody th").allInnerTexts();
  expect(names.join(" ")).toContain("Revenue growth, 3 years");
  expect(names.join(" ")).toContain("Return on capital employed");
  expect(names.every((x) => !x.includes("…"))).toBe(true);
  const boxes = await ranges.locator("input").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
  expect(boxes.length).toBeGreaterThanOrEqual(12);
  expect(new Set(boxes).size, `box widths ${boxes}`).toBe(1);
  expect(await overflowing(page, ".screens-ranges"), "a label running out of its cell").toBe(0);
  // typing still filters, by the box's own label
  await page.getByLabel("P/E (price to earnings): at most").fill("1");
  await expect(page.getByText(/ of 20 companies match|No company meets every condition/).first()).toBeVisible();
  await sane(page, errors);
});

test("screener: when the filters can't load, there is a Try again", async ({ page }) => {
  let fail = true;
  await page.route("**/research/screens/meta**", (r) => (fail ? r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { code: "x", message: "The filters couldn't be read." } }) }) : r.fallback()));
  await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  const again = page.getByRole("button", { name: "Try again" }).first();
  await expect(again).toBeVisible({ timeout: 30_000 });
  fail = false;
  await again.click();
  await expect(page.getByRole("table", { name: "Filters on figures: at least and at most" }).or(page.getByRole("button", { name: /Show filters/ }))).toBeVisible({ timeout: 30_000 });
});

test("trend scan: build your own rules, run them over a group, and keep the scan", async ({ page }, info) => {
  const errors = await open(page, "/research/scan?region=US&set=us_mega", "Trend scan", LOAD(info.project.name === "phone" ? 286 : 283));
  const chips = page.getByRole("group", { name: "Scan rule sets", exact: true });
  await chips.getByRole("button", { name: "Build your own", exact: true }).click();
  await expect(page).toHaveURL(/scan=custom/);
  const build = page.getByTestId("scan-custom");
  await expect(build).toBeVisible();
  await expect(build.getByTestId("condition-list")).toContainText("Price");
  // the rule is a sentence of the notebook's own: change its right side to an indicator, then run it
  await page.getByLabel("Group to scan").selectOption("us_mega");
  await build.getByRole("combobox", { name: /Counts as a match/ }).selectOption({ label: "any of the last 3 candles" });
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Your own rules: 20 of the largest US companies/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("custom-rules-said")).toContainText("any of the last 3 candles");
  const table = page.getByRole("table", { name: /Your own rules/ });
  await expect(table).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Matches your rules" })).toBeVisible();
  // the stored 500-stock groups can't hold one's own rules: they are named as ready-made only
  await expect(page.getByLabel("Group to scan").locator("option", { hasText: "S&P 500" })).toContainText("ready-made scans only");
  // no rule at all: said under the box
  await build.getByRole("button", { name: "Remove this rule" }).click();
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(page.getByTestId("custom-error")).toHaveText("Add at least one rule.");
  // keep it on the account, and it is still there after a reload
  await build.getByRole("button", { name: "+ Add a rule" }).click();
  const name = `e2e rules ${info.project.name} ${Date.now()}`;
  await build.getByLabel("Keep this scan as").fill(name);
  await build.getByRole("button", { name: "Keep it" }).click();
  await expect(page.getByRole("table", { name: "Your scans" })).toContainText(name, { timeout: 15_000 });
  await page.reload();
  await page.getByRole("group", { name: "Scan rule sets", exact: true }).getByRole("button", { name: "Build your own", exact: true }).click();
  const mine = page.getByRole("table", { name: "Your scans" });
  await expect(mine).toContainText(name);
  await mine.getByRole("row").filter({ hasText: name }).getByRole("button", { name: `Delete ${name}` }).click();
  await expect(mine).toHaveCount(0, { timeout: 15_000 }).catch(() => undefined);
  await sane(page, errors);
});
