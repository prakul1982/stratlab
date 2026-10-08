import { expect, test, type Page } from "@playwright/test";

// The owner's "View as": signed in as the fake world's site owner (a Pro account), the Trend scan page (a Basic feature) is
// open; viewing as Free shows its lock, viewing as Pro opens it again, the banner is on every page until it is turned off,
// the choice survives a reload, Admin stays reachable, and the owner's real plan never changes. Anyone else is unaffected.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const KEY = "stratlab.viewas.v1";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const owner = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const free = { ...base, access_token: "load-60", user: { id: "u-load-60", aud: "authenticated", email: "load60@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function signIn(page: Page, session: typeof owner) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer ${session.access_token}` }, data: { level: "some", focus: "both" } });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  return errors;
}

const lock = (page: Page) => page.locator("main .plan-note");
const banner = (page: Page) => page.getByRole("status", { name: "Viewing as another plan" });

async function openScan(page: Page) {
  await page.goto("/research/scan");
  await expect(page.locator("main").getByRole("heading", { level: 1 }).first()).toHaveText(/Trend scan/, { timeout: 30_000 });
  await page.waitForTimeout(500);
}

/** Pick a plan in the user menu (the phone's menu opens from the top bar first). */
async function pickInMenu(page: Page, phone: boolean, choice: "Free" | "Basic" | "Pro" | "Off") {
  if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
  const side = page.locator("aside.sidebar");
  await side.getByRole("button", { name: /account menu$/ }).click();
  const group = side.getByRole("group", { name: "View as plan" });
  await expect(group).toContainText("View as:");
  await expect(group.getByRole("menuitemradio")).toHaveText(["Free", "Basic", "Pro", "Off"]);
  await group.getByRole("menuitemradio", { name: choice, exact: true }).click();
}

const realPlan = async (page: Page) => (await (await page.request.get(`${API}/me`, { headers: { Authorization: "Bearer admin-token" } })).json()).plan;

test("view as: a locked page under Free, unlocked under Pro, banner on every page, kept across reloads, Admin still works", async ({ page }, info) => {
  test.setTimeout(150_000);
  const phone = info.project.name === "phone";
  const errors = await signIn(page, owner);

  // as the owner: everything is open, no banner
  await openScan(page);
  await expect(lock(page)).toHaveCount(0);
  await expect(banner(page)).toHaveCount(0);

  // View as Free (the user menu): the page reloads as Free and shows its lock, with the banner above it
  await pickInMenu(page, phone, "Free");
  await expect(banner(page)).toContainText("Viewing as Free. Your real plan is unchanged.", { timeout: 30_000 });
  await expect(banner(page).getByRole("button", { name: "Turn off" })).toBeVisible();
  await expect(lock(page).first()).toBeVisible({ timeout: 30_000 });
  await expect(lock(page).first()).toContainText("Basic");
  expect(await lock(page).count(), "one note, not two").toBe(1);
  expect(await page.evaluate((k) => localStorage.getItem(k), KEY)).toBe("free");

  // it persists across a reload, and the banner is on a different page too
  await page.reload();
  await expect(banner(page)).toContainText("Viewing as Free", { timeout: 30_000 });
  await expect(lock(page).first()).toBeVisible({ timeout: 30_000 });
  await page.goto("/plans");
  await expect(page.locator("main").getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 30_000 });
  await expect(banner(page)).toContainText("Viewing as Free");
  await page.goto("/trade/replay");
  await expect(banner(page)).toContainText("Viewing as Free", { timeout: 30_000 });

  // the server really gates it: the action is refused with the plan's upgrade message, only while viewing
  const scan = (view?: string) => page.request.fetch(`${API}/research/scan/alerts`, { method: "PUT", data: { on: true },
    headers: { Authorization: "Bearer admin-token", ...(view ? { "X-View-As": view } : {}) } });
  expect((await scan("free")).status()).toBe(402);
  expect((await scan("pro")).status()).not.toBe(402);
  expect((await scan()).status()).not.toBe(402);

  // Admin stays reachable while viewing, and has its own control
  await page.goto("/admin");
  await expect(page.getByText("Needs your attention", { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await expect(banner(page)).toContainText("Viewing as Free");
  const card = page.getByRole("region", { name: "View as a plan" });
  await expect(card.getByRole("radio", { name: "Free" })).toBeChecked();

  // View as Pro (Admin's control): the same page is unlocked, the banner says Pro
  await card.getByRole("radio", { name: "Pro" }).click();
  await expect(banner(page)).toContainText("Viewing as Pro. Your real plan is unchanged.", { timeout: 30_000 });
  await expect(page.getByRole("region", { name: "View as a plan" }).getByRole("radio", { name: "Pro" })).toBeChecked();
  await openScan(page);
  await expect(lock(page)).toHaveCount(0);
  await expect(banner(page)).toContainText("Viewing as Pro");

  // View as Basic, then Turn off from the banner: no banner, and the page is the owner's again
  await pickInMenu(page, phone, "Basic");
  await expect(banner(page)).toContainText("Viewing as Basic", { timeout: 30_000 });
  await banner(page).getByRole("button", { name: "Turn off" }).click();
  await expect(banner(page)).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator("main").getByRole("heading", { level: 1 }).first()).toHaveText(/Trend scan/, { timeout: 30_000 });
  expect(await page.evaluate((k) => localStorage.getItem(k), KEY)).toBeNull();
  await page.reload();
  await expect(page.locator("main").getByRole("heading", { level: 1 }).first()).toHaveText(/Trend scan/, { timeout: 30_000 });
  await expect(banner(page)).toHaveCount(0);

  // "Off" in the menu is the same as the banner's button
  await pickInMenu(page, phone, "Free");
  await expect(banner(page)).toBeVisible({ timeout: 30_000 });
  await pickInMenu(page, phone, "Off");
  await expect(banner(page)).toHaveCount(0, { timeout: 30_000 });

  expect(await realPlan(page), "the owner's real plan is untouched").toBe("pro");
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("view as: nobody else gets it, even with the choice saved on their device", async ({ page }, info) => {
  test.setTimeout(90_000);
  const phone = info.project.name === "phone";
  const errors = await signIn(page, free);
  await page.addInitScript((k) => localStorage.setItem(k, "pro"), KEY);      // a stale choice left on a shared device
  await openScan(page);
  await expect(lock(page).first(), "still Free: the server ignores it").toBeVisible();
  await expect(banner(page)).toHaveCount(0);
  await expect.poll(() => page.evaluate((k) => localStorage.getItem(k), KEY), { timeout: 15_000 }).toBeNull();     // and it is dropped
  // the menu has no View as for them, and the server refuses to set it
  if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
  await page.locator("aside.sidebar").getByRole("button", { name: /account menu$/ }).click();
  await expect(page.getByRole("menuitem", { name: "Account" })).toBeVisible();
  await expect(page.getByRole("group", { name: "View as plan" })).toHaveCount(0);
  const r = await page.request.put(`${API}/admin/view-as`, { headers: { Authorization: "Bearer load-60" }, data: { plan: "pro" } });
  expect(r.status()).toBe(403);
  expect(errors).toEqual([]);
});
