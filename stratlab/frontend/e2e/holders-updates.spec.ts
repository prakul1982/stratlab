import { expect, test, type Page } from "@playwright/test";

// Business updates read into numbers, and named holders above 1%, on desktop and phone. The fake world
// (tests/visual_server.py) holds real shareholding samples (XPRO India, Safari and HDFC Bank, trimmed; Safari's list is
// also shown on RELIANCE's page), Maruti's and TVS Motor's real September 2026 sales updates read into figures, and a
// made-up year of monthly updates on RELIANCE. Each project signs in as its own fake Basic user.
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|superstar|smart money|beat|miss)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nseindia/i;
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

async function sane(page: Page, errors: string[], scope = "main") {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator(scope).first().innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

test("company page: business updates in numbers and the named holders", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/IN/RELIANCE", "Reliance", phone ? 280 : 277);
  const biz = page.locator("#business-updates");
  await biz.scrollIntoViewIfNeeded();
  await expect(biz.getByRole("heading", { name: "Business updates" })).toBeVisible({ timeout: 20_000 });
  await expect(biz.getByText("Total sales 1,26,000 units in Sep 2026: up 23.5% on Sep 2025.")).toBeVisible();
  const table = biz.getByRole("table", { name: "RELIANCE business update figures" });
  await expect(table.getByRole("row")).toHaveCount(3);
  await expect(table.getByRole("row").nth(1)).toContainText("+1.6%");
  await expect(biz.getByRole("img", { name: /Total sales by month, Oct 2024 to Sep 2026/ })).toBeVisible();
  await table.getByRole("button", { name: "Exports" }).click();
  await expect(biz.getByRole("img", { name: /Exports by month/ })).toBeVisible();
  await expect(biz.getByRole("button", { name: "Alert on new updates" })).toBeVisible();
  if (SHOTS) await biz.screenshot({ path: `${SHOTS}/business-updates-${info.project.name}.png` });

  const held = page.locator("#named-holders");
  await held.scrollIntoViewIfNeeded();
  await expect(held.getByText(/Quarter to 30 Jun 2026/)).toBeVisible({ timeout: 20_000 });
  const rows = held.getByRole("table", { name: "RELIANCE named holders" });
  await expect(rows.locator("tr[data-holder='SUDHIR MOHANLAL JATIA']")).toContainText("36.74%");
  await expect(rows.locator("tr[data-holder='Invesco India Flexi Cap Fund']")).toContainText("New above 1%");
  await expect(rows.locator("tr[data-holder='Ashish Kacholia']")).toContainText("No change");
  await expect(held.getByText(/HSBC MUTUAL FUND - HSBC SMALL CAP FUND \(4\.41%\)/)).toBeVisible();
  await expect(held.getByRole("link", { name: "Search a holder" })).toBeVisible();
  if (SHOTS) await held.screenshot({ path: `${SHOTS}/named-holders-${info.project.name}.png` });
  await sane(page, errors);
});

test("named holders: search a name, see each company alphabetically, follow", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/holders?q=kacholia", "Named holders across companies", phone ? 286 : 283);
  const card = page.locator("#holder");
  await expect(card.getByRole("heading", { name: "Ashish Kacholia", exact: true })).toBeVisible();
  const rows = card.getByRole("table", { name: "Companies where the holder is named" }).locator("tbody tr");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toHaveAttribute("data-company", "RELIANCE");
  await expect(rows.nth(1)).toHaveAttribute("data-company", "SAFARI");
  await expect(rows.nth(2)).toHaveAttribute("data-company", "XPROINDIA");
  await expect(rows.nth(2)).toContainText("3.91%");
  await card.getByRole("button", { name: "Follow this holder" }).click();
  await expect(page.getByRole("region", { name: "Holders you follow" })).toContainText("Ashish Kacholia");
  await expect(card.getByRole("button", { name: "Following · stop" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/holders-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
  await card.getByRole("button", { name: "Following · stop" }).click();
  await expect(page.getByRole("region", { name: "Holders you follow" })).toHaveCount(0);
  // the scans' tabs lead here too
  await expect(page.getByRole("navigation", { name: "Scans" }).getByRole("link", { name: "Named holders" })).toBeVisible();
  // a name nobody holds
  await page.getByLabel("Holder's name").fill("zzzz nobody");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("No holder above 1% by that name")).toBeVisible();
});

test("business updates: automakers side by side, alphabetical", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/business-updates", "Automakers' monthly sales", phone ? 292 : 289);
  const rows = page.getByRole("table", { name: "Automakers' monthly sales" }).locator("tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toHaveAttribute("data-company", "MARUTI");
  await expect(rows.nth(0)).toContainText("2,36,013 units");
  await expect(rows.nth(0)).toContainText("+24.4%");
  await expect(rows.nth(1)).toHaveAttribute("data-company", "TVSMOTOR");
  await expect(page.getByText(/Not read yet: Ashok Leyland/)).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/business-updates-page-${info.project.name}.png`, fullPage: true });
  await sane(page, errors);
  await page.getByRole("radio", { name: "Banks' and lenders' quarterly updates" }).click();
  await expect(page.getByText("No update in this list has been read into numbers yet.")).toBeVisible();
});
