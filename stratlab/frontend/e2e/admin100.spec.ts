import { expect, test, type Page } from "@playwright/test";

// Lane admin100 (owner, 27 Nov: "errors in Admin", twice): Overview's Needs your attention holds only what the owner fixes by hand
// (Release 93), what StratLab handles itself is listed apart under "nothing for you to do", every outside source has a row with its last
// good answer and last failure, and a job switched off on purpose is not a Check.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string, ready: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(300);
  return errors;
}

test("admin100 Overview: only the owner's fixes need attention; the rest is apart; every source has its row", async ({ page }) => {
  const errors = await open(page, "/admin", "Needs your attention");
  const card = page.getByRole("region", { name: "Needs your attention" });
  // the feeds still waiting are listed apart, never as an item that needs the owner
  await expect(page.getByText("Data feeds", { exact: true }).first()).toBeVisible();
  const todo = (await card.locator(".adm-todo-body").allInnerTexts()).join("\n");
  expect(todo).not.toMatch(/data feeds? on Check|server errors? since the last restart|Live price feed:/);
  const apart = page.getByTestId("self-fixing");
  await expect(apart).toBeVisible();
  await expect(apart).toContainText(/StratLab is handling itself: nothing for you to do/);
  await apart.locator("summary").click();
  await expect(apart.getByRole("list", { name: "Handled by StratLab" })).toContainText(/data feeds? on Check/);
  // the menu's count is the owner's items only
  const items = await card.locator(".adm-todo-body").count();
  await expect(page.locator(".adm-count")).toHaveText(String(items));
  // Data sources: every known source by name, with a summary of words
  const sources = page.getByTestId("data-sources");
  await expect(sources).toBeVisible();
  await expect(page.getByTestId("sources-summary")).toHaveText(/^\d+ [A-Z][\w ]+( · \d+ [A-Z][\w ]+)*$/);
  const ok = page.getByTestId("sources-ok");
  if (await ok.count()) await ok.locator("summary").click();
  for (const name of ["Zerodha (broker data)", "Exchange file archive (NSE)", "Exchange announcements (NSE)", "BSE", "The SEC (EDGAR)", "Email service", "Razorpay"]) {
    await expect(sources.getByText(name, { exact: true })).toBeVisible();
  }
  // nothing pushes the page sideways (phone)
  const sw = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(sw).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});

test("admin100 Data and jobs: a job switched off on purpose is OK, not a Check", async ({ page }) => {
  const errors = await open(page, "/admin/data", "Background jobs");
  const table = page.getByRole("table", { name: "Background jobs" });
  const row = table.getByRole("row").filter({ hasText: "Customer and supplier map" });
  if (await table.count()) {
    await expect(row).toContainText("OK");
    await expect(row).not.toContainText("Check");
  } else {
    // a phone stacks the rows as cards
    const cardRow = page.locator("tr, [role='row'], li, .k-card-row").filter({ hasText: "Customer and supplier map" }).first();
    await expect(cardRow).not.toContainText("Check");
  }
  expect(errors).toEqual([]);
});
