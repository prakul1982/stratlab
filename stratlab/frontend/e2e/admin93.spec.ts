import { expect, test, type Page } from "@playwright/test";

// owner, 26 Nov ("make a button"): Admin → Users makes a test account on a plan and emails its one-time sign-in link to the admin's own
// inbox, lists the ones made, and re-sends a link to one of them. The endpoints are the server's own (/admin/test-account(s)); here the
// sign-in service and the email are stood in for, so the test checks what the page sends and says.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page) {
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto("/admin/users");
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
}

test("admin93 Test accounts: make one on a plan, the link goes to your own inbox, and a made one gets a new link", async ({ page }) => {
  const made: Record<string, { email: string; label: string; plan: string; at: string }> = {
    "u-t1": { email: "owner+reviewer@example.com", label: "reviewer", plan: "basic", at: "2026-11-20T10:00:00+00:00" } };
  const posted: unknown[] = [];
  await page.route("**/admin/test-accounts", (r) => r.fulfill({ json: { accounts: made, max: 8 } }));
  await page.route("**/admin/test-account", async (r) => {
    const b = r.request().postDataJSON() as { label: string; plan: string };
    posted.push(b);
    made[`u-${b.label}`] = { email: `owner+${b.label}@example.com`, label: b.label, plan: b.plan, at: "2026-11-26T03:00:00+00:00" };
    return r.fulfill({ json: { label: b.label, plan: b.plan, user_id: `u-${b.label}` } });
  });
  await open(page);
  const card = page.getByTestId("admin-test-accounts");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText("Test accounts (1 of 8)");
  await expect(card.getByTestId("test-account-list")).toContainText("owner+reviewer@example.com");
  const make = card.getByRole("button", { name: "Make it and email a sign-in link" });
  await expect(make).toBeDisabled();                                   // no name yet
  await card.getByLabel("Name").fill("Pro-Check");                     // lower-cased as typed
  await expect(card.getByLabel("Name")).toHaveValue("pro-check");
  await card.getByRole("radiogroup", { name: "Tier" }).getByRole("radio", { name: "Pro" }).click();
  await make.click();
  await expect(card.getByRole("status")).toContainText('"pro-check" (Pro) was sent to your own inbox');
  expect(posted).toEqual([{ label: "pro-check", plan: "pro" }]);
  await expect(card).toContainText("Test accounts (2 of 8)");
  await card.getByRole("listitem").filter({ hasText: "reviewer" }).getByRole("button", { name: "Email a new link" }).click();
  await expect.poll(() => posted.length).toBe(2);
  expect(posted[1]).toEqual({ label: "reviewer", plan: "basic" });
});
