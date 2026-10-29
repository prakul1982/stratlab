import { expect, test, type Page } from "@playwright/test";

// VR-6 (28 Oct 2026): what a harsh visual review of the company page, the blog and the most-used pages found, checked on the drawn pages. Each test sets
// its own width, so it is the same on the desktop and phone projects.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN = session("admin-token", "u-admin", "owner@example.com");

async function open(page: Page, path: string, s: object | null, width: number, height = 900) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width, height });
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.addInitScript((x) => { if (x) localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1"); }, s);
  await page.goto(path);
  return errors;
}
const noSideways = async (page: Page) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
};

test("VR6-003: on a phone the company page's market cap is half a row like the other tiles, and no tile is left alone but the odd last one", async ({ page, baseURL }) => {
  await open(page, `${baseURL}/stocks/in/RELIANCE`, null, 390);
  const tiles = page.locator(".tiles .stat");
  await expect(tiles.first()).toBeVisible({ timeout: 30_000 });
  const rows = await tiles.evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { top: Math.round(r.top), w: Math.round(r.width) }; }));
  const byRow = new Map<number, number>();
  for (const r of rows) byRow.set(r.top, (byRow.get(r.top) ?? 0) + 1);
  const alone = [...byRow.values()].filter((n) => n === 1).length;
  expect(alone, `tiles per row ${[...byRow.values()]}`).toBeLessThanOrEqual(rows.length % 2);        // two to a row; an odd count has one tile on its own, at the end
  expect(rows[0].w, "the market cap tile's width").toBeLessThan(390 * 0.55);
  await noSideways(page);
});

test("VR6-002: the exchange flag comes after the key figures, not between the price and the chart, with no grey paragraph of its own", async ({ page, baseURL }) => {
  await open(page, `${baseURL}/stocks/in/RELIANCE`, null, 1440);
  const order = await page.evaluate(() => {
    const y = (sel: string) => document.querySelector(sel)?.getBoundingClientRect().top ?? -1;
    const h2 = (t: string) => Array.from(document.querySelectorAll("h2")).find((e) => e.textContent === t)?.getBoundingClientRect().top ?? -1;
    return { chart: h2("Share price"), figures: h2("Key figures"), flag: h2("Exchange surveillance"), trend: h2("Price trend"), box: y("[data-surveillance]") };
  });
  expect(order.chart).toBeGreaterThan(0);
  expect(order.figures, "key figures after the chart").toBeGreaterThan(order.chart);
  expect(order.flag, "the flag after the key figures").toBeGreaterThan(order.figures);
  expect(order.trend, "and before the price trend").toBeGreaterThan(order.flag);
  await expect(page.locator("[data-surveillance] > p")).toHaveCount(0);
});

test("VR6-007: a post's three and four column tables fit a 360px phone, the four checks go four across, and no tile is half a row alone", async ({ page, baseURL }) => {
  for (const slug of ["sip-vs-lump-sum-nifty-50", "ipo-listing-day-india-2026-so-far", "classic-strategies-ten-markets-after-costs"]) {
    await open(page, `${baseURL}/blog/${slug}`, null, 360);
    await expect(page.locator("article").first()).toBeVisible({ timeout: 30_000 });
    const clipped = await page.locator(".btbl").evaluateAll((els) => els.filter((e) => e.scrollWidth > e.clientWidth + 1).length);
    expect(clipped, `${slug}: tables wider than their box`).toBe(0);
    await noSideways(page);
  }
  const checks = page.locator('.btbl.w4 tbody tr').first();
  await expect(checks).toBeVisible();
  const tops = await checks.locator("td").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  expect(new Set(tops).size, `the four figures of a check ${tops}`).toBe(1);
});

test("VR6-005 (O5): a brief opens with one line and one table of the indices, not a paragraph and tiles saying the same figures", async ({ page, baseURL }) => {
  await open(page, `${baseURL}/blog/briefs`, null, 390);
  await page.locator("ul.posts a.post", { hasText: "India market brief" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Index closes" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("article ul.kpis li")).toHaveCount(0);
  const idx = page.locator("article .btbl").first();
  await expect(idx).toContainText("NIFTY 50");
  expect(await idx.locator("tbody tr").count()).toBeGreaterThanOrEqual(2);
  await noSideways(page);
});

test("VR6-013: each plan card shows about 400 characters of its lines and folds the rest, every line still in the page", async ({ page }) => {
  await open(page, "/plans", ADMIN, 1440);
  await expect(page.locator(".k-plans")).toBeVisible({ timeout: 30_000 });
  for (const p of ["free", "basic", "pro"]) {
    const more = page.getByTestId(`plan-more-${p}`);
    await expect(more).toHaveCount(1);
    expect(await more.locator("li").count(), `${p}: folded lines`).toBeGreaterThanOrEqual(2);
    await expect(more).not.toHaveAttribute("open", "");
  }
  const heights = await page.locator(".k-plans > .k-card").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(Math.max(...heights) - Math.min(...heights), `card heights ${heights}`).toBeLessThan(130);          // were 984, 1,176 and 1,015
  await page.getByTestId("plan-more-basic").locator("summary").click();
  await expect(page.getByTestId("plan-more-basic").locator("li").first()).toBeVisible();
});

test("VR6-024: a phone shows twelve strategy cards and Show 12 more; a desktop shows them all", async ({ page }) => {
  await open(page, "/library", ADMIN, 390);
  await expect(page.locator(".lib-card").first()).toBeVisible({ timeout: 30_000 });
  const total = await page.getByText(/^\d+ strategies$/).innerText().then((t) => Number(t.split(" ")[0]));
  expect(total).toBeGreaterThan(12);
  expect(await page.locator(".lib-card").count()).toBe(12);
  await expect(page.getByTestId("lib-show-more")).toContainText(`Showing 12 of ${total}.`);
  await page.getByTestId("lib-show-more").getByRole("button").click();
  expect(await page.locator(".lib-card").count()).toBe(Math.min(24, total));
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("lib-show-more")).toHaveCount(0);
  expect(await page.locator(".lib-card").count()).toBe(total);
});

test("VR6-010 and VR6-011: with nothing on the watchlist, My space and the Invest home give it a row to itself, with no card left short beside a long one", async ({ page, request }, info) => {
  const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
  // each project empties its OWN Pro account's watchlist (load-131 / load-134): the desktop and phone runs of this test overlap,
  // and on one shared account one run's restore refilled the list while the other was measuring (CI, 29 Oct)
  const n = info.project.name === "phone" ? 134 : 131;
  const head = { Authorization: `Bearer load-${n}` };
  await request.put(`${API}/me/prefs`, { headers: head, data: { level: "some", focus: "both" } });        // past the welcome question
  const before = await (await request.get(`${API}/research/watchlist`, { headers: head })).json();
  try {
    await request.put(`${API}/research/watchlist`, { headers: head, data: { items: [] } });
    await open(page, "/mine", session(`load-${n}`, `u-load-${n}`, `load${n}@example.com`), 1440);
    await expect(page.getByTestId("mine-watch")).toContainText(/Your watchlist is empty/, { timeout: 30_000 });
    const w = await page.evaluate(() => ["coming", "watch"].map((id) => Math.round(document.querySelector(`[data-card="${id}"]`)!.getBoundingClientRect().width)));
    expect(Math.abs(w[0] - w[1]), `widths ${w}`).toBeLessThan(2);                         // both the page's width: neither stands beside the other
    expect(w[1]).toBeGreaterThan(900);
    await page.goto("/invest");
    await expect(page.getByRole("heading", { name: "Your watchlist" })).toBeVisible({ timeout: 30_000 });
    const cards = () => page.evaluate(() => ["Your watchlist", "Coming up", "Results today"].map((t) => {
      const c = Array.from(document.querySelectorAll(".k-card")).find((e) => e.querySelector("h2, h3")?.textContent?.trim() === t);
      const r = c?.getBoundingClientRect(); return r ? [Math.round(r.left), Math.round(r.width)] : [0, 0];
    }));
    // (until the watchlist is read the three share rows as before; once it is known to be empty they stack)
    await expect.poll(async () => { const c = await cards(); return Math.min(...c.map((x) => x[1])); }, { timeout: 30_000, message: "each card is the page's width, none beside another" }).toBeGreaterThan(900);
    const lefts = (await cards()).map((c) => c[0]);
    expect(Math.max(...lefts) - Math.min(...lefts), `left edges ${lefts}`).toBeLessThan(3);
  } finally {
    await request.put(`${API}/research/watchlist`, { headers: head, data: { items: before.items ?? [] } });
  }
});

test("VR6-020: link rows and the library search are 44px to a thumb on a phone", async ({ page }) => {
  await open(page, "/library", ADMIN, 390);
  const search = page.getByLabel("Search the library");
  await expect(search).toBeVisible({ timeout: 30_000 });
  expect((await search.boundingBox())!.height).toBeGreaterThanOrEqual(43.5);
  await page.goto("/research/IN/RELIANCE");
  const link = page.getByRole("link", { name: /^Read the full entry/ });
  await expect(link).toBeVisible({ timeout: 30_000 });
  expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(43.5);
});

test("VR6-018: on a wide screen the chart's view buttons are with the scale buttons under the chart, not alone on a second line of the toolbar", async ({ page }) => {
  await open(page, "/research/IN/RELIANCE", ADMIN, 1440);
  const chart = page.getByTestId("price-chart");
  await expect(chart).toBeVisible({ timeout: 30_000 });
  const where = await chart.evaluate((e) => ({ inBar: e.querySelectorAll(".pc-bar .pc-end").length, inFoot: e.querySelectorAll(".pc-foot .pc-end").length }));
  expect(where).toEqual({ inBar: 0, inFoot: 1 });
  await expect(chart.getByRole("button", { name: "Full screen" })).toBeVisible();
});

test("VR6-014: Account's usage list leaves no row alone beside an empty cell", async ({ page }) => {
  await open(page, "/account", ADMIN, 1440);
  const rows = page.locator("#plan .k-rows.two > div");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  const tops = await rows.evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.width)]; }));
  const byRow = new Map<number, number>();
  for (const [t] of tops) byRow.set(t, (byRow.get(t) ?? 0) + 1);
  const narrowAlone = tops.filter(([t, w]) => byRow.get(t) === 1 && w < 700).length;
  expect(narrowAlone, `rows ${JSON.stringify(tops)}`).toBe(0);
});
