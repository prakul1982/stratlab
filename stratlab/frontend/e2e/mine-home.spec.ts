import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { CARDS } from "../src/lib/mineLayout";

// "My space" (/mine, was "All"): a greeting with the date and one line on what is coming up, hero tiles (net worth, today's
// P&L, paper sessions), a strip of six markets, the dates ahead and the watchlist's movers. Every figure is from data the
// app already has; a card with nothing says so and offers the next step. Cards can be hidden and reordered. Desktop and phone.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const who = (n: number, phone: boolean) => { const i = n + (phone ? 1 : 0); return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` }; };
const ADMIN = { token: "admin-token", id: "u-admin", email: "owner@example.com" };
type Who = ReturnType<typeof who>;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });
const SHOTS = process.env.E2E_SHOTS;

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
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /yahoo|finnhub|screener\.in|kite|zerodha/i, /\byou should\b/i, /\b(buy|sell) (this|now)\b/i]) expect(text).not.toMatch(bad);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main a")).filter((el) => {
    const b = el.getBoundingClientRect();
    return b.width && b.height && !el.closest("p, li, .search-box") && !el.matches(".info-btn") && getComputedStyle(el).display !== "inline" && b.height < 32;
  }).map((el) => `${el.tagName} "${(el.textContent || "").trim().slice(0, 30)}"`));
  expect(small, "controls too small to tap").toEqual([]);
}

/** The cards on the page, in the order they show. */
const order = (page: Page) => page.locator(".mine-slot").evaluateAll((els) => els.map((e) => e.getAttribute("data-card")));

test("my space: opens from / for 'all of it', with a greeting, six cards and a friendly empty state where a new account has nothing", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(250, phone);
  await answer(request, u, "both");
  const errors = await signIn(page, u, "/");
  await expect(page).toHaveURL(/\/mine$/, { timeout: 30_000 });
  const home = page.getByTestId("mine-home");
  await expect(home.getByRole("heading", { level: 1 })).toContainText(/^Good (morning|afternoon|evening)/);
  await expect(home.locator(".k-eyebrow")).toContainText(new RegExp(`^${new Date().toLocaleDateString("en-GB", { weekday: "long" })}, ${new Date().getDate()} ${new Date().toLocaleDateString("en-GB", { month: "long" })}$`));
  await expect(home.locator(".k-lede")).not.toBeEmpty();
  expect(await order(page)).toEqual(CARDS.map((c) => c.id));

  // a new account has no net worth, holdings or paper sessions: each card says so and offers the next step; nothing is invented
  for (const [id, name, link] of [["mine-networth", "Add what you own", "/money/net-worth"], ["mine-pnl", "Add your holdings", "/holdings"], ["mine-paper", "Start paper trading", "/paper"]] as const) {
    const card = page.getByTestId(id);
    await expect(card.getByRole("link", { name })).toHaveAttribute("href", link, { timeout: 30_000 });
    await expect(card).not.toContainText("₹");
  }
  await expect(page.getByTestId("mine-watch")).toContainText(/Your watchlist is empty|No prices yet/, { timeout: 30_000 });

  // the markets strip: the six names, each with a level or a plain "not available"; never a made-up number
  const strip = page.getByTestId("mine-markets");
  await expect(strip.locator(".mine-mkt")).toHaveText(["NIFTY 50", "SENSEX", "BANK NIFTY", "S&P 500", "USD/INR", "Gold"].map((n) => new RegExp(`^${n.replace("/", "\\/")}`)));
  await expect(strip.locator(".k-skel")).toHaveCount(0, { timeout: 30_000 });
  // coming up: dated rows from the calendars (the tax dates are the law's own), each with its day
  const coming = page.getByTestId("mine-coming");
  await expect(coming.locator(".mine-tl-i, .k-state").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".k-skel-box")).toHaveCount(0, { timeout: 30_000 });

  await sane(page, errors, phone);
  await page.emulateMedia({ colorScheme: "dark" });
  await sane(page, errors, phone);
  const bg = await page.evaluate(() => getComputedStyle(document.querySelector(".k-card")!).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/mine-new-${phone ? "400" : "1300"}-dark.png`, fullPage: true });
  }
});

test("my space: the owner's net worth, holdings and sessions fill the tiles", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await signIn(page, ADMIN, "/mine");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 1500 }).catch(() => undefined);
  await page.getByRole("button", { name: /All of it/ }).click({ timeout: 2000 }).catch(() => undefined);
  await page.goto("/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".k-skel-box")).toHaveCount(0, { timeout: 30_000 });
  // the holdings are loaded by the fake world: the tile shows a rupee figure, or says why it has none
  const pnl = page.getByTestId("mine-pnl");
  await expect(pnl).toContainText(/₹|needs live prices/);
  await expect(pnl.getByRole("link", { name: "Holdings" })).toHaveAttribute("href", "/holdings");
  // a link on every card leads to the page the figure comes from
  await expect(page.getByTestId("mine-coming").getByRole("link", { name: "Calendar" })).toHaveAttribute("href", "/money/calendar");
  await expect(page.getByTestId("mine-watch").getByRole("link", { name: "All" })).toHaveAttribute("href", "/research/watchlist");
  await sane(page, errors, phone);
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/mine-owner-${phone ? "400" : "1300"}-light.png`, fullPage: true });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.screenshot({ path: `${SHOTS}/mine-owner-${phone ? "400" : "1300"}-dark.png`, fullPage: true });
  }
});

test("my space: Customise hides, shows and reorders the cards, and remembers it", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(252, phone);
  await answer(request, u, "both");
  const errors = await signIn(page, u, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Customise" }).click();
  const panel = page.locator("#mine-customise");
  await expect(panel.getByRole("checkbox")).toHaveCount(6);
  // hide Markets and move Coming up to the top
  await panel.getByRole("checkbox", { name: "Markets" }).uncheck();
  await expect(page.getByTestId("mine-markets")).toHaveCount(0);
  for (let i = 0; i < 4; i++) await panel.getByRole("button", { name: "Move Coming up up" }).click();
  expect((await order(page))[0]).toBe("coming");
  await expect(panel.getByRole("button", { name: "Move Coming up up" })).toBeDisabled();
  await panel.getByRole("button", { name: "Done" }).click();
  await expect(panel).toHaveCount(0);
  // kept: after a reload the cards are as left
  await page.reload();
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  expect(await order(page)).toEqual(["coming", "networth", "pnl", "paper", "watch"]);
  await expect(page.getByTestId("mine-markets")).toHaveCount(0);
  // reset puts everything back
  await page.getByRole("button", { name: "Customise" }).click();
  await page.locator("#mine-customise").getByRole("button", { name: "Reset" }).click();
  expect(await order(page)).toEqual(CARDS.map((c) => c.id));
  // hiding every card leaves one calm message and a way back
  for (const c of CARDS) await page.locator("#mine-customise").getByRole("checkbox", { name: c.label }).uncheck();
  await expect(page.getByText("Every card is hidden")).toBeVisible();
  await page.getByRole("button", { name: "Show the cards" }).click();
  expect(await order(page)).toEqual(CARDS.map((c) => c.id));
  await sane(page, errors, phone);
});

test("my space: the menu has My space, Pinned, Briefs and Connected accounts; a page pinned from its breadcrumb shows under Pinned", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(254, phone);
  await answer(request, u, "money");
  const errors = await signIn(page, u, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("radio", { name: "Mine" })).toHaveAttribute("aria-checked", "true");
  await expect(side.getByRole("link", { name: "My space" })).toHaveClass(/active/);
  await expect(side.locator('[data-group="pinned"]')).toContainText("Pin a page from the menu in its breadcrumb");
  await expect(side.getByRole("link", { name: "Briefs" })).toHaveAttribute("href", "/news");
  await expect(side.getByRole("link", { name: "Connected accounts" })).toHaveAttribute("href", "/holdings");
  if (phone) await page.getByRole("button", { name: "Close menu" }).click();

  // pin Margin funding from its own breadcrumb menu
  await page.goto("/invest/margin-funding");
  const crumb = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumb.getByRole("link", { name: "Invest", exact: true })).toHaveAttribute("href", "/invest");
  await expect(crumb.getByRole("link", { name: "Market view" })).toHaveAttribute("href", "/invest/g/market-view");
  await crumb.getByRole("button", { name: /Margin funding/ }).click();
  const menu = page.getByRole("menu", { name: /Pages near Margin funding/ });
  await expect(menu.getByRole("menuitem")).toHaveText(["Market pulse", "Market breadth", "Sector rotation", "ETF vs NAV", "Margin funding", "Stock lending fees", "All of Market view", "Pin to sidebar"]);
  await expect(menu.getByRole("menuitem", { name: "Margin funding" })).toHaveAttribute("aria-current", "page");
  await menu.getByRole("menuitem", { name: "Pin to sidebar" }).click();
  await expect(menu).toHaveCount(0);
  // Mine's menu lists it, and opening it keeps Mine's menu
  await page.goto("/mine");
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  const pinned = side.locator('[data-group="pinned"]');
  await expect(pinned.getByRole("link", { name: "Margin funding" })).toHaveAttribute("href", "/invest/margin-funding");
  await pinned.getByRole("link", { name: "Margin funding" }).click();
  await expect(page).toHaveURL(/\/invest\/margin-funding$/);
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  await expect(side.getByRole("radio", { name: "Mine" })).toHaveAttribute("aria-checked", "true");
  await expect(side.locator('[data-group="pinned"]').getByRole("link", { name: "Margin funding" })).toHaveClass(/active/);
  if (phone) await page.getByRole("button", { name: "Close menu" }).click();
  // kept after a reload; unpin removes it
  await page.reload();
  await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("button", { name: /Margin funding/ }).click();
  await page.getByRole("menuitem", { name: "Unpin from sidebar" }).click();
  await page.goto("/mine");
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  await expect(side.locator('[data-group="pinned"]')).toContainText("Pin a page from the menu in its breadcrumb");
  await sane(page, errors, phone);
});
