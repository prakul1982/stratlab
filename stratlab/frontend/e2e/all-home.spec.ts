import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { NAV_GROUPS } from "../src/lib/navGroups";
import { planOf, PLAN_NAME } from "../src/lib/plans";

// The "All" home (/all): one next step, a short folded list of what is new, a row of three tools for each space and a
// small Coming up line; wired to the All choice in the space switcher and to `/`. Desktop and phone, light and dark.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const who = (n: number, phone: boolean) => { const i = n + (phone ? 1 : 0); return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` }; };
type Who = ReturnType<typeof who>;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });

async function signIn(page: Page, u: Who, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: u.token, user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}
const answer = (request: APIRequestContext, u: Who, focus: string) => request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus, space: "all" } });

async function sane(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /yahoo|finnhub|screener\.in|kite|zerodha/i, /\byou should\b/i, /\b(buy|sell|hold) (this|now)\b/i]) expect(text).not.toMatch(bad);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main a")).filter((el) => {
    const b = el.getBoundingClientRect();
    return b.width && b.height && !el.closest("p, li, .search-box") && getComputedStyle(el).display !== "inline" && b.height < 32;
  }).map((el) => `${el.tagName} "${(el.textContent || "").trim().slice(0, 30)}"`));
  expect(small, "controls too small to tap").toEqual([]);
}

test("all home: opens from / and shows the next step, a folded New list, three tools per space and Coming up", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(250, phone);
  await answer(request, u, "both");
  const errors = await signIn(page, u, "/");
  await expect(page).toHaveURL(/\/all$/, { timeout: 30_000 });
  const home = page.getByTestId("all-home");
  await expect(home.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(home.locator(".space-next")).toHaveCount(1);          // one next step

  // New: folded to two a space, every row linking to a real page, plan badges from plans.ts
  const list = page.getByTestId("all-new");
  await expect(list.locator("[data-new]")).toHaveCount(2 + 2 + 2);
  await list.getByRole("button", { name: /^Show all 16$/ }).click();
  await expect(list.locator("[data-new]")).toHaveCount(16);
  const href = (t: string) => list.locator(`[data-new="${t}"]`);
  await expect(href("Market events")).toHaveAttribute("href", "/trade/events");
  await expect(href("Stock futures")).toHaveAttribute("href", "/trade/positioning/stocks");
  await expect(href("Strike picking")).toHaveAttribute("href", "/options");
  await expect(href("Business updates")).toHaveAttribute("href", NAV_GROUPS.Invest.find((e) => e.label === "Business updates")!.to);
  await expect(href("Named holders")).toHaveAttribute("href", NAV_GROUPS.Invest.find((e) => e.label === "Named holders")!.to);
  await expect(href("Rates")).toHaveAttribute("href", NAV_GROUPS.Money.find((e) => e.label === "Rates")!.to);
  await expect(href("AI assistant")).toHaveAttribute("href", "/account");
  expect(planOf("signal_webhooks")).toBe("pro");
  await expect(href("Signals")).toContainText(PLAN_NAME[planOf("signal_webhooks")]);
  await expect(href("Chart replay")).toContainText(PLAN_NAME[planOf("chart_replay")]);
  await expect(href("Market events").locator(".badge")).toHaveCount(0);
  await expect(list.locator('[data-new="AI assistant"]')).toBeVisible();
  await list.getByRole("button", { name: "Show fewer" }).click();
  await expect(list.locator("[data-new]")).toHaveCount(6);

  // one row a space: three tools and the way into its home
  for (const [id, label, home_] of [["trade", "Trade", "/trade"], ["invest", "Invest", "/invest"], ["money", "Money", "/money"]] as const) {
    const row = page.locator(`[data-space-row="${id}"]`);
    await expect(row.locator("a.space-card")).toHaveCount(3);
    await expect(row.getByRole("link", { name: `Open ${label} home →` })).toHaveAttribute("href", home_);
  }
  await expect(page.locator('[data-space-row="money"] a.space-card').first()).toHaveAttribute("href", NAV_GROUPS.Money[0].to);
  expect(await page.getByTestId("all-events").count()).toBeLessThanOrEqual(1);

  await sane(page, errors, phone);
  await page.emulateMedia({ colorScheme: "dark" });
  await sane(page, errors, phone);
  const bg = await page.evaluate(() => getComputedStyle(document.querySelector(".space-card")!).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");
  await page.locator('[data-space-row="invest"]').getByRole("link", { name: "Open Invest home →" }).click();
  await expect(page).toHaveURL(/\/invest$/);
});

test("all home: the All choice opens it, a space choice leaves it, and the menu links to it", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(252, phone);
  await request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus: "trade", space: "trade" } });
  const errors = await signIn(page, u, "/trade");
  await expect(page).toHaveURL(/\/trade$/, { timeout: 30_000 });
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  const side = page.locator("aside.sidebar");
  const space = side.getByRole("radiogroup", { name: "Space" });
  await space.getByRole("radio", { name: "All" }).click();
  // the switcher changes the menu only; the menu's own home link goes to the home of what shows
  await expect(page).toHaveURL(/\/trade$/);
  await expect(side.getByRole("link", { name: "All home" })).toHaveAttribute("href", "/all");
  await side.getByRole("link", { name: "All home" }).click();
  await expect(page).toHaveURL(/\/all$/);
  await expect(page.getByTestId("all-home")).toBeVisible();
  if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
  await space.getByRole("radio", { name: "Money" }).click();
  await expect(side.getByRole("link", { name: "Money home" })).toHaveAttribute("href", "/money");
  expect(errors).toEqual([]);
});

test("all home: focus decides the next step", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(254, phone);
  await answer(request, u, "money");
  const errors = await signIn(page, u, "/all");
  await expect(page.locator(".space-next")).toHaveCount(1);
  await expect(page.locator(".space-next")).toContainText(/holdings|Your money/i);
  await sane(page, errors, phone);
});
