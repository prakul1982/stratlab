import { expect, test, type Page } from "@playwright/test";
import { ALL_PAGES, NAV, groupPath } from "../src/lib/nav";

// Navigation: the sidebar is the only menu (no second row of tabs), group titles open a page of cards, every page has a
// breadcrumb whose last part lists its neighbours, "All features" lists every page, and ⌘K finds pages by everyday words.
// Signed in as the owner; the choices of space are kept out of the shared account.
const SHOTS = process.env.E2E_SHOTS;
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

async function sideMenu(page: Page, phone: boolean) {
  if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
  const side = page.locator("aside.sidebar");
  await expect(side.getByRole("navigation", { name: "Main" })).toBeVisible();
  return side;
}

test("a group's title opens its page: one card for each feature, with its name, a line on what it is for and a link", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/g/market-view");
  const g = NAV.invest.groups.find((x) => x.id === "market-view")!;
  const cards = page.getByTestId("group-card");
  await expect(cards).toHaveCount(g.pages.length, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Market view", level: 1 })).toBeVisible();
  for (const p of g.pages) {
    const card = cards.filter({ has: page.getByRole("link", { name: p.label, exact: true }) });
    await expect(card, p.label).toHaveCount(1);
    await expect(card.getByRole("link", { name: p.label, exact: true })).toHaveAttribute("href", p.to);
    await expect(card.locator(".nav-card-line")).toHaveText(p.blurb);
    await expect(card.getByRole("link", { name: `Open ${p.label}` })).toHaveAttribute("href", p.to);
  }
  // the breadcrumb ends at the group, the sidebar title is lit, and a card opens its page
  const crumb = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumb).toHaveText(/Invest\s*›\s*Market view/);
  await expect(crumb.getByRole("link", { name: "Invest", exact: true })).toHaveAttribute("href", "/invest");
  const side = await sideMenu(page, phone);
  await expect(side.locator('[data-group="market-view"] .side-title')).toHaveClass(/active/);
  await expect(side.getByRole("button", { name: "Market view", exact: true })).toHaveAttribute("aria-expanded", "true");
  if (SHOTS) {
    if (phone) await page.getByRole("button", { name: "Close menu" }).click();
    for (const scheme of ["dark", "light"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.screenshot({ path: `${SHOTS}/group-${phone ? "400" : "1300"}-${scheme}.png`, fullPage: true });
    }
  }
  if (phone) await page.getByRole("button", { name: "Close menu" }).click().catch(() => undefined);
  await cards.filter({ hasText: "Margin funding" }).getByRole("link", { name: "Open Margin funding" }).click();
  await expect(page).toHaveURL(/\/invest\/margin-funding$/);
  expect(errors).toEqual([]);
  // an unknown group goes to the list of every feature
  await page.goto("/invest/g/nothing-here");
  await expect(page).toHaveURL(/\/features$/);
});

test("every page has a breadcrumb: space, group and page, and the page's menu lists its neighbours", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/margin-funding");
  const crumb = page.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumb).toHaveText(/Invest\s*›\s*Market view\s*›\s*Margin funding/, { timeout: 30_000 });
  if (SHOTS) {
    if (phone) await page.getByRole("button", { name: "Close menu" }).click().catch(() => undefined);
    for (const scheme of ["dark", "light"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await crumb.getByRole("button", { name: /Margin funding/ }).click();
      await page.screenshot({ path: `${SHOTS}/breadcrumb-${phone ? "400" : "1300"}-${scheme}.png`, fullPage: false });
      await page.keyboard.press("Escape");
    }
  }
  // the menu opens on a click, moves with the arrow keys, closes with Esc and gives focus back
  const button = crumb.getByRole("button", { name: /Margin funding/ });
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
  const menu = page.getByRole("menu", { name: /Pages near Margin funding/ });
  await expect(menu.getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(menu.getByRole("menuitem").nth(1)).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(button).toBeFocused();
  // a neighbour is one click away
  await button.click();
  await menu.getByRole("menuitem", { name: "Stock lending fees" }).click();
  await expect(page).toHaveURL(/\/invest\/stock-lending$/);
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toHaveText(/Market view\s*›\s*Stock lending fees/);
  // "All of Market view" goes to the group's page
  await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("button", { name: /Stock lending fees/ }).click();
  await page.getByRole("menuitem", { name: "All of Market view" }).click();
  await expect(page).toHaveURL(/\/invest\/g\/market-view$/);

  // a few pages from other spaces and ones that were tabs or deeper
  for (const [path, trail] of [
    ["/trade/signals", /Trade\s*›\s*Build and test\s*›\s*Forward test/], ["/trade/positioning/stocks", /Trade\s*›\s*F&O desk\s*›\s*Positioning/],
    ["/research/IN/TCS", /Invest\s*›\s*Companies\s*›\s*Look up a company/], ["/research/investor", /Invest\s*›\s*Watch\s*›\s*Watchlist/],
    ["/money/calendar", /Money\s*›\s*Plan\s*›\s*Money calendar/], ["/holdings", /Money\s*›\s*What you own\s*›\s*Holdings/], ["/notebooks", /Trade\s*›\s*Build and test\s*›\s*Notebooks/],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("navigation", { name: "Breadcrumb" }), path).toHaveText(trail, { timeout: 30_000 });
  }
  expect(errors).toEqual([]);
});

test("the second rows of tabs are gone: Watchlist and Positioning switch views with a switch inside the page", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/pulse");
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toBeVisible({ timeout: 30_000 });
  for (const path of ["/research", "/research/pulse", "/research/scan", "/research/screens", "/research/rotation", "/research/results", "/invest/breadth", "/research/watchlist", "/trade/positioning"]) {
    await page.goto(path);
    await expect(page.getByRole("navigation", { name: "Breadcrumb" }), path).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".research-nav, .sub-seg, .pos-tabs, nav.seg"), `${path} has no row of tabs`).toHaveCount(0);
  }
  // Positioning: index view and stock futures are two views of one page
  await page.goto("/trade/positioning");
  const pos = page.getByRole("radiogroup", { name: "Positioning view" });
  await expect(pos.getByRole("radio")).toHaveText(["Index and participants", "Stock futures"]);
  await expect(pos.getByRole("radio", { name: "Index and participants" })).toHaveAttribute("aria-checked", "true");
  await pos.getByRole("radio", { name: "Stock futures" }).click();
  await expect(page).toHaveURL(/\/trade\/positioning\/stocks$/);
  await expect(page.getByRole("radiogroup", { name: "Positioning view" }).getByRole("radio", { name: "Stock futures" })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("radiogroup", { name: "Positioning view" }).getByRole("radio", { name: "Index and participants" }).click();
  await expect(page).toHaveURL(/\/trade\/positioning$/);
  if (phone) await expect(page.getByRole("radiogroup", { name: "Positioning view" })).toBeInViewport();
  // the market switch is a kit switch now, and keeps working
  await page.goto("/research/watchlist");
  const market = page.getByRole("radiogroup", { name: "Market" });
  await market.getByRole("radio", { name: "$ United States" }).click();
  await expect(market.getByRole("radio", { name: "$ United States" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText(/United States/).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("All features lists every page by space and group, is linked from the account menu and ⌘K, and narrows as you type", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/mine");
  const side = await sideMenu(page, phone);
  await side.getByRole("button", { name: /^Account menu/ }).click();
  await side.getByRole("menuitem", { name: "All features" }).click();
  await expect(page).toHaveURL(/\/features$/);
  const features = page.getByTestId("features-page");
  await expect(features.getByRole("heading", { name: "All features", level: 1 })).toBeVisible();
  // every page, each under its group, linking to its address, with a line on what it is for
  for (const { space, group, page: p } of ALL_PAGES) {
    const section = features.getByRole("region", { name: `${NAV[space].label}: ${group.label}` });
    const row = section.locator("li").filter({ has: page.getByRole("link", { name: p.label, exact: true }) });
    await expect(row, `${p.label} under ${group.label}`).toHaveCount(1);
    await expect(row.getByRole("link", { name: p.label, exact: true })).toHaveAttribute("href", p.to);
    await expect(row.locator(".feat-line")).toHaveText(p.line);
  }
  await expect(features.getByRole("link", { name: "Market view", exact: true })).toHaveAttribute("href", groupPath("invest", "market-view"));
  // "New" marks what shipped lately
  await expect(features.getByRole("region", { name: "Invest: Market view" }).locator("li").filter({ hasText: "Margin funding" })).toContainText("New");
  // narrowing, and a friendly message when nothing matches
  await features.getByLabel("Narrow the list of features").fill("tax");
  await expect(features.getByRole("link", { name: "Tax report", exact: true })).toBeVisible();
  await expect(features.getByRole("link", { name: "Chart replay", exact: true })).toHaveCount(0);
  await features.getByLabel("Narrow the list of features").fill("zzzzzz");
  await expect(features.getByText("No page matches that")).toBeVisible();
  await features.getByRole("button", { name: "Show everything" }).click();
  await expect(features.getByRole("link", { name: "Chart replay", exact: true })).toBeVisible();

  // ⌘K: the empty box offers it, and typing finds it
  await page.getByRole("button", { name: phone ? "Search or ask anything" : /Ask or do anything/ }).first().click();
  const box = page.getByRole("dialog", { name: "Ask or do anything" });
  await expect(box.getByRole("option", { name: /^All features/ })).toBeVisible();
  await box.getByLabel("Search or ask anything").fill("all features");
  await box.getByRole("option", { name: /^All features/ }).first().click();
  await expect(page).toHaveURL(/\/features$/);
  expect(errors).toEqual([]);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/features-${phone ? "400" : "1300"}-light.png`, fullPage: true });
});

test("⌘K finds every page, including by everyday words: MTF and 'borrowed money' find Margin funding", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  const ask = async (q: string) => {
    if (!(await page.getByRole("dialog", { name: "Ask or do anything" }).count())) await page.getByRole("button", { name: phone ? "Search or ask anything" : /Ask or do anything/ }).first().click();
    const box = page.getByRole("dialog", { name: "Ask or do anything" });
    await box.getByLabel("Search or ask anything").fill(q);
    return box;
  };
  for (const [q, name, space] of [["MTF", "Margin funding", "Invest"], ["borrowed money", "Margin funding", "Invest"], ["SLB", "Stock lending fees", "Invest"],
    ["advance tax", "Tax tools", "Money"], ["lot size", "F&O changes", "Trade"]] as const) {
    const box = await ask(q);
    const first = box.getByRole("option").filter({ has: page.locator(".space-tag") }).first();
    await expect(first, q).toContainText(name);
    await expect(first.locator(".space-tag")).toHaveText(space);
  }
  // every page opens from its own name
  for (const { page: p } of ALL_PAGES) {
    const box = await ask(p.label);
    await expect(box.getByRole("option", { name: new RegExp(`^${p.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) }).first(), p.label).toBeVisible();
  }
  // choosing a page by its everyday word opens it
  const box = await ask("MTF");
  await box.getByRole("option", { name: /^Margin funding/ }).first().click();
  await expect(page).toHaveURL(/\/invest\/margin-funding$/);
  expect(errors).toEqual([]);
});

test("Forward test explains itself in one plain line, and the old Signal forward test name is gone", async ({ page }) => {
  const errors = await open(page, "/trade/signals");
  await expect(page.getByRole("heading", { name: "Forward test", level: 1 })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".k-lede")).toContainText("tries a strategy on days that have not happened yet");
  await expect(page.getByText("Signal forward test")).toHaveCount(0);
  expect(errors).toEqual([]);
});
