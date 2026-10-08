import { expect, test, type Page } from "@playwright/test";

// Round 4, builder A: the sidebar's lock and scroll, one financial year across the Money pages and the links between them,
// public pages' tab titles and addresses, page widths, Settings' wording, form hints and chips, and who is asked "What brings
// you here?". Signed in as the owner (the fake world's admin, with holdings and trades) or as a person of their own
// (load-165 to load-170 and load-190, 191 are this file's).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const ownerSession = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const person = (n: number) => ({ ...base, access_token: `load-${n}`, user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } });

async function open(page: Page, where: string, who: object | null = ownerSession, tour = true) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(([s, seen]) => {
    if (s) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    if (seen) localStorage.setItem("stratlab.tour.v1", "1");
  }, [who, tour] as const);
  await page.goto(where);
  return errors;
}

const noSideways = async (page: Page) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
};

test("R4-006: the menu locks only a page that is locked whole; a part-paid page says its free part", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the menu is a drawer on a phone");
  const errors = await open(page, "/money/net-worth", person(165));          // Free: 5 net worth entries and 5 funds are free
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("link", { name: /^Net worth/ })).toBeVisible({ timeout: 30_000 });
  await expect(side.getByRole("link", { name: /^Net worth/ }).locator(".side-lock"), "Net worth is free in the main").toHaveCount(0);
  await expect(side.getByRole("link", { name: /^Mutual funds/ }).locator(".side-lock")).toHaveCount(0);
  await expect(page.locator("main")).toContainText(/\d+ of 5 free entries used/, { timeout: 30_000 });
  await page.goto("/money/mutual-funds");
  await expect(page.locator("main").getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  // a whole-locked page still has its lock
  await page.goto("/research/scan");
  await expect(side.getByRole("link", { name: /Trend scan/ }).locator(".side-lock")).toHaveAttribute("data-plan", "Basic", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("R4-007: the year follows one rule, and 'as in tax tools' lands on the same year and number", async ({ page }) => {
  const errors = await open(page, "/holdings");
  const stat = page.getByText("FY 2026-27 (estimated)").first();
  await expect(stat).toBeVisible({ timeout: 30_000 });
  const figure = await page.locator(".k-stat", { has: stat }).locator(".k-stat-v").first().innerText();
  await page.locator(".k-stat", { has: stat }).getByRole("link", { name: "as in tax tools" }).click();
  await expect(page).toHaveURL(/\/money\/tax-tools\?fy=2026/);
  await expect(page.getByRole("heading", { name: "Dividends, FY 2026-27" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main")).toContainText(figure);
  expect(errors).toEqual([]);
});

test("R4-007: the owner's year being filed has no sales, so the tax card and the report say so and agree", async ({ page }) => {
  const errors = await open(page, "/money");
  const card = page.getByTestId("tax-summary");
  await expect(card).toContainText("No sales in FY 2025-26, the year being filed, so this is FY 2024-25, the latest year with sales.", { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Tax, FY 2024-25" })).toBeVisible();
  await page.getByRole("link", { name: /Open Tax report/ }).click();
  await expect(page).toHaveURL(/\/tax-report\?fy=2024/);
  await expect(page.getByRole("heading", { name: /Total tax estimate, FY 2024-25/ })).toBeVisible({ timeout: 30_000 });
  // tax tools has dividends in the year being filed, so it opens there, and ITR with it
  await page.goto("/money/tax-tools?fy=2025");
  await expect(page.getByRole("heading", { name: "Dividends, FY 2025-26" })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("R4-007: a year asked for carries to the other Money pages", async ({ page }) => {
  const errors = await open(page, "/tax-report?fy=2024");
  await expect(page.getByRole("heading", { name: /Total tax estimate, FY 2024-25/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("tax-moved-year")).toHaveCount(0);                 // asked for, not moved
  await page.goto("/money/itr");
  await expect(page.getByRole("heading", { name: /Download for FY 2024-25/ })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("R4-016: the menu fades where more is behind it, and its last row scrolls fully into view", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the menu is a drawer on a phone");
  await page.setViewportSize({ width: 1280, height: 600 });
  const errors = await open(page, "/invest/business-updates");
  const nav = page.locator("aside.sidebar nav.side-groups");
  await expect(nav).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => document.querySelectorAll<HTMLElement>(".side-toggle[aria-expanded=false]").forEach((b) => b.click()));
  await expect(nav).toHaveAttribute("data-fade", "bottom");
  await nav.evaluate((n) => { n.scrollTop = n.scrollHeight; });
  await expect(nav).toHaveAttribute("data-fade", "top");
  const last = nav.locator("a").last();
  const [n, l] = await Promise.all([nav.boundingBox(), last.boundingBox()]);
  expect(l!.y + l!.height, "the last row is clipped by the footer").toBeLessThanOrEqual(n!.y + n!.height);
  expect(errors).toEqual([]);
});

test("R4-017: every public page has its own tab title, and /login, /signup, /about open the landing page", async ({ page }) => {
  const errors = await open(page, "/terms", null);
  await expect(page).toHaveTitle("Terms · StratLab");
  await page.goto("/privacy");
  await expect(page).toHaveTitle("Privacy · StratLab");
  await page.goto("/refunds");
  await expect(page).toHaveTitle("Refunds · StratLab");
  await page.goto("/contact");
  await expect(page).toHaveTitle("Contact · StratLab");
  for (const [path, title] of [["/login", "Sign in · StratLab"], ["/signup", "Sign up · StratLab"], ["/about", "About · StratLab"]] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: /Test it, research it, track it/ })).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveTitle(title);
    await expect(page.getByText("Page not found")).toHaveCount(0);
  }
  await page.goto("/nowhere-at-all");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found", { timeout: 30_000 });
  await expect(page).toHaveTitle("Page not found · StratLab");
  expect(errors).toEqual([]);
});

test("R4-017: signed in, the policies and a missing page keep their own titles, and the landing addresses go on", async ({ page }) => {
  const errors = await open(page, "/terms", person(166));
  await expect(page).toHaveTitle("Terms · StratLab");
  await page.goto("/nowhere-at-all");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found", { timeout: 30_000 });
  await expect(page).toHaveTitle("Page not found · StratLab");
  await page.goto("/login");
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 30_000 });
  await page.goto("/about");
  await expect(page).toHaveURL(/\/features$/, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("R4-018: /import and /options are as wide and as centred as other pages", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the width rule is for a laptop screen");
  const errors = await open(page, "/money/tax-tools");
  const box = async (path: string) => {
    await page.goto(path);
    await expect(page.locator("main .k-page").first()).toBeVisible({ timeout: 30_000 });
    return page.locator("main .k-page").first().boundingBox();
  };
  const standard = await box("/money/tax-tools");
  for (const path of ["/import", "/options"]) {
    const b = await box(path);
    expect(Math.round(b!.x), `${path} starts where other pages do`).toBe(Math.round(standard!.x));
    expect(Math.round(b!.width), `${path} is as wide as other pages`).toBe(Math.round(standard!.width));
  }
  expect(errors).toEqual([]);
});

test("R4-020: Settings names only what is on the page, and a disabled test says why", async ({ page }) => {
  const errors = await open(page, "/settings", person(167));
  const card = page.locator("#alerts");
  await expect(card).toBeVisible({ timeout: 30_000 });
  const test = card.getByRole("button", { name: "Send a test" });
  await expect(test).toBeVisible();
  const telegram = await card.getByLabel("Telegram chat ID").count();
  const email = await card.getByLabel("Email").count();
  if (await test.isDisabled()) {
    const why = card.locator("#alert-test-why");
    await expect(why, "a disabled test says why, under the buttons").toBeVisible();
    if (!telegram) await expect(why).not.toContainText("Telegram");
    if (!email) await expect(why).not.toContainText("email");
    await expect(test).toHaveAttribute("title", /./);
  }
  if (!telegram && !email) await expect(card).not.toContainText(/Telegram chat ID|an email above/);
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("R4-021: the symbol box is full width, and a rule shows once the person has been in the box", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the width is checked on a laptop screen");
  const errors = await open(page, "/holdings");
  const card = page.locator("form", { has: page.getByLabel("Quantity") });
  await expect(card).toBeVisible({ timeout: 30_000 });
  const symbol = await card.getByRole("combobox").first().boundingBox();
  const qty = await card.getByLabel("Quantity").boundingBox();
  expect(symbol!.width, "the symbol box spans the form").toBeGreaterThan(qty!.width * 2);
  await expect(card.getByPlaceholder("Name or symbol, e.g. Reliance")).toBeVisible();
  await expect(card.getByText("More than 0"), "a rule on a clean form").toHaveCount(0);
  await card.getByLabel("Quantity").fill("3");
  await card.getByLabel("Quantity").blur();
  await expect(card.getByText("More than 0")).toBeVisible();
  expect(errors).toEqual([]);
});

test("R4-021: a lending title does not repeat its field, the ETF placeholder fits, chips show on and off", async ({ page }, info) => {
  const errors = await open(page, "/invest/stock-lending");
  const lookup = page.locator("#slb-lookup");
  await expect(lookup.getByRole("heading", { level: 2 })).not.toHaveText("Look up a stock", { timeout: 30_000 });
  await expect(lookup.getByLabel("Look up a stock", { exact: true })).toBeVisible();
  await page.goto("/invest/etf-gaps");
  const etf = page.getByLabel("Find an ETF");
  await expect(etf).toBeVisible({ timeout: 30_000 });
  await expect(etf).toHaveAttribute("placeholder", "e.g. NIFTYBEES");
  const fits = await etf.evaluate((el: HTMLInputElement) => { const s = document.createElement("span"); s.style.cssText = `font:${getComputedStyle(el).font};position:absolute;visibility:hidden;white-space:nowrap`; s.textContent = el.placeholder; document.body.append(s); const w = s.offsetWidth; s.remove(); return w <= el.clientWidth - 28; });
  expect(fits, "the placeholder is cut").toBe(true);
  await page.goto("/money/calendar");
  const chips = page.getByRole("group", { name: "Show" }).getByRole("button");
  await expect(chips.first()).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
  const on = await chips.first().evaluate((el) => getComputedStyle(el, "::before").content);
  expect(on, "an on chip carries a tick").toContain("✓");
  await chips.first().click();
  await expect(chips.first()).toHaveAttribute("aria-pressed", "false");
  expect(await chips.first().evaluate((el) => getComputedStyle(el).borderStyle)).toBe("dashed");
  expect(await chips.first().evaluate((el) => getComputedStyle(el, "::before").content)).not.toContain("✓");
  if (info.project.name === "phone") {
    await page.goto("/options");
    const vw = page.viewportSize()!.width;
    const unders = page.getByRole("group", { name: "Underlying" }).getByRole("button");
    await expect(unders.first()).toBeVisible({ timeout: 30_000 });
    for (const b of await unders.all()) { const r = (await b.boundingBox())!; expect(r.x + r.width, "an underlying chip runs off the screen").toBeLessThanOrEqual(vw); }
    await page.goto("/admin");
    const tabs = page.getByRole("navigation", { name: "Admin sections" }).getByRole("link");
    await expect(tabs.first()).toBeVisible({ timeout: 30_000 });
    for (const t of await tabs.all()) { const r = (await t.boundingBox())!; expect(r.x + r.width, "an admin tab runs off the screen").toBeLessThanOrEqual(vw); }
    await noSideways(page);
  }
  expect(errors).toEqual([]);
});

test("R4-101: 'What brings you here?' is for an empty account, starts on the close button, and never reaches an established one", async ({ page, browser }, info) => {
  const phone = info.project.name === "phone";
  const fresh = phone ? 169 : 168;
  // an account with nothing yet is asked, and focus does not start on a choice
  const errors = await open(page, "/", person(fresh), false);
  const dialog = page.getByRole("dialog", { name: "What brings you here?" });
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  await expect(dialog.locator(":focus")).not.toHaveAttribute("role", "radio");
  // the same kind of account with a holding is established: it is never asked, whatever it answered
  const n = phone ? 191 : 190;
  await page.request.put(`${API}/holdings`, { headers: { Authorization: `Bearer load-${n}` }, data: { items: [{ symbol: "RELIANCE", qty: 5, avg: 1200, market: "IN" }] } });
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const other = await ctx.newPage();
  const errors2 = await open(other, "/", person(n), false);
  await expect(other.getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 30_000 });
  await other.waitForTimeout(1500);
  await expect(other.getByRole("dialog", { name: "What brings you here?" })).toHaveCount(0);
  const me = await (await page.request.get(`${API}/me`, { headers: { Authorization: `Bearer load-${n}` } })).json();
  expect(me.established).toBe(true);
  await ctx.close();
  expect(errors).toEqual([]);
  expect(errors2).toEqual([]);
});
