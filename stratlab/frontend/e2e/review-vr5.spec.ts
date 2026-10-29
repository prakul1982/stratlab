import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// VR-5 (28 Oct 2026): what a harsh phone-first visual review found, checked on the drawn pages. Each test sets its own width (390 or 360),
// so it is the same on the desktop and phone projects.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN = session("admin-token", "u-admin", "owner@example.com");

async function open(page: Page, path: string, s: object | null, width: number, extra?: (p: Page) => Promise<void>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width, height: 800 });
  await page.route("**/*", (r) => { const h = new URL(r.request().url()).hostname; return h === "127.0.0.1" || h === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  if (extra) await extra(page);
  await page.addInitScript((x) => { if (x) localStorage.setItem("sb-demo-auth-token", JSON.stringify(x)); localStorage.setItem("stratlab.tour.v1", "1"); }, s);
  await page.goto(path);
  return errors;
}
const noSideways = async (page: Page) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
};

test("VR5-006: Holdings' four totals go two across on a phone, and the breadth card's three go 2 + 1, not one under another", async ({ page }) => {
  await open(page, "/holdings", ADMIN, 390);
  const stats = page.locator("#h-summary .k-stats");
  await expect(stats).toBeVisible({ timeout: 30_000 });
  await expect(stats).toHaveClass(/\bduo\b/);
  const tops = await stats.locator(".k-stat").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  expect([...new Set(tops)].length, `tops ${tops}`).toBe(2);
  await page.goto("/invest");
  const card = page.getByTestId("breadth-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  const rows = await card.locator(".k-stat").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)));
  expect([...new Set(rows)].length, `breadth tops ${rows}`).toBe(2);
  // each figure on one line, at the smallest phone too
  await page.setViewportSize({ width: 360, height: 780 });
  const lines = await card.locator(".k-stat-v").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight)));
  expect(Math.max(...lines)).toBeLessThan(1.5);
  await noSideways(page);
});

test("VR5-001 and VR5-002: the Invest home's eyebrow is not its title again, and the live breadth line has no second Live pill", async ({ page }) => {
  await open(page, "/invest", ADMIN, 390);
  await expect(page.getByRole("heading", { level: 1, name: "Invest home" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".k-eyebrow", { hasText: /^Invest · companies and markets$/i })).toBeVisible();
  const card = page.getByTestId("breadth-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.locator(".k-badge.live")).toHaveCount(0);
});

test("VR5-003: at 360px the signed-out library's header has the logo whole beside the Menu and a one-line button, and nothing scrolls sideways", async ({ page }) => {
  await open(page, "/library", null, 360);
  const btn = page.locator(".pub-nav").getByRole("button", { name: "Continue with Google" });
  await expect(btn).toBeVisible({ timeout: 30_000 });
  await expect(btn).toHaveText(/Sign in/);
  const [logo, menu, b] = await Promise.all([page.locator(".pub-nav > a").first().boundingBox(), page.locator(".pub-nav summary").boundingBox(), btn.boundingBox()]);
  expect(logo!.x + logo!.width, "the logo ends before the Menu starts").toBeLessThanOrEqual(menu!.x);
  expect(menu!.x + menu!.width).toBeLessThanOrEqual(b!.x);
  expect(b!.height, "one line").toBeLessThan(50);
  await page.locator("details.pub-menu summary").click();
  await noSideways(page);
});

test("VR5-007: a research post's six-column tables are cards on a phone, and none runs past the screen", async ({ page }) => {
  await open(page, "/blog/classic-strategies-ten-markets-after-costs", null, 360);
  // (VR6-008: the post's first card table is now "The four checks"; the rule sets' tables are the ones with a Trades column)
  // (VR7-002: on a phone each market's tables are folded: the first market is opened, as e2e/blog.spec.ts opens it)
  await page.locator("details.mk").first().evaluate((e) => { (e as HTMLDetailsElement).open = true; });
  const table = page.locator('.btbl.wide:has(td[data-l="Trades"])').first();
  await expect(table).toBeVisible({ timeout: 30_000 });
  const clipped = await page.locator(".btbl").evaluateAll((els) => els.filter((e) => e.scrollWidth > e.clientWidth + 1).length);
  expect(clipped, "tables wider than their box").toBe(0);
  await expect(table.locator("tbody tr").first().locator("td").nth(0)).toBeVisible();
  const first = await table.locator("tbody tr").first().locator("td").nth(3).evaluate((e) => getComputedStyle(e, "::before").content);
  expect(first).toContain("Trades");
  await noSideways(page);
});

test("VR5-004: a long chip or badge wraps at 360px instead of pushing the page sideways (the US filings page's 8-K item names)", async ({ page }) => {
  await open(page, "/research/filings?region=US&view=all", ADMIN, 360);
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  await noSideways(page);
});

test("VR5-011: the Free column's trial note in the plan table stays two lines at 390px", async ({ page }) => {
  await open(page, "/plans", ADMIN, 390);
  // (LIVE1C-092: in the app the side-by-side tables are one fold, closed: open it)
  await page.getByText("Compare every limit and feature side by side").click();
  const row = page.getByRole("row", { name: /Paper trading sessions at a time/ });
  await expect(row).toContainText("1 (5-market-day trial)", { timeout: 30_000 });
  const h = await row.locator(".k-sub-line").first().evaluate((e) => e.getBoundingClientRect().height);
  expect(h, "the note's height (two lines of 13px is about 36)").toBeLessThan(50);
  await noSideways(page);
});

test("VR5-013: the cookie question takes under a quarter of a 360x800 phone screen, its two answers one width", async ({ page }) => {
  await open(page, "/", null, 360, async (p) => {
    await p.route(/connect\.facebook\.net|clarity\.ms/, (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
    await p.route(/\/config\.js(\?|$)/, async (r) => { const real = await (await r.fetch()).text(); await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, {CLARITY_PROJECT_ID:"abc123"});\n` }); });
  });
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible({ timeout: 30_000 });
  const box = await ask.boundingBox();
  expect(box!.height, "the question's height").toBeLessThan(200);
  const w = await ask.getByRole("button").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
  expect(new Set(w).size, `answer widths ${w}`).toBe(1);
});

test("VR5-014: Net worth's 'Add an entry' kinds are short rows on a phone (the picture beside the words), not 120px cards one under another", async ({ page }) => {
  await open(page, "/money/net-worth", ADMIN, 360);
  await page.getByRole("button", { name: /Add an entry/ }).first().click();
  const tiles = page.getByRole("dialog").locator(".k-tile");
  await expect(tiles.first()).toBeVisible({ timeout: 30_000 });
  const hs = await tiles.evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(Math.max(...hs), `tile heights ${hs}`).toBeLessThan(80);
  const dlg = await page.getByRole("dialog").evaluate((e) => e.scrollHeight);
  expect(dlg, "the dialog's whole height").toBeLessThan(1300);
});

// VR5-owner-1 (the owner's choice for VR4-016): the Invest home's watchlist shows its first six stocks and "See all" for the rest
// The two watchlist tests set the watchlist of a Pro user of the fake database, one per project: on the owner's own list the desktop and
// phone runs (two workers at once) set it under each other, so the phone one saw the other's three stocks, not its eight.
async function watcher(request: APIRequestContext, phone: boolean, API: string) {
  const n = phone ? 89 : 83;
  const head = { Authorization: `Bearer load-${n}` };
  await request.put(`${API}/me/prefs`, { headers: head, data: { focus: "both", level: "some", space: "all" } });
  return { head, who: session(`load-${n}`, `u-load-${n}`, `load${n}@example.com`) };
}

test("VR5-owner-1: the Invest home's watchlist card shows six of a longer list, with See all to the full watchlist, and ends near its neighbour column", async ({ page, request }, info) => {
  const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
  const { head, who } = await watcher(request, info.project.name === "phone", API);
  const before = await (await request.get(`${API}/research/watchlist`, { headers: head })).json();
  const eight = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC", "SBIN", "WIPRO", "AXISBANK"].map((symbol) => ({ region: "IN", symbol }));
  try {
    await request.put(`${API}/research/watchlist`, { headers: head, data: { items: eight } });
    await open(page, "/invest", who, info.project.name === "phone" ? 390 : 1440);
    const card = page.locator(".k-card", { has: page.getByRole("heading", { name: "Your watchlist" }) });
    await expect(card.locator(".inv-tile").first()).toBeVisible({ timeout: 30_000 });
    await expect(card.locator(".inv-tile")).toHaveCount(6);
    await expect(card.getByTestId("watch-see-all")).toHaveText("See all 8 →");
    await expect(card.getByTestId("watch-see-all")).toHaveAttribute("href", "/research/watchlist");
    await expect(card.getByText(/^India$/i)).toHaveCount(0);           // the market is the toggle above, not a label again over the stocks
    if (info.project.name !== "phone") {
      await expect(page.getByRole("heading", { name: "Results today" })).toBeVisible();
      const ends = await page.locator(".k-card").evaluateAll((els) => {
        const by = (t: string) => els.find((e) => e.querySelector("h2, h3")?.textContent?.trim() === t)!.getBoundingClientRect().bottom;
        return [by("Your watchlist"), by("Results today")];
      });
      expect(Math.abs(ends[0] - ends[1]), `bottoms ${ends}`).toBeLessThan(80);
    }
    await card.getByTestId("watch-see-all").click();
    await expect(page).toHaveURL(/\/research\/watchlist/);
  } finally {
    await request.put(`${API}/research/watchlist`, { headers: head, data: { items: before.items ?? [] } });
  }
});

test("VR5-owner-1: a list of six or fewer has no See all", async ({ page, request }, info) => {
  const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
  const { head, who } = await watcher(request, info.project.name === "phone", API);
  const before = await (await request.get(`${API}/research/watchlist`, { headers: head })).json();
  try {
    await request.put(`${API}/research/watchlist`, { headers: head, data: { items: ["RELIANCE", "TCS", "INFY"].map((symbol) => ({ region: "IN", symbol })) } });
    await open(page, "/invest", who, 390);
    await expect(page.locator(".inv-tile").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("watch-see-all")).toHaveCount(0);
  } finally {
    await request.put(`${API}/research/watchlist`, { headers: head, data: { items: before.items ?? [] } });
  }
});
