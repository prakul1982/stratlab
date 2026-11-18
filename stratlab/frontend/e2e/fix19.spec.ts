import { expect, test, type Page } from "@playwright/test";

// fix19: the owner's decisions of 18 Nov, proved on the pages as drawn, on the desktop and phone projects.

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const PRO = { access_token: "pro-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id: "u-pro", aud: "authenticated", email: "u-pro@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function signedIn(page: Page, s: object = PRO) {
  await page.addInitScript((x) => { try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ } }, s);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

/** The menu's geometry: the pill's box (null when it is not shown), its row's top edge line, the menu's visible box, and every menu
 * item's box cut to what is visible of it inside the menu. */
const menuBoxes = (page: Page) => page.evaluate(() => {
  const nav = document.querySelector("aside.sidebar nav.side-groups")!;
  const n = nav.getBoundingClientRect();
  const pill = document.querySelector("aside.sidebar .side-more");
  const row = pill?.closest(".side-more-row");
  const items = [...nav.querySelectorAll("a, button")].filter((e) => e.getClientRects().length).map((e) => {
    const b = e.getBoundingClientRect();
    return { name: (e.textContent ?? "").trim().slice(0, 30), top: Math.max(b.top, n.top), bottom: Math.min(b.bottom, n.bottom), left: b.left, right: b.right };
  }).filter((b) => b.bottom > b.top);
  const p = pill?.getBoundingClientRect();
  return { nav: { top: n.top, bottom: n.bottom }, pill: p ? { top: p.top, bottom: p.bottom, left: p.left, right: p.right } : null,
    line: row ? getComputedStyle(row).borderTopWidth : null, items, over: nav.scrollHeight - nav.clientHeight, top: nav.scrollTop };
});

/** Companies and Market today open, as the owner had them: on Breadth (Market today is the section it is in) with Companies and Market
 * data unfolded. */
async function twoOpen(page: Page, phone: boolean) {
  await page.goto("/invest/breadth");
  if (phone) {
    await page.getByRole("button", { name: "Open menu" }).click();
    await expect(page.locator("aside.sidebar.open")).toBeVisible();
    await page.waitForTimeout(400);           // the drawer's slide-in, so a tap lands where it is aimed
  }
  const nav = page.locator("aside.sidebar nav.side-groups");
  await expect(nav.locator('[data-group="market-today"]')).toHaveAttribute("data-open", "true", { timeout: 30_000 });
  // the menu's folds are the person's own, read once the account is in: unfold after that, or the person's own folds replace the taps
  await expect(page.locator("aside.sidebar").getByRole("button", { name: /Pro plan, account menu$/ })).toBeAttached({ timeout: 30_000 });
  // Companies unfolded, and Market data too (where "ETF vs NAV" is, the item the pill sat over)
  for (const name of ["Companies pages", "Market data pages"]) {
    const btn = nav.getByRole("button", { name, exact: true });
    await expect(async () => {
      if ((await btn.getAttribute("aria-expanded")) !== "true") await btn.click();
      await expect(btn).toHaveAttribute("aria-expanded", "true", { timeout: 1000 });
    }).toPass({ timeout: 15_000 });
  }
  await expect(nav.locator('.side-sub a[href="/invest/etf-gaps"]')).toBeVisible();
  return nav;
}

// owner (18 Nov): the "More below" pill sat over "ETF vs NAV" at 1440x900 with Companies and Market today open. It has a row of its own
// under the menu's edge line now, so no menu item is ever under it, and it goes once the menu's last item is in view.
for (const [w, h] of [[1440, 900], [1280, 800]] as const) {
  test(`the "More below" pill never covers a menu item, and goes when the last item is in view, at ${w}x${h}`, async ({ page }, info) => {
    test.skip(info.project.name === "phone", "a laptop's size; the phone drawer has its own test");
    await page.setViewportSize({ width: w, height: h });
    await signedIn(page);
    const nav = await twoOpen(page, false);
    await expectNeverCovered(page, nav);
  });
}

test(`the "More below" pill never covers a menu item in the phone's drawer`, async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone's drawer");
  await signedIn(page);
  const nav = await twoOpen(page, true);
  await expectNeverCovered(page, nav);
});

async function expectNeverCovered(page: Page, nav: ReturnType<Page["locator"]>) {
  await expect(page.locator("aside.sidebar .side-more")).toBeVisible();      // the menu runs past the window: the pill shows
  for (const at of ["start", "middle"] as const) {
    if (at === "middle") await nav.evaluate((el) => { el.scrollTop = Math.round((el.scrollHeight - el.clientHeight) / 2); });
    await page.waitForTimeout(150);
    const m = await menuBoxes(page);
    if (!m.pill) continue;
    expect(m.line, "the pill's row has the menu's edge line above it").toBe("1px");
    expect(m.pill.top, `${at}: the pill is under the menu, not over it`).toBeGreaterThanOrEqual(m.nav.bottom);
    const under = m.items.filter((b) => b.top < m.pill!.bottom && b.bottom > m.pill!.top && b.left < m.pill!.right && b.right > m.pill!.left);
    expect(under.map((b) => b.name), `${at}: menu items under the pill`).toEqual([]);
  }
  // the last item in view, with only the menu's own bottom padding left to scroll: nothing more is below, so no pill
  await nav.evaluate((el) => { el.scrollTop = el.scrollHeight - el.clientHeight - 8; });
  await expect(page.locator("aside.sidebar .side-more")).toHaveCount(0);
  await expect(nav).not.toHaveAttribute("data-fade", /bottom|both/);
  // at the very end too
  await nav.evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await expect(page.locator("aside.sidebar .side-more")).toHaveCount(0);
  // back at the top it says so again
  await nav.evaluate((el) => { el.scrollTop = 0; });
  await expect(page.locator("aside.sidebar .side-more")).toBeVisible();
}
