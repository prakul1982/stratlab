import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// VR-7 (28 Oct 2026): what the phone-first visual review and the Market Watch pass found, checked on the drawn pages. Each test sets its own width, so it is the
// same on the desktop and phone projects.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN = session("admin-token", "u-admin", "owner@example.com");

async function open(page: Page, path: string, s: object | null, width: number, height = 900) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width, height });
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.addInitScript((x) => { if (x) localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1"); }, s);
  await page.goto(path);
  return errors;
}
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
/** Three instruments on the owner's Market Watch list (the fake world starts with none). */
async function seed(request: APIRequestContext) {
  await request.put(`${API}/watch/lists/default/items`, { headers: { Authorization: "Bearer admin-token" },
    data: { items: [{ market: "IN", symbol: "INFY", name: "Infosys" }, { market: "IN", symbol: "TCS", name: "Tata Consultancy Services" }, { market: "IN", symbol: "RELIANCE", name: "Reliance Industries" }] } });
}
test.afterEach(async ({ request }) => { await request.put(`${API}/watch/lists/default/items`, { headers: { Authorization: "Bearer admin-token" }, data: { items: [] } }); });
const small = (page: Page, sel: string) => page.locator(sel).evaluateAll((els) => els.filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && (r.width < 43.5 || r.height < 43.5); })
  .map((e) => `${e.tagName.toLowerCase()} "${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 20)}" ${Math.round(e.getBoundingClientRect().width)}x${Math.round(e.getBoundingClientRect().height)}`));

test("VR7-001: the chart's range and scale buttons are 44px each way on a phone, and every range is still there", async ({ page }) => {
  await open(page, "/research/IN/RELIANCE", ADMIN, 390);
  const chart = page.getByTestId("price-chart");
  await expect(chart).toBeVisible({ timeout: 30_000 });
  expect(await small(page, ".pc-foot button")).toEqual([]);
  const ranges = await chart.getByRole("radiogroup", { name: "Range" }).getByRole("radio").allInnerTexts();
  expect(ranges).toEqual(["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "All"]);
});

test("VR7-002, VR7-005: the strategy post folds each market on a phone, with every row still in the page", async ({ page }) => {
  await open(page, "/blog/classic-strategies-ten-markets-after-costs", null, 390);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Classic strategies");
  const folds = page.locator("details.mk");
  expect(await folds.count()).toBe(10);
  expect(await folds.evaluateAll((e) => e.every((x) => !(x as HTMLDetailsElement).open))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollHeight), "the post is a few screens, not ten thousand pixels").toBeLessThan(6500);
  expect(await page.locator("details.mk a[href^='/library/']").count(), "every test is still in the page").toBeGreaterThanOrEqual(43);
  await folds.first().locator("summary").click();                                  // one opens at a time on a tap
  await expect(folds.first().locator("table")).toBeVisible();
  expect(await small(page, "article .btbl.wide th[scope=row] a")).toEqual([]);
});

test("VR7-002: on a wide screen the markets are open as before", async ({ page }) => {
  await open(page, "/blog/classic-strategies-ten-markets-after-costs", null, 1440);
  await expect(page.locator("details.mk").first().locator("table")).toBeVisible();
  await expect(page.locator("details.mk").last().locator("table")).toBeVisible();
});

test("VR7-003: A to Z on a phone fills its rows (no last row of one or two letters)", async ({ page }) => {
  for (const w of [390, 360]) {
    await open(page, "/stocks/in", null, w);
    const rows = await page.locator("nav[data-az] a").evaluateAll((els) => { const m = new Map<number, number>(); for (const e of els) { const t = Math.round(e.getBoundingClientRect().top); m.set(t, (m.get(t) ?? 0) + 1); } return [...m.values()]; });
    expect(rows.length, `${w}px: rows ${rows}`).toBeGreaterThan(1);
    expect(rows[rows.length - 1], `${w}px: rows ${rows}`).toBeGreaterThanOrEqual(Math.min(3, rows[0]));
    expect(await small(page, "nav[data-az] a")).toEqual([]);
  }
});

test("VR7-004: the signed-out library keeps every card in the page and shows twelve on a phone", async ({ page }) => {
  await open(page, "/library", null, 390);
  await expect(page.locator(".lib-card").first()).toBeVisible({ timeout: 30_000 });
  const total = await page.locator(".lib-card").count();
  expect(total).toBeGreaterThan(12);
  expect(await page.locator(".lib-card:visible").count()).toBe(12);
  await page.getByTestId("lib-show-more").getByRole("button").click();
  expect(await page.locator(".lib-card:visible").count()).toBe(Math.min(24, total));
  await open(page, "/library", null, 1440);
  await expect(page.locator(".lib-card").first()).toBeVisible({ timeout: 30_000 });
  expect(await page.locator(".lib-card:visible").count()).toBe(total);
  await expect(page.getByTestId("lib-show-more")).toBeHidden();
});

test("VR7-006 (UI-CO item 2): Key numbers' groups are tables of one width, in two columns on a wide page", async ({ page }) => {
  await open(page, "/research/IN/RELIANCE", ADMIN, 1440);
  const cols = page.locator(".inv-metrics > .inv-mt");
  await expect(cols.first()).toBeVisible({ timeout: 30_000 });
  const boxes = await cols.evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width)]; }));
  expect(boxes.length).toBeGreaterThanOrEqual(4);
  expect(new Set(boxes.map((b) => b[1])).size, `widths ${JSON.stringify(boxes)}`).toBe(1);        // one width: the second row's groups sit under the first row's
  expect(new Set(boxes.map((b) => b[0])).size).toBe(2);
  // each is a table with its header row and one row for every figure
  await expect(page.getByRole("table", { name: "Key numbers: Valuation" }).getByRole("columnheader")).toHaveText(["Valuation", "Value", "Basis", "Range"]);
});

test("VR7-008, VR7-019: the Markets button fits the margin on a laptop, and a chart in the panel is as tall as its tool rail", async ({ page, request }) => {
  await seed(request);
  await open(page, "/invest", ADMIN, 1440);
  const btn = page.getByTestId("markets-launch");
  await expect(btn).toBeVisible({ timeout: 30_000 });
  const b = (await btn.boundingBox())!;
  expect(b.width).toBeCloseTo(44, 0);
  const right = await page.locator("main .k-card").evaluateAll((els) => Math.max(...els.map((e) => e.getBoundingClientRect().right)));
  expect(b.x, "the button is in the margin, right of the page's cards").toBeGreaterThanOrEqual(right - 1);
  await btn.click();
  await page.getByRole("button", { name: /^Open the chart of/ }).first().click();
  const chart = page.getByTestId("price-chart");
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  const [rail, stage] = [await chart.locator(".pc-rail").boundingBox(), await chart.locator(".pc-stage").boundingBox()];
  expect(stage!.height + 1).toBeGreaterThanOrEqual(rail!.height);
});

test("VR7-009, VR7-011: the Market Watch sheet's controls are 44px on a phone", async ({ page, request }) => {
  await seed(request);
  await open(page, "/mine", ADMIN, 390, 800);
  await page.getByRole("button", { name: "Markets", exact: true }).click();
  const mw = page.getByTestId("market-watch");
  await expect(mw).toBeVisible();
  await expect(mw.locator(".mw-row").first()).toBeVisible({ timeout: 30_000 });
  expect(await small(page, ".mw button, .mw a")).toEqual([]);
  await mw.getByRole("button", { name: "+ Add symbol" }).click();
  expect((await mw.locator(".mw-tabs").boundingBox())!.height, "the list tabs keep their height with the add form open").toBeGreaterThanOrEqual(43);
});

test("VR7-013: the plans tables fit their cards at 390px and 360px", async ({ page }) => {
  for (const w of [390, 360]) {
    await open(page, "/plans", ADMIN, w);
    await expect(page.locator(".k-tbl-wrap table").first()).toBeVisible({ timeout: 30_000 });
    const over = await page.locator(".k-tbl-wrap table").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width - (e.parentElement as HTMLElement).clientWidth)).filter((d) => d > 1));
    expect(over, `${w}px: tables wider than their cards`).toEqual([]);
  }
});

test("VR7-012: a long value in Account's plan and usage reads from the left on a phone", async ({ page }) => {
  await open(page, "/account", ADMIN, 390);
  const row = page.locator("#plan .k-rows > div.long").first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  expect(await row.locator("b").evaluate((e) => getComputedStyle(e).textAlign)).toBe("left");
});
