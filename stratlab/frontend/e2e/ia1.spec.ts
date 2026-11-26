import { expect, test, type Page } from "@playwright/test";
import { ALL_PAGES, NAV } from "../src/lib/nav";

// IA-1 (owner, 29 Oct): 42 menu entries became 14, each a page of tabs, nothing removed. Every address the menu had opens its
// page as the right tab of the right entry; the one Calendar's All dates lists every type of date with its filters, each space's
// Calendar entry opens it pre-filtered for that space; Market today has a Flows tab; Help lists every page by its old name.
// Signed in as the fake world's owner; the space choices are kept out of the shared account.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/me/prefs", (r) => (r.request().method() === "PUT" ? r.fulfill({ json: { prefs: {} } }) : r.fallback()));
  await page.route(/\/me(\?.*)?$/, async (r) => {
    if (r.request().method() !== "GET") return r.fallback();
    const res = await r.fetch();
    const me = await res.json();
    await r.fulfill({ response: res, json: { ...me, prefs: { ...(me.prefs || {}), level: "some", focus: "invest" } } });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}

// a /me read still in flight when a test ends must not fail it: its route callback would fetch on a closed page (CI #323)
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

test("every page of the menu opens at its own address as the right tab of its entry", async ({ page }) => {
  test.setTimeout(240_000);
  const errors = await open(page, "/invest");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  for (const { group, page: p } of ALL_PAGES) {
    await page.goto(p.to);
    await expect(page.getByRole("heading", { level: 1 }).first(), p.to).toBeVisible({ timeout: 30_000 });
    await expect(page, `${p.to} stays at its address`).toHaveURL(new RegExp(`${p.to.replace(/[/]/g, "\\/")}(\\?.*)?$`));
    // (changed on purpose, cal94, owner 26 Nov: one Calendar fixed in the sidebar): the Calendar's addresses are its filters, a row inside it, not tabs
    if (group.pages.length > 1 && !group.fixed) {
      const tabs = page.getByTestId("hub-tabs");
      await expect(tabs, p.to).toHaveAttribute("aria-label", group.label);
      // (updated on purpose, R43: a tab may carry a shorter name where its entry's name says the rest, NavPage.tab, so the row of tabs
      // stays on the breadcrumb's line at 1280 (ui-lint R17); the breadcrumb and the menu keep the full name)
      await expect(tabs.locator("a")).toHaveText(group.pages.map((t) => t.tab ?? t.label));
      await expect(tabs.locator("[aria-current=page]"), p.to).toHaveText(p.tab ?? p.label);
    } else await expect(page.getByTestId("hub-tabs"), p.to).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

// (changed on purpose, cal94, owner 26 Nov: one Calendar fixed in the sidebar): one Calendar entry in the sidebar's top part in every
// space and none inside the spaces' menus; it opens on the dates for where you are; one row of filters inside it switches, the choice in
// the address and remembered per space; its old addresses land on their filter; search still finds it.
test("the one Calendar: fixed in the sidebar, opening on each space's dates; its filters are the address, kept per space; All has every type", async ({ page }, info) => {
  test.setTimeout(180_000);
  const phone = info.project.name === "phone";
  const errors = await open(page, "/trade");
  const side = page.locator("aside.sidebar");
  const row = page.getByRole("group", { name: "Which dates" });
  const pressed = row.locator('[aria-pressed="true"]');
  const menu = async () => { if (phone) await page.getByRole("button", { name: "Open menu" }).click(); };
  // each space: one entry, fixed above the menu, none in the space's own list; it opens that space's dates
  for (const [space, label, url, on] of [["trade", "Trade", /\/trade\/events(\?.*)?$/, /^Market events & expiries$/], ["invest", "Invest", /\/calendar$/, /^(My stocks|All)$/],
    ["money", "Money", /\/money\/calendar(\?.*)?$/, /^My money dates$/]] as const) {
    await page.goto(NAV[space].home);
    await menu();
    await expect(side.getByRole("group", { name: "Space" }).getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
    await expect(side.getByTestId("side-calendar")).toHaveCount(1);
    await expect(side.locator(".side-top").getByTestId("side-calendar")).toHaveText("Calendar");
    await expect(side.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Calendar", exact: true })).toHaveCount(0);
    await expect(side.locator('[data-group="calendar"]')).toHaveCount(0);
    await side.getByTestId("side-calendar").click();
    await expect(page).toHaveURL(url);
    await expect(pressed).toHaveText(on, { timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toHaveText(new RegExp(`^${label}\\s*›\\s*Calendar`));
    await expect(page.getByTestId("hub-tabs")).toHaveCount(0);
    await menu();
    await expect(side.getByTestId("side-calendar")).toHaveAttribute("aria-current", "page");
    if (phone) await page.getByRole("button", { name: "Close menu" }).click();
  }
  // My space too: one entry, the same place
  await page.goto("/mine");
  await menu();
  await expect(side.getByTestId("side-calendar")).toHaveCount(1, { timeout: 30_000 });
  await expect(side.getByTestId("side-calendar")).toHaveAttribute("href", "/calendar");
  if (phone) await page.getByRole("button", { name: "Close menu" }).click();

  // All: one table, a header row, every type of date the fake world has this week and next, in date order
  await page.goto("/calendar?show=all");
  const all = page.getByTestId("cal-all");
  await expect(all.getByRole("row").nth(1)).toBeVisible({ timeout: 30_000 });
  await expect(pressed).toHaveText("All");
  await expect(page.getByTestId("cal-count")).toContainText(/\d+ dates? from /);
  const types = phone ? null : await all.locator("tbody tr td:nth-child(2)").allInnerTexts();
  if (types) for (const t of ["Results", "Corporate action", "IPO", "Market event"]) expect(types, t).toContain(t);
  if (!phone) expect((await all.locator("tbody tr th, tbody tr td:first-child").allInnerTexts()).length).toBeGreaterThan(3);
  // every company: size and sector are there
  await expect(page.getByRole("group", { name: "Company size" })).toBeVisible({ timeout: 30_000 });
  // a filter narrows it, and is the address: IPOs only, linking to the IPOs table
  await row.getByRole("button", { name: "IPOs", exact: true }).click();
  await expect(page).toHaveURL(/\/calendar\?show=ipos$/);
  await expect(page.getByRole("heading", { level: 1, name: "IPO dates" })).toBeVisible();
  if (!phone) await expect.poll(async () => [...new Set(await all.locator("tbody tr td:nth-child(2)").allInnerTexts())]).toEqual(["IPO"]);
  await expect(page.getByTestId("cal-count").getByRole("link", { name: "IPOs" })).toHaveAttribute("href", "/invest/ipos");
  // a row opens its own page: an IPO's detail page
  await all.getByRole("link").first().click();
  await expect(page).toHaveURL(/\/invest\/ipos\/[^/]+$/);
  await page.goBack();
  // My stocks: your companies' dates, no size or sector
  await row.getByRole("button", { name: "My stocks", exact: true }).click();
  await expect(page).toHaveURL(/\/calendar\?show=mine$/);
  await expect(page.getByRole("heading", { level: 1, name: "My stocks' dates" })).toBeVisible();
  await expect(page.getByTestId("cal-count")).toContainText(/\d+ dates? from /, { timeout: 30_000 });
  await expect(page.getByRole("group", { name: "Company size" })).toHaveCount(0);
  // remembered per space: Invest's Calendar opens on My stocks now, Trade's still on the market events
  await page.goto("/calendar");
  await expect(pressed).toHaveText("My stocks", { timeout: 30_000 });
  await page.goto("/invest");
  await menu();
  await expect(side.getByTestId("side-calendar")).toHaveAttribute("href", "/calendar?show=mine", { timeout: 30_000 });
  if (phone) await page.getByRole("button", { name: "Close menu" }).click();
  await page.goto("/trade");
  await menu();
  await expect(side.getByTestId("side-calendar")).toHaveAttribute("href", "/trade/events", { timeout: 30_000 });
  if (phone) await page.getByRole("button", { name: "Close menu" }).click();
  // the old addresses land on their filter
  for (const [to, on] of [["/trade/events", "Market events & expiries"], ["/money/calendar", "My money dates"], ["/calendar?type=ipo", "IPOs"], ["/calendar?scope=all", "All"]] as const) {
    await page.goto(to);
    await expect(pressed, to).toHaveText(on, { timeout: 30_000 });
  }
  // the filter stays in the address, so a link shares it
  await page.goto("/calendar?show=actions");
  await expect(pressed).toHaveText("Dividends & splits", { timeout: 30_000 });
  await expect(page.getByRole("heading", { level: 1, name: "Dividends & splits" })).toBeVisible();
  // search still finds it: "calendar", "expiry", "tax due"
  for (const [q, name] of [["calendar", /^Calendar/], ["expiry", /Market events & expiries/], ["tax due", /My money dates/]] as const) {
    if (!(await page.getByRole("dialog", { name: "Ask or do anything" }).count())) await page.getByRole("button", { name: phone ? "Search or ask anything" : /Ask or do anything/ }).first().click();
    const box = page.getByRole("dialog", { name: "Ask or do anything" });
    await box.getByLabel("Search or ask anything").fill(q);
    await expect(box.getByRole("option", { name }).first(), q).toBeVisible({ timeout: 15_000 });
  }
  expect(errors).toEqual([]);
});

// cal94: each space home has a small "Coming up" card with a "See calendar" link to the Calendar on that home's filter
test("Coming up on every home: Trade, Invest, Money and My space each link to the Calendar on their own dates", async ({ page }) => {
  test.setTimeout(120_000);
  const errors = await open(page, "/trade");
  for (const [home, card, to] of [["/trade", "trade-coming", "/trade/events"], ["/invest", "invest-events", "/calendar"], ["/money", "money-coming", "/money/calendar"], ["/mine", "mine-coming", "/calendar"]] as const) {
    await page.goto(home);
    const c = page.getByTestId(card);
    await expect(c.getByRole("heading", { name: "Coming up" }), home).toBeVisible({ timeout: 30_000 });
    await expect(c.getByTestId("see-calendar"), home).toHaveAttribute("href", to);
    await expect(c.getByTestId("see-calendar")).toContainText("See calendar");
  }
  // following Money's lands on the money dates, inside Money's menu
  await page.getByTestId("mine-coming").getByTestId("see-calendar").click();
  await expect(page).toHaveURL(/\/calendar$/);
  await page.goto("/money");
  await page.getByTestId("money-coming").getByTestId("see-calendar").click();
  await expect(page).toHaveURL(/\/money\/calendar$/);
  await expect(page.getByRole("group", { name: "Which dates" }).locator('[aria-pressed="true"]')).toHaveText("My money dates", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("Market today's Flows tab: the latest day's FII and DII figures as a table, with every recorded day", async ({ page }, info) => {
  const errors = await open(page, "/research/pulse");
  // the tabs: beside the breadcrumb on a laptop, in the breadcrumb's menu on a phone
  if (info.project.name === "phone") {
    await expect(page.getByTestId("hub-tabs")).toBeHidden({ timeout: 30_000 });
    await page.getByRole("navigation", { name: "Breadcrumb" }).locator(".k-crumb-btn").click();
    await page.getByRole("menuitem", { name: "Flows", exact: true }).click();
  } else await page.getByRole("navigation", { name: "Market today" }).getByRole("link", { name: "Flows" }).click();
  await expect(page).toHaveURL(/\/invest\/flows$/);
  await expect(page.getByRole("heading", { level: 1, name: "Flows" })).toBeVisible({ timeout: 30_000 });
  const latest = page.getByTestId("flows-latest");
  await expect(latest.getByRole("columnheader")).toHaveText(["Who", "Bought", "Sold", "Net"]);
  await expect(latest.getByRole("row", { name: /FII\/FPI/ })).toContainText(/[▲▼] [+−]₹[\d,]+ cr/);
  // the fake world's owner is on Pro: every recorded day, with a total row
  const days = page.getByTestId("flows-days");
  await expect(days.getByRole("row").last()).toContainText(/days?, total/);
  expect(errors).toEqual([]);
});

test("Help lists every page by the name it had and where it is now, and the one box narrows it", async ({ page }) => {
  const errors = await open(page, "/help");
  const places = page.getByTestId("help-places");
  await expect(places.getByRole("row")).toHaveCount(ALL_PAGES.length + 1, { timeout: 30_000 });
  await page.getByLabel("Narrow the pages and explanations").fill("screener");
  await expect(places.getByRole("row", { name: /Screener/ })).toContainText("Invest › Find stocks › Figures");
  await places.getByRole("link", { name: "Invest › Find stocks › Figures" }).click();
  await expect(page).toHaveURL(/\/research\/screens$/);
  expect(errors).toEqual([]);
});
