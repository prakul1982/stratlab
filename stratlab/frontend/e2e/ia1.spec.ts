import { expect, test, type Page } from "@playwright/test";
import { ALL_PAGES, NAV, startOf } from "../src/lib/nav";

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
    if (group.pages.length > 1) {
      const tabs = page.getByTestId("hub-tabs");
      await expect(tabs, p.to).toHaveAttribute("aria-label", group.label);
      await expect(tabs.locator("a")).toHaveText(group.pages.map((t) => t.label));
      await expect(tabs.locator("[aria-current=page]"), p.to).toHaveText(p.label);
    } else await expect(page.getByTestId("hub-tabs"), p.to).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test("each space's Calendar entry opens the one Calendar pre-filtered for that space; All dates has every type, its filters and links", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/calendar");
  const all = page.getByTestId("cal-all");
  await expect(all.getByRole("row").nth(1)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("cal-count")).toContainText(/\d+ dates? from /);
  // one table: a header row, every type of date the fake world has this week and next, in date order
  const types = phone ? null : await all.locator("tbody tr td:nth-child(2)").allInnerTexts();
  if (types) for (const t of ["Results", "Corporate action", "IPO", "Market event"]) expect(types, t).toContain(t);
  if (!phone) {
    const days = await all.locator("tbody tr th, tbody tr td:first-child").allInnerTexts();
    expect(days.length).toBeGreaterThan(3);
  }
  // the type chips narrow it: IPOs only
  const chips = page.getByRole("group", { name: "Type" });
  for (const t of ["Results", "Corporate actions", "Market events", "My money dates"]) await chips.getByRole("button", { name: t }).click();
  await expect(chips.getByRole("button", { name: "IPOs" })).toHaveAttribute("aria-pressed", "true");
  if (!phone) await expect.poll(async () => [...new Set(await all.locator("tbody tr td:nth-child(2)").allInnerTexts())]).toEqual(["IPO"]);
  // every company: size and sector appear
  await page.getByRole("radiogroup", { name: "Companies" }).getByRole("radio", { name: "Every company" }).click();
  await expect(page).toHaveURL(/scope=all/);
  await expect(page.getByRole("group", { name: "Company size" })).toBeVisible({ timeout: 30_000 });
  // a row opens its own page: an IPO's detail page
  await all.getByRole("link").first().click();
  await expect(page).toHaveURL(/\/invest\/ipos\/[^/]+$/);
  // each space's menu entry: Trade on the market events, Invest on every date, Money on the person's own
  for (const [space, label] of [["trade", "Trade"], ["invest", "Invest"], ["money", "Money"]] as const) {
    await page.goto(NAV[space].home);
    if (phone) await page.getByRole("button", { name: "Open menu" }).click();
    const side = page.locator("aside.sidebar");
    await expect(side.getByRole("group", { name: "Space" }).getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
    const cal = NAV[space].groups.find((g) => g.id === "calendar")!;
    await side.getByRole("link", { name: "Calendar", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${startOf(cal, space).replace(/[/]/g, "\\/")}$`));
    await expect(page.getByTestId("hub-tabs")).toHaveAttribute("aria-label", "Calendar");
  }
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
