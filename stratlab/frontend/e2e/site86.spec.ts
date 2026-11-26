import { expect, test, type Page } from "@playwright/test";

// site86 (Release 86), the owner's scroll request (21 Nov: "it doesn't show all the stocks; add a scroll, don't extend it, and do it
// everywhere"): /mine's watchlist lists every stock and Coming up every date, each scrolling inside its card; the two cards side by side are
// the same height, and the page is no taller with more of either. Desktop at 1280 and 1440, and a 390 phone, on the fake world with a long
// watchlist and a long calendar laid over it.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
// S86_SHOTS=<folder>: also save the screenshots (the lane's before/after; never in CI)
const SHOTS = process.env.S86_SHOTS;
const SYMS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "AXISBANK", "KOTAKBANK", "BHARTIARTL", "MARUTI", "TITAN", "ONGC", "WIPRO",
  "SUNPHARMA", "NTPC", "POWERGRID", "TATASTEEL", "HINDALCO", "ADANIPORTS", "ASIANPAINT", "ULTRACEMCO", "NESTLEIND", "BAJFINANCE", "COALINDIA", "DRREDDY", "CIPLA", "GRASIM", "JSWSTEEL"];

async function world(page: Page, { watch, dates, theme = "dark" }: { watch: number; dates: number; theme?: "dark" | "light" }) {
  const user = { id: "u-pro", aud: "authenticated", email: "u-pro@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} };
  await page.addInitScript(([u, th]) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: "pro-token", token_type: "bearer", expires_in: 3600, expires_at: 4102444800, refresh_token: "r", user: u }));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.consent.v1", "no");
      localStorage.setItem("stratlab-theme", th);
    } catch { /* none */ }
  }, [user, theme] as const);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
  const items = SYMS.slice(0, watch).map((s) => ({ region: "IN", symbol: s, name: `${s} Ltd` }));
  await page.route((u) => u.pathname === "/research/watchlist", (r) => (r.request().method() === "GET" ? r.fulfill({ json: { items } }) : r.fallback()));
  await page.route((u) => u.pathname === "/research/quotes", (r) => {
    const asked = (new URL(r.request().url()).searchParams.get("symbols") ?? "").split(",").filter(Boolean);
    expect(asked.length, "24 to a read, the server's limit").toBeLessThanOrEqual(24);
    return r.fulfill({ json: Object.fromEntries(asked.map((s) => [s, { price: 100 + SYMS.indexOf(s) * 7.5, change_pct: (SYMS.indexOf(s) % 5) - 2, at: "2026-10-28T05:30:00Z" }])) });
  });
  // the money calendar answers with `dates` of the account's own dates over the next weeks, the fake world's events left out
  await page.route((u) => u.pathname === "/money/calendar", async (r) => {
    const res = await r.fetch(), body = await res.json();
    const start = new URL(r.request().url()).searchParams.get("start") ?? body.today;
    const day = (n: number) => new Date(Date.parse(`${start}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);
    const events = Array.from({ length: dates }, (_, i) => ({ id: `s86-${i}`, date: day(1 + Math.floor(i / 2)), title: `Your date number ${i + 1}`, cat: "custom", kind: "custom",
      detail: "A date of your own, for the scroll check.", amount: null, symbol: null, url: null }));
    await r.fulfill({ response: res, json: { ...body, events, market_on: true } });
  });
  await page.route((u) => u.pathname === "/research/results", (r) => r.fulfill({ json: { today: "2026-10-28", weeks: [] } }));
}

/** The two cards, their lists and the page, measured. */
const measure = (page: Page) => page.evaluate(() => {
  const box = (id: string) => { const r = document.querySelector(`[data-testid="${id}"]`)!.getBoundingClientRect(); return { top: Math.round(r.top + scrollY), h: r.height, w: r.width }; };
  const list = (id: string) => { const el = document.querySelector<HTMLElement>(`[data-testid="${id}"]`)!; return { h: el.clientHeight, sh: el.scrollHeight, over: el.hasAttribute("data-over"), tab: el.tabIndex, label: el.getAttribute("aria-label"), role: el.getAttribute("role"), overscroll: getComputedStyle(el).overscrollBehaviorY, more: el.hasAttribute("data-more") }; };
  return { coming: box("mine-coming"), watch: box("mine-watch"), cl: list("mine-coming-list"), wl: list("mine-watch-list"), page: document.documentElement.scrollHeight };
});

async function ready(page: Page, watch: number) {
  await page.goto("/mine");
  await expect(page.getByTestId("mine-watch-list").locator("li")).toHaveCount(watch, { timeout: 30_000 });
  await expect(page.getByTestId("mine-coming-list").locator("li").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);                 // the boxes' heights are set a frame after the rows draw
}

/** No row cut through the middle at rest: the list's bottom edge is a row's bottom edge. */
const wholeRows = (page: Page, id: string) => page.evaluate((id) => {
  const el = document.querySelector<HTMLElement>(`[data-testid="${id}"]`)!;
  const top = el.getBoundingClientRect().top, bottom = top + el.clientHeight;
  return [...el.querySelectorAll("li")].some((li) => Math.abs(li.getBoundingClientRect().bottom - bottom) <= 1.5);
}, id);

for (const width of [1280, 1440]) {
  test(`SCROLL: /mine at ${width}: every watchlist stock and every date inside its card, the cards level, the page no taller with more`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "a desktop width");
    await page.setViewportSize({ width, height: 900 });
    await world(page, { watch: 18, dates: 30 });
    await ready(page, 18);
    const a = await measure(page);
    if (SHOTS) await page.getByTestId("mine-coming").screenshot({ path: `${SHOTS}/after-desktop-${width}-coming.png` }).catch(() => undefined);
    if (SHOTS) await page.locator(".mine-grid").screenshot({ path: `${SHOTS}/after-desktop-${width}.png` });
    // side by side, the same height
    expect(Math.abs(a.coming.top - a.watch.top), "Coming up and the watchlist share a row").toBeLessThanOrEqual(2);
    expect(Math.abs(a.coming.h - a.watch.h), `Coming up ${a.coming.h}px, the watchlist ${a.watch.h}px`).toBeLessThanOrEqual(2);
    // both lists scroll inside their cards, named and reachable by keyboard, the page not dragged along
    for (const l of [a.cl, a.wl]) {
      expect(l.over).toBe(true);
      expect(l.sh).toBeGreaterThan(l.h + 40);
      expect(l.tab).toBe(0);
      expect(l.role).toBe("region");
      expect(l.label).toBeTruthy();
      expect(l.overscroll).toBe("contain");
      expect(l.more, "the fade while more is below").toBe(true);
    }
    expect(await wholeRows(page, "mine-watch-list"), "a watchlist row cut through the middle").toBe(true);
    expect(await wholeRows(page, "mine-coming-list"), "a dated row cut through the middle").toBe(true);
    // every stock is reachable by scrolling inside the card (the wheel, over the list), and the page stays where it is
    const wl = page.getByTestId("mine-watch-list");
    await wl.scrollIntoViewIfNeeded();
    const y0 = await page.evaluate(() => scrollY);
    const lb = (await wl.boundingBox())!;
    await page.mouse.move(lb.x + lb.width / 2, lb.y + lb.height / 2);
    for (let i = 0; i < 12; i++) await page.mouse.wheel(0, 400);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => scrollY), "the page moved under a list's wheel").toBe(y0);
    const end = await wl.evaluate((el) => ({ top: el.scrollTop, max: el.scrollHeight - el.clientHeight, more: el.hasAttribute("data-more") }));
    expect(end.top).toBeGreaterThanOrEqual(end.max - 1);
    expect(end.more, "the fade is gone at the end").toBe(false);
    await expect(wl.getByRole("link", { name: /^POWERGRID/ })).toBeInViewport();
    // each of the 18 in turn, scrolled to inside the card
    for (const s of SYMS.slice(0, 18)) {
      const link = wl.getByRole("link", { name: new RegExp(`^${s}`) });
      await link.scrollIntoViewIfNeeded();
      await expect(link).toBeInViewport();
      const inside = await link.evaluate((a) => { const l = a.closest(".k-scroll")!.getBoundingClientRect(), r = a.getBoundingClientRect(); return r.top >= l.top - 1 && r.bottom <= l.bottom + 1; });
      expect(inside, `${s} shown inside the card's list`).toBe(true);
    }
    // the keyboard scrolls it too
    await wl.evaluate((el) => { el.scrollTop = 0; });
    await wl.focus();
    await page.keyboard.press("End");
    await expect.poll(() => wl.evaluate((el) => el.scrollTop)).toBeGreaterThan(100);
    // more stocks and more dates: the page is no taller, the cards still level
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await world(page, { watch: 30, dates: 45 });
    await ready(page, 30);
    const b = await measure(page);
    expect(Math.abs(b.coming.h - b.watch.h)).toBeLessThanOrEqual(2);
    expect(Math.abs(b.page - a.page), `the page was ${a.page}px with 18 stocks, ${b.page}px with 30`).toBeLessThanOrEqual(2);
    // the calendar link stays
    // (changed on purpose, cal94, owner 26 Nov: one Calendar fixed in the sidebar): "See calendar" opens the one Calendar
    await expect(page.getByTestId("mine-coming").getByRole("link", { name: "See calendar", exact: true })).toHaveAttribute("href", "/calendar");
    await expect(page.getByTestId("mine-coming-more")).toHaveAttribute("href", "/money/calendar");
  });
}

test("SCROLL: a short watchlist beside a long Coming up: level, the dates giving way and scrolling, no blank box", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "a desktop width");
  await page.setViewportSize({ width: 1280, height: 900 });
  await world(page, { watch: 4, dates: 30, theme: "light" });
  await ready(page, 4);
  const a = await measure(page);
  if (SHOTS) await page.locator(".mine-grid").screenshot({ path: `${SHOTS}/after-desktop-1280-short-watchlist-light.png` });
  expect(Math.abs(a.coming.h - a.watch.h)).toBeLessThanOrEqual(2);
  expect(a.wl.over, "four stocks fit").toBe(false);
  expect(a.cl.over).toBe(true);
  expect(await wholeRows(page, "mine-coming-list")).toBe(true);
});

test("SCROLL: phone 390: every stock reachable inside the card, a taller list, the page still scrolls from outside it", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone");
  await page.setViewportSize({ width: 390, height: 844 });
  await world(page, { watch: 18, dates: 30 });
  await ready(page, 18);
  const a = await measure(page);
  if (SHOTS) await page.getByTestId("mine-watch").screenshot({ path: `${SHOTS}/after-phone-390-watchlist.png` });
  if (SHOTS) await page.getByTestId("mine-coming").screenshot({ path: `${SHOTS}/after-phone-390-coming.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth), "the page scrolls sideways").toBeLessThanOrEqual(391);
  expect(a.wl.over).toBe(true);
  // about eight rows on a phone, so it isn't cramped
  const rows = await page.getByTestId("mine-watch-list").evaluate((el) => { const t = el.getBoundingClientRect().top; return [...el.querySelectorAll("li")].filter((li) => li.getBoundingClientRect().bottom <= t + el.clientHeight + 1).length; });
  expect(rows).toBeGreaterThanOrEqual(8);
  expect(await wholeRows(page, "mine-watch-list")).toBe(true);
  // every stock reachable by scrolling the list
  const wl = page.getByTestId("mine-watch-list");
  await wl.scrollIntoViewIfNeeded();
  await wl.evaluate((el) => { el.scrollTop = el.scrollHeight; });
  await expect(wl.getByRole("link", { name: /^POWERGRID/ })).toBeInViewport();
  expect(await wl.getByRole("link", { name: /^POWERGRID/ }).evaluate((a) => { const l = a.closest(".k-scroll")!.getBoundingClientRect(), r = a.getBoundingClientRect(); return r.top >= l.top - 1 && r.bottom <= l.bottom + 1; }), "the last stock shown inside the card's list").toBe(true);
  // a finger (or wheel) that starts outside the list scrolls the page
  await page.evaluate(() => scrollTo(0, 0));
  const y0 = await page.evaluate(() => scrollY);
  const hb = (await page.locator("main h1").first().boundingBox())!;
  await page.mouse.move(hb.x + 10, hb.y + hb.height / 2);
  await page.mouse.wheel(0, 300);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(y0);
});
