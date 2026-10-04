import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Signed in as the site owner (the fake database's admin-token), with the tour already seen.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

/** Signed in as another of the fake database's users instead (free-token, basic-token, ...). */
function sessionAs(token: string, id: string, email: string) {
  return { ...session, access_token: token, user: { ...session.user, id, email } };
}

async function open(page: Page, path: string, ready: string, who: typeof session = session) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    // fallback: a test's own route for a backend call (registered before this) still gets its turn
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(path);
  // a first visit asks what the person came for; answer it like a new user would
  const ask = page.getByText("What brings you to StratLab?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /Both/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

/** What every page must get right: no crash, nothing wider than the screen, no broken numbers. */
async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  await expect(page.getByText(/couldn't load your account|can't reach the StratLab server/i), "the page couldn't reach the server").toHaveCount(0);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\b0k\b/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
}

/** On a phone: every button, menu and stand-alone link is big enough for a finger (small icons that carry a larger
 * invisible touch area are left out). */
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

/** Bars for gains end at the zero line from above; bars for losses start at it and hang below. */
async function barsAroundZero(page: Page) {
  const charts = page.locator(".tbars");
  expect(await charts.count()).toBeGreaterThan(0);
  let losses = 0;
  for (const chart of await charts.all()) {
    if (!(await chart.locator(".tbar-zero").count())) continue;        // no losses in this chart: no zero line drawn
    const zero = await chart.locator(".tbar-zero").first().boundingBox();
    for (const bar of await chart.locator(".tbar-bar").all()) {
      const v = Number(await bar.getAttribute("data-v"));
      const b = await bar.boundingBox();
      if (!b || !zero) continue;
      if (v < 0) { losses++; expect(Math.abs(b.y - zero.y), "a loss bar starts at the zero line").toBeLessThan(2); }
      else expect(Math.abs(b.y + b.height - zero.y), "a gain bar ends at the zero line").toBeLessThan(2);
    }
  }
  expect(losses, "loss years are drawn").toBeGreaterThan(0);
}

const PAGES: [string, string][] = [
  ["/", "notebook"], ["/notebooks", "notebook"], ["/library", "librar"], ["/options", "Options"], ["/paper", "Paper"],
  ["/research", "Companies"], ["/research/IN/RELIANCE", "Reliance"], ["/research/US/AAPL", "AAPL"], ["/research/IN/RELIANCE/deep", "Growth and margins"],
  ["/research/scan", "Stage 2"], ["/research/screens", "Filter companies by plain facts"], ["/alerts", "Your stock alerts"], ["/research/watchlist", "Companies you're watching"], ["/research/rotation", "rotation"], ["/research/results", "Results this week and next"], ["/research/corporate-actions", "Dividends, bonuses and splits"], ["/research/investor", "Investor"], ["/holdings", "By sector"], ["/tax-report", "How FY"], ["/news", "News"], ["/plans", "Plans"],
  ["/account", "Account"], ["/admin", "Needs your attention"], ["/admin?tab=services", "Market data"], ["/admin?tab=checks", "Check every feature"],
  ["/admin?tab=users", "Paper trading now"], ["/admin?tab=billing", "Launch offer"],
];

for (const [path, ready] of PAGES) {
  test(`page ${path}`, async ({ page }, info) => {
    await sane(page, await open(page, path, ready));
    if (info.project.name === "phone") await touchable(page);
  });
}

test("results calendar: every company's dates, and the company page links to it", async ({ page }, info) => {
  await sane(page, await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called"));
  await expect(page.getByRole("link", { name: "RELIANCE" }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Financial Results").first()).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await expect(page.getByRole("link", { name: "RELIANCE" }).first()).toHaveAttribute("href", "/research/IN/RELIANCE");
  await page.goto("/research/IN/RELIANCE");
  await expect(page.getByRole("link", { name: /^Results on / })).toBeVisible({ timeout: 30_000 });
});

test("losses hang below the zero line, with exact labels (company page)", async ({ page }) => {
  const errors = await open(page, "/research/IN/TCS", "Sales and profit, by year");
  await barsAroundZero(page);
  await expect(page.getByText("-133").first()).toBeVisible();
  await expect(page.getByText("loss years in between, so no yearly rate").first()).toBeVisible();
  await sane(page, errors);
});

test("losses hang below the zero line (deep dive)", async ({ page }) => {
  const errors = await open(page, "/research/IN/TCS/deep", "Growth and margins");
  await barsAroundZero(page);
  await expect(page.getByText("A loss year in the period, so no yearly rate").first()).toBeVisible();
  await sane(page, errors);
});

test("a US deep dive is in dollars, from the SEC's filings", async ({ page }) => {
  const errors = await open(page, "/research/US/AAPL/deep", "Growth and margins");
  await expect(page.getByText("$ billion").first()).toBeVisible();          // a company this size reads in billions
  expect(await page.locator("main").innerText()).not.toMatch(/\d{3},\d{3} million/);
  await expect(page.getByText("Read the annual report and releases")).toBeVisible();
  await expect(page.getByText("Check past releases")).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/₹|crore/);
  await sane(page, errors);
});

// Public company pages are plain HTML from the API (the site's host forwards /stocks/* there), for search engines.
for (const [path, name, symbol] of [["/stocks/in/RELIANCE", "Reliance Industries", "RELIANCE"], ["/stocks/us/AAPL", "Apple Inc.", "AAPL"]]) {
  test(`public company page ${path}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(API + path);
    await expect(page.locator("h1")).toContainText(name);
    await expect(page.getByRole("link", { name: `Test a strategy on ${symbol}` })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open the full deep dive" })).toBeVisible();
    await expect(page.getByText(/As of \d+ \w+ \d{4}/).first()).toBeVisible();
    expect(errors).toEqual([]);
    const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
    expect(await page.locator("main").innerText()).not.toMatch(/\bNaN\b|\bundefined\b|\bnull\b|Infinity/);
    if (info.project.name === "phone") await touchable(page);
  });
}

test("a company page's test link opens a new test on that company", async ({ page }) => {
  const errors = await open(page, "/new?market=IN&symbol=RELIANCE", "testing a strategy on RELIANCE");
  await sane(page, errors);
});

test.describe("a visitor from the UK", () => {
  test.use({ locale: "en-GB", timezoneId: "Europe/London" });
  test("sees prices in pounds", async ({ page }) => {
    const errors = await open(page, "/plans", "Plans");
    await expect(page.getByText(/£\d+/).first()).toBeVisible();
    await sane(page, errors);
  });
});

test.describe("a visitor in India", () => {
  test.use({ locale: "en-US", timezoneId: "Asia/Kolkata" });
  test("sees prices in rupees", async ({ page }) => {
    const errors = await open(page, "/plans", "Plans");
    await expect(page.getByText("₹999").first()).toBeVisible();
    await sane(page, errors);
  });
});

test("invoices: in Account for the customer, with the GST setup in Admin", async ({ page }) => {
  let errors = await open(page, "/account", "Invoices");
  await expect(page.getByText("Details on your invoices")).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/admin?tab=billing", "LUT ARN");
  await expect(page.getByText(/Financial year \d{4}-\d{2}/)).toBeVisible();
  await sane(page, errors);
});

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";     // the fake backend (tests/visual_server.py)

test("first steps on Home tick themselves from real data, and hide for good", async ({ page, request }, info) => {
  // each project signs in as its own brand-new user, so hiding the list on one doesn't hide it on the other
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["free-token", "u-free", "free@example.com"];
  const auth = { Authorization: `Bearer ${token}` };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });     // skip the welcome questions
  expect((await request.put(`${API}/me/first-steps`, { headers: auth, data: { dismissed: false } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/research/watchlist`, { headers: auth, data: { items: [{ region: "IN", symbol: "TCS" }] } })).ok()).toBeTruthy();
  const errors = await open(page, "/", "Your first steps", sessionAs(token, id, email));
  const list = page.locator(".first-steps");
  await expect(list.locator("li")).toHaveCount(5);
  await expect(list.locator('[data-step="watchlist"]')).toHaveClass(/done/);
  await expect(list.locator('[data-step="backtest"] a')).toHaveAttribute("href", "/new");
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  expect((await request.get(`${API}/research/deep/RELIANCE?region=IN`, { headers: auth })).ok()).toBeTruthy();
  await page.reload();
  await expect(list.locator('[data-step="deepdive"]')).toHaveClass(/done/, { timeout: 30_000 });
  await expect(page.getByText(/\d of 5 done/)).toBeVisible();

  await list.getByRole("button", { name: "Hide this" }).click();
  await expect(page.getByText("Your first steps")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("notebook", { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  await expect(page.getByText("Your first steps")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("the launch offer counts down on Home and Plans", async ({ page }, info) => {
  const until = new Date(Date.now() + (2 * 24 + 5) * 3600_000 + 10 * 60_000).toISOString();
  await page.route(`${API}/me`, async (r) => {
    const res = await r.fetch();
    await r.fulfill({ response: res, json: { ...(await res.json()), promo: { until } } });
  });
  let errors = await open(page, "/", "Launch offer:");
  await expect(page.locator(".promo-countdown")).toContainText("2 days 5 hours");
  await expect(page.getByText("Launch offer:")).toHaveCount(1);              // the countdown replaces the site-wide note here
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  errors = await open(page, "/plans", "Launch offer:");
  await expect(page.locator(".promo-countdown")).toContainText("2 days 5 hours");
  await sane(page, errors);
});

const HOLDINGS_FILES = new URL("../../backend/tests/fixtures/holdings/", import.meta.url).pathname;

/** The first-visit questions stay open over the page until answered; these tests click on the page, so answer them. */
async function settle(page: Page) {
  const level = page.getByRole("dialog", { name: /How much .* have you done/ });
  await level.waitFor({ timeout: 4000 }).then(() => level.getByRole("button", { name: /done a bit/ }).click()).catch(() => undefined);
  await expect(level).toHaveCount(0);
}

test("my holdings: positions, sectors and facts per stock, then a broker file added", async ({ page, request }, info) => {
  // start from the owner's Zerodha file again: the other project's run of this test added a Groww file to the shared account
  const zerodha = "zerodha_console_holdings.xlsx";
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: "Bearer admin-token" },
    data: { filename: zerodha, data: readFileSync(HOLDINGS_FILES + zerodha).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "By sector");
  await settle(page);
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.getByText("RELIANCE", { exact: true })).toBeVisible();
  await expect(table.getByText("TINYCO", { exact: true })).toBeVisible();            // listed only on BSE
  await expect(page.getByText(/your Zerodha Console file/)).toBeVisible();
  await expect(table.getByText(/red flag/).first()).toBeVisible({ timeout: 30_000 });  // the QIP filing, once the facts arrive
  await expect(table.getByText(/Stage \d/).first()).toBeVisible();
  await expect(page.getByText("Recent filings")).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/\b(buy|sell|accumulate|avoid)\b/i);
  await page.getByRole("radio", { name: "Add to them" }).click();
  await page.locator("input[type=file]").setInputFiles(HOLDINGS_FILES + "groww_holdings_statement.xlsx");
  await expect(page.getByText("Read as a Groww file")).toBeVisible({ timeout: 30_000 });   // matching a first file reads the stock lists
  const missed = page.getByRole("table", { name: "Lines that couldn't be matched" });
  await expect(missed.getByText(/INE000X01000/)).toBeVisible();
  await expect(table.getByText("INFY", { exact: true })).toBeVisible();
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});

test("my holdings: edit by hand and delete them all", async ({ page }, info) => {
  const errors = await open(page, "/holdings", "By sector");
  await settle(page);
  await page.getByRole("button", { name: "Edit RELIANCE" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit RELIANCE" });
  await expect(dialog.getByRole("button", { name: "Save" })).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Close" }).click();
  // the delete is answered here, so the shared fake account keeps its holdings for the other tests
  const empty = { rows: [], allocation: [], totals: { value: 0, invested: 0, pnl: null, pnl_pct: null, day: null, day_pct: null, count: 0, priced: 0 },
    source: null, updated_at: null, prices: true, limit: 300, facts_max: 40 };
  await page.route("**/holdings", (r) => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify(r.request().method() === "DELETE" ? { deleted: true } : empty) }));
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete my holdings" }).click();
  await expect(page.getByText("No holdings yet")).toBeVisible();
  await expect(page.getByText("Your holdings are deleted.")).toBeVisible();
  await sane(page, errors);
});

const TRADEBOOKS = new URL("../../backend/tests/fixtures/tradebooks/", import.meta.url).pathname;

test("tax report: tradebooks from several brokers, one year's gains, lots below cost, downloads and delete", async ({ page, request }, info) => {
  // each project signs in as its own user and starts with no trades, so the two runs don't share tax data
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  expect((await request.delete(`${API}/tax`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/tax-report", "Capital gains on your shares", sessionAs(token, id, email));
  await settle(page);
  await expect(page.getByText("No trades yet")).toBeVisible();
  await expect(page.getByText(/not tax advice/).first()).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // three files, two brokers, one pick: the last one's result is shown, with the line it left out
  await page.locator("input[type=file]").setInputFiles(["upstox_tradebook.csv", "zerodha_tax_pnl.xlsx", "zerodha_console_tradebook.csv"].map((f) => TRADEBOOKS + f));
  await expect(page.getByText(/Read as a Zerodha Console tradebook/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("table", { name: "Lines left out" }).getByText(/Futures, options/)).toBeVisible();
  await expect(page.getByText(/15 trades from 3 files/)).toBeVisible();

  await page.getByRole("combobox", { name: "Financial year" }).selectOption("2024");
  await expect(page.getByRole("heading", { name: "How FY 2024-25 adds up" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Gains by rate" }).getByText("Long-term, sold from 23 Jul 2024")).toBeVisible();
  await expect(page.getByText("1 same-day round trip", { exact: false })).toBeVisible();          // INFY, kept apart
  const sales = page.getByRole("table", { name: "Realised sales" });
  await expect(sales.getByText("RELIANCE").first()).toBeVisible();
  await expect(sales.getByText("grandfathered")).toBeVisible();                                   // WIPRO, from the tax P&L
  await expect(page.getByRole("table", { name: "Open lots below cost" }).getByText("TCS")).toBeVisible();
  await expect(page.getByText("Shares held on 31 Jan 2018")).toBeVisible();
  await page.getByRole("button", { name: "What is tax-loss harvesting?" }).click();
  await expect(page.getByRole("note").filter({ hasText: "wash-sale" })).toBeVisible();

  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/you should|we suggest|consider selling|sell now|recommend/i);
  expect(text).not.toMatch(/yahoo|finnhub|kite|screener/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await csv).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.csv");
  const pdf = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF summary" }).click();
  expect((await pdf).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.pdf");

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete my tax data" }).click();
  await expect(page.getByText("Your tax data is deleted.")).toBeVisible();
  await expect(page.getByText("No trades yet")).toBeVisible();
});

test("tax report: a file that isn't a tradebook gets a plain answer", async ({ page }) => {
  const errors = await open(page, "/tax-report", "Capital gains on your shares");
  await settle(page);
  await page.locator("input[type=file]").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  await expect(page.getByText(/looks like a holdings file/)).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);
});

/** The experience question that follows the first one covers the page; answer it before clicking anything. */
async function answerLevel(page: Page) {
  const ask = page.getByText(/How much (trading|investing) have you done\?/);
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /done a bit/ }).click()).catch(() => undefined);
  await expect(ask).toHaveCount(0);
}

test("alerts: set one on a company page, then edit and delete it on the Alerts page", async ({ page }, info) => {
  const tag = `e2e ${info.project.name} ${Date.now()}`;             // both projects share the fake database
  let errors = await open(page, "/research/IN/RELIANCE", "Reliance");
  await answerLevel(page);
  await page.getByRole("button", { name: "Set alert" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Alert on RELIANCE" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Price level (₹)").fill("1");
  await dialog.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Set alert" }).click();
  await expect(page.getByText(/already above ₹1/).first()).toBeVisible();   // the price is far above: it waits for a cross
  await sane(page, errors);

  errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Price crosses above ₹1");
  if (info.project.name === "phone") await touchable(page);
  await row.getByRole("button", { name: /Edit/ }).click();
  const edit = page.getByRole("dialog", { name: "Edit alert on RELIANCE" });
  await edit.getByLabel("Alert me when").selectOption("ma_below");
  await edit.getByLabel("Moving average", { exact: true }).selectOption("200");
  await edit.getByRole("button", { name: "Save alert" }).click();
  await expect(row).toContainText("Price crosses below its 200-day average");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await sane(page, errors);
});

test("alerts: a new one from the Alerts page, for any stock", async ({ page }, info) => {
  const tag = `e2e-new ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("TCS");
  await page.getByLabel("Alert me when").selectOption("move_either");
  await page.getByLabel("Move in a day (%)").fill("4");
  await page.getByLabel("Note for yourself (optional)").fill(tag);
  await page.getByLabel(/Repeat/).check();
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Moves 4% or more either way in a day");
  await expect(row).toContainText("Repeats");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await sane(page, errors);
});

test("alerts: Set alert on the watchlist offers its stocks", async ({ page }, info) => {
  const tag = `e2e-watch ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/research/watchlist?region=IN", "Companies you're watching");
  await answerLevel(page);
  // a watchlist of one, without changing the shared one other tests read
  await page.route("**/research/watchlist", (r) => r.request().method() === "GET"
    ? r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ region: "IN", symbol: "RELIANCE", name: "Reliance Industries" }] }) })
    : r.fallback());
  await page.reload();
  await page.getByRole("button", { name: "Set alert" }).click();
  const dialog = page.getByRole("dialog", { name: "Set an alert" });
  await expect(dialog.getByLabel("Stock")).toHaveValue("IN:RELIANCE");
  await dialog.getByLabel("Alert me when", { exact: true }).selectOption("high52");
  await dialog.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Set alert" }).click();
  await expect(page.getByText("Alert set on RELIANCE.")).toBeVisible();
  await sane(page, errors);
  await open(page, "/alerts", "Your stock alerts");
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Makes a new 52-week high");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
});

test("the tools grid shows one group until asked, and the menu reaches Account without scrolling", async ({ page }, info) => {
  const errors = await open(page, "/new", "What trading idea do you want to test?");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 4000 }).catch(() => undefined);   // the experience question
  await expect(page.getByRole("button", { name: "Paper trade options" })).toHaveCount(0);
  await page.getByRole("button", { name: /Show \d+ more tools/ }).click();
  await expect(page.getByRole("button", { name: "Paper trade options" })).toBeVisible();
  if (info.project.name === "desktop") await expect(page.getByRole("link", { name: /^Account/ })).toBeInViewport();
  await sane(page, errors);
});

// ---------- sharing: company fact cards and invite links ----------
/** Watch what the page shares: the phone's share sheet (stubbed, as headless browsers have none) and the clipboard. */
async function watchSharing(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __shared: unknown[]; __copied: string[] };
    w.__shared = []; w.__copied = [];
    Object.defineProperty(navigator, "share", { configurable: true, value: async (d: { url?: string; text?: string; files?: File[] }) => {
      w.__shared.push({ url: d.url, text: d.text, files: (d.files ?? []).map((f) => ({ name: f.name, type: f.type, size: f.size })) });
    } });
    Object.defineProperty(navigator, "canShare", { configurable: true, value: () => true });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (t: string) => { w.__copied.push(t); }, write: async () => undefined } });
  });
}

type SharedCall = { url: string; files: { type: string; size: number }[] };
const shared = (page: Page) => page.evaluate(() => (window as unknown as { __shared: SharedCall[] }).__shared);
const copied = (page: Page) => page.evaluate(() => (window as unknown as { __copied: string[] }).__copied);

/** Phone: the share sheet got the card's link and image. Desktop: the link was copied. Returns the link. */
async function sharedLink(page: Page, phone: boolean): Promise<string> {
  if (phone) {
    await expect.poll(async () => (await shared(page)).length, { timeout: 30_000 }).toBeGreaterThan(0);
    const s = (await shared(page))[0];
    expect(s.files[0]?.type, "the card image goes with the link").toBe("image/png");
    expect(s.files[0].size).toBeGreaterThan(5000);
    expect(await copied(page), "a phone uses its share sheet, not the clipboard").toEqual([]);
    return s.url;
  }
  await expect.poll(async () => (await copied(page)).length, { timeout: 30_000 }).toBeGreaterThan(0);
  await expect(page.getByRole("status")).toContainText("Link copied");
  await expect(page.getByRole("status").getByRole("button", { name: "Save the image" })).toBeVisible();
  expect(await shared(page), "a computer copies the link instead of a share sheet").toEqual([]);
  return (await copied(page))[0];
}

for (const [path, ready] of [["/research/IN/RELIANCE", "Reliance"], ["/research/US/AAPL/deep", "Growth and margins"]]) {
  test(`share a company's fact card from ${path}`, async ({ page, request }, info) => {
    const phone = info.project.name === "phone";
    await watchSharing(page);
    const errors = await open(page, path, ready);
    await answerLevel(page);
    const button = page.getByRole("button", { name: "Share", exact: true });
    await expect(button).toBeVisible();
    if (phone) await touchable(page);
    await button.click();
    const link = await sharedLink(page, phone);
    const token = link.match(/\/c\/([A-Za-z0-9_-]+)$/)?.[1];
    expect(token, `a card link: ${link}`).toBeTruthy();
    // the public link previews as the card the browser drew, and opens the company's public page
    const preview = await (await request.get(`${API}/c/${token}`)).text();
    expect(preview).toContain('property="og:image"');
    expect(preview).toContain(`/c/${token}.png`);
    expect(preview).toMatch(/\/stocks\/(in\/RELIANCE|us\/AAPL)\?ref=[A-Za-z0-9_-]{12}/);
    expect(preview).toContain("Facts, not advice");
    expect(preview).not.toMatch(/kite|zerodha|yahoo|screener|finnhub/i);
    const png = await request.get(`${API}/c/${token}.png`);
    expect(png.status()).toBe(200);
    expect((await png.body()).subarray(0, 4).toString("latin1")).toBe("\x89PNG");
    await sane(page, errors);
  });
}

test("account: your invite link, how many friends joined, and sharing it", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await watchSharing(page);
  const errors = await open(page, "/account", "Invite friends");
  await expect(page.getByTestId("friends-joined")).toHaveText(/^3 friends joined · 1 free month earned$/);
  await expect(page.getByTestId("invite-reward-line")).toHaveText(/you both get a month of Basic free \(up to 12 months for you\)/);
  await expect(page.getByLabel("Your invite link")).toHaveValue(/\/\?ref=[A-Za-z0-9_-]{12}$/);
  if (phone) await touchable(page);
  await page.getByRole("button", { name: "Share your link" }).click();
  const link = await page.getByLabel("Your invite link").inputValue();
  if (phone) await expect.poll(async () => (await shared(page)).map((s) => s.url)).toEqual([link]);
  else {
    await expect.poll(() => copied(page)).toEqual([link]);
    await expect(page.getByRole("status")).toContainText("Invite link copied");
  }
  await sane(page, errors);
});

test("an invite link is remembered through sign-in, sent once, and taken out of the address", async ({ page }) => {
  const sent: unknown[] = [];
  await page.route("**/me/referral", async (r) => { sent.push(r.request().postDataJSON()); await r.fulfill({ status: 200, contentType: "application/json", body: '{"recorded":false}' }); });
  const errors = await open(page, "/?ref=AbCdEf123_-x", "notebook");
  await expect.poll(() => sent).toEqual([{ code: "AbCdEf123_-x" }]);
  expect(new URL(page.url()).search).toBe("");
  await page.reload();
  await expect(page.getByText("notebook").first()).toBeVisible();
  await page.waitForTimeout(500);
  expect(sent, "sent only once").toHaveLength(1);
  await sane(page, errors);
});

test("admin: invite counts in the Users tab", async ({ page }, info) => {
  const errors = await open(page, "/admin?tab=users", "Paper trading now");
  await expect(page.getByRole("cell", { name: "Invited", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Free months", exact: true })).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("admin: invite rewards waiting for review are approved or rejected", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/admin?tab=users", "Invite rewards");
  const panel = page.getByTestId("invite-rewards");
  await expect(panel.getByText("Waiting for your review")).toBeVisible();
  await expect(panel.locator("tr", { hasText: "load3@example.com" })).toBeVisible();          // given
  if (phone) await touchable(page);
  // each run decides its own row: desktop rejects one, phone approves the other
  const row = panel.locator("tr", { hasText: phone ? "load2@example.com" : "load1@example.com" }).filter({ has: page.getByRole("button") });
  await row.getByRole("button", { name: phone ? "Approve" : "Reject" }).click();
  await expect(page.getByRole("status")).toContainText(phone ? "Approved" : "Rejected");
  await expect(row).toHaveCount(0);
  await sane(page, errors);
});

test("account: free Basic from invites shows on the plan", async ({ page }, info) => {
  const errors = await open(page, "/account", "Invite friends", sessionAs("load-3", "u-load-3", "load3@example.com"));
  await expect(page.getByText("Free Basic from invites")).toBeVisible();
  await expect(page.getByText("Basic (free from invites)")).toBeVisible();
  await expect(page.getByTestId("friends-joined")).toHaveText("0 friends joined · 1 free month earned");
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("screens: filter by plain facts, sort by a column, save one; no provider names", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const tag = `e2e screen ${info.project.name} ${Date.now()}`;          // both projects share the fake database
  const errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Prices as of 1 Oct 2026/)).toBeVisible();
  const table = page.locator(".screens-table");
  await expect(table.locator("tbody tr").first()).toContainText("Axisbank Ltd");          // alphabetical by default
  if (phone) await page.getByRole("button", { name: /Show filters/ }).click();
  await page.getByRole("button", { name: "Energy", exact: true }).click();
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: "What is Debt to equity?" }).click();
  await expect(page.getByRole("note")).toContainText("Borrowings divided by shareholders' equity");
  await page.getByLabel("P/E (price to earnings): at most").fill("abc");
  await expect(page.getByText("Enter a plain number, like 15 or -10.")).toBeVisible();
  await page.getByLabel("P/E (price to earnings): at most").fill("1");
  await expect(page.getByText("No company meets every condition.", { exact: false })).toBeVisible();
  await page.getByLabel("P/E (price to earnings): at most").fill("");
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await table.getByRole("button", { name: "P/E" }).click();                             // sort by a column the user picks
  await expect(table.locator("th[aria-sort=ascending]")).toContainText("P/E");
  await page.getByRole("button", { name: /Low to high/ }).click();
  await expect(table.locator("th[aria-sort=descending]")).toContainText("P/E");
  if (phone) await touchable(page);
  await page.getByLabel("Name").fill(tag);
  await page.getByLabel("Weekly email of new matches").check();
  await page.getByRole("button", { name: "Save screen" }).click();
  const saved = page.getByRole("button", { name: `${tag} · weekly` });
  await expect(saved).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible();
  await saved.click();                                                                  // a saved screen opens its conditions
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: `Delete ${tag}` }).click();
  await expect(page.getByRole("button", { name: `${tag} · weekly` })).toHaveCount(0);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub/i);
  expect(text).not.toMatch(/\b(buy|sell|undervalued|best stocks?|score)\b/i);
  await sane(page, errors);
});

test("as-of lines: the company page, deep dive and holdings say how fresh their numbers are", async ({ page }) => {
  let errors = await open(page, "/research/IN/RELIANCE", "Reliance");
  await expect(page.getByText(/Prices as of \d+ \w+ \d{4}, \d\d:\d\d/).first()).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
  await expect(page.getByText(/Reported numbers as of \d+ \w+ \d{4}/).first()).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/holdings", "By sector");
  await expect(page.getByText(/Prices as of \d+ \w+ \d{4}/).first()).toBeVisible();
  await sane(page, errors);
});

test("deals and insider trades: a dated table on the company page and the deep dive, facts only", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  let errors = await open(page, "/research/IN/RELIANCE", "Deals and insider trades");
  const panel = page.locator("#deals");
  const table = panel.locator(".deals-table");
  await expect(table).toContainText("Mukesh Shah Family Trust", { timeout: 30_000 });
  await expect(table).toContainText("Promoter");
  await expect(table).toContainText("25,000");
  await expect(table).toContainText("₹7.3 cr");
  await expect(panel).toContainText("1 person bought 25,000 shares");
  await expect(table.getByRole("link", { name: /Disclosure/ }).first()).toHaveAttribute("href", /^https:\/\//);
  await panel.getByRole("radio", { name: "Bulk and block deals" }).click();
  await expect(table).toContainText("Index Fund One");
  await expect(table).not.toContainText("Mukesh Shah Family Trust");
  const text = await panel.innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener|finnhub|nseindia/i);
  expect(text).not.toMatch(/\b(signal|smart money|buy|sell|accumulate|avoid)\b/i);
  if (phone) await touchable(page);
  await sane(page, errors);

  errors = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
  await expect(page.getByText("Promoter and insider buying and selling, 6 months").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".deals-table").first()).toContainText("Pension Plan Two");
  if (phone) await touchable(page);
  await sane(page, errors);
});

test("alerts: one on bulk or block deals, India only", async ({ page }, info) => {
  const tag = `e2e-deal ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("RELIANCE");
  await page.getByLabel("Alert me when").selectOption("deal");
  await expect(page.getByText("Checked once each evening against that day's exchange disclosures.", { exact: false })).toBeVisible();
  await page.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("A bulk or block deal is reported");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Market").selectOption("US");
  await expect(page.getByLabel("Alert me when").locator("option", { hasText: "bulk or block deal" })).toHaveCount(0);
  await sane(page, errors);
});

test("screens: promoter or insider bought in the last N days", async ({ page }, info) => {
  const errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  if (info.project.name === "phone") await page.getByRole("button", { name: /Show filters/ }).click();
  const group = page.getByRole("radiogroup", { name: "Promoter or insider bought" });
  await group.getByRole("radio", { name: "Yes" }).click();
  await expect(page.getByText(/5 of 20 companies match/)).toBeVisible();
  await page.getByLabel("Promoter or insider bought: in the last").selectOption("365");
  await expect(page.getByText(/10 of 20 companies match/)).toBeVisible();
  await group.getByRole("radio", { name: "No" }).click();
  await expect(page.getByText(/10 of 20 companies match/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "What is Promoter or insider bought?" }).click();
  await expect(page.getByRole("note")).toContainText("insider-trading disclosures");
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub/i);
  expect(text).not.toMatch(/\b(buy|sell|signal|score)\b/i);
  await sane(page, errors);
});

test("surveillance flags: badges with what each measure is on the company page, holdings and screens; facts only", async ({ page, request }, info) => {
  // the fake exchange: RELIANCE on long-term ASM Stage II, TATASTEEL short-term ASM Stage I, ITC GSM Stage II and T2T, INFY in the F&O ban
  let errors = await open(page, "/research/IN/RELIANCE", "Sales and profit, by year");
  await answerLevel(page);
  const flags = page.locator("[data-surveillance=RELIANCE]").first();
  await expect(flags.getByText("LT-ASM 2")).toBeVisible({ timeout: 30_000 });
  await flags.getByRole("button", { name: "What RELIANCE's exchange surveillance flags mean" }).click();
  const note = page.getByRole("note");
  await expect(note).toContainText("Stage 2: 100% margin");
  await expect(note).toContainText("List as of");
  const said = await note.innerText();
  expect(said).not.toMatch(/\b(buy|sell|avoid|risky|danger|warning)\b/i);
  expect(said).not.toMatch(/nseindia|kite|zerodha|yahoo|screener|finnhub/i);
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  errors = await open(page, "/holdings", "By sector");
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.locator("[data-surveillance=RELIANCE]").getByText("LT-ASM 2")).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);

  errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  if (info.project.name === "phone") await page.getByRole("button", { name: /Show filters/ }).click();
  await page.getByRole("radiogroup", { name: "Exchange surveillance" }).getByRole("radio", { name: "On a list" }).click();
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: "ASM (long or short term)", exact: true }).click();
  await expect(page.getByText(/2 of 20 companies match/)).toBeVisible();
  const rows = page.locator(".screens-table");
  await expect(rows.getByText("ST-ASM 1")).toBeVisible();
  await page.getByRole("radiogroup", { name: "Exchange surveillance" }).getByRole("radio", { name: "On none" }).click();
  await expect(page.getByText(/18 of 20 companies match/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  const pub = await (await request.get(`${API}/stocks/in/RELIANCE`)).text();
  expect(pub).toContain("Exchange surveillance");
  expect(pub).toContain("LT-ASM 2");
});

test("alerts: one on a stock entering or leaving a surveillance list, India only", async ({ page }, info) => {
  const tag = `e2e-surv ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts");
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("INFY");
  await page.getByLabel("Alert me when").selectOption("surveillance");
  await expect(page.getByText("Checked twice each trading day against the exchange's surveillance lists", { exact: false })).toBeVisible();
  await page.getByLabel("Note for yourself (optional)").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Enters or leaves an exchange surveillance list");
  await row.getByRole("button", { name: /Delete/ }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Market").selectOption("US");
  await expect(page.getByLabel("Alert me when").locator("option", { hasText: "surveillance list" })).toHaveCount(0);
  await sane(page, errors);
});

test("corporate actions: the calendar, a company's actions, and a bonus applied (and undone) in My Holdings", async ({ page, request }, info) => {
  // each project signs in as its own user, so the two runs don't adjust the same holdings at once
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  const csv = Buffer.from("Symbol,Quantity,Average price\nTCS,12,3520\nRELIANCE,50,2400\n").toString("base64");
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: `Bearer ${token}` },
    data: { filename: "holdings.csv", data: csv, mode: "replace" } })).ok()).toBeTruthy();
  const who = sessionAs(token, id, email);

  let errors = await open(page, "/research/corporate-actions?region=IN&scope=all", "Dividends, bonuses and splits", who);
  await settle(page);
  await expect(page.getByRole("link", { name: "TCS" }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Bonus 1:1 (1 new share for every 1 held)")).toBeVisible();
  await expect(page.getByText(/Interim dividend ₹11 a share/).first()).toBeVisible();
  await expect(page.getByText("Annual General Meeting")).toHaveCount(0);           // a meeting isn't an action
  await page.getByRole("combobox", { name: "Kind of action" }).selectOption("bonus");
  await expect(page.getByText(/Dividend - Rs|₹5.50 a share/)).toHaveCount(0);
  await expect(page.getByText("Bonus 1:1 (1 new share for every 1 held)")).toBeVisible();
  await page.getByRole("radio", { name: "My stocks" }).click();
  await expect(page.getByText("Bonus 1:1 (1 new share for every 1 held)")).toBeVisible();      // TCS is in the holdings
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  expect(await page.locator("main").innerText()).not.toMatch(/yahoo|finnhub|kite|screener/i);

  await page.goto("/research/IN/TCS");
  const panel = page.locator("#corporate-actions");
  await expect(panel.getByText(/Interim dividend ₹11 a share/)).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByText(/Final dividend ₹30 a share/)).toBeVisible();
  await expect(panel.getByText(/Dividends with an ex-date in the last 12 months/)).toBeVisible();

  errors = await open(page, "/holdings", "By sector", who);
  await settle(page);
  const notice = page.getByText(/TCS had a 1:1 bonus on .*: your quantity is now 24, average price ₹1,760/);
  await expect(notice).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Dividends" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Dividends ahead" }).getByText("TCS")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("TCS: quantity 24, average price ₹1,760.00.")).toBeVisible();
  const positions = page.getByRole("table", { name: "Positions" });
  await expect(positions.getByRole("row").filter({ hasText: "TCS" }).getByText("24", { exact: true })).toBeVisible();
  await expect(notice).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("TCS is back to 12 shares.")).toBeVisible();
  await expect(notice).toBeVisible();
  await sane(page, errors);
});

test("admin: the whole-market audit tells facts and companies not checked yet apart, and re-checks those", async ({ page }, info) => {
  const sent: object[] = [];
  const row = (symbol: string, name: string, level: string, area: string, detail: string) => ({ symbol, name, seconds: 1, issues: [{ level, area, detail }] });
  const refused = "Not checked yet: the exchange feed refused the request (403). It is checked again later.";
  const rows = [row("BSE:543210", "Tiny Co Ltd", "pending", "Documents", refused), row("BSE:543211", "Small Co Ltd", "pending", "Documents", refused),
    row("NEWCO", "New Co Ltd", "fact", "Numbers", "Only 2 years of annual results so far: listed, demerged or first reporting recently")];
  const summary = { companies: 3, clean: 1, mismatches: 0, gaps: 0, errors: 0, facts: 1, pending: 2, avg_seconds: 1, slowest: [],
    by_area: { Documents: { mismatch: 0, gap: 0, error: 0, fact: 0, pending: 2 }, Numbers: { mismatch: 0, gap: 0, error: 0, fact: 1, pending: 0 } } };
  const state = (retrying: boolean, india: boolean) => ({ enabled: true, listed: 3, checked: 3, due: retrying ? 2 : 0, current: null, eta_hours: null,
    list_at: null, list_error: null, new_listings: [], pending: india ? 2 : 0, rows: india ? rows : [], summary: india ? summary : { ...summary, companies: 0 },
    full: { running: retrying, since: retrying ? new Date().toISOString() : null, done_at: null, left: retrying ? 2 : 0, checked: null, pending_only: retrying } });
  let retrying = false;
  await page.route((u) => u.pathname === "/admin/audit/market", async (r) => {
    const req = r.request();
    const body = req.method() === "POST" ? req.postDataJSON() : null;
    if (body) { sent.push(body); retrying = true; }
    const india = body ? (body.region ?? "IN") === "IN" : new URL(req.url()).searchParams.get("region") !== "US";
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state(retrying && india, india)) });
  });
  const errors = await open(page, "/admin?tab=checks", "Whole market: India");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 3000 }).catch(() => undefined);   // asked once, if not yet
  const india = page.locator("section", { hasText: "Whole market: India" });
  await expect(india.getByText("1 facts · 2 not checked yet")).toBeVisible();
  await india.getByRole("radio", { name: "Facts" }).click();
  await expect(india.getByText("Only 2 years of annual results so far")).toBeVisible();
  await india.getByRole("radio", { name: "Not checked yet" }).click();
  await expect(india.getByText("Tiny Co Ltd")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await india.getByRole("button", { name: "Re-check 2 not checked yet" }).click();
  await expect.poll(() => sent).toEqual([{ region: "IN", retry: true }]);
  await expect(india.getByText("Re-checking companies not checked yet:")).toBeVisible();
  await sane(page, errors);
});
