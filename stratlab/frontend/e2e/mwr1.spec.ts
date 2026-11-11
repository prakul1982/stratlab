import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// MWR-1: the review of Market Watch and the chart workspace. A timeframe change keeps the moment on screen, the list tabs work from
// the keyboard and keep their height when the add box opens, and the first list and the Research watchlist stay one list whichever
// side changes it. Each project signs in as its own user so runs never share lists.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
// its own Pro accounts (the fake world's load-242 and load-284), not admin and pro: e2e/mw1-watch.spec.ts resets those two's lists and drawings in each
// test's setup, which cleared a list here mid-test when the two files ran side by side
const WHO = { pro: session("load-284", "u-load-284", "load284@example.com"), admin: session("load-242", "u-load-242", "load242@example.com") };
type Who = keyof typeof WHO;
const mine = (info: { project: { name: string } }): Who => (info.project.name === "phone" ? "pro" : "admin");

async function reset(request: APIRequestContext, who: Who) {
  const auth = { Authorization: `Bearer ${WHO[who].access_token}` };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });
  const got = await (await request.get(`${API}/watch/lists`, { headers: auth })).json();
  for (const l of got.lists) if (!l.default) await request.delete(`${API}/watch/lists/${l.id}`, { headers: auth });
  await request.put(`${API}/watch/lists/default/items`, { headers: auth, data: { items: [] } });
  await request.delete(`${API}/me/drawings`, { headers: auth });
}

async function open(page: Page, path: string, who: Who, layout?: Record<string, unknown>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(([s, lay]) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    if (!sessionStorage.getItem("fresh")) {
      sessionStorage.setItem("fresh", "1");
      for (const k of Object.keys(localStorage)) if (k.startsWith("stratlab.pc.") || k.startsWith("stratlab.watch.")) localStorage.removeItem(k);
      if (lay) localStorage.setItem(`stratlab.watch.layout.${(s as { user: { id: string } }).user.id}`, JSON.stringify(lay));
    }
  }, [WHO[who], layout ?? null] as const);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 2500 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return { errors };
}

const panel = (page: Page) => page.getByTestId("market-watch");
const OPEN_FLOAT = { open: true, mode: "float", w: 400, h: 600, x: null, y: null, list: null, sort: "custom", chart: null };

test.beforeEach(async ({ request }, info) => { await reset(request, mine(info)); });
test.afterEach(async ({ request }, info) => { await reset(request, mine(info)); });

test("a timeframe change keeps the moment on screen", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop only: the drag is the mouse's");
  const { errors } = await open(page, "/chart/IN/RELIANCE", mine(info));
  const chart = page.getByTestId("price-chart").first();
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  const pick = async (t: string) => { await chart.getByRole("group", { name: "Timeframe" }).getByRole("button", { name: t, exact: true }).click(); await expect(chart).toHaveAttribute("data-loaded", t.toLowerCase(), { timeout: 30_000 }); await page.waitForTimeout(500); };
  // the candle under the pointer: its start (data-at, ms) once the pointer has moved there
  const hoverAt = async () => {
    const stage = chart.locator(".pc-stage");
    const b = (await stage.boundingBox())!;
    await page.mouse.move(b.x + b.width * 0.4, b.y + b.height * 0.3);
    await page.mouse.move(b.x + b.width * 0.4 + 1, b.y + b.height * 0.3 + 1);
    // the pointer's candle, not the newest one shown before the hover is drawn (data-at names the newest bar while nothing
    // is hovered, and a read right after a move or a timeframe switch can catch that frame): wait for the hover, then for
    // the value to hold still across two frames
    await expect(chart).toHaveAttribute("data-hovering", "1");
    let at = -1;
    await expect.poll(async () => {
      const a = Number(await chart.getAttribute("data-at"));
      await page.waitForTimeout(150);
      const b2 = Number(await chart.getAttribute("data-at"));
      at = b2;
      return a === b2 && Number.isFinite(b2) && b2 > 0;
    }).toBe(true);
    return at;
  };
  await pick("5m");
  const newest = await hoverAt();
  // scrolled back by dragging the chart: the candles under the pointer are not the newest ones any more
  const b = (await chart.locator(".pc-stage").boundingBox())!;
  await page.mouse.move(b.x + b.width / 2, b.y + 150);
  await page.mouse.down(); await page.mouse.move(b.x + b.width / 2 + 700, b.y + 150, { steps: 12 }); await page.mouse.up();
  await page.waitForTimeout(600);
  const back = await hoverAt();
  expect(newest - back, "scrolled back").toBeGreaterThan(30 * 60_000);
  // 15m and 1m keep looking at that same moment: the candle under the pointer is near the one scrolled back to, not the newest.
  // (It was measured by the price there being over ₹20 from today's: that rested on the fake world's price wave, which at the fixed
  // E2E_NOW stands 12 away; the candle's own time is what "the moment" is.)
  const near = (t: number, tf: number) => Math.abs(t - back) <= Math.max(2 * tf, (newest - back) / 3);
  await pick("15m");
  const at15 = await hoverAt();
  expect(near(at15, 15 * 60_000), `15m after scrolling back: ${new Date(at15).toISOString()} vs ${new Date(back).toISOString()}`).toBe(true);
  await pick("1m");
  const at1 = await hoverAt();
  expect(near(at1, 60_000), `1m after scrolling back: ${new Date(at1).toISOString()} vs ${new Date(back).toISOString()}`).toBe(true);
  expect(errors).toEqual([]);
});

test("the list tabs are reached with the arrow keys and keep their row when the add box opens", async ({ page, request }, info) => {
  const who = mine(info);
  await request.post(`${API}/watch/lists`, { headers: { Authorization: `Bearer ${WHO[who].access_token}` }, data: { name: "R test two" } });
  const phone = info.project.name === "phone";
  const { errors } = await open(page, "/", who, phone ? undefined : OPEN_FLOAT);         // a sheet is never open at load: it is asked for
  if (phone) await page.getByRole("button", { name: "Markets", exact: true }).click();
  const mw = panel(page);
  await expect(mw).toBeVisible();
  const tabs = mw.getByRole("tab");
  await expect(tabs).toHaveCount(2);
  await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
  // only the open list is a stop in the tab order; the arrow keys move along the tabs, Home and End go to the ends
  await tabs.nth(0).focus();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
  await expect(tabs.nth(1)).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("End");
  await expect(tabs.nth(1)).toBeFocused();
  await page.keyboard.press("Home");
  await expect(tabs.nth(0)).toBeFocused();
  // the search's results take the list's place but never the tab row's: it stays as tall as it was (MW-2: the results are in the list area)
  const before = (await mw.locator(".mw-tabs").boundingBox())!;
  await mw.getByRole("combobox", { name: /^Search/ }).fill("REL");
  await expect(mw.getByTestId("mw-results").getByRole("option").first()).toBeVisible({ timeout: 10_000 });
  const after = (await mw.locator(".mw-tabs").boundingBox())!;
  expect(Math.round(after.height)).toBe(Math.round(before.height));
  expect(after.height).toBeGreaterThan(30);
  await expect(tabs.nth(0)).toBeVisible();
  expect(errors).toEqual([]);
});

test("a stock starred on a company page and one added in the panel are both on the first list", async ({ page, request }, info) => {
  test.skip(info.project.name === "phone", "desktop only: the panel floats over the page it follows");
  const auth = { Authorization: `Bearer ${WHO.admin.access_token}` };
  // docked beside the page (from 1600), so it stays from page to page; a floating one shuts on another page since LIVE5-006 (mw1-watch)
  await page.setViewportSize({ width: 1700, height: 1000 });
  const { errors } = await open(page, "/", "admin", { ...OPEN_FLOAT, mode: "dock" });
  const mw = panel(page);
  await expect(mw).toBeVisible();
  await expect(mw.getByText("Your watchlist is empty")).toBeVisible();
  // the panel is open while a company page (a client-side move, the docked panel stays) stars a stock
  await page.evaluate(() => { history.pushState({}, "", "/research/IN/INFY"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await page.getByRole("button", { name: /^Watch\b/ }).first().click();
  const rows = mw.getByRole("list", { name: "Watchlist" }).getByRole("listitem");
  await expect(rows).toHaveCount(1, { timeout: 10_000 });                                  // the panel read the lists again
  // then a symbol from another market is added in the panel: the stock starred a moment ago must still be there
  // (MW-2: one field over every market: no market to pick first)
  await mw.getByRole("combobox", { name: /^Search/ }).fill("BTC");
  await mw.getByTestId("mw-results").getByRole("option").filter({ hasText: "BTC/USD" }).first().click();
  await expect(rows).toHaveCount(2);
  await expect.poll(async () => (await (await request.get(`${API}/watch/lists`, { headers: auth })).json()).lists[0].items.map((i: { id: string }) => i.id).sort(), { timeout: 8000 })
    .toEqual(["CRYPTO:BTC-USD", "IN:INFY"]);
  const research = await (await request.get(`${API}/research/watchlist`, { headers: auth })).json();
  expect(research.items.map((i: { symbol: string }) => i.symbol)).toEqual(["INFY"]);
  // and the other way: a stock added in the panel is known to the company page (its star is on), and another starred there keeps both
  await mw.getByRole("combobox", { name: /^Search/ }).fill("TCS");
  await mw.getByTestId("mw-results").getByRole("option").filter({ hasText: "NSE" }).filter({ hasText: "TCS" }).first().click();
  await expect(rows).toHaveCount(3);
  await page.evaluate(() => { history.pushState({}, "", "/research/IN/TCS"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page.getByRole("button", { name: /^Watching\b/ }).first()).toBeVisible({ timeout: 10_000 });
  // starring another stock here keeps the two already on the list
  await page.evaluate(() => { history.pushState({}, "", "/research/IN/ITC"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await page.getByRole("button", { name: /^Watch\b/ }).first().click();
  await expect(rows).toHaveCount(4, { timeout: 10_000 });
  await expect.poll(async () => (await (await request.get(`${API}/watch/lists`, { headers: auth })).json()).lists[0].items.map((i: { id: string }) => i.id).sort(), { timeout: 8000 })
    .toEqual(["CRYPTO:BTC-USD", "IN:INFY", "IN:ITC", "IN:TCS"]);
  expect(errors).toEqual([]);
});
