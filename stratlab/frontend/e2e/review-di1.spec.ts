import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// 25 Oct 2026, the deep audit of search, navigation, My space, the tour, Help and the briefs (DI-001 .. DI-033): the search
// finds Indian companies with the feed off and ranks them above "Do it", one home for "What you see first", the menu marks
// one page as current, Help has a way in, the tour points at what it describes on a phone, and My space keeps its order.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const who = (n: number, phone: boolean) => { const i = n + (phone ? 1 : 0); return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` }; };
type Who = ReturnType<typeof who>;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });
const prefs = async (request: APIRequestContext, u: Who) => (await (await request.get(`${API}/me`, { headers: auth(u) })).json()).prefs ?? {};

async function signIn(page: Page, u: Who, path: string, tourSeen = true) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: u.token, user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript(([s, seen]) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); if (seen) localStorage.setItem("stratlab.tour.v1", "1"); }, [session, tourSeen] as const);
  await page.goto(path);
  return errors;
}
const answer = (request: APIRequestContext, u: Who, focus: string, space = "all") => request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus, space } });
async function menu(page: Page, phone: boolean) {
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  return page.locator("aside.sidebar");
}

test("DI-032 / DP1-028: Esc closes the welcome question, and it isn't asked again", async ({ page, request }, info) => {
  const u = who(110, info.project.name === "phone");
  const errors = await signIn(page, u, "/", false);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  await expect(welcome).toBeVisible({ timeout: 30_000 });
  // the dialog moves focus into itself once it is ready for keys; pressing Esc the instant it is painted raced that in CI
  await expect.poll(() => welcome.evaluate((d) => d.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(welcome).toHaveCount(0);
  // closing it is "not now": no tour starts in its place
  await page.waitForTimeout(600);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect.poll(async () => (await (await request.get(`${API}/me`, { headers: auth(u) })).json()).onboarding?.welcome).toBeTruthy();
  await page.reload();
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  await expect(welcome).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("DI-001..004: with the live feed off, search still finds Indian companies, ranks them above Do it, and allows a typo", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const u = who(112, phone);
  const errors = await signIn(page, u, "/research");
  // a weekend: the instrument search has no Indian stocks at all
  await page.route((url) => url.pathname === "/instruments/search", (r) => r.fulfill({ status: 200, json: [] }));
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  if (phone) await page.getByRole("button", { name: "Search or ask anything" }).click();
  else await page.locator("aside.sidebar .search-btn").click();
  const pal = page.getByRole("dialog", { name: "Ask or do anything" });
  const box = pal.getByRole("textbox", { name: "Search or ask anything" });
  await box.fill("RELIANCE");
  const first = pal.locator(".palette-grp").first();
  await expect(first.locator(".palette-group")).toHaveText("Companies", { timeout: 15_000 });
  await expect(first.locator(".palette-row").first()).toContainText("RELIANCE");
  await expect(pal.locator('.palette-row[aria-selected="true"]')).not.toContainText("Do it");
  // a typo still finds the company
  await box.fill("relaince");
  await expect(pal.locator(".palette-grp").first().locator(".palette-group")).toHaveText("Companies", { timeout: 15_000 });
  await expect(pal.locator(".palette-grp").first()).toContainText(/Reliance/i);
  // a page's own name: the page first, no strategy ideas for it
  await box.fill("sign out");
  await expect(pal.locator(".palette-row").filter({ hasText: "Sign out" }).first()).toBeVisible();
  await expect(pal.locator(".palette-row", { hasText: "Options on your own signal" })).toHaveCount(0);
  await box.fill("settings");
  await expect(pal.locator(".palette-row").filter({ hasText: "Settings" }).first()).toBeVisible();
  await expect(pal.getByText(/Get strategy ideas/)).toHaveCount(0);
  await box.fill("dark mode");
  await expect(pal.locator('.palette-grp:has(.palette-group:text-is("Features")) .palette-row').first()).toContainText("Theme");
  // a phone has a close button, not an Esc key hint
  if (phone) {
    await expect(pal.locator(".esc-hint")).toBeHidden();
    await pal.getByRole("button", { name: "Close search" }).click();
    await expect(pal).toHaveCount(0);
  } else {
    // Enter on a company opens its page
    await box.fill("TCS");
    await expect(pal.locator(".palette-grp").first().locator(".palette-group")).toHaveText("Companies", { timeout: 15_000 });
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/research\/IN\/TCS$/);
  }
  expect(errors).toEqual([]);
});

test("DI-013, DI-016: `/` and the logo open the home of What you see first; the menu marks one page as current", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(114, phone);
  await answer(request, u, "both", "money");          // "All of it", with Money picked once in the switcher
  const errors = await signIn(page, u, "/trade");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  await page.goto("/");
  await expect(page).toHaveURL(/\/mine$/, { timeout: 30_000 });
  // one link is the page you are on
  for (const [path, current] of [["/research/watchlist", "Watchlist"], ["/research/investor", "Watchlist"], ["/settings#notifications", "Settings"]] as const) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
    const side = await menu(page, phone);
    const marked = side.locator('nav[aria-label="Main"] [aria-current="page"]');
    await expect(marked, path).toHaveCount(1);
    await expect(marked).toHaveText(current);
    if (phone) await page.getByRole("button", { name: "Close menu" }).click();
  }
  await page.goto("/plans");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  const side = await menu(page, phone);
  await expect(side.locator('nav[aria-label="Main"] [aria-current="page"]')).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Plans");
  expect(errors).toEqual([]);
});

test("DI-014, DI-022: Help is in the account menu and lists the explanations; Settings has its own icon, the plan is named once", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(116, phone);
  await answer(request, u, "trade");
  const errors = await signIn(page, u, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  const side = await menu(page, phone);
  await side.getByRole("button", { name: /account menu$/ }).click();
  const acct = page.getByRole("menu", { name: "Account" });
  await expect(acct.getByRole("menuitem", { name: "Account", exact: true })).toBeVisible();
  await expect(acct.locator(".plan-tag")).toHaveCount(1);
  await acct.getByRole("menuitem", { name: "Help", exact: true }).click();
  await expect(page).toHaveURL(/\/help$/);
  await expect(page.getByRole("heading", { level: 1, name: "Help" })).toBeVisible();
  const topics = page.getByTestId("help-topics");
  await expect(topics.locator("details")).not.toHaveCount(0);
  await expect(topics).toContainText("Walk-forward test");
  await expect(page.getByRole("link", { name: /Contact us/ }).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("DI-005, DI-006: My space keeps the chosen order, and the layout is kept on the account", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(118, phone);
  await answer(request, u, "money");
  const errors = await signIn(page, u, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Customise", exact: true }).click();
  await page.getByRole("button", { name: "Move Markets up" }).click();
  await page.getByRole("button", { name: "Move Markets up" }).click();
  await expect.poll(async () => (await prefs(request, u)).mine?.order?.slice(0, 3)).toEqual(["networth", "markets", "pnl"]);
  await page.getByRole("button", { name: "Done" }).click();
  const slots = page.locator(".mine-slot");
  await expect(slots.nth(1)).toHaveAttribute("data-card", "markets");
  if (!phone) {
    // drawn in that order: Markets is under Net worth, not beside Today's P&L with a gap above it
    const [nw, mk, pnl] = await Promise.all(["networth", "markets", "pnl"].map((c) => page.locator(`.mine-slot[data-card="${c}"]`).boundingBox()));
    expect(mk!.y).toBeGreaterThan(nw!.y + nw!.height - 2);
    expect(pnl!.y).toBeGreaterThan(mk!.y + mk!.height - 2);
  }
  // another browser (nothing in its storage) shows the same order
  await page.evaluate(() => localStorage.removeItem("stratlab.mine.cards"));
  await page.reload();
  await expect(page.locator(".mine-slot").nth(1)).toHaveAttribute("data-card", "markets", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("DI-023: on a phone the tour opens the menu for the steps about it, and step 3 names the space's own button", async ({ page, request }, info) => {
  test.skip(info.project.name !== "phone", "the phone's menu");
  const u = who(120, true);
  await answer(request, u, "money", "money");
  const errors = await signIn(page, u, "/money");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => window.dispatchEvent(new Event("stratlab:tour")));
  const tour = page.getByRole("dialog", { name: "A quick tour" });
  await expect(tour).toBeVisible();
  await expect(page.locator("aside.sidebar.open")).toHaveCount(1);
  await expect(page.locator("aside.sidebar .space-switch")).toBeInViewport();
  await tour.getByRole("button", { name: "Next" }).click();
  await tour.getByRole("button", { name: "Next" }).click();
  await expect(tour).toContainText("Add your holdings");
  await tour.getByRole("button", { name: "Next" }).click();
  await expect(tour).toContainText("Settings");
  await expect(page.locator("aside.sidebar .acct-btn")).toBeInViewport();
  await tour.getByRole("button", { name: "Done" }).click();
  await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("DI-029, DI-033: signed out, /app gives the install steps, and /help, /faq and /about each lead with their own heading", async ({ page }) => {
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto("/app");
  await expect(page.getByRole("heading", { level: 1, name: "Get the app" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("install-steps")).toContainText("Add to Home Screen");
  await expect(page).toHaveTitle("Get the app · StratLab");
  for (const [path, h] of [["/help", "Help"], ["/faq", "Questions"], ["/about", "About StratLab"]]) {
    await page.goto(path);
    const h1 = page.locator(".lp").getByRole("heading", { level: 1 });
    await expect(h1).toHaveText(h, { timeout: 30_000 });
    expect(await h1.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThan(30);    // the hero's heading, not an eyebrow
  }
});
