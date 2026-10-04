import { expect, test, type Locator, type Page } from "@playwright/test";

// The price chart on a company page and on a backtest in a notebook: chart types, indicators, drawings, zoom and
// reset, full screen, older candles loading on scroll-back, and nothing wider than a phone's screen.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
// Desktop and phone run at the same time and both save drawings, so each signs in as its own user.
const USERS: Record<string, [string, string, string]> = { desktop: ["admin-token", "u-admin", "owner@example.com"], phone: ["pro-token", "u-pro", "pro@example.com"] };
let admin = { Authorization: "Bearer admin-token" };
let session = sessionOf(USERS.desktop);
function sessionOf([token, id, email]: [string, string, string]) {
  return { access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
    refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}
test.beforeEach(async ({ request }, info) => {
  const u = USERS[info.project.name] ?? USERS.desktop;
  admin = { Authorization: `Bearer ${u[0]}` };
  session = sessionOf(u);
  await request.put(`${API}/me/prefs`, { headers: admin, data: { level: "some", focus: "both" } });     // no welcome questions
});

/** No drawings on this symbol yet, for this test's user. */
async function noDrawings(request: import("@playwright/test").APIRequestContext, symbol: string) {
  const r = await request.put(`${API}/chart/drawings`, { headers: admin, data: { symbol, items: [] } });
  expect(r.ok(), await r.text()).toBeTruthy();
}

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1");
    for (const k of Object.keys(localStorage)) if (k.startsWith("stratlab.pc.")) localStorage.removeItem(k);
  }, session);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  const chart = page.getByTestId("price-chart").first();
  await expect(chart).toHaveAttribute("data-bars", /^[1-9]\d*$/, { timeout: 30_000 });
  await chart.scrollIntoViewIfNeeded();
  return { chart, errors };
}

const num = async (chart: Locator, key: string) => Number(await chart.getAttribute(`data-${key}`));

async function noOverflow(page: Page) {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
}

/** Every control in the chart is big enough for a finger on a phone. */
async function touchable(chart: Locator) {
  const small = await chart.evaluate((root) => Array.from(root.querySelectorAll("button, select, input")).filter((el) => {
    const b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 && b.height < 32;
  }).map((el) => `${el.tagName} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 20)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

async function addIndicator(page: Page, chart: Locator, name: RegExp) {
  await chart.getByRole("button", { name: "Indicators" }).click();
  await page.getByRole("menuitem", { name }).click();
}

async function pickTool(page: Page, chart: Locator, name: string, phone: boolean) {
  if (phone) {
    await chart.getByRole("button", { name: "Draw", exact: true }).click();
    await page.getByRole("menuitem", { name }).click();
  } else await chart.getByRole("button", { name, exact: true }).click();
}

/** Drag across the chart's plot, from and to fractions of its size. */
async function dragOn(page: Page, chart: Locator, from: [number, number], to: [number, number]) {
  const box = (await chart.locator(".pc-stage").boundingBox())!;
  await page.mouse.move(box.x + box.width * from[0], box.y + box.height * from[1]);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * (from[0] + to[0]) / 2, box.y + box.height * (from[1] + to[1]) / 2, { steps: 4 });
  await page.mouse.move(box.x + box.width * to[0], box.y + box.height * to[1], { steps: 4 });
  await page.mouse.up();
}

/** The full set of checks, on whichever page the chart is on. */
async function exercise(page: Page, chart: Locator, phone: boolean, key: string) {
  // chart types, remembered
  await chart.getByLabel("Chart type").selectOption("heikin");
  await expect(chart).toHaveAttribute("data-type", "heikin");
  await chart.getByLabel("Chart type").selectOption("bars");
  await expect(chart).toHaveAttribute("data-type", "bars");
  expect(await page.evaluate(() => localStorage.getItem("stratlab.pc.type"))).toBe('"bars"');
  await chart.getByLabel("Chart type").selectOption("candles");

  // an indicator: add, change its setting, remove
  const before = await num(chart, "studies");
  await addIndicator(page, chart, /Moving average \(SMA\)/);
  await expect(chart).toHaveAttribute("data-studies", String(before + 1));
  await expect(chart.locator(".pc-legend")).toContainText("SMA 20");
  await chart.getByRole("button", { name: "Settings for SMA 20" }).click();
  await page.getByRole("dialog", { name: /SMA 20 settings/ }).getByLabel("Length").fill("50");
  await expect(chart.locator(".pc-legend")).toContainText("SMA 50");
  await page.getByRole("button", { name: "Done" }).click();
  await addIndicator(page, chart, /^RSI/);
  await expect(chart).toHaveAttribute("data-studies", String(before + 2));
  await chart.getByRole("button", { name: "Remove SMA 50" }).click();
  await expect(chart).toHaveAttribute("data-studies", String(before + 1));
  await chart.getByRole("button", { name: /^Remove RSI/ }).click();
  await expect(chart).toHaveAttribute("data-studies", String(before));

  // draw a trend line, see it saved to the account, then delete it
  await pickTool(page, chart, "Trend line", phone);
  await expect(chart).toHaveAttribute("data-tool", "trend");
  await dragOn(page, chart, [0.3, 0.55], [0.6, 0.7]);
  await expect(chart).toHaveAttribute("data-drawings", "1");
  await expect(chart).not.toHaveAttribute("data-selected", "");
  await expect.poll(async () => (await (await page.request.get(`${API}/chart/drawings?symbol=${encodeURIComponent(key)}`, { headers: admin })).json()).items.length, { timeout: 5000 }).toBe(1);
  await chart.getByRole("button", { name: "Delete drawing" }).click();
  await expect(chart).toHaveAttribute("data-drawings", "0");
  await expect.poll(async () => (await (await page.request.get(`${API}/chart/drawings?symbol=${encodeURIComponent(key)}`, { headers: admin })).json()).items.length, { timeout: 5000 }).toBe(0);
  // a price level: one click; selected by clicking it again, deleted with the key
  await pickTool(page, chart, "Price level", phone);
  const stage = chart.locator(".pc-stage");
  const at = async (fx: number, fy: number) => { const b = (await stage.boundingBox())!; await page.mouse.click(b.x + b.width * fx, b.y + b.height * fy); };
  await at(0.4, 0.6);
  await expect(chart).toHaveAttribute("data-drawings", "1");
  await at(0.2, 0.85);                     // somewhere else: deselects
  await expect(chart).toHaveAttribute("data-selected", "");
  await at(0.5, 0.6);                      // on the line: selects
  await expect(chart).not.toHaveAttribute("data-selected", "");
  await page.keyboard.press("Delete");
  await expect(chart).toHaveAttribute("data-drawings", "0");

  // zoom in, then reset
  const spacing = await num(chart, "spacing");
  if (phone) await chart.locator(".pc-stage").press("+");
  else await chart.getByRole("button", { name: "Zoom in" }).click();
  await expect.poll(() => num(chart, "spacing")).toBeGreaterThan(spacing * 1.1);
  if (!phone) {
    const box = (await stage.boundingBox())!;
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    const s2 = await num(chart, "spacing");
    await page.mouse.wheel(0, 300);                 // wheel down zooms out around the pointer
    await expect.poll(() => num(chart, "spacing")).toBeLessThan(s2);
  }
  await chart.getByRole("button", { name: "Reset the view" }).click();
  // back to the first view (the price axis may have widened a few px for longer labels meanwhile)
  await expect.poll(async () => Math.abs(await num(chart, "spacing") / spacing - 1)).toBeLessThan(0.06);

  // log and % scales
  await chart.getByRole("button", { name: "Log" }).click();
  await expect(chart).toHaveAttribute("data-mode", "log");
  await chart.getByRole("button", { name: "%" }).click();
  await expect(chart).toHaveAttribute("data-mode", "percent");
  await chart.getByRole("button", { name: "%" }).click();
  await expect(chart).toHaveAttribute("data-mode", "normal");

  // full screen and back
  await chart.getByRole("button", { name: "Full screen" }).click();
  await expect(chart).toHaveAttribute("data-full", "true");
  const vh = page.viewportSize()!.height;
  await expect.poll(async () => (await chart.locator(".pc-stage").boundingBox())!.height).toBeGreaterThan(vh * 0.5);
  await noOverflow(page);
  await chart.getByRole("button", { name: "Exit full screen" }).click();
  await expect(chart).toHaveAttribute("data-full", "false");

  // the PNG download
  const download = page.waitForEvent("download");
  await chart.getByRole("button", { name: "Download as PNG" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.png$/);

  // the table view
  await chart.getByRole("button", { name: "Table" }).click();
  await expect(chart.locator(".pc-table tbody tr").first()).toBeVisible();
  await chart.getByRole("button", { name: "Table" }).click();
}

test("price chart on a company page: types, indicators, drawings, zoom, full screen", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  await noDrawings(request, "IN:RELIANCE");
  const chunks: string[] = [];
  page.on("request", (r) => { if (/PriceChart-[\w-]+\.js$/.test(r.url())) chunks.push(r.url()); });
  const { chart, errors } = await open(page, "/research/IN/RELIANCE");
  expect(chunks.length, "the chart's code loads in its own file").toBe(1);
  await exercise(page, chart, phone, "IN:RELIANCE");
  // timeframes: hourly candles, then scroll back until older ones load
  if (phone) await chart.getByLabel("Timeframe (phone)").selectOption("1h");
  else await chart.getByRole("radio", { name: "1h" }).click();
  await expect(chart).toHaveAttribute("data-loaded", "1h", { timeout: 20_000 });
  await expect(chart).toHaveAttribute("data-more", "true");
  const n = await num(chart, "bars");
  await expect(async () => {
    await chart.locator(".pc-stage").focus();
    for (let k = 0; k < 15; k++) await page.keyboard.press("ArrowLeft");
    expect(await num(chart, "bars")).toBeGreaterThan(n);
  }).toPass({ timeout: 30_000 });
  // ranges pick their timeframe
  await chart.getByRole("radio", { name: "5Y" }).click();
  await expect(chart).toHaveAttribute("data-tf", "1w");
  // compare with another company on a % scale
  await chart.getByRole("button", { name: "Compare" }).click();
  await page.getByLabel("Symbol to compare").fill("TCS");
  await page.getByRole("button", { name: "Compare on a % scale" }).click();
  await expect(chart).toHaveAttribute("data-mode", "percent");
  await expect(chart.locator(".pc-legend")).toContainText("TCS");
  await noOverflow(page);
  if (phone) await touchable(chart);
  expect(errors).toEqual([]);
  await expect(chart.locator(".pc-legend")).not.toContainText(/NaN|undefined|Infinity/);
});

test("price chart on a backtest: candles with the trades and the rules' indicators", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const ema = { name: "Chart check", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
    exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `Chart ${info.project.name}`, question: "q", strategy: ema, instrument: "CRYPTO:BTC-USD" } })).json();
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 800 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  await noDrawings(request, "CRYPTO:BTC-USD");
  const { chart, errors } = await open(page, `/n/${nb.id}/e/1`);
  await expect(chart).toHaveAttribute("data-studies", "2");          // EMA 10 and EMA 30, from the rules
  await expect(chart.locator(".pc-legend")).toContainText("EMA 10");
  expect(await num(chart, "markers")).toBeGreaterThan(0);
  await exercise(page, chart, phone, "CRYPTO:BTC-USD");
  await noOverflow(page);
  if (phone) await touchable(chart);
  expect(errors).toEqual([]);
});

test("pages without a price chart don't download its code", async ({ page }) => {
  const chunks: string[] = [];
  page.on("request", (r) => { if (/PriceChart-[\w-]+\.js$/.test(r.url())) chunks.push(r.url()); });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto("/plans");
  await expect(page.getByText("Plans").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  expect(chunks).toEqual([]);
});
