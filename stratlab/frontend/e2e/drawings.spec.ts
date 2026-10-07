import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

// Drawing tools on the shared price chart: a trend line and a long position are drawn, saved to the account for the
// symbol, still there after a reload, then edited (colour, style, lock, undo, handle drag, hide all) and deleted.
// Desktop uses the left rail and the mouse; the phone uses the bottom sheet and taps. Each project signs in as its
// own user so the two runs never share drawings.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const USERS: Record<string, [string, string, string]> = { desktop: ["admin-token", "u-admin", "owner@example.com"], phone: ["pro-token", "u-pro", "pro@example.com"] };
let auth = { Authorization: "Bearer admin-token" };
let session = sessionOf(USERS.desktop);
function sessionOf([token, id, email]: [string, string, string]) {
  return { access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
    refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}
const MINE = `${API}/me/drawings/IN/INFY`;

test.beforeEach(async ({ request }, info) => {
  const u = USERS[info.project.name] ?? USERS.desktop;
  auth = { Authorization: `Bearer ${u[0]}` };
  session = sessionOf(u);
  await request.put(`${API}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });
  await request.put(MINE, { headers: auth, data: { drawings: [], layout: null } });
});
test.afterEach(async ({ request }) => { await request.put(MINE, { headers: auth, data: { drawings: [], layout: null } }); });

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1");
    if (!sessionStorage.getItem("fresh")) { sessionStorage.setItem("fresh", "1"); for (const k of Object.keys(localStorage)) if (k.startsWith("stratlab.pc.")) localStorage.removeItem(k); }
  }, session);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  const chart = page.getByTestId("price-chart").first();
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  await chart.scrollIntoViewIfNeeded();
  return { chart, errors };
}

async function stageBox(chart: Locator) {
  const stage = chart.locator(".pc-stage");
  await stage.scrollIntoViewIfNeeded();
  let box = (await stage.boundingBox())!;
  await expect.poll(async () => {
    const now = (await stage.boundingBox())!;
    const same = now.x === box.x && now.y === box.y && now.width === box.width && now.height === box.height;
    box = now;
    return same;
  }, { timeout: 5000, intervals: [100] }).toBe(true);
  return box;
}

/** Click (desktop) or tap (phone) at fractions of the plot. */
async function place(page: Page, chart: Locator, phone: boolean, fx: number, fy: number) {
  const b = await stageBox(chart);
  const x = b.x + b.width * fx * 0.82, y = b.y + b.height * (fy * 0.72 + 0.04);      // keep clear of the price axis on the right and of the settings bar at the bottom of a phone chart
  if (phone) await page.touchscreen.tap(x, y); else { await page.mouse.move(x, y); await page.mouse.click(x, y); }
  return { x, y };
}

async function pickTool(page: Page, chart: Locator, phone: boolean, group: string, name: string) {
  if (phone) {
    await chart.getByRole("button", { name: "Draw", exact: true }).click();
    await page.getByRole("button", { name, exact: true }).click();
  } else {
    await chart.getByRole("button", { name: group, exact: true }).click();
    await page.getByRole("menuitem", { name, exact: true }).click();
  }
}

const saved = async (request: APIRequestContext) => (await (await request.get(MINE, { headers: auth })).json());
const count = (chart: Locator, n: number) => expect(chart).toHaveAttribute("data-drawings", String(n));

/** The drawings list: a pop-up beside the rail on desktop, a section of the sheet on a phone. */
async function openList(page: Page, chart: Locator, phone: boolean) {
  if (phone) {
    const sheet = page.getByRole("dialog", { name: "Drawing tools" });
    if (!(await sheet.isVisible())) await chart.getByRole("button", { name: "Draw", exact: true }).click();
    return sheet.getByRole("list", { name: "Drawings" });
  }
  const pop = page.getByRole("dialog", { name: "Drawings" });
  if (!(await pop.isVisible())) await chart.getByRole("button", { name: /^Drawings \(\d+\)$/ }).click();
  return pop.getByRole("list", { name: "Drawings" });
}
async function closeList(page: Page, phone: boolean) { if (phone) await page.getByRole("dialog", { name: "Drawing tools" }).getByRole("button", { name: "Done" }).click(); else await page.keyboard.press("Escape"); }

test("draw a trend line and a long position, reload, edit and delete", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const { chart, errors } = await open(page, "/research/IN/INFY");
  await count(chart, 0);

  // a trend line: click or tap the first point, then the second
  await pickTool(page, chart, phone, "Lines", "Trend line");
  await expect(chart).toHaveAttribute("data-tool", "trend");
  await place(page, chart, phone, 0.3, 0.55);
  await expect(chart).toHaveAttribute("data-step", "1");
  await place(page, chart, phone, 0.55, 0.4);
  await count(chart, 1);
  await expect(chart).toHaveAttribute("data-tool", "");

  // a long position: entry, then target; the risk amount sets the quantity
  await pickTool(page, chart, phone, "Positions", "Long position");
  await place(page, chart, phone, 0.6, 0.62);
  await place(page, chart, phone, 0.8, 0.35);
  await count(chart, 2);
  const bar = chart.getByRole("toolbar", { name: "Long position settings" });
  await expect(bar).toBeVisible();
  await bar.getByLabel("Risk amount").fill("5000");

  // saved to the account for this symbol
  await expect.poll(async () => (await saved(request)).drawings.map((d: { kind: string }) => d.kind), { timeout: 8000 }).toEqual(["trend", "long"]);
  const body = await saved(request);
  expect(body.drawings[1].risk).toBe(5000);
  expect(body.drawings[1].points).toHaveLength(3);
  await touchSafe(chart, phone);

  // reload: both come back
  await page.reload();
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  await count(chart, 2);

  // drag the trend line's first handle: its price changes in the saved copy
  const before = (await saved(request)).drawings[0].points[0].p;
  await (await openList(page, chart, phone)).getByRole("button", { name: "Trend line", exact: true }).click();
  await closeList(page, phone);
  await expect(chart.getByRole("toolbar", { name: "Trend line settings" })).toBeVisible();
  const box = await stageBox(chart);
  const ax = box.x + box.width * 0.3 * 0.82, ay = box.y + box.height * (0.55 * 0.72 + 0.04);
  await page.mouse.move(ax, ay);
  await page.mouse.down();
  await page.mouse.move(ax, ay + 40, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => (await saved(request)).drawings[0].points[0].p, { timeout: 8000 }).not.toBe(before);
  expect(box.width).toBeGreaterThan(0);

  // colour and line style
  const trend = chart.getByRole("toolbar", { name: "Trend line settings" });
  await trend.getByRole("button", { name: "Green" }).click();
  await trend.getByRole("button", { name: "Dashed line" }).click();
  await expect.poll(async () => { const d = (await saved(request)).drawings[0]; return `${d.color}/${d.dash}`; }, { timeout: 8000 }).toBe("green/dashed");

  // lock: it can't be deleted until unlocked
  await trend.getByRole("button", { name: "Lock", exact: true }).click();
  await expect(trend.getByRole("button", { name: "Delete drawing" })).toBeDisabled();
  await trend.getByRole("button", { name: "Unlock", exact: true }).click();

  // duplicate, then undo and redo it
  await trend.getByRole("button", { name: "Duplicate" }).click();
  await count(chart, 3);
  await chart.getByRole("button", { name: "Undo", exact: true }).click();
  await count(chart, 2);
  await chart.getByRole("button", { name: "Redo", exact: true }).click();
  await count(chart, 3);
  await chart.getByRole("button", { name: "Undo", exact: true }).click();
  await count(chart, 2);

  // hide all, then show again (the drawings are kept)
  if (!phone) {
    await chart.getByRole("button", { name: "Hide all drawings" }).click();
    await expect(chart).toHaveAttribute("data-hidden", "true");
    await count(chart, 2);
    await chart.getByRole("button", { name: "Show all drawings" }).click();
    await expect(chart).toHaveAttribute("data-hidden", "false");
  }

  // the list hides one drawing without deleting it
  let list = await openList(page, chart, phone);
  await list.getByRole("button", { name: "Hide Long position" }).click();
  await expect.poll(async () => (await saved(request)).drawings.find((d: { kind: string }) => d.kind === "long").hidden, { timeout: 8000 }).toBe(true);
  await list.getByRole("button", { name: "Show Long position" }).click();
  await expect.poll(async () => (await saved(request)).drawings.find((d: { kind: string }) => d.kind === "long").hidden, { timeout: 8000 }).toBe(false);

  // delete the long position from the list, then the trend line with the Delete key
  await list.getByRole("button", { name: "Delete Long position" }).click();
  await count(chart, 1);
  list = await openList(page, chart, phone);
  await list.getByRole("button", { name: "Trend line", exact: true }).click();
  await closeList(page, phone);
  await chart.locator(".pc-stage").focus();
  await page.keyboard.press("Delete");
  await count(chart, 0);
  await expect.poll(async () => (await saved(request)).drawings.length, { timeout: 8000 }).toBe(0);
  await page.reload();
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  await count(chart, 0);
  expect(errors).toEqual([]);
});

/** Nothing on the page is wider than the screen, and (on a phone) every control is big enough to tap. */
async function touchSafe(chart: Locator, phone: boolean) {
  const page = chart.page();
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  if (!phone) return;
  const small = await chart.evaluate((root) => Array.from(root.querySelectorAll("button, select, input")).filter((el) => {
    const b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 && b.height < 32;
  }).map((el) => `${el.tagName} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 20)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

test("a fibonacci, the measure tools, a note and the magnet", async ({ page, request }, info) => {
  test.setTimeout(120_000);
  const phone = info.project.name === "phone";
  const { chart, errors } = await open(page, "/research/IN/INFY");
  await pickTool(page, chart, phone, "Shapes and Fibonacci", "Fibonacci retracement");
  await place(page, chart, phone, 0.3, 0.7);
  await place(page, chart, phone, 0.6, 0.3);
  await count(chart, 1);
  await pickTool(page, chart, phone, "Measure", "Measure");
  await place(page, chart, phone, 0.4, 0.6);
  await place(page, chart, phone, 0.7, 0.45);
  await count(chart, 2);
  await pickTool(page, chart, phone, "Measure", "Date range");
  await place(page, chart, phone, 0.2, 0.2);
  await place(page, chart, phone, 0.5, 0.2);
  await pickTool(page, chart, phone, "Measure", "Price range");
  await place(page, chart, phone, 0.75, 0.3);
  await place(page, chart, phone, 0.85, 0.6);
  await pickTool(page, chart, phone, "Notes", "Text note");
  await place(page, chart, phone, 0.35, 0.25);
  await chart.getByLabel("Note text").fill("Planning note");
  await pickTool(page, chart, phone, "Lines", "Vertical line");
  await place(page, chart, phone, 0.45, 0.5);
  await pickTool(page, chart, phone, "Notes", "Arrow");
  await place(page, chart, phone, 0.15, 0.8);
  await place(page, chart, phone, 0.25, 0.7);
  await pickTool(page, chart, phone, "Shapes and Fibonacci", "Parallel channel");
  await place(page, chart, phone, 0.1, 0.9);
  await place(page, chart, phone, 0.4, 0.75);
  await place(page, chart, phone, 0.4, 0.9);
  await pickTool(page, chart, phone, "Lines", "Horizontal ray");
  await place(page, chart, phone, 0.5, 0.65);
  await pickTool(page, chart, phone, "Shapes and Fibonacci", "Rectangle");
  await place(page, chart, phone, 0.55, 0.8);
  await place(page, chart, phone, 0.7, 0.9);
  await pickTool(page, chart, phone, "Lines", "Ray");
  await place(page, chart, phone, 0.2, 0.4);
  await place(page, chart, phone, 0.3, 0.35);
  await pickTool(page, chart, phone, "Notes", "Brush");
  const b = await stageBox(chart);
  await page.mouse.move(b.x + b.width * 0.5, b.y + b.height * 0.15);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width * 0.58, b.y + b.height * 0.2, { steps: 6 });
  await page.mouse.move(b.x + b.width * 0.66, b.y + b.height * 0.12, { steps: 6 });
  await page.mouse.up();
  await count(chart, 12);
  await expect.poll(async () => (await saved(request)).drawings.map((d: { kind: string }) => d.kind).sort(), { timeout: 8000 })
    .toEqual(["arrow", "brush", "channel", "drange", "fib", "hray", "measure", "prange", "ray", "rect", "text", "vline"]);
  expect((await saved(request)).drawings.find((d: { kind: string }) => d.kind === "text").text).toBe("Planning note");

  // the magnet snaps a new level's time to a candle
  if (!phone) {
    await chart.getByRole("button", { name: "Magnet" }).click();
    await expect(chart).toHaveAttribute("data-magnet", "true");
    await pickTool(page, chart, phone, "Lines", "Horizontal line");
    await place(page, chart, phone, 0.9, 0.5);
    await count(chart, 13);
  }
  await touchSafe(chart, phone);
  expect(errors).toEqual([]);
});

test("the shortcut list and keys", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const { chart } = await open(page, "/research/IN/INFY");
  await chart.getByRole("button", { name: "Drawing tools and shortcuts" }).click();
  const dlg = page.getByRole("dialog", { name: "Drawing shortcuts" });
  await expect(dlg).toContainText("Trend line");
  await expect(dlg).toContainText("Ctrl/Cmd + Z");
  await page.keyboard.press("Escape");
  if (phone) return;
  await chart.locator(".pc-stage").focus();
  await page.keyboard.press("t");
  await expect(chart).toHaveAttribute("data-tool", "trend");
  await page.keyboard.press("Escape");
  await expect(chart).toHaveAttribute("data-tool", "");
  await page.keyboard.press("Shift+L");
  await expect(chart).toHaveAttribute("data-tool", "");
  await page.keyboard.press("l");
  await expect(chart).toHaveAttribute("data-tool", "long");
  await page.keyboard.press("Escape");
});

test("drawings follow a timeframe change and survive being signed in elsewhere", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  // saved by "another device": straight to the account, anchored to a time and price inside the daily history
  const candles = (await (await request.get(`${API}/research/chart/IN/INFY?tf=1d&range=1y`, { headers: auth })).json()).candles;
  const mid = candles[Math.floor(candles.length / 2)], end = candles[candles.length - 20];
  const t = (c: { t: string }) => Date.parse(c.t);
  const put = await request.put(MINE, { headers: auth, data: { drawings: [{ id: "far1", kind: "trend", color: "blue", points: [{ t: t(mid), p: mid.c }, { t: t(end), p: end.c }] }], layout: { tf: "1d", range: "1Y", type: "line", volume: false } } });
  expect(put.ok(), await put.text()).toBeTruthy();
  const { chart } = await open(page, "/research/IN/INFY");
  await count(chart, 1);                                                // it came from the account, not this browser
  await expect(chart).toHaveAttribute("data-type", "line");             // the saved layout too
  await chart.getByRole("group", { name: "Timeframe" }).getByRole("button", { name: "1 hour", exact: true }).click();
  await expect(chart).toHaveAttribute("data-loaded", "1h", { timeout: 20_000 });
  await count(chart, 1);                                                // still anchored after the timeframe change
  await expect.poll(async () => (await saved(request)).layout?.tf, { timeout: 8000 }).toBe("1h");
  expect((await saved(request)).drawings[0].points[0].t).toBe(t(mid));
  void phone;
});

test("a replay chart takes drawings too, kept apart from any symbol", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 221 : 218;                            // Basic accounts in the fake world (not the ones replay.spec uses)
  const who = { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  const h = { Authorization: `Bearer load-${n}` };
  await request.delete(`${API}/trade/replay`, { headers: h });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto("/trade/replay");
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  if (await welcome.waitFor({ timeout: 3000 }).then(() => true).catch(() => false)) { await welcome.getByRole("button", { name: /^All of it/ }).click(); await page.goto("/trade/replay"); }
  await page.getByRole("group", { name: "Candle size" }).getByRole("button", { name: "Daily" }).click();
  await page.getByRole("button", { name: "Random stock and date" }).click();
  await expect(page.getByTestId("rp-label")).toHaveText("Hidden symbol", { timeout: 30_000 });
  const chart = page.getByTestId("price-chart");
  await expect(chart).toHaveAttribute("data-bars", /\d+/);
  await pickTool(page, chart, phone, "Lines", "Horizontal line");
  await place(page, chart, phone, 0.5, 0.5);
  await count(chart, 1);
  await page.getByRole("button", { name: "Next candle" }).click();
  await count(chart, 1);
  await expect(page.getByTestId("rp-label")).toHaveText("Hidden symbol");
  await request.delete(`${API}/trade/replay`, { headers: h });
});

// Screenshots for review: E2E_SHOTS=<folder> npx playwright test e2e/drawings.spec.ts -g screenshots
test("screenshots of the toolbar, a long position, a fibonacci and the phone sheet", async ({ page }, info) => {
  const dir = process.env.E2E_SHOTS;
  test.skip(!dir, "set E2E_SHOTS to a folder to save pictures");
  test.setTimeout(120_000);
  const phone = info.project.name === "phone";
  const { chart } = await open(page, "/research/IN/INFY");
  await pickTool(page, chart, phone, "Shapes and Fibonacci", "Fibonacci retracement");
  await place(page, chart, phone, 0.25, 0.85);
  await place(page, chart, phone, 0.6, 0.15);
  await pickTool(page, chart, phone, "Positions", "Long position");
  await place(page, chart, phone, 0.62, 0.6);
  await place(page, chart, phone, 0.9, 0.3);
  await chart.getByLabel("Risk amount").fill("10000");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${dir}/${info.project.name}-long-position-and-fib.png` });
  if (phone) {
    await chart.getByRole("button", { name: "Draw", exact: true }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${dir}/phone-sheet.png` });
  } else {
    await chart.getByRole("button", { name: "Lines", exact: true }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${dir}/desktop-toolbar.png` });
  }
});
