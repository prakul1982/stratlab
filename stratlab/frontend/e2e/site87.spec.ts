import { expect, test, type Page } from "@playwright/test";

// site87 (Release 87): the owner's rules, proved on the fake world.
// 1. SCROLL BY SCREEN ("it works on screen size, how much of the block a person can see on screen. Then you give a scroll"): a list or table
//    block is never taller than the screen; content that fits is drawn whole (Mood's 16 sectors at 1440x900), only content taller than the
//    screen scrolls inside its block, with its header row sticky (the owner's reference: Movers), never for fewer than three hidden rows.
// 2. Every side-by-side layout ends level (±2 px): Invest home's watchlist beside the column of Coming up and Results today, /mine's pair.
// 3. No "Show more", "Show all", "+N more" or paging button on any list; long server lists load more on their own (Filings).
// 4. Themes: compact chips, never the same theme twice, the "updated" day inside the chip (no hover box over the next chips), India and the
//    US strictly apart: switching market never maps India's "India defence" in the US.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
// S87_SHOTS=<folder>: also save the screenshots (the lane's before/after; never in CI)
const SHOTS = process.env.S87_SHOTS;
const TAG = process.env.S87_TAG ?? "after";
const SYMS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "AXISBANK", "KOTAKBANK", "BHARTIARTL", "MARUTI", "TITAN", "ONGC", "WIPRO",
  "SUNPHARMA", "NTPC", "POWERGRID", "TATASTEEL", "HINDALCO"];

async function signIn(page: Page, theme: "dark" | "light" = "dark") {
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
}

async function watchWorld(page: Page, watch: number) {
  await signIn(page);
  const items = SYMS.slice(0, watch).map((s) => ({ region: "IN", symbol: s, name: `${s} Ltd` }));
  await page.route((u) => u.pathname === "/research/watchlist", (r) => (r.request().method() === "GET" ? r.fulfill({ json: { items } }) : r.fallback()));
  await page.route((u) => u.pathname === "/research/quotes", (r) => {
    const asked = (new URL(r.request().url()).searchParams.get("symbols") ?? "").split(",").filter(Boolean);
    return r.fulfill({ json: Object.fromEntries(asked.map((s) => [s, { price: 100 + SYMS.indexOf(s) * 7.5, change_pct: (SYMS.indexOf(s) % 5) - 2, at: "2026-10-28T05:30:00Z" }])) });
  });
}

const shot = async (page: Page, name: string, sel?: string) => {
  if (!SHOTS) return;
  if (sel) await page.locator(sel).first().screenshot({ path: `${SHOTS}/${TAG}-${name}.png` }).catch(() => undefined);
  else await page.screenshot({ path: `${SHOTS}/${TAG}-${name}.png`, fullPage: false }).catch(() => undefined);
};

/** Invest home's watchlist card and the column beside it, measured. */
const investPair = (page: Page) => page.evaluate(() => {
  const row = document.querySelector('[data-testid="invest-watch-row"]')!;
  const [a, b] = Array.from(row.children) as HTMLElement[];
  const card = (el: Element) => (el.matches(".k-card") ? el : el.querySelector(".k-card"))!;
  const col = b.matches(".k-card") ? b : b;
  const ra = card(a).getBoundingClientRect(), rb = col.getBoundingClientRect();
  const lastCard = Array.from(col.querySelectorAll(":scope > .k-card")).pop() ?? col;
  const wrap = card(a).querySelector<HTMLElement>(".k-tbl-wrap");
  return { aTop: ra.top, aBottom: ra.bottom, bTop: rb.top, bBottom: rb.bottom, lastBottom: lastCard.getBoundingClientRect().bottom, side: ra.right <= rb.left + 2,
    rows: card(a).querySelectorAll("tbody tr").length, over: !!wrap?.hasAttribute("data-over"), boxH: wrap?.clientHeight ?? 0, boxSh: wrap?.scrollHeight ?? 0,
    csvInBody: !!card(a).querySelector(".k-tbl-tools [data-csv]"), border: wrap ? getComputedStyle(wrap).borderTopWidth : "", seeAll: !!card(a).querySelector('[data-testid="watch-see-all"]') };
});

for (const width of [1280, 1440, 1700]) {
  for (const watch of [4, 12]) {
    test(`LEVEL: Invest home at ${width} with ${watch} stocks: the watchlist and the column beside it end level (±2 px), every stock in the card`, async ({ page }, info) => {
      test.skip(info.project.name !== "desktop", "a desktop width");
      await page.setViewportSize({ width, height: 900 });
      await watchWorld(page, watch);
      await page.goto("/invest");
      const row = page.getByTestId("invest-watch-row");
      await expect(row.locator(".k-card").first().locator("tbody tr")).toHaveCount(watch, { timeout: 30_000 });
      await expect(row.getByTestId("invest-events")).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(600);                // the blocks are sized a frame after the rows draw
      const m = await investPair(page);
      await shot(page, `invest-${width}-${watch}`, '[data-testid="invest-watch-row"]');
      expect(m.side, "the watchlist beside the column").toBe(true);
      expect(Math.abs(m.aTop - m.bTop)).toBeLessThanOrEqual(2);
      expect(Math.abs(m.aBottom - m.bBottom), `watchlist ends ${m.aBottom}, the column ${m.bBottom}`).toBeLessThanOrEqual(2);
      expect(Math.abs(m.lastBottom - m.bBottom), "the column's last card reaches its bottom").toBeLessThanOrEqual(2);
      expect(m.rows).toBe(watch);
      expect(m.csvInBody, "no Download CSV button in the card's body").toBe(false);
      expect(m.seeAll, "no See all: every stock is in the card").toBe(false);
      expect(m.border, "no box inside the card: the card is the frame").toBe("0px");
      if (m.over) expect(m.boxSh - m.boxH, "a scroll hides at least three rows").toBeGreaterThan(80);
      // the CSV is in the card's ⋯ menu
      await row.locator(".k-card").first().getByRole("button", { name: "Section menu" }).click();
      await expect(page.getByTestId("card-menu-csv")).toBeVisible();
      const dl = page.waitForEvent("download");
      await page.getByTestId("card-menu-csv").click();
      expect((await dl).suggestedFilename()).toMatch(/^stratlab-watchlist-/);
    });
  }
}
