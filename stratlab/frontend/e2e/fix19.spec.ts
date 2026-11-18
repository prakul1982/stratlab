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

// owner (18 Nov): the analytics question in the app is one small card in the page's flow, after the page's content, never a band over
// it; it can be closed; once answered it is gone on every page; nothing moves when it comes or goes.
const BASIC = { ...PRO, access_token: "basic-token", user: { ...PRO.user, id: "u-basic", email: "basic@example.com" } };
const TRACK = { META_PIXEL_ID: "1234567890", CLARITY_PROJECT_ID: "abc123def4" };

/** The question switched on (a fake config) for every tab of the browser, signed in on Basic. */
async function withQuestion(page: Page) {
  const ctx = page.context();
  await ctx.route(/connect\.facebook\.net|clarity\.ms/, (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
  await ctx.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(TRACK)});\n` });
  });
  await ctx.addInitScript((x) => {
    try { localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1"); } catch { /* none */ }
    // the layout shifts that moved the question itself (the page's own cards filling in are other checks' business)
    const w = window as unknown as { __askMoves: number };
    w.__askMoves = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean; sources?: { node?: Node }[] }[])
        if (!e.hadRecentInput && (e.sources ?? []).some((x) => (x.node as HTMLElement | undefined)?.closest?.("[data-testid=consent]"))) w.__askMoves += e.value;
    }).observe({ type: "layout-shift", buffered: true });
  }, BASIC);
  await ctx.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

/** Whatever shows through the card: elements at a grid of points over it that are neither it, inside it, nor what it sits in. */
const under = (page: Page) => page.evaluate(() => {
  const c = document.querySelector("[data-testid=consent]")!;
  const r = c.getBoundingClientRect();
  const hits = new Set<string>();
  for (let i = 1; i < 12; i++) for (let j = 1; j < 4; j++)
    for (const e of document.elementsFromPoint(r.left + (r.width * i) / 12, r.top + (r.height * j) / 4)) if (!c.contains(e) && !e.contains(c)) hits.add(`${e.tagName}.${e.className}`);
  return [...hits];
});

test("the analytics question is one small card after the page, and closing it hides it on every page for the visit, moving nothing", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await withQuestion(page);
  await page.goto("/trade");
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  // in the page's flow, after the page's content, covering nothing; a small card, not a band the page's width
  expect(await ask.evaluate((e) => getComputedStyle(e).position)).not.toBe("fixed");
  const [qTop, mainEnd] = await page.evaluate(() => [document.querySelector("[data-testid=consent]")!.getBoundingClientRect().top, document.querySelector("#main")!.getBoundingClientRect().bottom]);
  expect(qTop, "after the page").toBeGreaterThanOrEqual(mainEnd - 1);
  await ask.scrollIntoViewIfNeeded();
  expect(await under(page)).toEqual([]);
  const box = (await ask.boundingBox())!;
  if (!phone) expect(box.width, "a small card, not the page's width").toBeLessThanOrEqual(641);
  expect(box.height, "a small card").toBeLessThanOrEqual(160);
  // closing it: "Not now" takes it away and nothing above it moves
  const top = () => page.locator("h1").filter({ visible: true }).first().evaluate((e) => Math.round(e.getBoundingClientRect().top + window.scrollY));
  const before = await top();
  await ask.getByRole("button", { name: "Not now" }).click();
  await expect(ask).toHaveCount(0);
  expect(await top()).toBe(before);
  expect(await page.evaluate(() => (window as unknown as { __askMoves: number }).__askMoves), "layout shifts that moved the question").toBeLessThan(0.01);
  // no answer was saved (so nothing loads), and no other page asks again in this visit, opened in the app or loaded afresh
  expect(await page.evaluate(() => localStorage.getItem("stratlab.ads"))).toBeNull();
  for (const path of ["/research/IN/RELIANCE", "/invest"]) {
    await page.goto(path);
    await expect(page.locator("main h1").filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(2000);
    await expect(ask, path).toHaveCount(0);
  }
});

test("once answered, the analytics question is gone everywhere: other app pages, a public page and another tab", async ({ page, context }) => {
  await withQuestion(page);
  await page.goto("/trade");
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible({ timeout: 30_000 });
  await ask.getByRole("button", { name: "No thanks" }).click();
  await expect(ask).toHaveCount(0);
  const other = await context.newPage();
  for (const [p, path] of [[page, "/research/IN/RELIANCE"], [page, "/about"], [other, "/invest"]] as const) {
    await p.goto(path);
    await expect(p.locator("h1").filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
    await p.waitForTimeout(2000);
    await expect(p.getByTestId("consent"), path).toHaveCount(0);
  }
});
