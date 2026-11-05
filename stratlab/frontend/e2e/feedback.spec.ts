// Help & feedback (owner, 4 Nov; in the account menu since 5 Nov: "put this in accounts section") and the public
// footer's link open one dialog; a report sent signed in and one sent signed out both land in Admin → Feedback, with the page and
// the plan, and new ones are counted in "Needs your attention".
import { expect, test, type Page } from "@playwright/test";

const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function signIn(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}

// each run its own address, so the signed-out allowance (3 an hour an address) isn't shared by both projects or a retry
async function ownAddress(page: Page) {
  const ip = `203.0.113.${Math.floor(Math.random() * 250) + 1}`;
  await page.route(/\/feedback$/, (r) => r.continue({ headers: { ...r.request().headers(), "x-forwarded-for": ip } }));
}

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

test("a signed-in report from the Feedback button lands in Admin → Feedback with its page and plan", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const words = `The chart froze after switching to 1h (${info.project.name} ${Date.now()})`;
  const errors = await signIn(page, "/trade");
  // in the account menu beside Help (owner, 5 Nov): not crowding the logo's row or the phone's top bar
  await expect(page.locator("aside.sidebar .side-top, header.topbar").getByRole("button", { name: "Feedback" })).toHaveCount(0);
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  await page.locator("aside.sidebar").getByRole("button", { name: /account menu$/ }).click({ timeout: 30_000 });
  const button = page.getByRole("menu", { name: "Account" }).getByRole("menuitem", { name: "Feedback", exact: true });
  await expect(button).toBeVisible();
  await button.click();
  const dlg = page.getByRole("dialog", { name: "Help & feedback" });
  await expect(dlg.getByRole("radiogroup", { name: "What is it?" }).getByRole("radio")).toHaveCount(3);
  await dlg.getByRole("button", { name: "Send" }).click();
  await expect(dlg.getByRole("alert")).toContainText("Say a few words");          // nothing sent empty
  await dlg.getByRole("textbox").fill(words);
  await dlg.getByRole("checkbox").check();
  await expect(dlg).toContainText("Reply to me (at your account's email)");
  await dlg.getByRole("button", { name: "Send" }).click();
  await expect(dlg.getByTestId("feedback-done")).toContainText("who will write back", { timeout: 30_000 });
  await dlg.getByRole("button", { name: "Close", exact: true }).first().click();

  await page.goto("/admin/feedback");
  const row = page.getByRole("table", { name: "Feedback reports" }).getByRole("row").filter({ hasText: words });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText("Something's broken");
  await expect(row).toContainText("/trade");
  await expect(row).toContainText("Yes: owner@example.com");
  await page.goto("/admin");
  await expect(page.getByRole("region", { name: "Needs your attention" })).toContainText(/\d+ new feedback reports? from users\./, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("a visitor's report from the public footer lands in the inbox as signed out, and can be marked fixed", async ({ page, browser }, info) => {
  const words = `An idea from a visitor: a dark chart theme (${info.project.name} ${Date.now()})`;
  const visitor = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: page.viewportSize() ?? undefined });
  const v = await visitor.newPage();
  await ownAddress(v);
  await v.goto("/terms");
  await v.getByRole("navigation", { name: "Policies" }).getByRole("button", { name: "Feedback" }).click();
  const dlg = v.getByRole("dialog", { name: "Help & feedback" });
  await dlg.getByRole("radio", { name: /Idea/ }).click();
  await dlg.getByRole("textbox").fill(words);
  await dlg.getByRole("button", { name: "Send" }).click();
  await expect(dlg.getByTestId("feedback-done")).toBeVisible({ timeout: 30_000 });
  await visitor.close();

  const errors = await signIn(page, "/admin/feedback");
  const table = page.getByRole("table", { name: "Feedback reports" });
  const row = table.getByRole("row").filter({ hasText: words });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText("Idea for a new feature");
  await expect(row).toContainText("Signed out");
  await expect(row).toContainText("/terms");
  await row.getByRole("combobox").selectOption("fixed");
  await page.getByRole("combobox", { name: "Status", exact: true }).selectOption("fixed");
  await expect(table.getByRole("row").filter({ hasText: words })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});
