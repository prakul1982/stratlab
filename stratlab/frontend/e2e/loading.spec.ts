import { expect, test } from "@playwright/test";

// Owner, 5 Nov: a wait on the server always shows a moving bar along the top of the screen, and it goes once the answer is in.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

test("a slow answer shows the top loading bar, and it goes when the answer is in", async ({ page }) => {
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto("/trade");
  await expect(page.locator("aside.sidebar .acct-btn").or(page.getByRole("button", { name: "Open menu" })).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".top-progress")).toHaveCount(0, { timeout: 15_000 });
  // the library's list answers 2 s late
  await page.route(/\/library(\?|$)/, async (r) => { await new Promise((res) => setTimeout(res, 2000)); await r.fallback(); });
  await page.evaluate(() => { history.pushState({}, "", "/library"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page.locator(".top-progress > span")).toBeVisible({ timeout: 2_000 });
  await expect(page.locator(".top-progress")).toHaveCount(0, { timeout: 15_000 });
});
