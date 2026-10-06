import { expect, test, type Locator, type Page } from "@playwright/test";

// The charts' interactions on the pages that lean on them: a tooltip on hover (a tap on a phone), the crosshair shared
// by linked charts, drag-to-zoom and Reset, range buttons, switching series in the legend, Index to 100, the table view
// and keyboard moves. Signed in as the site owner (the fake world's admin), tour seen.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}

/** No crash, nothing wider than the screen, and on a phone every chart control big enough to tap. */
async function sane(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll(".ch button"))
    .filter((el) => { const b = el.getBoundingClientRect(); return b.width && b.height && b.height < 32; })
    .map((el) => `"${(el.textContent || "").trim()}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "chart controls too small to tap").toEqual([]);
}

/** Point at a spot of a chart's plot: hover with a mouse, tap on a touch screen. */
async function point(page: Page, chart: Locator, fx: number, phone: boolean) {
  const svg = chart.locator("svg.ch-svg");
  await svg.scrollIntoViewIfNeeded();
  const box = (await svg.boundingBox())!;
  if (phone) await page.touchscreen.tap(box.x + box.width * fx, box.y + box.height / 2);
  else await page.mouse.move(box.x + box.width * fx, box.y + box.height / 2);
}

/** Drag across a chart from one fraction of its width to another (desktop). */
async function drag(page: Page, chart: Locator, from: number, to: number) {
  const box = (await chart.locator("svg.ch-svg").boundingBox())!;
  await page.mouse.move(box.x + box.width * from, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * to, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
}

/** The first x-axis label of a chart. */
const firstTick = (chart: Locator) => chart.locator("svg.ch-svg text.ch-tick").filter({ hasText: /[A-Za-z]{3}|\d{4}|\d+ [A-Z]/ }).first().textContent();

test("charts: breadth's linked charts show a tooltip, switch series, zoom together and reset", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/breadth");
  const grid = page.getByTestId("breadth-charts");
  await expect(grid).toBeVisible({ timeout: 30_000 });
  const ad = grid.locator(".ch").first();
  const ma = grid.locator(".ch").filter({ has: page.getByRole("button", { name: "Above 200-day" }) });
  await expect(ma).toHaveCount(1);

  // the tooltip: the date in full and every series at that day, values first
  await point(page, ma, 0.6, phone);
  const tip = ma.locator(".ch-tip");
  await expect(tip).toBeVisible();
  await expect(tip.locator(".ch-tip-h")).toHaveText(/^[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2,3} \d{4}$/);
  await expect(tip).toContainText("Above 50-day");
  await expect(tip).toContainText("Above 200-day");
  await expect(tip.locator("b").first()).toHaveText(/^\d+(\.\d)?%$/);
  // linked: the A/D chart above draws its crosshair on the same day, and only the chart pointed at shows a tooltip
  const day = await ma.locator(".ch-cross").getAttribute("data-at");
  await expect(ad.locator(".ch-cross")).toHaveAttribute("data-at", day!);
  await expect(page.locator(".ch-tip")).toHaveCount(1);

  // the legend switches a series off and on; the last one can't be switched off
  const b200 = ma.getByRole("button", { name: "Above 200-day" });
  await expect(b200).toHaveAttribute("aria-pressed", "true");
  await b200.click();
  await expect(b200).toHaveAttribute("aria-pressed", "false");
  await point(page, ma, 0.4, phone);
  await expect(ma.locator(".ch-tip")).toBeVisible();
  await expect(ma.locator(".ch-tip")).not.toContainText("Above 200-day");
  await ma.getByRole("button", { name: "Above 50-day" }).click();
  await expect(ma.getByRole("button", { name: "Above 50-day" })).toHaveAttribute("aria-pressed", "true");
  await b200.click();
  await expect(b200).toHaveAttribute("aria-pressed", "true");

  if (!phone) {
    // drag across the A/D line: it zooms in, the linked charts follow, Reset brings back everything
    const before = await firstTick(ad);
    await drag(page, ad, 0.5, 0.8);
    const reset = ad.getByRole("button", { name: "Reset zoom" });
    await expect(reset).toBeVisible();
    await expect(ma.getByRole("button", { name: "Reset zoom" })).toBeVisible();
    await expect.poll(() => firstTick(ad)).not.toBe(before);
    await reset.click();
    await expect(reset).toHaveCount(0);
    await expect(ma.getByRole("button", { name: "Reset zoom" })).toHaveCount(0);
    await expect.poll(() => firstTick(ad)).toBe(before);
    // keys: the arrows walk the crosshair, plus zooms, Escape goes back
    await ad.locator(".ch-plot").focus();
    await page.keyboard.press("End");
    await expect(ad.locator(".ch-tip[role=status]")).toBeVisible();
    const last = await ad.locator(".ch-tip-h").innerText();
    await page.keyboard.press("ArrowLeft");
    await expect(ad.locator(".ch-tip-h")).not.toHaveText(last);
    await page.keyboard.press("+");
    await expect(reset).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(reset).toHaveCount(0);
  }
  // the card's Table switch lists the days
  const card = grid.locator("section.k-card").first();
  await card.getByRole("button", { name: "Table" }).click();
  await expect(card.getByRole("table").locator("tbody tr").first()).toBeVisible();
  await card.getByRole("button", { name: "Table" }).click();
  await expect(card.getByRole("table")).toHaveCount(0);
  await sane(page, errors, phone);
});

test("charts: the options payoff shows P&L at a price, the spot and breakevens, and zooms on a price range", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/options");
  await page.getByRole("button", { name: /Price it now/ }).click({ timeout: 30_000 });
  const chart = page.getByTestId("payoff-chart");
  await expect(chart).toBeVisible({ timeout: 30_000 });
  await expect(chart.locator("svg text").filter({ hasText: /^Spot [\d,]+$/ })).toHaveCount(1);
  await point(page, chart, 0.5, phone);
  await expect(chart.locator(".ch-tip .ch-tip-h")).toHaveText(/^At [\d,]+$/);
  await expect(chart.locator(".ch-tip")).toContainText(/−?₹[\d,]+\s*At expiry/);
  if (!phone) {
    await drag(page, chart, 0.3, 0.7);
    await expect(chart.getByRole("button", { name: "Reset zoom" })).toBeVisible();
    await chart.getByRole("button", { name: "Reset zoom" }).click();
    await expect(chart.getByRole("button", { name: "Reset zoom" })).toHaveCount(0);
  }
  await sane(page, errors, phone);
});

test("charts: an experiment's equity curve has ranges, Index to 100 and a legend that switches lines", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const post = async (path: string, data: object) => {
    const r = await request.post(API + path, { headers: admin, data });
    expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  const EMA = { name: "Charts test", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
    exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await post("/notebooks", { name: "Charts test", question: "Do the charts work?", strategy: EMA, instrument: "CRYPTO:BTC-USD" });
  await post(`/notebooks/${nb.id}/experiments`, { days: 1500 });
  const errors = await open(page, `/n/${nb.id}/e/1`);
  const chart = page.locator(".ch").filter({ has: page.getByRole("button", { name: "Buy and hold" }) });
  await expect(chart).toBeVisible({ timeout: 30_000 });
  // ranges: 1Y shows the last year only
  const ranges = chart.getByRole("group", { name: "Chart range" });
  await expect(ranges.getByRole("button")).toHaveText(["1M", "3M", "6M", "1Y", "All"]);
  await ranges.getByRole("button", { name: "1Y" }).click();
  await expect(ranges.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "true");
  await expect(chart.getByRole("button", { name: "Reset zoom" })).toBeVisible();
  // index to 100: values read as an index, the money in brackets
  await chart.getByRole("button", { name: "Index to 100" }).click();
  await point(page, chart, 0.7, phone);
  await expect(chart.locator(".ch-tip b").first()).toHaveText(/^\d+(\.\d+)?$/);
  await expect(chart.locator(".ch-tip")).toContainText(/\(\$[\d,]+\)/);
  await chart.getByRole("button", { name: "Index to 100" }).click();
  // switch buy and hold off
  await chart.getByRole("button", { name: "Buy and hold" }).click();
  await point(page, chart, 0.6, phone);
  await expect(chart.locator(".ch-tip")).toContainText("Strategy");
  await expect(chart.locator(".ch-tip")).not.toContainText("Buy and hold");
  await ranges.getByRole("button", { name: "All" }).click();
  await expect(chart.getByRole("button", { name: "Reset zoom" })).toHaveCount(0);
  await sane(page, errors, phone);
});
