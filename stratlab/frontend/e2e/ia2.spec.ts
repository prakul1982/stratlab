import { expect, test, type Page } from "@playwright/test";

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
