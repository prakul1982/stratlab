import { expect, test, type Page } from "@playwright/test";

// Company search by name (F3-004, F3-005, R1-048): Ctrl K offers the company first for "hdfc bank" and "infosys" and
// Enter opens it; a question gets the explanation already written for it; the Invest home's box finds its own
// placeholder ("Apollo Hospitals"); the notebook market picker finds "HDFC Bank". Signed in as the owner.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/me/prefs", (r) => (r.request().method() === "PUT" ? r.fulfill({ json: { prefs: {} } }) : r.fallback()));
  await page.route(/\/me(\?.*)?$/, async (r) => {
    if (r.request().method() !== "GET") return r.fallback();
    const res = await r.fetch();
    const me = await res.json();
    await r.fulfill({ response: res, json: { ...me, prefs: { ...(me.prefs || {}), level: "some", focus: "invest" } } });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}

async function palette(page: Page, phone: boolean) {
  const box = page.getByRole("dialog", { name: "Ask or do anything" });
  if (!(await box.count())) await page.getByRole("button", { name: phone ? "Search or ask anything" : /Ask or do anything/ }).first().click();
  await expect(box).toBeVisible();
  return box;
}

test("Ctrl K: a company's name finds the company first, and Enter opens its page", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  for (const [q, name, sym] of [["hdfc bank", "HDFC Bank", "HDFCBANK"], ["infosys", "Infosys", "INFY"], ["Apollo Hospitals", "Apollo Hospitals Enterprise", "APOLLOHOSP"],
    ["RIL", "Reliance Industries", "RELIANCE"]] as const) {
    const box = await palette(page, phone);
    await box.getByLabel("Search or ask anything").fill(q);
    await expect(box.locator(".palette-group").first(), q).toHaveText("Companies");
    const first = box.getByRole("option").first();
    await expect(first, q).toContainText(name);
    await expect(first).toContainText(sym);
    await expect(first.locator(".space-tag")).toHaveText("Invest");
    await expect(first).toHaveAttribute("aria-selected", "true");
  }
  // features still follow the companies
  const box = await palette(page, phone);
  await box.getByLabel("Search or ask anything").fill("hdfc bank");
  await expect(box.getByRole("option").first()).toContainText("HDFC Bank");
  await box.getByLabel("Search or ask anything").press("Enter");
  await expect(page).toHaveURL(/\/research\/IN\/HDFCBANK$/);
  expect(errors).toEqual([]);
});

test("Ctrl K: a question shows the explanation already written for it", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  const box = await palette(page, phone);
  await box.getByLabel("Search or ask anything").fill("what is walk-forward?");
  await expect(box.locator(".palette-group").first()).toHaveText("Help");
  await expect(box.getByRole("option").first()).toContainText("Walk-forward test");
  await expect(box.getByRole("option", { name: /^Watchlist/ })).toHaveCount(0);
  await box.getByLabel("Search or ask anything").press("Enter");
  const answer = box.locator(".palette-answer");
  await expect(answer).toContainText("Walk-forward test");
  await expect(answer).toContainText("The strictest test for an idea you've tuned");
  expect(errors).toEqual([]);
});

test("the Invest home's company box finds a company by its name, as its placeholder suggests", async ({ page }) => {
  const errors = await open(page, "/invest");
  const input = page.getByRole("textbox", { name: "Search any company listed in India (NSE or BSE)" });
  await expect(input).toBeVisible({ timeout: 30_000 });
  for (const [q, sym] of [["Apollo Hospitals", "APOLLOHOSP"], ["HDFC Bank", "HDFCBANK"], ["Infosys", "INFY"], ["Tata Motors", "TMPV"]] as const) {
    await input.fill(q);
    const first = page.locator(".search-box .results button").first();
    await expect(first, q).toContainText(sym);
    await expect(page.getByText("No matches")).toHaveCount(0);
  }
  await input.fill("Apollo Hospitals");
  await expect(page.locator(".search-box .results button").first()).toContainText("Apollo Hospitals Enterprise");
  await input.press("Enter");
  await expect(page).toHaveURL(/\/research\/IN\/APOLLOHOSP$/);
  expect(errors).toEqual([]);
});

test("the notebook's market picker finds a company by its name", async ({ page }) => {
  const errors = await open(page, "/new");
  const market = page.getByRole("group", { name: "Market" });
  await expect(market).toBeVisible({ timeout: 30_000 });
  await market.getByRole("button", { name: /India/ }).first().click();
  const input = page.getByPlaceholder(/Search a stock, index or F&O/);
  await input.fill("HDFC Bank");
  const first = page.locator(".results button").first();
  await expect(first).toContainText("HDFCBANK");
  await expect(first).toContainText("HDFC Bank");
  await input.fill("Infosis");                       // a typo
  await expect(page.locator(".results button").first()).toContainText("INFY");
  expect(errors).toEqual([]);
});
