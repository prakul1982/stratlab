import { expect, test, type Page } from "@playwright/test";

// Release 17 fixes, in the fake world: a signed-out visitor's first click shows the next page's loading bar at once (the visitor router
// no longer runs page moves as transitions), and the cards that drew their own title now have the section frame (close and move).
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const ADMIN = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };

async function open(page: Page, where: string, signedIn: boolean) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  if (signedIn) {
    await page.addInitScript((s) => {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.onboarding.v1", "done");
    }, ADMIN);
  }
  await page.goto(where);
  await expect(page.locator("main h1").first()).toBeAttached({ timeout: 30_000 });
  return errors;
}

test("signed out: a click on the landing page whose next page's code is still on its way shows the loading bar at once", async ({ page }) => {
  const errors = await open(page, "/", false);
  // the landing page drawn by its code (not the words the server sent first, whose links are plain page loads)
  await expect(page.locator(".lp-space-name").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForLoadState("networkidle");
  await page.route(/\/assets\/.*\.js$/, async (r) => { await new Promise((ok) => setTimeout(ok, 2500)); await r.fallback(); });
  await page.locator('a[href="/terms"]').filter({ visible: true }).first().click();
  await expect(page.locator(".k-loading").filter({ hasText: "Opening StratLab" })).toBeVisible({ timeout: 700 });
  await expect(page.locator("main h1").filter({ visible: true }).first()).toHaveText("Terms of service", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("the Features page's space cards and the deep dive's document cards close and move like every section", async ({ page }) => {
  const errors = await open(page, "/features", true);
  for (const id of ["features-trade", "features-invest", "features-money"]) {
    const card = page.getByTestId(id);
    if (!(await card.count())) continue;
    await expect(card.locator(".k-card-head h2.k-card-title a")).toBeVisible({ timeout: 30_000 });
    await expect(card.getByRole("button", { name: "Close section" })).toBeVisible();
  }
  await page.goto("/research/IN/RELIANCE/deep");
  for (const title of ["Management report card", "From the company's own documents"]) {
    const card = page.locator("main section.k-card").filter({ has: page.locator("h2.k-card-title", { hasText: title }) });
    await expect(card).toBeVisible({ timeout: 30_000 });
    // the line under the title and the read button stay in the header row, beside the section's own buttons
    await expect(card.locator(".k-card-head .k-card-headtext .k-small")).toBeVisible();
    await expect(card.locator(".k-card-head .dd-ask button")).toBeVisible();
    await card.getByRole("button", { name: "Close section" }).click();
    await expect(card).toHaveClass(/k-folded/);
    await expect(card.locator(".dd-ask")).toBeHidden();
    await card.getByRole("button", { name: "Open section" }).click();
    await expect(card).not.toHaveClass(/k-folded/);
  }
  expect(errors).toEqual([]);
});
