import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// MW-1: Market Watch. A "Markets" button on every page opens a panel that stays open from page to page: add a symbol and see its price,
// reorder the list, open the chart, change the timeframe, add an indicator, draw a trend line and find it all again after a reload.
// A phone gets a full-height sheet from the top bar; the panel never covers the cookie question or the page's main actions; a visitor
// gets a read-only board; Free is told its limits before they bite. Each project signs in as its own user so runs never share lists.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const WHO = { free: session("free-token", "u-free", "free@example.com"), basic: session("basic-token", "u-basic", "basic@example.com"), pro: session("pro-token", "u-pro", "pro@example.com"), drawer: session("load-233", "u-load-233", "load233@example.com"), admin: session("admin-token", "u-admin", "owner@example.com") };
const ADS_ON = { ADS_ENABLED: "true", ADSENSE_CLIENT: "ca-pub-1234567890123456", ADSENSE_SLOT_PUBLIC: "1111111111", ADSENSE_SLOT_AI: "2222222222" };

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

async function open(page: Page, path: string, o: { who?: Who | null; ads?: boolean; layout?: Record<string, unknown> } = {}) {
  const errors: string[] = [], asked: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => asked.push(new URL(r.url()).pathname));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  if (o.ads) {
    await page.route(/\/config\.js(\?|$)/, async (r) => {
      const real = await (await r.fetch()).text();
      await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(ADS_ON)});\n` });
    });
  }
  const who = o.who === undefined ? "admin" : o.who;
  await page.addInitScript(([s, layout]) => {
    if (s) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    if (!sessionStorage.getItem("fresh")) {
      sessionStorage.setItem("fresh", "1");
      for (const k of Object.keys(localStorage)) if (k.startsWith("stratlab.pc.") || k.startsWith("stratlab.watch.")) localStorage.removeItem(k);
      if (layout) localStorage.setItem(`stratlab.watch.layout.${s ? s.user.id : "visitor"}`, JSON.stringify(layout));
    }
  }, [who ? WHO[who] : null, o.layout ?? null] as const);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 2500 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return { errors, asked };
}

const panel = (page: Page) => page.getByTestId("market-watch");
const launch = (page: Page) => page.getByTestId("markets-launch");

async function openPanel(page: Page) {
  const phone = page.viewportSize()!.width <= 900;
  if (phone) await page.getByRole("button", { name: "Markets", exact: true }).click(); else await launch(page).click();
  await expect(panel(page)).toBeVisible();
  return panel(page);
}

const gone = (a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }) =>
  a.x + a.width <= b.x + 1 || b.x + b.width <= a.x + 1 || a.y + a.height <= b.y + 1 || b.y + b.height <= a.y + 1;

test.beforeEach(async ({ request }, info) => { await reset(request, mine(info)); });
test.afterEach(async ({ request }, info) => { await reset(request, mine(info)); });

test("add a symbol and see its price, reorder the list, and the list is kept", async ({ page, request }, info) => {
  test.skip(info.project.name === "phone", "the phone's sheet has its own test below");
  const { errors } = await open(page, "/");
  const mw = await openPanel(page);
  await expect(mw.getByText("Your watchlist is empty")).toBeVisible();
  // one tap for the usual ones, on an empty list
  await mw.getByRole("button", { name: "BTC/USD", exact: true }).click();
  // MW-2: one search field over every market, always there (no "+ Add symbol" to open first, no market to pick): type, click a result
  const field = mw.getByRole("combobox", { name: "Search to add a symbol" });
  await field.fill("NIFTY 50");
  const nifty = mw.getByRole("option").filter({ hasText: "NIFTY 50" }).first();
  await expect(nifty).toContainText("NSE");                                  // a result says where it trades
  await nifty.click();
  // added: the line says so, the search has ended and the field is ready for the next one
  await expect(mw.getByTestId("mw-said")).toHaveText("Added NIFTY 50 to your watchlist.");
  await expect(field).toHaveValue("");
  await expect(mw.getByRole("option")).toHaveCount(0);
  // ...and from the keyboard: type, Enter adds the highlighted (first) result
  await field.fill("INFY");
  await expect(mw.getByRole("option").first()).toHaveAttribute("aria-selected", "true");
  await expect(mw.getByRole("option").first()).toContainText("INFY");
  await field.press("ArrowDown");
  await field.press("ArrowUp");
  await expect(mw.getByRole("option").first()).toHaveAttribute("aria-selected", "true");
  await field.press("Enter");
  await expect(mw.getByTestId("mw-said")).toHaveText("Added INFY to your watchlist.");
  await expect(field).toBeFocused();
  // one already on the list is said, not added twice; Esc ends the search and leaves the panel open
  await field.fill("INFY");
  await expect(mw.getByRole("option").first()).toContainText("On this list");
  await field.press("Enter");
  await expect(mw.getByTestId("mw-said")).toHaveText("INFY is already on your watchlist.");
  await field.press("Escape");
  await expect(field).toHaveValue("");
  await expect(mw).toBeVisible();
  const rows = mw.getByRole("list", { name: "Watchlist" }).getByRole("listitem");
  await expect(rows).toHaveCount(3);
  // prices come in within a few seconds, and the day's change carries its sign and arrow
  for (let i = 0; i < 3; i++) await expect(rows.nth(i).locator(".mw-price")).not.toHaveText("–", { timeout: 15_000 });
  await expect(rows.nth(0).locator(".mw-chg")).toHaveText(/^(▲ \+|▼ −)?\d+\.\d\d%$|^[+−]?0\.00%$/);
  // MW-2: a row is one line under the column heads, and each column of figures ends on one line down the list
  await expect(mw.locator(".mw-cols")).toHaveText(/Symbol\s*Last\s*Change\s*Change %/);
  for (const col of [".mw-price", ".mw-abs", ".mw-chg"]) {
    const rights = await rows.locator(col).evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().right)));
    expect(new Set(rights).size, `${col} is right-aligned in one column: ${rights}`).toBe(1);
  }
  expect((await rows.nth(0).boundingBox())!.height).toBeLessThanOrEqual(44);
  const names = async () => (await rows.locator(".mw-name b").allInnerTexts());
  expect(await names()).toEqual(["BTC/USD", "NIFTY 50", "INFY"]);
  // reorder with the keyboard: the grip of the last row, arrow up
  await rows.nth(2).getByRole("button", { name: /^Move INFY/ }).focus();
  await page.keyboard.press("ArrowUp");
  await expect.poll(names).toEqual(["BTC/USD", "INFY", "NIFTY 50"]);
  await expect.poll(async () => (await (await request.get(`${API}/watch/lists`, { headers: { Authorization: "Bearer admin-token" } })).json()).lists[0].items.map((i: { id: string }) => i.id),
    { timeout: 8000 }).toEqual(["CRYPTO:BTC-USD", "IN:INFY", "IN:^NSEI"]);
  // Research's watchlist holds the stock only: nothing is kept twice
  const research = await (await request.get(`${API}/research/watchlist`, { headers: { Authorization: "Bearer admin-token" } })).json();
  expect(research.items.map((i: { symbol: string }) => i.symbol)).toEqual(["INFY"]);
  // sorted by the day's change leaves the kept order alone
  // (MW-2: the Change % column's head sorts: biggest rise first, a second press biggest fall first, a third your own order again)
  const byChange = mw.getByRole("button", { name: "Sort by the day's change" });
  await byChange.click();
  await expect(rows.first().locator(".mw-grip")).toHaveClass(/off/);
  await expect(byChange).toHaveAttribute("aria-pressed", "true");
  await byChange.click();
  await byChange.click();
  await expect(byChange).toHaveAttribute("aria-pressed", "false");
  await expect(rows.first().locator(".mw-grip")).not.toHaveClass(/off/);
  // a reload: the panel is open where it was, with the list
  await page.reload();
  await expect(panel(page)).toBeVisible();
  await expect(rows).toHaveCount(3);
  expect(await names()).toEqual(["BTC/USD", "INFY", "NIFTY 50"]);
  expect(errors).toEqual([]);
});

test("LIVE5-006: a panel floating over the page shuts on another page; a docked one stays mounted from page to page", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop only");
  // 1440: a "docked" panel floats in the corner over the page (it docks from 1600): going to another page shuts it (behaviour changed on
  // purpose: it stayed open over Sector rotation's controls)
  await open(page, "/");
  await openPanel(page);
  await page.getByRole("link", { name: "Settings", exact: true }).first().click().catch(() => page.goto("/settings"));
  await expect(page).toHaveURL(/\/settings/);
  await expect(panel(page)).toHaveCount(0);
  await expect(launch(page)).toBeVisible();
  // 1700: docked beside the page, it takes its width from the page and stays, the same element
  await page.setViewportSize({ width: 1700, height: 1000 });
  await page.goto("/");
  await openPanel(page);
  await page.evaluate(() => { (window as unknown as { __mw: Element }).__mw = document.querySelector("[data-testid=market-watch]")!; });
  await page.getByRole("link", { name: "Settings", exact: true }).first().click().catch(() => page.goto("/settings"));
  await expect(page).toHaveURL(/\/settings/);
  await expect(panel(page)).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __mw: Element }).__mw.isConnected)).toBe(true);        // the same element: not drawn again
  await page.goBack();
  expect(await page.evaluate(() => (window as unknown as { __mw: Element }).__mw.isConnected)).toBe(true);
});

test("open the chart, change the timeframe, add an indicator, draw a trend line, reload: all of it is still there", async ({ page, request }, info) => {
  test.skip(info.project.name === "phone", "the chart's drawing tools have their own phone test (drawings.spec)");
  // (its own Pro user, not admin: other specs clear admin's drawings in their setup while this one draws and reloads)
  await reset(request, "drawer");
  const { errors } = await open(page, "/", { who: "drawer" });
  const mw = await openPanel(page);
  await mw.getByRole("combobox", { name: /^Search/ }).fill("INFY");
  await mw.getByRole("option").filter({ hasText: "INFY" }).first().click();
  await mw.getByRole("button", { name: "Open the chart of INFY" }).click();
  const chart = mw.getByTestId("price-chart");
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  // every timeframe from a minute up is offered
  // (in the narrow panel they are one box; the full page below has them as chips)
  const tf = chart.getByRole("combobox", { name: "Timeframe" });
  expect(await tf.locator("option").allInnerTexts()).toEqual(["1 min", "3 min", "5 min", "10 min", "15 min", "30 min", "1 hour", "2 hours", "4 hours", "1 day", "1 week", "1 month"]);
  await tf.selectOption({ label: "5 min" });
  await expect(chart).toHaveAttribute("data-loaded", "5m", { timeout: 30_000 });
  await expect(chart).toHaveAttribute("data-tf", "5m");
  // a number key picks a timeframe too; ] steps up
  await chart.locator(".pc-stage").focus();
  await page.keyboard.press("3");
  await expect(chart).toHaveAttribute("data-loaded", "5m", { timeout: 30_000 });
  await page.keyboard.press("]");
  await expect(chart).toHaveAttribute("data-loaded", "10m", { timeout: 30_000 });
  await tf.selectOption({ label: "5 min" });
  await expect(chart).toHaveAttribute("data-loaded", "5m", { timeout: 30_000 });
  // the pill says how current the prices are (the test world's broker is on: live)
  await expect(chart.locator(".pc-pill")).toHaveText(/^(Live|Closed · last close .+)$/);                        // never "Live" with the market shut (LIVE3-011)
  // an indicator
  await chart.getByRole("button", { name: "Indicators" }).click();
  await page.getByRole("menuitem", { name: /^Moving average/i }).first().click();
  await expect(chart).toHaveAttribute("data-studies", "1");
  // a trend line
  await chart.getByRole("button", { name: "Lines", exact: true }).click();
  await page.getByRole("menuitem", { name: "Trend line", exact: true }).click();
  const stage = chart.locator(".pc-stage");
  const b = (await stage.boundingBox())!;
  for (const [fx, fy] of [[0.3, 0.55], [0.55, 0.4]]) { const x = b.x + b.width * fx * 0.82, y = b.y + b.height * (fy * 0.72 + 0.04); await page.mouse.move(x, y); await page.mouse.click(x, y); }
  await expect(chart).toHaveAttribute("data-drawings", "1");
  // kept on the account for this symbol: the drawing, the indicator and the timeframe
  await expect.poll(async () => {
    const got = await (await request.get(`${API}/me/drawings/IN/INFY`, { headers: { Authorization: "Bearer load-233" } })).json();
    return [got.drawings.length, got.layout?.studies?.length, got.layout?.tf];
  }, { timeout: 10_000 }).toEqual([1, 1, "5m"]);
  await page.reload();
  const again = panel(page).getByTestId("price-chart");
  await expect(again).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  await expect(again).toHaveAttribute("data-drawings", "1");
  await expect(again).toHaveAttribute("data-studies", "1");
  await expect(again).toHaveAttribute("data-loaded", "5m");
  // and the same chart opens as a full page, with the same drawing
  await page.goto("/chart/IN/INFY");
  const full = page.getByTestId("price-chart").first();
  await expect(full).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  await expect(full).toHaveAttribute("data-drawings", "1");
  await expect(full).toHaveAttribute("data-loaded", "5m");
  const chips = full.getByRole("group", { name: "Timeframe" });
  for (const t of ["1m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "1D", "1W", "1M"]) await expect(chips.getByRole("button", { name: t, exact: true })).toBeVisible();
  await expect(chips.getByRole("button", { name: "5m", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("INFY");
  expect(errors).toEqual([]);
});

test("the phone gets a full-height sheet from the top bar and no floating button", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone only");
  const { errors } = await open(page, "/", { who: "pro" });
  await expect(launch(page)).toBeHidden();
  const mw = await openPanel(page);
  await expect(mw).toHaveAttribute("role", "dialog");
  const vp = page.viewportSize()!, box = (await mw.boundingBox())!;
  expect(Math.round(box.x)).toBe(0); expect(Math.round(box.y)).toBe(0);
  expect(Math.round(box.width)).toBe(vp.width); expect(Math.round(box.height)).toBe(vp.height);
  const side = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  expect(side).toBe(true);
  // adding from the quick row, then Esc closes the sheet and focus returns to the top bar's button
  await mw.getByRole("button", { name: "Add a symbol" }).click();
  await mw.getByRole("button", { name: "BTC/USD", exact: true }).click();
  await expect(mw.getByRole("list", { name: "Watchlist" }).getByRole("listitem")).toHaveCount(1);
  await mw.getByRole("button", { name: "Open the chart of BTC/USD" }).click();
  await expect(mw.getByTestId("price-chart")).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  await mw.getByRole("button", { name: "Back to the list" }).click();
  await mw.getByRole("button", { name: "Close Market Watch" }).click();
  await expect(panel(page)).toHaveCount(0);
  // a reload with the sheet open on the phone does not open it again
  await openPanel(page);
  await page.reload();
  await page.waitForTimeout(800);
  await expect(panel(page)).toHaveCount(0);
  // ...and one press of the top bar's button opens it then (it took two: the first only marked the kept sheet shut)
  await openPanel(page);
  await panel(page).getByRole("button", { name: "Close Market Watch" }).click();
  expect(errors).toEqual([]);
});

test("the panel never covers the cookie question or the page's main actions", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "the phone's sheet is a dialog over everything by design");
  await open(page, "/", { ads: true });
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible();
  // signed in, the question is a band in the page's flow above the page (LIVE5 partial), the button in its corner: never over it
  const l = (await launch(page).boundingBox())!, a = (await ask.boundingBox())!;
  expect(gone(l, a), `the button ${JSON.stringify(l)} covers the question ${JSON.stringify(a)}`).toBe(true);
  await launch(page).click();
  const p = (await panel(page).boundingBox())!;
  // at this window width the panel floats in the corner above the question and leaves the page as it is (the page keeps its width)
  const a2 = (await ask.boundingBox())!;
  expect(gone(p, a2), `the panel ${JSON.stringify(p)} covers the question ${JSON.stringify(a2)}`).toBe(true);
  await expect(ask.getByRole("button", { name: "Allow" })).toBeVisible();
  const main = (await page.locator("#main").boundingBox())!;
  expect(main.x + main.width, "the page keeps its width").toBeGreaterThan(p.x + 100);
  const action = (await page.locator(".side-new").first().boundingBox())!;
  expect(gone(action, p)).toBe(true);
  // closing it brings the button back, clear of the question
  await panel(page).getByRole("button", { name: "Close Market Watch" }).click();
  await expect(launch(page)).toBeVisible();
  await expect(launch(page)).toBeFocused();
  const l2 = (await launch(page).boundingBox())!, a3 = (await ask.boundingBox())!;
  expect(gone(l2, a3)).toBe(true);
});

test("the panel can float, be dragged and be resized, and remembers where it was", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop only");
  await open(page, "/");
  const mw = await openPanel(page);
  // on a window under 1600px wide there is no dock to choose: it floats, and says so by having no dock button
  await expect(mw.getByRole("button", { name: /Dock the panel|Float the panel/ })).toHaveCount(0);
  const before = (await mw.boundingBox())!;
  expect(before.height).toBeLessThan(page.viewportSize()!.height);
  // dragged by its title bar
  await page.mouse.move(before.x + 80, before.y + 26);
  await page.mouse.down();
  await page.mouse.move(before.x - 120, before.y - 60, { steps: 6 });
  await page.mouse.up();
  const moved = (await mw.boundingBox())!;
  expect(Math.round(moved.x)).toBeLessThan(Math.round(before.x) - 100);
  expect(Math.round(moved.y)).toBeLessThan(Math.round(before.y) - 40);
  // wider from its corner
  await page.mouse.move(moved.x + 3, moved.y + 3);
  await page.mouse.down();
  await page.mouse.move(moved.x - 80, moved.y - 40, { steps: 6 });
  await page.mouse.up();
  const bigger = (await mw.boundingBox())!;
  expect(bigger.width).toBeGreaterThan(moved.width + 60);
  await page.reload();
  const again = (await panel(page).boundingBox())!;
  expect(Math.abs(again.x - bigger.x)).toBeLessThan(2); expect(Math.abs(again.width - bigger.width)).toBeLessThan(2);
});

test.describe("on a wide window", () => {
  test.use({ viewport: { width: 1680, height: 1000 } });
  test("the panel docks to the right edge, the page makes room, and it can be floated and docked again", async ({ page }, info) => {
    test.skip(info.project.name === "phone", "desktop only");
    await open(page, "/", { ads: true });
    const ask = page.getByTestId("consent");
    await expect(ask).toBeVisible();
    await launch(page).click();
    const p = (await panel(page).boundingBox())!;
    expect(Math.round(p.x + p.width)).toBe(1680);
    expect(Math.round(p.height)).toBe(1000);
    const main = (await page.locator("#main").boundingBox())!;
    expect(main.x + main.width, "the page makes room").toBeLessThanOrEqual(p.x + 1);
    const a2 = (await ask.boundingBox())!;
    expect(a2.x + a2.width, "the cookie question is left of the panel").toBeLessThanOrEqual(p.x + 1);
    await panel(page).getByRole("button", { name: "Float the panel over the page" }).click();
    expect((await panel(page).boundingBox())!.height).toBeLessThan(1000);
    await panel(page).getByRole("button", { name: "Dock the panel to the right" }).click();
    const dock = (await panel(page).boundingBox())!;
    expect(Math.round(dock.x + dock.width)).toBe(1680);
    expect(Math.round(dock.height)).toBe(1000);
  });
});

test("LIVE5-007: a visitor's public pages have no Markets button over their text, and read no market board", async ({ page }) => {
  // behaviour changed on purpose: the round button sat over the Free plan's bullets on an iPhone, for visitors the board wasn't for
  for (const path of ["/library", "/plans", "/"]) {
    const { errors, asked } = await open(page, path, { who: null });
    await expect(page.locator("h1").first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(800);
    await expect(launch(page)).toHaveCount(0);
    await expect(panel(page)).toHaveCount(0);
    expect(asked).not.toContain("/public/markets/watch");
    expect(errors).toEqual([]);
    await page.unrouteAll({ behavior: "ignoreErrors" });
  }
});

test("Free is told what it keeps before a limit bites", async ({ page, request }, info) => {
  test.skip(info.project.name === "phone", "desktop only");
  const auth = { Authorization: "Bearer free-token" };
  await reset(request, "free");
  const ids = ["BTC-USD", "ETH-USD", "SOL-USD"].map((s) => ({ market: "CRYPTO", symbol: s })).concat(["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ"].map((s) => ({ market: "US", symbol: s })),
    ["EURUSD=X", "USDJPY=X", "GBPUSD=X", "USDINR=X"].map((s) => ({ market: "FX", symbol: s })), ["GC=F", "CL=F", "SI=F", "NG=F", "BZ=F", "HG=F", "PL=F", "ZC=F", "ZW=F"].map((s) => ({ market: "CMDTY", symbol: s })));
  const put = await request.put(`${API}/watch/lists/default/items`, { headers: auth, data: { items: ids.slice(0, 18) } });
  expect(put.status()).toBe(200);
  await open(page, "/", { who: "free" });
  const mw = await openPanel(page);
  await expect(mw.getByRole("list", { name: "Watchlist" }).getByRole("listitem").first()).toBeVisible();
  await expect(mw.getByText("18 of 20 symbols on Free. Basic keeps 100.")).toBeVisible();
  await expect(mw.getByRole("link", { name: "See plans" })).toBeVisible();
  // a second list is refused before the tab is even offered
  await expect(mw.getByText("Free keeps 1 list. Basic keeps 10.")).toBeVisible();
  await expect(mw.getByRole("button", { name: "New list" })).toHaveCount(0);
  // fill it: the last two go in, the next is refused in plain words
  await request.put(`${API}/watch/lists/default/items`, { headers: auth, data: { items: ids.slice(0, 20) } });
  const refused = await request.put(`${API}/watch/lists/default/items`, { headers: auth, data: { items: ids.slice(0, 21) } });
  expect(refused.status()).toBe(402);
  expect((await refused.json()).detail.message).toMatch(/^The Free plan keeps 20 symbols in a list\. Basic keeps 100\./);
  await reset(request, "free");
});

test("Free is told about indicators and saved charts in the chart itself", async ({ page, request }, info) => {
  test.skip(info.project.name === "phone", "desktop only");
  await reset(request, "free");
  await open(page, "/chart/IN/INFY", { who: "free" });
  const chart = page.getByTestId("price-chart").first();
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  for (let i = 0; i < 3; i++) {
    await chart.getByRole("button", { name: "Indicators" }).click();
    await page.getByRole("menuitem").first().click();
  }
  await expect(chart).toHaveAttribute("data-studies", "3");
  await chart.getByRole("button", { name: "Indicators" }).click();
  await expect(page.getByText("Free keeps 3 indicators on a chart. Basic keeps 10.")).toBeVisible();
  await expect(page.getByRole("menuitem").first()).toBeDisabled();
  await page.keyboard.press("Escape");
  await reset(request, "free");
});

test("the Plans page lists the new limits", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "desktop only");
  await open(page, "/plans", { who: "pro" });
  for (const row of ["Market Watch lists", "Symbols in one Market Watch list", "Charts that keep your drawings and indicators", "Indicators on one chart"]) await expect(page.getByText(row).first()).toBeAttached();
});
