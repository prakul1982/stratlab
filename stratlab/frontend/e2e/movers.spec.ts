import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { serious } from "./a11y-kit";
import { open, sane, session, sessionAs } from "./pages-kit";

// Market movers and the data status page, on desktop and phone against the fake world: the daily breadth run there stores each
// stock's day and its 52-week marks, so the lists are real. A paid account gets every list in full, the filters and the CSV; Free gets the
// top 5 of the default index with the plan that has the rest; a row opens its company; the public movers and data status pages (API
// pages, as on the site) read without signing in; light and dark, and axe finds nothing serious.
const SHOTS = process.env.E2E_SHOTS;
const ADVICE = /\b(buy|sell|hold|accumulate|avoid|cheap|expensive|bullish|bearish|should)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|nseindia/i;
const FREE = sessionAs("free-token", "u-free", "free@example.com");

const table = (page: Page) => page.getByTestId("movers").locator("table");
const list = (page: Page, name: string) => page.getByTestId("movers").getByRole("button", { name, exact: true });

test("the movers list every list of a market in full, with filters, the CSV and links to each company", async ({ page }) => {
  const errors = await open(page, "/invest/movers?region=IN", "Closes of");
  await expect(page.getByRole("heading", { level: 1, name: "Movers" })).toBeVisible();
  await expect(page.getByTestId("movers").getByRole("heading", { name: "NIFTY 500: gainers" })).toBeVisible();
  await expect(page.getByTestId("mv-facts")).toContainText(/Closes of \d+ \w+ \d{4}/);
  await expect(table(page).locator("tbody tr").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Download CSV: NIFTY 500: Gainers/ })).toBeVisible();
  await expect(page.locator(".plan-note")).toHaveCount(0);
  // each list in place: the heading and the address follow
  for (const [chip, heading] of [["Losers", "losers"], ["Most traded", "most traded"], ["Volume spikes", "volume spikes"], ["52-week highs", "52-week highs"], ["52-week lows", "52-week lows"]]) {
    await list(page, chip).click();
    await expect(page.getByTestId("movers").getByRole("heading", { name: `NIFTY 500: ${heading}` })).toBeVisible();
  }
  await expect(page).toHaveURL(/list=lows/);
  await list(page, "Most traded").click();
  // another group, from the paid filters
  await page.getByLabel("Stocks").selectOption({ label: "NIFTY 50" });
  await expect(page.getByTestId("movers").getByRole("heading", { name: "NIFTY 50: most traded" })).toBeVisible();
  await expect(page).toHaveURL(/u=nifty50/);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
  await sane(page, errors);
  // a row opens its company's page
  await table(page).locator("tbody tr").first().getByRole("link").first().click();
  await expect(page).toHaveURL(/\/research\/IN\/[A-Z0-9&-]+/);
});

test("Free sees the top 5 of the default index, no filters and no CSV, and which plan has the rest", async ({ page }) => {
  const errors = await open(page, "/invest/movers?region=IN&u=nifty50&min=5000", "Closes of", FREE);
  const note = page.locator(".plan-note");
  await expect(note).toContainText("top 5 of each list");
  await expect(note).toContainText("Basic plan");
  await expect(page.getByTestId("movers").getByRole("heading", { name: "NIFTY 500: gainers" })).toBeVisible();     // the default index, whatever was asked
  expect(await table(page).locator("tbody tr").count()).toBeLessThanOrEqual(5);
  await expect(page.getByLabel("Stocks")).toBeDisabled();
  await expect(page.getByLabel("Smallest market value")).toBeDisabled();
  await expect(page.getByRole("button", { name: /^Download CSV/ })).toHaveCount(0);
  await sane(page, errors);
});

test("the public movers and data status pages read without signing in, and link each other", async ({ page }) => {
  await page.goto("/stocks/in/movers");
  await expect(page.getByRole("heading", { level: 1, name: "India market movers" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Gainers" })).toBeVisible();
  await expect(page.getByText("on the Basic plan", { exact: false })).toBeVisible();
  const pub = await page.locator("main").innerText();
  expect(pub).not.toMatch(PROVIDERS);
  expect(pub).not.toMatch(ADVICE);
  await page.goto("/status");
  await expect(page.getByRole("heading", { level: 1, name: "Data status" })).toBeVisible();
  await expect(page.locator('tr[data-id="closes-in"]')).toContainText("India closing prices");
  await expect(page.locator('tr[data-id="closes-in"]')).toContainText(/IST/);
  await expect(page.locator('tr[data-id="closes-us"]')).toContainText(/ET|Not yet/);
  const status = await page.locator("main").innerText();
  expect(status).not.toMatch(PROVIDERS);
  expect(status).not.toMatch(/railway|error|exception/i);
  await expect(page.locator("footer").getByRole("link", { name: "Data status" })).toBeVisible();
});

test("the movers and the data status page in light and dark: axe finds nothing serious", async ({ browser }, info) => {
  test.setTimeout(180_000);
  const phone = info.project.name === "phone";
  const found: string[] = [];
  for (const scheme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ colorScheme: scheme, viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 1000 }, hasTouch: phone, isMobile: phone });
    const page = await ctx.newPage();
    await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
    const errors = await open(page, "/invest/movers?region=US", "Closes of");
    await expect(table(page).locator("tbody tr").first()).toBeVisible();
    await sane(page, errors);
    const width = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(width, "no sideways scroll").toBeLessThanOrEqual(1);
    let r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]).analyze();
    found.push(...serious(r, `/invest/movers [${scheme} ${info.project.name}]`));
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/movers-${scheme}-${info.project.name}.png`, fullPage: true });
    for (const path of ["/status", "/stocks/in/movers"]) {
      await page.goto(path);
      await expect(page.locator("h1")).toBeVisible();
      const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(over, `${path}: no sideways scroll`).toBeLessThanOrEqual(1);
      r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      found.push(...serious(r, `${path} [${scheme} ${info.project.name}]`));
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${path.replace(/\//g, "_")}-${scheme}-${info.project.name}.png`, fullPage: true });
    }
    await ctx.close();
  }
  expect(found, found.join("\n")).toEqual([]);
});
