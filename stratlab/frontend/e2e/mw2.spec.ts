import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// MW-2 (owner, 9 Nov, with a screenshot of the Markets panel): "why is this only extendable from one top corner ... while adding
// something why is it so cluttered ... we need to redesign it". The floating panel is sized from every edge and corner and stays whole
// inside the window when the window shrinks; lists named "1" and "2" have tabs that read "List 1" and "List 2" (they read "1 6" and
// "2 1": the name beside its count); and with the markets shut the foot names the last trading day, never the weekend day it was read
// on. The add-symbol search is in e2e/mw1-watch.spec.ts (its first test). Its own Pro accounts (the fake world's load-245 and load-248),
// so nothing here meets the other Market Watch specs' lists.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const WHO = { desktop: session("load-245", "u-load-245", "load245@example.com"), phone: session("load-248", "u-load-248", "load248@example.com") };
const mine = (info: { project: { name: string } }) => (info.project.name === "phone" ? WHO.phone : WHO.desktop);
const FLOAT = { open: true, mode: "float", w: 400, h: 500, x: 500, y: 200, list: null, sort: "custom", chart: null };
const item = (market: string, symbol: string, name: string, kind = "stock") => ({ id: `${market}:${symbol}`, market, symbol, name, kind });

async function reset(request: APIRequestContext, api: string, token: string) {
  const auth = { Authorization: `Bearer ${token}` };
  await request.put(`${api}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });
  const got = await (await request.get(`${api}/watch/lists`, { headers: auth })).json();
  for (const l of got.lists) if (!l.default) await request.delete(`${api}/watch/lists/${l.id}`, { headers: auth });
  await request.put(`${api}/watch/lists/default/items`, { headers: auth, data: { items: [] } });
}

async function open(page: Page, who: ReturnType<typeof mine>, layout?: Record<string, unknown>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(([s, l]) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    if (!sessionStorage.getItem("fresh")) {
      sessionStorage.setItem("fresh", "1");
      for (const k of Object.keys(localStorage)) if (k.startsWith("stratlab.watch.")) localStorage.removeItem(k);
      if (l) localStorage.setItem(`stratlab.watch.layout.${s.user.id}`, JSON.stringify(l));
    }
  }, [who, layout ?? null] as const);
  await page.goto("/");
  await page.getByText("What brings you here?").waitFor({ timeout: 2500 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}

const panel = (page: Page) => page.getByTestId("market-watch");
const box = async (page: Page) => { const b = (await panel(page).boundingBox())!; return { l: Math.round(b.x), t: Math.round(b.y), r: Math.round(b.x + b.width), b: Math.round(b.y + b.height) }; };

test("the floating panel is resized from every edge and corner, stays inside a smaller window, and is where it was after a reload", async ({ page, request, api }, info) => {
  test.skip(info.project.name === "phone", "a phone's panel is a full-height sheet: nothing to size");
  const who = mine(info);
  await reset(request, api, who.access_token);
  const errors = await open(page, who, FLOAT);
  await expect(panel(page)).toBeVisible();
  await expect(panel(page).locator(".mw-size")).toHaveCount(8);
  expect(await box(page)).toEqual({ l: 500, t: 200, r: 900, b: 700 });
  // each grip in turn: pressed at its middle, pulled 40px outward both ways; only the edges it holds move
  const pull = async (edge: string) => {
    const g = (await panel(page).locator(`.mw-size.${edge}`).boundingBox())!;
    const x = g.x + g.width / 2, y = g.y + g.height / 2;
    const dx = edge.includes("e") ? 40 : edge.includes("w") ? -40 : 15, dy = edge.includes("s") ? 40 : edge.includes("n") ? -40 : 15;
    const before = await box(page);
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + dx, y + dy, { steps: 5 });
    await page.mouse.up();
    const after = await box(page);
    expect(after, `pulled from ${edge}`).toEqual({
      l: before.l + (edge.includes("w") ? -40 : 0), t: before.t + (edge.includes("n") ? -40 : 0),
      r: before.r + (edge.includes("e") ? 40 : 0), b: before.b + (edge.includes("s") ? 40 : 0) });
  };
  for (const edge of ["e", "s", "w", "n", "se", "sw", "ne", "nw"]) await pull(edge);
  expect(await box(page)).toEqual({ l: 380, t: 80, r: 1020, b: 820 });
  // never smaller than its least size, however far an edge is pushed in
  const e = (await panel(page).locator(".mw-size.e").boundingBox())!;
  await page.mouse.move(e.x + e.width / 2, e.y + e.height / 2);
  await page.mouse.down();
  await page.mouse.move(100, 400, { steps: 5 });
  await page.mouse.up();
  expect((await box(page)).r - (await box(page)).l).toBe(300);
  // dragged by its header to the bottom right, then the window shrinks: the panel is still whole inside it
  const b0 = await box(page);
  await page.mouse.move(b0.l + 60, b0.t + 24);
  await page.mouse.down();
  await page.mouse.move(b0.l + 60 + 2000, b0.t + 24 + 2000, { steps: 5 });
  await page.mouse.up();
  const vp = page.viewportSize()!;
  expect((await box(page)).r).toBe(vp.width);
  expect((await box(page)).b).toBe(vp.height);
  await page.setViewportSize({ width: 1000, height: 620 });
  await expect.poll(async () => { const b = await box(page); return b.l >= 0 && b.t >= 0 && b.r <= 1000 && b.b <= 620; }, { message: "inside the smaller window" }).toBe(true);
  // kept for this person on this device: a reload finds it where it was left
  const kept = await box(page);
  await page.reload();
  await expect(panel(page)).toBeVisible();
  expect(await box(page)).toEqual(kept);
  expect(errors).toEqual([]);
});

test("a finger sizes the floating panel too", async ({ browser, request, api }, info) => {
  test.skip(info.project.name === "phone", "a phone's panel is a full-height sheet: nothing to size");
  const who = mine(info);
  await reset(request, api, who.access_token);
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, hasTouch: true, baseURL: info.project.use.baseURL });
  const page = await context.newPage();
  await open(page, who, FLOAT);
  await expect(panel(page)).toBeVisible();
  const before = await box(page);
  const g = (await panel(page).locator(".mw-size.se").boundingBox())!;
  expect(g.width, "a finger's grip is wider").toBeGreaterThanOrEqual(28);
  // a touch pointer pressed on the bottom-right corner and moved 50px out
  const x = g.x + g.width / 2, y = g.y + g.height / 2;
  await page.evaluate(([px, py]) => {
    const el = document.querySelector(".mw-size.se")!;
    const ev = (type: string, dx: number) => new PointerEvent(type, { pointerId: 7, pointerType: "touch", isPrimary: true, bubbles: true, cancelable: true, clientX: px + dx, clientY: py + dx, button: 0 });
    el.dispatchEvent(ev("pointerdown", 0));
    window.dispatchEvent(ev("pointermove", 25));
    window.dispatchEvent(ev("pointermove", 50));
    window.dispatchEvent(ev("pointerup", 50));
  }, [x, y]);
  await expect.poll(() => box(page)).toEqual({ l: before.l, t: before.t, r: before.r + 50, b: before.b + 50 });
  await context.close();
});

test("lists named only a number have tabs in words, and the count is said in words below, not beside the name", async ({ page, request, api }, info) => {
  const who = mine(info), auth = { Authorization: `Bearer ${who.access_token}` };
  await reset(request, api, who.access_token);
  for (const name of ["1", "2"]) await request.post(`${api}/watch/lists`, { headers: auth, data: { name } });
  const lists = (await (await request.get(`${api}/watch/lists`, { headers: auth })).json()).lists as { id: string; name: string }[];
  const one = lists.find((l) => l.name === "1")!, two = lists.find((l) => l.name === "2")!;
  await request.put(`${api}/watch/lists/${one.id}/items`, { headers: auth, data: { items: [item("IN", "^NSEI", "NIFTY 50", "index"), item("IN", "ICICIBANK", "ICICI Bank"), item("IN", "SBIN", "State Bank of India"),
    item("IN", "WIPRO", "Wipro"), item("IN", "INFY", "Infosys"), item("IN", "TCS", "Tata Consultancy Services")] } });
  await request.put(`${api}/watch/lists/${two.id}/items`, { headers: auth, data: { items: [item("US", "^IXIC", "NASDAQ", "index")] } });
  const phone = info.project.name === "phone";
  const errors = await open(page, who, phone ? undefined : { ...FLOAT, x: null, y: null });
  if (phone) await page.getByRole("button", { name: "Markets", exact: true }).click();
  const mw = panel(page);
  const tabs = mw.getByRole("tab");
  await expect(tabs).toHaveText(["Watchlist", "List 1", "List 2"]);            // was "Watchlist 0", "1 6", "2 1"
  await expect(tabs.nth(1)).toHaveAttribute("title", "List 1: 6 symbols");
  await tabs.nth(1).click();
  await expect(mw.getByRole("list", { name: "List 1" }).getByRole("listitem")).toHaveCount(6);
  await expect(mw.locator(".mw-foot")).toContainText("6 symbols");
  await tabs.nth(2).click();
  await expect(mw.locator(".mw-foot")).toContainText("1 symbol");
  // the bar is the one search field and the list's two buttons: no "+ Add symbol", no market or sort pickers
  await expect(mw.locator(".mw-bar").getByRole("combobox")).toHaveCount(1);
  await expect(mw.locator(".mw-bar select")).toHaveCount(0);
  await expect(mw.getByRole("button", { name: "+ Add symbol" })).toHaveCount(0);
  expect(errors).toEqual([]);
  await reset(request, api, who.access_token);
});

test.describe("with the market shut", () => {
  test.use({ moment: "closed" });

  test("the foot says the last trading day, Friday, on a Sunday: never 'last close Sun'", async ({ page, request, api }, info) => {
    const who = mine(info), auth = { Authorization: `Bearer ${who.access_token}` };
    await reset(request, api, who.access_token);
    await request.put(`${api}/watch/lists/default/items`, { headers: auth, data: { items: [item("IN", "INFY", "Infosys"), item("IN", "TCS", "Tata Consultancy Services")] } });
    const phone = info.project.name === "phone";
    await open(page, who, phone ? undefined : { ...FLOAT, x: null, y: null });
    if (phone) await page.getByRole("button", { name: "Markets", exact: true }).click();
    const mw = panel(page);
    await expect(mw.getByRole("list", { name: "Watchlist" }).getByRole("listitem")).toHaveCount(2);
    // the closed moment is Sun 1 Nov 2026: India last traded on Fri 30 Oct
    await expect(mw.getByTestId("mw-as-of")).toHaveText("· Closed · last close Fri 30 Oct", { timeout: 20_000 });
    await expect(mw.locator(".mw-foot")).not.toContainText(/Sat|Sun/);
    await reset(request, api, who.access_token);
  });
});
