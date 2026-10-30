import { expect, test } from "@playwright/test";
import { NAV, startOf } from "../src/lib/nav";
import { sessionAs, open, sane, touchable, API, tab, menu, watchSharing, shared, copied } from "./pages-kit";

// Prices by visitor, plans, invoices, Home's first steps and launch offer, the menu, the footer's markets, the account menu and
// invites.

test.describe("a visitor from the UK", () => {
  test.use({ locale: "en-GB", timezoneId: "Europe/London" });
  // changed on purpose by item 34 (owner, 29 Oct): rupees first, the currency charged, with the dollar beside them, never pounds alone
  test("sees prices in rupees, with the dollar figure beside them", async ({ page }) => {
    const errors = await open(page, "/plans", "Plans");
    await expect(page.getByText("₹699 / month", { exact: true })).toBeVisible();
    await expect(page.getByTestId("about-basic")).toHaveText(/^about \$\d+$/);
    await expect(page.locator("main")).not.toContainText("£");
    await sane(page, errors);
  });
});

test.describe("a visitor in India", () => {
  test.use({ locale: "en-US", timezoneId: "Asia/Kolkata" });
  test("sees prices in rupees", async ({ page }) => {
    const errors = await open(page, "/plans", "Plans");
    await expect(page.getByText("₹699 / month", { exact: true })).toBeVisible();
    await expect(page.getByText("₹1,999 / month", { exact: true })).toBeVisible();
    await expect(page.getByText("incl. GST", { exact: true })).toHaveCount(2);        // next to each rupee price
    await sane(page, errors);
  });
});

test("plans: short cards, the full comparison, and backtests (not experiments)", async ({ page }, info) => {
  const errors = await open(page, "/plans", "Side by side");
  for (const line of ["Everything in Free, plus:", "Everything in Basic, plus:", "10 backtests a month, each with a full verdict",
    "2 company deep dives a month, each with the report card and checklist, and 1 company slide deck (its PDF and PowerPoint count as one)", "Indian F&O contracts (futures and options on stocks and indices) in notebooks, each backtested on its own past prices; the stocks themselves are on every plan",
    "Options paper trading on your own rules' signals, strikes picked by delta or premium, and what-if sliders with a roll preview"]) {
    await expect(page.locator(".k-plans li", { hasText: line })).toBeVisible();
  }
  for (const card of await page.locator(".k-plans > .k-card").all()) expect(await card.locator("li").count()).toBeLessThanOrEqual(9);
  expect(await page.locator("main").innerText()).not.toMatch(/experiment/i);
  await page.getByTestId("plans-compare-fold").locator("summary").first().click();          // the comparison is one fold under the cards (LIVE1C-092)
  const table = page.locator("#compare");        // one table for each group (how much, what each plan adds, on every plan), each with the plan names on top
  const row = (label: string) => table.locator("tr", { has: page.getByText(label, { exact: true }) }).locator("td");
  await expect(row("Backtests a month, each with a verdict")).toHaveText(["Backtests a month, each with a verdict", "10", "100", "Unlimited"]);
  await expect(row("Company deep dives a month")).toHaveText(["Company deep dives a month", "2", "15", "Unlimited"]);
  await expect(row("Trades the journal keeps")).toHaveText(["Trades the journal keeps", "50", "Unlimited", "Unlimited"]);
  await expect(row("All 20+ indicators in strategy rules")).toHaveText(["All 20+ indicators in strategy rules", "–", "✓", "✓"]);
  await expect(row("Trade notifications")).toHaveText(["Trade notifications", "–", "✓", "✓"]);
  await expect(row("Indian F&O in notebooks and backtests")).toHaveText(["Indian F&O in notebooks and backtests", "–", "–", "✓"]);   // Basic's options paper trading is its own row (R54-008)
  // what every plan has is one folded list, and what each plan adds is under its own subheadings (DP1-022, DI-032)
  await expect(table.getByRole("heading", { name: "Trading" })).toBeVisible();
  await expect(table.getByRole("heading", { name: "Money and tax" })).toBeVisible();
  await table.getByText(/^On every plan \(\d+ tools\)$/).click();
  await expect(table.locator("li", { hasText: "Red flags on every company page" })).toBeVisible();
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});

test("invoices: in Account for the customer, with the GST setup in Admin", async ({ page }) => {
  let errors = await open(page, "/account", "Invoices");
  await expect(page.getByText("Details on your invoices")).toBeVisible();
  await sane(page, errors);
  // the seller form is one click away, its values summed up above it (DJ-018)
  errors = await open(page, "/admin/money", "Edit the invoice details");
  await expect(page.getByTestId("invoice-summary")).toContainText("GSTIN");
  await page.getByTestId("invoice-edit").locator("summary").click();
  await expect(page.getByText("LUT ARN")).toBeVisible();
  await expect(page.getByText(/financial year \d{4}-\d{2}/i).first()).toBeVisible();
  await sane(page, errors);
});

test("first steps on Home tick themselves from real data, and hide for good", async ({ page, request }, info) => {
  // each project signs in as its own brand-new user, so hiding the list on one doesn't hide it on the other
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["free-token", "u-free", "free@example.com"];
  const auth = { Authorization: `Bearer ${token}` };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });     // skip the welcome questions
  expect((await request.put(`${API}/me/first-steps`, { headers: auth, data: { dismissed: false } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/research/watchlist`, { headers: auth, data: { items: [{ region: "IN", symbol: "TCS" }] } })).ok()).toBeTruthy();
  const errors = await open(page, "/", "Your first steps", sessionAs(token, id, email));
  const list = page.locator(".first-steps");
  // My space shows the checklist as one line with the next step (LIVE1B-086): the watchlist step is done, so one of five
  await expect(list).toContainText(/Your first steps · 1 of 5 done · next:/);
  await expect(list.getByRole("link")).toHaveCount(1);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  expect((await request.get(`${API}/research/deep/RELIANCE?region=IN`, { headers: auth })).ok()).toBeTruthy();
  await page.reload();
  await expect(list).toContainText(/2 of 5 done/, { timeout: 30_000 });

  await list.getByRole("button", { name: "Hide this" }).click();
  await expect(page.getByText("Your first steps")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Net worth", { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  await expect(page.getByText("Your first steps")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("the launch offer counts down on Home and Plans", async ({ page }, info) => {
  const until = new Date(Date.now() + (2 * 24 + 5) * 3600_000 + 10 * 60_000).toISOString();
  await page.route(`${API}/me`, async (r) => {
    const res = await r.fetch();
    await r.fulfill({ response: res, json: { ...(await res.json()), promo: { until } } });
  });
  let errors = await open(page, "/", "Launch offer:");
  await expect(page.locator(".promo-countdown")).toContainText("2 days 5 hours");
  await expect(page.getByText("Launch offer:")).toHaveCount(1);              // the countdown replaces the site-wide note here
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  await page.locator(".promo-countdown").getByRole("button", { name: "Got it" }).click();      // put away on Home (R45A-010)
  await expect(page.locator(".promo-countdown")).toHaveCount(0);
  errors = await open(page, "/plans", "Launch offer:");
  await expect(page.locator(".promo-countdown")).toContainText("2 days 5 hours");
  await sane(page, errors);
});

test("the tools grid shows every group at once, and the menu reaches Account without scrolling", async ({ page }, info) => {
  const errors = await open(page, "/new", "What trading idea do you want to test?");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 4000 }).catch(() => undefined);   // the experience question
  // every group of tools shows at once: no "Show N more tools" button folds them away
  await expect(page.getByRole("button", { name: /Show \d+ more tools/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Options builder/ })).toBeVisible();          // IA-1: under Practise, by its menu name
  if (info.project.name === "desktop") await expect(page.getByRole("button", { name: /account menu$/ })).toBeInViewport();
  await sane(page, errors);
});

test("the menu (IA-1): a space's short list of entries, the one you are in lit, each opening its tabs, old links still open", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  // the owner's account is shared with every other test: keep this test's space choices out of it
  await page.route("**/me/prefs", (r) => (r.request().method() === "PUT" ? r.fulfill({ json: { prefs: {} } }) : r.fallback()));
  // ...and reads them as already answered, so the first-visit question doesn't come back on every page load
  await page.route(/\/me(\?.*)?$/, async (r) => {
    if (r.request().method() !== "GET") return r.fallback();
    const res = await r.fetch();
    const me = await res.json();
    await r.fulfill({ response: res, json: { ...me, prefs: { ...(me.prefs || {}), level: me.prefs?.level ?? "some", focus: me.prefs?.focus ?? "invest" } } });
  });
  const errors = await open(page, "/research", "Companies");
  await page.evaluate(() => { localStorage.removeItem("stratlab.side.groups"); localStorage.setItem("stratlab.space", "invest"); });
  await page.reload();
  let side = await menu(page, phone);
  const main = side.getByRole("navigation", { name: "Main" });
  const space = side.getByRole("group", { name: "Space" });
  await expect(space.getByRole("button")).toHaveText(["My space", "Trade", "Invest", "Money"]);
  await expect(space.getByRole("button", { name: "Invest" })).toHaveAttribute("aria-pressed", "true");
  // Invest: its home, then its seven entries; the other spaces' entries wait behind the switcher
  const entries = main.locator(".side-entries > .side-entry > .side-head > a");
  await expect(entries).toHaveText(NAV.invest.groups.map((g) => g.label));
  for (const g of ["Practise", "Strategies", "Tax", "Plan", "Portfolio"]) await expect(main.getByRole("link", { name: g, exact: true })).toHaveCount(0);
  await expect(main.getByRole("link", { name: "Invest home" })).toHaveAttribute("href", "/invest");
  // IA-2 (item 36): the page you are on is the one lit (its section's heading only bold); its section is open with its pages, the
  // others folded, each heading with more than one page has its open/close button; each heading opens its first page
  await expect(main.getByRole("link", { name: "Look up a company", exact: true })).toHaveClass(/active/);
  await expect(main.getByRole("link", { name: "Look up a company", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(main.getByRole("link", { name: "Companies", exact: true })).toHaveClass(/in-section/);
  await expect(main.locator(".side-entries a.active")).toHaveCount(1);
  await expect(main.locator(".side-toggle")).toHaveCount(NAV.invest.groups.filter((g) => g.pages.length > 1).length);
  await expect(main.getByRole("button", { name: "Companies pages" })).toHaveAttribute("aria-expanded", "true");
  await expect(main.getByRole("button", { name: "Find stocks pages" })).toHaveAttribute("aria-expanded", "false");
  for (const g of NAV.invest.groups) await expect(main.locator(`[data-group="${g.id}"] > .side-head > a`)).toHaveAttribute("href", startOf(g, "invest"));
  await expect(main.getByRole("link", { name: "Scans", exact: true })).toHaveCount(0);       // no catch-all "Scans" entry any more
  // the footer is two slim lines: the markets now and the account button; the menu above is the only part that scrolls
  const foot = side.locator(".side-foot");
  await expect(foot.getByRole("button", { name: /^India (open|closed) · \d+\/\d+ markets open$/ })).toBeVisible();
  await expect(foot.getByRole("button", { name: /Pro plan, account menu$/ })).toBeVisible();
  expect((await foot.boundingBox())!.height, "the footer stays slim").toBeLessThanOrEqual(100);
  const scrolls = await side.evaluate((aside) => [aside, ...aside.querySelectorAll("*")].filter((el) => /(auto|scroll)/.test(getComputedStyle(el).overflowY)).map((el) => el.className));
  expect(scrolls, "one scrolling part in the sidebar").toEqual(["side-groups"]);
  if (phone) for (const el of await side.locator("a, button").all()) {
    const b = await el.boundingBox();
    if (b && b.height) expect(b.height, `"${(await el.innerText().catch(() => "")).slice(0, 30)}" is too small to tap`).toBeGreaterThanOrEqual(32);
  }

  // an entry opens its first tab; the tabs are the pages that were entries, each at its own address
  await main.getByRole("link", { name: "Find stocks", exact: true }).click();
  await expect(page).toHaveURL(/\/research\/screens$/);
  await expect(page.getByTestId("hub-tabs").locator("a")).toHaveText(["Figures", "Chart rules", "Filings"]);
  await tab(page, phone, "Find stocks", "Chart rules");
  await expect(page).toHaveURL(/\/research\/scan$/);
  await expect(page.getByRole("navigation", { name: "Scans" }), "no old second row of tabs").toHaveCount(0);
  await expect(page.locator(".research-nav, .sub-seg")).toHaveCount(0);
  side = await menu(page, phone);
  // IA-2 (item 36): the page is the one lit, under its heading (bold, open)
  await expect(side.locator('#side-sub-find-stocks a[href="/research/scan"]')).toHaveClass(/active/);
  await expect(side.getByRole("link", { name: "Find stocks", exact: true })).toHaveClass(/in-section/);
  await side.getByRole("link", { name: "Market today", exact: true }).click();
  await expect(page).toHaveURL(/\/research\/pulse$/);
  await tab(page, phone, "Market today", "Sectors");
  await expect(page).toHaveURL(/\/research\/rotation$/);
  side = await menu(page, phone);
  await expect(side.locator('#side-sub-market-today a[href="/research/rotation"]')).toHaveClass(/active/);
  await expect(side.getByRole("link", { name: "Market today", exact: true })).toHaveClass(/in-section/);
  await expect(side.getByRole("link", { name: "Find stocks", exact: true })).not.toHaveClass(/active|in-section/);    // one entry lit at a time
  await expect(side.locator("nav .active")).toHaveCount(1);
  // an entry's page of cards is the breadcrumb's middle link
  if (phone) await page.getByRole("button", { name: "Close menu" }).click();
  await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Market today" }).click();
  await expect(page).toHaveURL(/\/invest\/g\/market-today$/);
  await expect(page.getByTestId("group-card")).toHaveCount(5);
  // the old addresses still work, the old groups' pages too
  await page.goto("/research/scans");
  await expect(page).toHaveURL(/\/research\/scan$/);
  await page.goto("/scans");
  await expect(page).toHaveURL(/\/research\/scan$/);
  await page.goto("/watchlist");
  await expect(page).toHaveURL(/\/research\/watchlist$/);
  await page.goto("/all");
  await expect(page).toHaveURL(/\/mine$/);
  await page.goto("/scans?q=banks#top");                                       // a moved address keeps its query and hash
  await expect(page).toHaveURL(/\/research\/scan\?q=banks#top$/);
  await page.goto("/invest/g/market-view");
  await expect(page).toHaveURL(/\/invest\/g\/market-today$/);

  // Watchlist: the list and "at a glance" are two views of one page, a switch inside it; the entry's tabs stay above both
  await page.goto("/research/watchlist");
  await expect(page.getByText("Companies you're watching").first()).toBeVisible({ timeout: 30_000 });
  const views = page.getByRole("radiogroup", { name: "Watchlist view" });
  await expect(views.getByRole("radio")).toHaveText(["List", "At a glance"]);
  await views.getByRole("radio", { name: "At a glance" }).click();
  await expect(page).toHaveURL(/\/research\/investor$/);
  await expect(page.getByRole("radiogroup", { name: "Watchlist view" }).getByRole("radio", { name: "At a glance" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("hub-tabs").locator("a")).toHaveText(["Stocks", "Alerts"]);

  // the keyboard: Tab from the search button passes the space's home and lands on the first entry, with a visible focus ring
  side = await menu(page, phone);
  await side.getByRole("button", { name: /Ask or do anything/ }).focus();
  await page.keyboard.press("Tab");
  await expect(side.getByRole("link", { name: "Invest home" })).toBeFocused();
  await page.keyboard.press("Tab");
  const first = side.locator(".side-entries > .side-entry > .side-head > a").first();
  await expect(first).toBeFocused();
  expect(await first.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("solid");
  await sane(page, errors);
});

test("the menu shows Admin only to admins", async ({ page }, info) => {
  await open(page, "/research", "Companies", sessionAs("free-token", "u-free", "free@example.com"));
  const side = await menu(page, info.project.name === "phone");
  await side.getByRole("button", { name: /Free plan, account menu$/ }).click();
  const acct = side.getByRole("menu", { name: "Account" });
  await expect(acct.getByRole("menuitem", { name: /^Account/ })).toBeVisible();
  await expect(acct.getByRole("menuitem", { name: "Admin" })).toHaveCount(0);
});

test("the markets now: one line in the footer that opens the list, by mouse or keyboard, and Esc or a click outside closes it", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research", "Companies");
  const side = await menu(page, phone);
  const btn = side.getByRole("button", { name: /^India (open|closed) · \d+\/\d+ markets open$/ });
  const [, , total] = (await btn.innerText()).match(/(\d+)\/(\d+) markets/)!.map(Number);
  await expect(btn).toHaveAttribute("aria-expanded", "false");
  const footBefore = (await side.locator(".side-foot").boundingBox())!.height;
  await btn.click();
  const pop = page.getByRole("dialog", { name: "Markets now" });
  await expect(pop).toBeVisible();
  await expect(btn).toHaveAttribute("aria-expanded", "true");
  // one row per market, each with what it's doing now; as many open as the line said
  const rows = pop.getByRole("listitem");
  await expect(rows).toHaveCount(total);
  for (const r of await rows.all()) await expect(r).toHaveText(/(Open 24\/7|Closes in|Opens in|Holiday|Data offline|Closed)/);
  // the count is re-read now: a market can open or close between reading the line and opening the list
  await expect(async () => {
    const now = Number((await btn.innerText()).match(/(\d+)\/\d+ markets/)![1]);
    expect(await pop.locator(".mkt-dot.on").count()).toBe(now);
  }).toPass({ timeout: 5_000 });
  // it floats: the sidebar's footer and menu keep their size
  expect((await side.locator(".side-foot").boundingBox())!.height).toBe(footBefore);
  const box = (await pop.boundingBox())!;
  const vp = page.viewportSize()!;
  if (phone) {
    // a sheet from the bottom of the screen, full width, with its own close button
    expect(Math.round(box.y + box.height)).toBe(vp.height);
    expect(Math.round(box.width)).toBe(vp.width);
    await pop.getByRole("button", { name: "Close" }).click();
    await expect(pop).toHaveCount(0);
    await btn.click();
  } else expect(box.y + box.height).toBeLessThanOrEqual((await btn.boundingBox())!.y);
  // Esc closes it and hands focus back; the drawer on a phone stays open
  await page.keyboard.press("Escape");
  await expect(pop).toHaveCount(0);
  await expect(btn).toBeFocused();
  await expect(btn).toHaveAttribute("aria-expanded", "false");
  if (phone) await expect(page.locator("aside.sidebar.open")).toHaveCount(1);
  // the keyboard opens it too, with a visible focus ring on the line
  expect(await btn.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("solid");
  await page.keyboard.press("Enter");
  await expect(pop).toBeVisible();
  await expect(pop).toBeFocused();
  // a click anywhere else closes it
  await page.mouse.click(phone ? 5 : vp.width - 20, 5);
  await expect(pop).toHaveCount(0);
  await sane(page, errors);
});

test("the account menu: Account, Settings, Plan, Invite, Get the app, Admin, All features, Help, the tour and Sign out, with arrow keys and Esc", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research", "Companies");
  let side = await menu(page, phone);
  const btn = side.getByRole("button", { name: /Pro plan, account menu$/ });
  await expect(btn).toContainText("Account");
  await expect(btn).toContainText("Pro");
  await btn.click();
  const acct = page.getByRole("menu", { name: "Account" });
  await expect(acct).toBeVisible();
  // the plan is named once, on Plan; Help opens the help page and the tour is its own item (DI-014, DI-022)
  await expect(acct.getByRole("menuitem")).toHaveText(["Account", "Settings", /^Plan\s*Pro$/, "Invite friends", "Get the app", "Admin", "All features", "Help", "Take the tour", "Sign out"]);
  for (const [name, href] of [["Account", "/account"], ["Settings", "/settings"], ["Plan", "/plans"], ["Invite friends", "/invite"], ["Get the app", "/app"], ["All features", "/features"], ["Help", "/help"]])
    await expect(acct.getByRole("menuitem", { name })).toHaveAttribute("href", href);
  if (phone) {
    for (const el of await acct.getByRole("menuitem").all()) expect((await el.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    const box = (await acct.boundingBox())!;
    expect(Math.round(box.y + box.height)).toBe(page.viewportSize()!.height);
  }
  // the first item has focus; arrows, Home and End move through the items, and Esc closes the menu
  const items = acct.getByRole("menuitem");
  await expect(items.first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(items.nth(1)).toBeFocused();
  expect(await items.nth(1).evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("solid");
  await page.keyboard.press("End");
  await expect(items.last()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(items.first()).toBeFocused();
  await page.keyboard.press("ArrowUp");
  await expect(items.last()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(acct).toHaveCount(0);
  await expect(btn).toBeFocused();

  // the theme moved to Settings (e2e/account.spec.ts flips it both ways)
  await btn.click();
  await expect(acct.getByRole("menuitem", { name: /mode$/ })).toHaveCount(0);
  await page.keyboard.press("Escape");

  // Take the tour opens the tour
  await btn.click();
  await acct.getByRole("menuitem", { name: "Take the tour" }).click();
  await expect(page.getByRole("tablist", { name: "Tour steps" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^(Close|Skip|Done)/ }).first().click({ timeout: 2000 }).catch(() => undefined);
  await expect(page.getByRole("tablist", { name: "Tour steps" })).toHaveCount(0);

  // Account and Admin open their pages (and close the drawer on a phone)
  side = await menu(page, phone);
  await btn.click();
  await acct.getByRole("menuitem", { name: "Admin" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  if (phone) await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
  side = await menu(page, phone);
  await btn.click();
  await acct.getByRole("menuitem", { name: /^Account/ }).click();
  await expect(page).toHaveURL(/\/account$/);
  await sane(page, errors);

  // Sign out ends the session on this device
  side = await menu(page, phone);
  await btn.click();
  await acct.getByRole("menuitem", { name: "Sign out" }).click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("sb-demo-auth-token"))).toBeNull();
  await expect(page.locator("aside.sidebar")).toHaveCount(0, { timeout: 15_000 });
});

test("invite: your invite link, how many friends joined, and sharing it", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await watchSharing(page);
  const errors = await open(page, "/invite", "Invite friends");
  await expect(page.getByTestId("friends-joined")).toHaveText(/^6 friends joined · 3 free months earned$/);
  // plain words: what a friend gets, and what you get on your plan (the owner is on Pro, so the time is kept, never "a month of Basic" now)
  const words = page.getByTestId("invite-reward-line");
  await expect(words).toContainText("What a friend gets. A friend who joins with your link and uses StratLab on 3 different days in their first 2 weeks gets a month of Basic free.");
  // what you get is a point a line, not one dense paragraph (DP2-035)
  const got = words.getByRole("listitem");
  await expect(got).toHaveText(["A month of Basic for each of your first 2 friends a year who use StratLab on 3 days in their first 2 weeks.",
    "A month of Basic for each of your first 2 friends a year who subscribe.", "After that, 8 more days for each friend who subscribes, up to 8 times a year.",
    "You're on Pro, so it's kept for you and starts only if your Pro plan stops."]);
  await expect(words).not.toContainText("You get a month of Basic");
  const status = page.getByTestId("invite-status");
  for (const [k, v] of [["This year: friends who used StratLab", "2 of 2 months"], ["This year: friends who subscribed", "1 of 2 months"],
    ["Waiting to subscribe", "1 friend"], ["Kept for when your plan stops", /days of Basic|Nothing yet/]] as const) {
    await expect(status.locator("div", { hasText: k })).toContainText(v);
  }
  await expect(status).not.toContainText(/Use:|Extra:|weeks/);
  for (const id of ["invite-reward-line", "invite-status"]) {      // nothing spills past the card
    const box = (await page.getByTestId(id).boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
  await expect(page.getByLabel("Your invite link")).toHaveValue(/\/\?ref=[A-Za-z0-9_-]{12}$/);
  if (phone) await touchable(page);
  await page.getByRole("button", { name: "Share your link" }).click();
  const link = await page.getByLabel("Your invite link").inputValue();
  if (phone) await expect.poll(async () => (await shared(page)).map((s) => s.url)).toEqual([link]);
  else {
    await expect.poll(() => copied(page)).toEqual([link]);
    await expect(page.getByRole("status")).toContainText("Invite link copied");
  }
  await sane(page, errors);
});

test("an invite link is remembered through sign-in, sent once, and taken out of the address", async ({ page }) => {
  const sent: unknown[] = [];
  await page.route("**/me/referral", async (r) => { sent.push(r.request().postDataJSON()); await r.fulfill({ status: 200, contentType: "application/json", body: '{"recorded":false}' }); });
  const errors = await open(page, "/?ref=AbCdEf123_-x", "Net worth");
  await expect.poll(() => sent).toEqual([{ code: "AbCdEf123_-x" }]);
  expect(new URL(page.url()).search).toBe("");
  await page.reload();
  await expect(page.getByText("Net worth").filter({ visible: true }).first()).toBeVisible();
  await page.waitForTimeout(500);
  expect(sent, "sent only once").toHaveLength(1);
  await sane(page, errors);
});

test("admin: invite counts in Users and growth", async ({ page }, info) => {
  const errors = await open(page, "/admin/users", "Paper trading now");
  await expect(page.getByRole("table", { name: "Users" }).getByRole("columnheader", { name: /Invited/ })).toHaveCount(0);           // a click away, so the table fits a laptop
  await page.getByTestId("cols-admin-users").click();
  await expect(page.getByRole("table", { name: "Users" }).getByRole("columnheader", { name: /Invited/ })).toBeVisible();
  await expect(page.getByRole("table", { name: "Users" }).getByRole("columnheader", { name: /Free months/ })).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("admin: invite rewards waiting for review are approved or rejected", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/admin/users", "Invite rewards");
  const panel = page.getByTestId("invite-rewards");
  await expect(panel.getByText("Waiting for your review")).toBeVisible();
  await expect(panel.locator("tr", { hasText: "load3@example.com" })).toBeVisible();          // given
  await expect(panel.getByRole("columnheader", { name: /^Reward/ })).toBeVisible();
  await expect(panel.locator("tr", { hasText: "load3@example.com" }).getByTestId("reward-type")).toHaveText("Use");
  await expect(panel.locator("tr", { hasText: "load6@example.com" }).getByTestId("reward-type")).toHaveText("Payment");
  await expect(panel.locator("tr", { hasText: "load5@example.com" }).getByTestId("reward-type")).toHaveText("Waiting to subscribe");
  if (phone) await touchable(page);
  // each run decides its own row: desktop rejects one, phone approves the other
  const row = panel.locator("tr", { hasText: phone ? "load2@example.com" : "load1@example.com" }).filter({ has: page.getByRole("button") });
  await row.getByRole("button", { name: phone ? "Approve" : "Reject" }).click();
  await expect(page.getByRole("status")).toContainText(phone ? "Approved" : "Rejected");
  await expect(row).toHaveCount(0);
  await sane(page, errors);
});

test("account: free Basic from invites shows on the plan", async ({ page }, info) => {
  const errors = await open(page, "/account", "Plan and usage", sessionAs("load-3", "u-load-3", "load3@example.com"));
  await expect(page.getByText("Free Basic from invites")).toBeVisible();
  await expect(page.getByText("Basic (free from invites)")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
  await page.goto("/invite");
  await expect(page.getByTestId("friends-joined")).toHaveText("0 friends joined · 1 free month earned");
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});
