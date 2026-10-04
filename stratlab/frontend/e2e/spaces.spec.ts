import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { NAV_GROUPS } from "../src/lib/navGroups";

// The three spaces: Trade (the strategy lab), Invest and Money. The switcher at the top of the menu, the welcome
// question that picks the first space, each space's home, deep links opening their own space, and search labelling
// results by space. Each test signs in as its own fake user (one per project), so choices saved here touch no other test.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };

/** A fake user for this test and project: load-N on desktop, load-(N+1) on a phone. */
function who(n: number, phone: boolean) {
  const i = n + (phone ? 1 : 0);
  return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` };
}
const ADMIN = { token: "admin-token", id: "u-admin", email: "owner@example.com" };
type Who = typeof ADMIN;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });

/** Signed in as `u`, tour seen; answers nothing, so a test can look at the welcome question itself. */
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

const prefs = async (request: APIRequestContext, u: Who) => (await (await request.get(`${API}/me`, { headers: auth(u) })).json()).prefs;

/** On a phone the menu is a drawer: open it. */
async function menu(page: Page, phone: boolean) {
  if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("navigation", { name: "Main" })).toBeVisible();
  return side;
}

/** No crash, nothing wider than the screen, no broken numbers, no advice words; on a phone, big enough to tap. */
async function sane(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /yahoo|finnhub|screener\.in|kite connect/i,
    /\byou should\b/i, /\b(buy|sell|hold) (this|now)\b/i, /\btarget price\b/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio]), aside .space-switch button"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

const groups = (side: ReturnType<Page["locator"]>) => side.getByRole("navigation", { name: "Main" }).locator(".side-toggle");

test("spaces: the switcher shows one space's menu, All shows every group folded, and the choice is kept", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(230, phone);
  await request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus: "trade" } });     // came to trade
  const errors = await signIn(page, u, "/");
  // `/` opens the space's home: Trade, with Options first
  await expect(page).toHaveURL(/\/trade$/, { timeout: 30_000 });
  await expect(page.locator(".space-card-lead")).toContainText("Options");
  let side = await menu(page, phone);
  const space = side.getByRole("radiogroup", { name: "Space" });
  await expect(space.getByRole("radio")).toHaveText(["Trade", "Invest", "Money", "All"]);
  await expect(space.getByRole("radio", { name: "Trade" })).toHaveAttribute("aria-checked", "true");
  await expect(groups(side)).toHaveText([/Notebooks$/, /Trading$/]);
  await expect(side.locator('[data-group="trading"] .side-nav a')).toHaveText(["Options", "Paper trading", "Strategy library", "Import a strategy", "Positioning", "Trade journal"]);
  // the space's main action is a normal-sized button, not a banner
  const action = side.getByRole("button", { name: "New notebook" });
  await expect(action).toBeVisible();
  expect((await action.boundingBox())!.height).toBeLessThanOrEqual(40);

  // Money: its own menu, from the one list each Money feature adds itself to; the page stays where it is
  await space.getByRole("radio", { name: "Money" }).click();
  await expect(space.getByRole("radio", { name: "Money" })).toHaveAttribute("aria-checked", "true");
  await expect(groups(side)).toHaveText([/Money$/]);
  await expect(side.locator('[data-group="money"] .side-nav a')).toHaveText(NAV_GROUPS.Money.map((e) => e.label));
  await expect(side.getByRole("link", { name: "Money home" })).toHaveAttribute("href", "/money");
  await expect(page).toHaveURL(/\/trade$/);
  // kept on the account and on this device
  await expect.poll(async () => (await prefs(request, u)).space).toBe("money");
  expect(await page.evaluate(() => localStorage.getItem("stratlab.space"))).toBe("money");
  if (phone) await sane(page, errors, phone);

  // All: every group, Trade's first, folded until opened
  await space.getByRole("radio", { name: "All" }).click();
  await expect(groups(side)).toHaveText([/Notebooks$/, /Trading$/, /Research$/, /Watch$/, /Money$/]);
  for (const g of await groups(side).all()) await expect(g).toHaveAttribute("aria-expanded", "false");
  await expect(side.getByRole("link", { name: "Paper trading" })).toBeHidden();
  await side.getByRole("button", { name: "Research", exact: true }).click();
  await expect(side.getByRole("link", { name: "Companies" })).toBeVisible();
  await expect.poll(async () => (await prefs(request, u)).space).toBe("all");

  // after a reload, and on a new device (nothing saved in the browser), the menu is still All
  await page.reload();
  side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "true");
  await page.evaluate(() => localStorage.removeItem("stratlab.space"));
  await page.reload();
  side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "true");
  // in All, a link into a space keeps every group, opening the one it's in
  await side.getByRole("link", { name: "Companies" }).click();
  await expect(page).toHaveURL(/\/research$/);
  side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "true");
  await expect(side.getByRole("button", { name: "Research", exact: true })).toHaveAttribute("aria-expanded", "true");
  await sane(page, errors, phone);
});

test("spaces: a deep link opens its own space, without changing the account's choice", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(232, phone);
  await request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus: "invest" } });
  const errors = await signIn(page, u, "/");
  await expect(page).toHaveURL(/\/invest$/, { timeout: 30_000 });
  for (const [path, ready, name] of [["/holdings", "My Holdings", "Money"], ["/tax-report", "Capital gains on your shares", "Money"], ["/options", "Options", "Trade"],
    ["/library", "librar", "Trade"], ["/research/IN/TCS", "TCS", "Invest"], ["/alerts", "Your stock alerts", "Invest"], ["/account", "Account", "Invest"]] as const) {
    await page.goto(path);
    await expect(page.locator("main").getByText(ready).first()).toBeVisible({ timeout: 30_000 });
    const side = await menu(page, phone);
    await expect(side.getByRole("radio", { name }), `${path} opens in ${name}`).toHaveAttribute("aria-checked", "true");
    if (name === "Money") await expect(side.getByRole("link", { name: path === "/holdings" ? "My Holdings" : "Tax report" })).toHaveClass(/active/);
  }
  // a deep link only switches the menu on this device; `/` still opens the space the person picked
  expect((await prefs(request, u)).space ?? null).toBeNull();
  // picking a space in the switcher makes it the home
  const side = await menu(page, phone);
  await side.getByRole("radio", { name: "Money" }).click();
  await expect.poll(async () => (await prefs(request, u)).space).toBe("money");
  await page.goto("/");
  await expect(page).toHaveURL(/\/money$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible();
  await sane(page, errors, phone);
});

test("onboarding: one short step asks what brings you here, with the experience, and opens that space", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(234, phone);
  expect((await prefs(request, u)).focus ?? null, "a brand-new account").toBeNull();
  const errors = await signIn(page, u, "/");
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  await expect(welcome).toBeVisible({ timeout: 30_000 });
  await expect(welcome.getByRole("button", { name: /^(Trade|Invest|Manage my money|All of it)/ })).toHaveCount(4);
  await expect(welcome.locator(".explore-card b")).toHaveText(["Trade", "Invest", "Manage my money", "All of it"]);
  const exp = welcome.getByRole("radiogroup", { name: "Experience" });
  await expect(exp.getByRole("radio", { name: "I've done a bit" })).toHaveAttribute("aria-checked", "true");
  if (phone) for (const el of await welcome.locator(".explore-card, [role=radio]").all()) {
    const b = await el.boundingBox();
    if (b && b.height) expect(b.height, `"${(await el.innerText()).slice(0, 30)}" is too small to tap`).toBeGreaterThanOrEqual(32);
  }
  await exp.getByRole("radio", { name: "I do this actively" }).click();
  await welcome.getByRole("button", { name: /Manage my money/ }).click();
  // one answer, one step: no second question, and the Money home opens
  await expect(welcome).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(/\/money$/);
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible();
  await expect.poll(() => prefs(request, u)).toEqual({ level: "pro", focus: "money", space: "money" });
  const side = await menu(page, phone);
  await expect(side.getByRole("radio", { name: "Money" })).toHaveAttribute("aria-checked", "true");
  await expect(side.getByRole("button", { name: "Add your holdings" })).toBeVisible();
  // answered once: not asked again
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await expect(page.getByRole("dialog", { name: "What brings you here?" })).toHaveCount(0);
  await sane(page, errors, phone);
});

test("space homes: Trade with Options first, Invest at a glance, Money with holdings, tax and its tools", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  // the owner: holdings and tradebooks are loaded by the fake world, and Basic tools are on
  const errors = await signIn(page, ADMIN, "/trade");
  await page.getByRole("button", { name: /All of it/ }).click({ timeout: 4000 }).catch(() => undefined);   // first visit of the run
  await expect(page.locator(".space-strip")).toBeVisible({ timeout: 30_000 });
  const strip = page.locator(".space-strip > a");
  await expect(strip.first()).toContainText("Options");
  await expect(strip.first()).toHaveAttribute("href", "/options");
  await expect(page.getByTestId("paper-summary")).not.toHaveText(/Checking/, { timeout: 30_000 });
  await expect(page.getByText(/Your notebooks|What trading idea/).first()).toBeVisible();
  await sane(page, errors, phone);

  await page.goto("/invest");
  await expect(page.getByRole("heading", { name: "Which company do you want to look into?" })).toBeVisible({ timeout: 30_000 });
  for (const t of ["Your watchlist", "Results today", "Red flags in your watchlist"]) await expect(page.getByText(t, { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Checking results dates|Reading your companies' filings/)).toHaveCount(0, { timeout: 30_000 });
  await sane(page, errors, phone);

  await page.goto("/money");
  await expect(page.getByRole("heading", { name: "Your money" })).toBeVisible({ timeout: 30_000 });
  const holdings = page.getByTestId("holdings-summary");
  await expect(holdings).toContainText(/Value · \d+ stocks/, { timeout: 30_000 });
  await expect(holdings).toContainText("₹");
  await expect(holdings.locator(".as-of")).toContainText("as of");
  const tax = page.getByTestId("tax-summary");
  await expect(tax).toContainText(/Capital gains tax, FY ?\d{4}/, { timeout: 30_000 });
  await expect(tax).toContainText("Assumes only the sales in the tradebooks you uploaded");       // every estimate says what it assumes
  await expect(tax.locator(".as-of")).toContainText("as of");
  // one card per Money feature that exists, and nothing for one that doesn't yet
  const cards = page.locator("[data-money]");
  await expect(cards).toHaveCount(NAV_GROUPS.Money.length);
  for (const e of NAV_GROUPS.Money) await expect(page.locator(`[data-money="${e.to}"]`)).toContainText(e.label);
  await sane(page, errors, phone);
  await cards.first().click();
  await expect(page).toHaveURL(new RegExp(NAV_GROUPS.Money[0].to + "$"));
});

test("search labels each result with its space", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await signIn(page, ADMIN, "/research");
  await page.getByRole("button", { name: /All of it/ }).click({ timeout: 4000 }).catch(() => undefined);
  await expect(page.getByText("Companies").first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: phone ? "Search or ask anything" : /Ask or do anything/ }).first().click();
  const box = page.getByRole("dialog", { name: "Ask or do anything" });
  await box.getByLabel("Search or ask anything").fill("tax report");
  await expect(box.getByRole("option", { name: /Tax report/ }).first().locator(".space-tag")).toHaveText("Money");
  await box.getByLabel("Search or ask anything").fill("options");
  await expect(box.getByRole("option", { name: /Paper trade options/ }).locator(".space-tag")).toHaveText("Trade");
  await box.getByLabel("Search or ask anything").fill("sector rotation");
  await expect(box.getByRole("option", { name: /^Sector rotation/ }).first().locator(".space-tag")).toHaveText("Invest");
  await box.getByLabel("Search or ask anything").fill("money");
  await box.getByRole("option", { name: /^Money/ }).first().click();
  await expect(page).toHaveURL(/\/money$/);
  expect(errors).toEqual([]);
});
