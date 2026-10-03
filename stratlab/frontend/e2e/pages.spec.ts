import { expect, test, type Page } from "@playwright/test";

// Signed in as the site owner (the fake database's admin-token), with the tour already seen.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string, ready: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.continue() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
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
  ["/research/scan", "Stage 2"], ["/alerts", "Your stock alerts"], ["/research/watchlist", "Companies you're watching"], ["/research/rotation", "rotation"], ["/research/investor", "Investor"], ["/news", "News"], ["/plans", "Plans"],
  ["/account", "Account"], ["/admin", "Needs your attention"], ["/admin?tab=services", "Market data"], ["/admin?tab=checks", "Check every feature"],
  ["/admin?tab=users", "Paper trading now"], ["/admin?tab=billing", "Launch offer"],
];

for (const [path, ready] of PAGES) {
  test(`page ${path}`, async ({ page }, info) => {
    await sane(page, await open(page, path, ready));
    if (info.project.name === "phone") await touchable(page);
  });
}

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
