import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// The per-stock desks on desktop and phone: stock futures (a Positioning tab), stock lending fees and margin funding
// (with the MTF cost calculator). The fake world's exchange files are made up (backend/tests/fake_stock_desks.py):
// RELIANCE's futures rise with open interest every day (a long buildup), AMBUJACEM is over 95% of its MWPL (F&O ban),
// RELIANCE lends every day and TCS never does, and every stock has margin funding. Each test signs in as its own user.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const HOLDINGS = new URL("../../backend/tests/fixtures/holdings/zerodha_kite_holdings.csv", import.meta.url).pathname;
const ADVICE = /\b(bullish|bearish|accumulate|avoid|cheap|expensive|overvalued|undervalued|risky|overleveraged|recommend\w*|you can earn)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|nseindia|nsearchives/i;
const SHOTS = process.env.E2E_SHOTS;

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

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

async function mine(request: APIRequestContext, n: number) {
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.post(`${API}/holdings/import`, { headers: auth,
    data: { filename: "zerodha_kite_holdings.csv", data: readFileSync(HOLDINGS).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/research/watchlist`, { headers: auth,
    data: { items: [{ region: "IN", symbol: "RELIANCE" }, { region: "IN", symbol: "TCS" }] } })).ok()).toBeTruthy();
}

test("stock futures: every F&O stock's buildup, rollover, basis and MWPL use, and one stock's history", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/trade/positioning/stocks", "trading days stored", phone ? 286 : 283);
  const table = page.getByRole("table", { name: "Stock futures by stock" });
  const rows = table.locator("tbody tr");
  await expect(rows).toHaveCount(9);
  await expect(rows.first()).toHaveAttribute("data-stock", "AMBUJACEM");                 // alphabetical: no ranking
  await expect(table.locator("tr[data-stock=RELIANCE]")).toContainText("Long buildup");
  await expect(table.locator("tr[data-stock=AMBUJACEM]")).toContainText("F&O ban");
  await expect(page.getByRole("radiogroup", { name: "Positioning view" }).getByRole("radio", { name: "Index and participants" })).toBeVisible();
  await expect(page.getByTestId("sf-status")).toContainText("trading days stored");

  await page.getByRole("group", { name: "Show" }).getByRole("button", { name: /^MWPL 80%\+/ }).click();
  await expect(table.locator("tr[data-stock=SAIL], tr[data-stock=AMBUJACEM]")).not.toHaveCount(0);
  await expect(table.locator("tr[data-stock=RELIANCE]")).toHaveCount(0);
  await page.getByRole("group", { name: "Show" }).getByRole("button", { name: /^All/ }).click();
  await page.getByLabel("Sort by").selectOption("m");
  await expect(rows.first()).toHaveAttribute("data-stock", "AMBUJACEM");

  await table.getByRole("link", { name: "RELIANCE" }).click();
  await expect(page).toHaveURL(/s=RELIANCE/);
  const panel = page.locator("#sf-detail");
  await expect(panel.getByRole("heading", { name: "RELIANCE futures" })).toBeVisible();
  await expect(panel.getByText(/long buildup, \d+ stored days in a row/)).toBeVisible();
  await expect(panel.getByRole("img", { name: /RELIANCE futures open interest by day/ })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/stock-futures-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
  await page.getByRole("radiogroup", { name: "Positioning view" }).getByRole("radio", { name: "Index and participants" }).click();
  await expect(page).toHaveURL(/\/trade\/positioning$/);
});

test("stock lending fees: your holdings and watchlist, and one stock day by day", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 292 : 289;
  await mine(request, n);
  const errors = await open(page, "/invest/stock-lending", "Days with trades", n);
  const table = page.getByRole("table", { name: "Lending fees for your stocks" });
  await expect(table.locator("tr[data-stock=SBIN]")).toContainText("You hold it");
  await expect(table.locator("tr[data-stock=RELIANCE]")).toContainText("Watchlist");
  await expect(table.locator("tr[data-stock=TCS]")).toContainText("None in 90 days");
  await expect(table.locator("tr[data-stock=WIPRO]")).toContainText("Eligible");
  await expect(page.getByRole("heading", { name: "How lending works" })).toBeVisible();
  await table.getByRole("link", { name: "RELIANCE" }).click();
  const one = page.locator("#slb-one");
  await expect(one.getByRole("heading", { name: "RELIANCE: lending fees that traded" })).toBeVisible();
  await expect(one.getByRole("table", { name: "RELIANCE lending in the last 30 days" })).toBeVisible();
  await page.getByLabel("Look up a stock").fill("tcs");
  await page.getByRole("button", { name: "Show fees" }).click();
  await expect(page.locator("#slb-one").getByText("No lending traded in TCS in the last 90 days.")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/stock-lending-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
});

test("margin funding: the market's book, your stocks, one stock and your own MTF cost", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 298 : 295;
  await mine(request, n);
  const errors = await open(page, "/invest/margin-funding", "The market's MTF book", n);
  await expect(page.getByRole("heading", { name: "Margin funding", level: 1 })).toBeVisible();
  await expect(page.getByText(/Data up to/)).toBeVisible();
  await expect(page.getByText(/^Funded on \d/).first()).toBeVisible();
  await expect(page.locator("main")).not.toContainText(/crore\b/);        // Indian units: lakh cr and cr, never "crore" spelled out or "k cr"
  const table = page.getByRole("table", { name: "Margin funding for your stocks" });
  await expect(table.locator("tr[data-stock=SBIN]")).toContainText("1.20%");
  await expect(table.locator("tr[data-stock=GOLDBEES]")).toContainText("No margin funding");
  await table.getByRole("link", { name: "RELIANCE" }).click();
  const one = page.locator("#mtf-one");
  await expect(one.getByRole("heading", { name: "RELIANCE: margin funded" })).toBeVisible();
  await expect(one.getByText(/^Funded on \d/)).toBeVisible();
  await expect(one.getByText(/of shares issued/).first()).toBeVisible();

  const calc = page.locator("#mtf-cost");
  await calc.getByRole("textbox", { name: /^Buy price/ }).fill("1000");
  await calc.getByRole("textbox", { name: /^Shares/ }).fill("100");
  await calc.getByRole("textbox", { name: /^Days held/ }).fill("60");
  await calc.getByRole("textbox", { name: /^Price now/ }).fill("1100");
  await calc.getByRole("textbox", { name: /^Margin to keep/ }).fill("20");
  await calc.getByRole("button", { name: "Work it out" }).click();
  const out = page.getByTestId("mtf-cost-out");
  await expect(out).toContainText("₹75,000");                 // 75% of ₹1,00,000 funded
  await expect(out).toContainText("₹1,849.32");               // ₹75,000 × 15% × 60/365
  await expect(out).toContainText("₹1,018.49");               // the price that covers the interest
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/margin-funding-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
});
