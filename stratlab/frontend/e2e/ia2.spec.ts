import { expect, test, type Page } from "@playwright/test";
import { NAV, startOf } from "../src/lib/nav";

// IA-2 (owner, 30 Oct). Item 37: Market Watch's button on a laptop, both ways the owner is choosing between (lib/mwButton.ts):
// "float" (the default) keeps the round button, in a real margin clear of the cards; "menu" makes the menu's market line the Markets
// button and has no floating one from 901 to 1599px. ?mwButton= on any address picks one and keeps it.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
/** A user of the fake world of its own for each project, so the desktop and phone runs never share a Market Watch layout. */
const who = (phone: boolean) => { const n = phone ? 147 : 141; return session(`load-${n}`, `u-load-${n}`, `load${n}@example.com`); };

async function open(page: Page, path: string, s: object, width: number, height = 800) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width, height });
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.addInitScript((x) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1");
    // each test starts with Market Watch shut and no choice kept
    if (!sessionStorage.getItem("fresh")) {
      sessionStorage.setItem("fresh", "1");
      for (const k of Object.keys(localStorage)) if (k.startsWith("stratlab.watch.") || k === "stratlab.mwButton" || k === "stratlab.side.slim") localStorage.removeItem(k);
    }
  }, s);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 2500 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}
const floating = (page: Page) => page.getByTestId("markets-launch");
const menuLine = (page: Page) => page.getByTestId("markets-menu");
const watch = (page: Page) => page.getByTestId("market-watch");

for (const width of [1280, 1440]) {
  test(`item 37, "float" at ${width}: the round button opens Market Watch; the menu's market line still lists the markets`, async ({ page }, info) => {
    test.skip(info.project.name === "phone", "a laptop's widths");
    const errors = await open(page, "/invest?mwButton=float", who(false), width);
    await expect(page.locator("body")).toHaveAttribute("data-mw-button", "float");
    const btn = floating(page);
    await expect(btn).toBeVisible({ timeout: 30_000 });
    expect((await btn.boundingBox())!.width).toBeCloseTo(44, 0);
    await expect(btn).toHaveAccessibleName("Open Market Watch");
    await expect(menuLine(page)).toHaveCount(0);
    await expect(page.locator(".side-foot .mkt-btn")).toHaveAttribute("aria-haspopup", "dialog");
    await btn.click();
    await expect(watch(page)).toBeVisible({ timeout: 30_000 });
    expect(errors).toEqual([]);
  });

  test(`item 37, "menu" at ${width}: no floating button; the menu's Markets line opens Market Watch`, async ({ page }, info) => {
    test.skip(info.project.name === "phone", "a laptop's widths");
    const errors = await open(page, "/invest?mwButton=menu", who(false), width);
    await expect(page.locator("body")).toHaveAttribute("data-mw-button", "menu");
    const line = menuLine(page);
    await expect(line).toBeVisible({ timeout: 30_000 });
    await expect(floating(page)).toBeHidden();
    // a clear button: its name, the candles and the word, a finger's height, inside the menu's foot
    await expect(line).toHaveAccessibleName("Open Market Watch");
    await expect(line).toContainText("Markets");
    await expect(line).toContainText(/(India (open|closed) · )?\d+\/\d+ markets open/);
    // the state fits beside the word, never cut
    expect(await line.locator(".mkt-mw-state").evaluate((e) => e.scrollWidth <= e.clientWidth + 1)).toBe(true);
    await expect(line.locator("svg")).toHaveCount(1);
    const box = (await line.boundingBox())!;
    expect(box.height).toBeGreaterThanOrEqual(36);
    expect(await line.evaluate((e) => !!e.closest(".side-foot"))).toBe(true);
    // the focus ring shows from the keyboard
    await line.focus();
    expect(await line.evaluate((e) => getComputedStyle(e).outlineStyle)).not.toBe("none");
    await line.click();
    await expect(watch(page)).toBeVisible({ timeout: 30_000 });
    expect(errors).toEqual([]);
  });
}

test(`item 37, "float" at 1280: the button sits at least 16px clear of every card on Invest, in the page's right margin`, async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a laptop's width");
  await open(page, "/invest", who(false), 1280);
  await expect(page.locator("body")).toHaveAttribute("data-mw-button", "float");          // the default until the owner picks
  const btn = floating(page);
  await expect(btn).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main .k-card").first()).toBeVisible({ timeout: 30_000 });
  const b = (await btn.boundingBox())!;
  const cards = await page.locator("main .k-card").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, r: r.right, b: r.bottom }; })
    .filter((r) => r.r > r.x));
  expect(cards.length).toBeGreaterThan(0);
  // the gap to each card on the nearer side: beside it, or above or below it (the page scrolls under the fixed button)
  const near = cards.map((c) => Math.max(b.x - c.r, c.x - (b.x + b.width)));
  expect(Math.min(...near), "the button's distance from the nearest card's edge").toBeGreaterThanOrEqual(16);
  // centred in the margin: as far from the cards as from the window's edge
  const margin = 1280 - Math.max(...cards.map((c) => c.r));
  expect(Math.abs((1280 - (b.x + b.width)) - (b.x - (1280 - margin)))).toBeLessThanOrEqual(2);
  expect(b.y + b.height).toBeCloseTo(800 - 16, 0);                                      // its bottom where it was
  // the page still fits: no sideways scroll
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});

test(`item 37: the choice is kept from page to page, a menu folded away keeps the floating button, and from 1600px the pill keeps its word`, async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a laptop's widths");
  await open(page, "/invest?mwButton=menu", who(false), 1280);
  await expect(menuLine(page)).toBeVisible({ timeout: 30_000 });
  await page.goto("/research/screens");
  await expect(page.locator("body")).toHaveAttribute("data-mw-button", "menu");
  await expect(menuLine(page)).toBeVisible({ timeout: 30_000 });
  await expect(floating(page)).toBeHidden();
  // the menu folded away: Market Watch is still one press away
  await page.getByRole("button", { name: "Hide the menu" }).click();
  await expect(floating(page)).toBeVisible();
  await page.getByRole("button", { name: "Show the menu" }).click();
  await expect(floating(page)).toBeHidden();
  // 1600px: the floating pill with its word, in both ways
  await page.setViewportSize({ width: 1600, height: 900 });
  await expect(floating(page)).toBeVisible();
  await expect(floating(page)).toContainText("Markets");
  await page.goto("/research/screens?mwButton=float");
  await expect(page.locator("body")).toHaveAttribute("data-mw-button", "float");
  await expect(floating(page)).toContainText("Markets");
});

test(`item 37, "menu" on a phone: the menu sheet's Markets line opens Market Watch and shuts the menu`, async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's menu sheet");
  await open(page, "/invest?mwButton=menu", who(true), 390, 844);
  await page.getByRole("button", { name: "Open menu" }).click();
  const line = menuLine(page);
  await expect(line).toBeVisible({ timeout: 30_000 });
  await line.click();
  await expect(watch(page)).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
});

// Item 36 (owner, 30 Oct: "you have squeezed the menu bar too much"): the 14 headings stay, and under each heading are its pages, the same
// pages, names and locks as its tabs. The section you are in is open, the others fold behind a disclosure button, and what the person
// opened or folded is kept. A heading with one page has no list. The current page is marked.
const side = (page: Page) => page.locator("aside.sidebar");
const mainNav = (page: Page) => side(page).getByRole("navigation", { name: "Main" });

test("item 36: each heading lists its pages; the section you are in is open, the others fold, and the choice is kept", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the phone's sheet has its own test below");
  const errors = await open(page, "/research/screens", who(false), 1280);
  const nav = mainNav(page);
  await expect(nav.locator(".side-entries > .side-entry > .side-head > a")).toHaveText(NAV.invest.groups.map((g) => g.label), { timeout: 30_000 });
  // Find stocks is open with its pages, as its tabs name them; Figures is the page marked
  const find = NAV.invest.groups.find((g) => g.id === "find-stocks")!;
  const sub = nav.locator("#side-sub-find-stocks");
  await expect(sub.getByRole("link")).toHaveText(find.pages.map((p) => p.label));
  await expect(page.getByTestId("hub-tabs").getByRole("link")).toHaveText(find.pages.map((p) => p.label));
  for (const p of find.pages) await expect(sub.getByRole("link", { name: p.label, exact: true })).toHaveAttribute("href", p.to);
  await expect(sub.getByRole("link", { name: "Figures", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(nav.locator("[aria-current=page]")).toHaveCount(1);
  await expect(nav.getByRole("link", { name: "Find stocks", exact: true })).not.toHaveClass(/active/);      // never two selected at once
  // the others are folded behind their buttons; a heading with one page has none
  for (const g of NAV.invest.groups) {
    const btn = nav.getByRole("button", { name: `${g.label} pages`, exact: true });
    if (g.pages.length === 1) { await expect(btn).toHaveCount(0); await expect(nav.locator(`#side-sub-${g.id}`)).toHaveCount(0); continue; }
    await expect(btn).toHaveAttribute("aria-expanded", g.id === "find-stocks" ? "true" : "false");
    await expect(btn).toHaveAttribute("aria-controls", `side-sub-${g.id}`);
  }
  // the keyboard opens a folded section; it stays open after a reload (kept for this person)
  const today = nav.getByRole("button", { name: "Market today pages", exact: true });
  await today.focus();
  await page.keyboard.press("Enter");
  await expect(today).toHaveAttribute("aria-expanded", "true");
  await expect(nav.locator("#side-sub-market-today").getByRole("link")).toHaveText(NAV.invest.groups.find((g) => g.id === "market-today")!.pages.map((p) => p.label));
  await page.reload();
  await expect(mainNav(page).getByRole("button", { name: "Market today pages", exact: true })).toHaveAttribute("aria-expanded", "true", { timeout: 30_000 });
  await mainNav(page).getByRole("button", { name: "Market today pages", exact: true }).click();
  await expect(mainNav(page).getByRole("button", { name: "Market today pages", exact: true })).toHaveAttribute("aria-expanded", "false");
  // the section you are in can be folded too; coming back into it opens it again
  await mainNav(page).getByRole("button", { name: "Find stocks pages", exact: true }).click();
  await expect(mainNav(page).locator("#side-sub-find-stocks")).toBeHidden();
  // a heading still opens its first page, and its section opens
  await mainNav(page).getByRole("link", { name: "Market data", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${startOf(NAV.invest.groups.find((g) => g.id === "market-data")!, "invest")}$`));
  await expect(mainNav(page).getByRole("button", { name: "Market data pages", exact: true })).toHaveAttribute("aria-expanded", "true");
  await mainNav(page).getByRole("link", { name: "Find stocks", exact: true }).click();
  await expect(mainNav(page).getByRole("button", { name: "Find stocks pages", exact: true })).toHaveAttribute("aria-expanded", "true");
  expect(errors).toEqual([]);
});

test("item 36: on a 1280x800 laptop the menu does not scroll with the section you are in open, in every space", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a laptop's size");
  await open(page, "/invest", who(false), 1280, 800);
  // a person with many notebooks: the menu lists six of them and "All 8 notebooks" under Notebooks, the longest a section gets
  await page.route(`${process.env.E2E_API ?? "http://127.0.0.1:8765"}/notebooks`, (r) => r.request().method() !== "GET" ? r.fallback() : r.fulfill({ json: Array.from({ length: 8 }, (_, i) => ({
    id: `nb-${i}`, name: `Opening range breakout with a long name ${i}`, pinned: i < 2, instrument: { market: "IN", symbol: "RELIANCE" }, summary: { experiments: 2, last_verdict: "robust" } })) }));
  await expect(mainNav(page)).toBeVisible({ timeout: 30_000 });
  const seen = new Set<string>(["/notebooks"]);
  for (const to of ["/notebooks"]) {
    await page.goto(to);
    const nav = side(page).locator("nav.side-groups");
    await expect(nav.locator(".nb-more")).toHaveText("All 8 notebooks", { timeout: 30_000 });
    const over = await nav.evaluate((el) => el.scrollHeight - el.clientHeight);
    expect(over, `${to} with 8 notebooks: the menu scrolls by ${over}px`).toBeLessThanOrEqual(0);
  }
  for (const space of ["trade", "invest", "money"] as const) for (const g of NAV[space].groups) {
    const to = startOf(g, space);
    if (seen.has(to)) continue;
    seen.add(to);
    await page.goto(to);
    const nav = side(page).locator("nav.side-groups");
    await expect(nav.locator(".side-entries")).toBeVisible({ timeout: 30_000 });
    const over = await nav.evaluate((el) => el.scrollHeight - el.clientHeight);
    expect(over, `${to}: the menu scrolls by ${over}px`).toBeLessThanOrEqual(0);
    await expect(side(page).locator(".side-more")).toHaveCount(0);
  }
});

test("item 36: the phone's menu sheet shows the same headings and pages", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's sheet");
  await open(page, "/invest/breadth", who(true), 390, 844);
  await page.getByRole("button", { name: "Open menu" }).click();
  const nav = mainNav(page);
  await expect(nav.locator(".side-entries > .side-entry > .side-head > a")).toHaveText(NAV.invest.groups.map((g) => g.label), { timeout: 30_000 });
  await expect(nav.locator("#side-sub-market-today").getByRole("link", { name: "Breadth", exact: true })).toHaveAttribute("aria-current", "page");
  const btn = nav.getByRole("button", { name: "Companies pages", exact: true });
  expect((await btn.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await btn.click();
  await nav.getByRole("link", { name: "Compare", exact: true }).click();
  await expect(page).toHaveURL(/\/research\/compare$/);
  await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
});

// screenshots of the menu for a person to LOOK at (IA2_SHOTS=<folder>)
const SHOTS = process.env.IA2_SHOTS;
test("item 36: menu screenshots", async ({ page }, info) => {
  test.skip(!SHOTS, "only when asked for");
  const phone = info.project.name === "phone";
  const sizes = phone ? [[390, 844], [360, 780]] : [[1440, 900], [1280, 800]];
  for (const [path, name] of [["/research/screens", "invest"], ["/notebooks", "trade"], ["/money/tax-tools", "money"]] as const) {
    await open(page, path, who(phone), sizes[0][0], sizes[0][1]);
    for (const [w, h] of sizes) for (const scheme of ["light", "dark"] as const) {
      await page.setViewportSize({ width: w, height: h });
      await page.emulateMedia({ colorScheme: scheme });
      if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
      await expect(mainNav(page).locator(".side-entries")).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${SHOTS}/menu-${name}-${w}-${scheme}.png` });
    }
    await page.goto("about:blank");
  }
});
