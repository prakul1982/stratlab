import { expect, test, type Page } from "@playwright/test";

// US stocks in Indian tax and the ITR-ready export, on desktop and phone: a US trade added from the form, each sale
// in rupees, Schedule FA and its CSV, the tax report's US card, and the export's workbook, CSV files and PDF pack.
// Each project signs in as its own Pro user of the fake database (287 and 290), so the two runs never share data.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, path: string, ready: string, n: number) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(path);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

/** `words`: where to look for advice words (the tax report's upload help names a CSV's "buy or sell" column). */
async function sane(page: Page, errors: string[], words = "main") {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(await page.locator(words).innerText()).not.toMatch(/\b(buy|sell|accumulate|avoid)\b/i);
  expect(text).not.toMatch(/yahoo|finnhub|screener\.in|kite/i);
}

async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

/** A fresh start for the user: their tax data and US trades deleted, then an Indian tradebook and two US trades. */
async function seed(request: import("@playwright/test").APIRequestContext, n: number) {
  const headers = { Authorization: `Bearer load-${n}` };
  expect((await request.delete(`${API}/tax`, { headers })).ok()).toBeTruthy();
  const csv = "Date,Symbol,ISIN,Type,Quantity,Price\n2017-01-02,RELIANCE,INE002A01018,BUY,10,100\n2025-06-03,RELIANCE,INE002A01018,SELL,4,300\n"
    + "2025-05-02,INFY,INE009A01021,BUY,10,1500\n2025-11-03,INFY,INE009A01021,SELL,10,1400\n";
  expect((await request.post(`${API}/tax/import`, { headers, data: { filename: "trades.csv", data: Buffer.from(csv).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/tax/fmv`, { headers, data: { symbol: "RELIANCE", fmv: 150 } })).ok()).toBeTruthy();
  expect((await request.post(`${API}/money/us-tax/trades`, { headers, data: { d: "2023-03-01", side: "B", sym: "AAPL", qty: 3, price: 150, fees: 1 } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/money/advance-tax`, { headers, data: { fy: 2025, tds: 2000, paid: [{ d: "2025-12-12", amount: 4000 }] } })).ok()).toBeTruthy();
}

test("US stocks tax: a sale added from the form, each sale in rupees, and Schedule FA with its CSV", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 290 : 287;
  await seed(request, n);
  const errors = await open(page, "/money/us-tax", "US stocks in Indian tax", n);
  await expect(page.getByRole("heading", { name: "Your US trades" })).toBeVisible();

  // a sale typed in
  const form = page.getByRole("group", { name: "Add a trade" });
  await form.getByLabel("Trade date").fill("2025-08-14");
  await form.getByLabel("Purchase or sale").selectOption("S");
  await form.getByLabel("Ticker").fill("aapl");
  await form.getByLabel("Shares").fill("2");
  await form.getByLabel("Price in dollars").fill("220");
  await form.getByRole("button", { name: "Add trade" }).click();
  await expect(page.getByText("Sale of AAPL added.")).toBeVisible({ timeout: 15_000 });

  // the year it fell in, with the sale in rupees at the month-end rate
  await page.getByLabel("Financial year").selectOption({ label: "FY 2025-26" });
  const sales = page.getByRole("table", { name: "US sales in rupees" });
  await expect(sales).toBeVisible({ timeout: 15_000 });
  await expect(sales.getByRole("row").filter({ hasText: "AAPL" }).first()).toContainText("31 Jul 2025");
  await expect(sales.getByRole("row").filter({ hasText: "AAPL" }).first()).toContainText("Long, 12.5%");
  await expect(page.getByRole("table", { name: "Open US lots" })).toContainText("AAPL");

  // Schedule FA for last year, and its CSV
  const fa = page.getByRole("region", { name: "Schedule FA" });
  await expect(fa.getByRole("heading", { name: "Schedule FA, Table A3" })).toBeVisible();
  await expect(fa.getByRole("table", { name: "Schedule FA" })).toContainText("AAPL");
  const [csv] = await Promise.all([page.waitForEvent("download"), fa.getByRole("button", { name: "Download CSV" }).click()]);
  expect(csv.suggestedFilename()).toMatch(/^stratlab-schedule-FA-CY\d{4}\.csv$/);
  await expect(page.getByRole("list", { name: "Deadlines and rules" })).toContainText("Form 67");
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  // the tax report shows the US sales with the Indian ones
  const errs2 = await open(page, "/tax-report", "Capital gains on your shares", n);
  await page.getByLabel("Financial year").selectOption({ label: "FY 2025-26" });
  const card = page.getByRole("region", { name: "US stocks" });
  await expect(card).toContainText("1 sale in FY 2025-26");
  await expect(page.getByRole("table", { name: "Gains by rate" })).toContainText("foreign shares");
  await sane(page, errs2, "section[aria-label='US stocks']");
});

test("ITR-ready export: the schedules on the page, and the workbook, CSV files and PDF pack", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 290 : 287;
  await seed(request, n);
  expect((await request.post(`${API}/money/us-tax/trades`, { headers: { Authorization: `Bearer load-${n}` },
    data: { d: "2025-08-14", side: "S", sym: "AAPL", qty: 2, price: 220 } })).ok()).toBeTruthy();
  const errors = await open(page, "/money/itr", "Your year, laid out for the return", n);
  await page.getByLabel("Financial year").selectOption({ label: "FY 2025-26 (AY 2026-27)" });
  await expect(page.getByRole("heading", { name: "Download for FY 2025-26 (AY 2026-27)" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("note").filter({ hasText: "not a filed return" }).first()).toBeVisible();

  // Schedule 112A is open, scrip by scrip with the 31 Jan 2018 value
  const t112 = page.getByRole("table", { name: "Schedule 112A (scrip-wise long-term gains)" });
  await expect(t112).toBeVisible();
  await expect(t112.getByRole("row").filter({ hasText: "INE002A01018" })).toContainText("150");
  // other schedules open one at a time
  await page.getByRole("button", { name: /Schedule CG \(capital gains by section\)/ }).click();
  await expect(page.getByRole("table", { name: "Schedule CG (capital gains by section)" })).toContainText("foreign shares");
  await page.getByRole("button", { name: /Tax paid \(Schedule IT and TDS\)/ }).click();
  await expect(page.getByRole("table", { name: "Tax paid (Schedule IT and TDS)" })).toContainText("4,000");
  await page.getByRole("button", { name: /Schedule FA, Table A3/ }).click();
  await expect(page.getByRole("table", { name: "Schedule FA, Table A3 (foreign equity)" })).toContainText("2-UNITED STATES OF AMERICA");

  for (const [name, file] of [[/Excel workbook/, /schedules\.xlsx$/], [/CSV files/, /schedules\.zip$/], [/PDF pack for your CA/, /CA-pack\.pdf$/]] as const) {
    const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name }).click()]);
    expect(dl.suggestedFilename()).toMatch(file);
  }
  await expect(page.getByRole("list", { name: "Sources" })).toContainText("Your file trades.csv");
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("ITR-ready export and US stocks tax: in the Money menu", async ({ page }, info) => {
  const n = info.project.name === "phone" ? 290 : 287;
  const errors = await open(page, "/money/tax-tools", "Dividends, advance tax", n);
  if (info.project.name === "phone") await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "ITR-ready export" }).click();
  await expect(page).toHaveURL(/\/money\/itr$/);
  await expect(page.getByRole("heading", { name: "Your year, laid out for the return" })).toBeVisible();
  if (info.project.name === "phone") await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "US stocks tax" }).click();
  await expect(page).toHaveURL(/\/money\/us-tax$/);
  await expect(page.getByRole("heading", { name: "US stocks in Indian tax" })).toBeVisible();
  expect(errors).toEqual([]);
});
