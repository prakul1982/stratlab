import { test, expect, type Page } from "@playwright/test";
import { open, sane, sessionAs } from "./pages-kit";

// LIVE5 (re-score after Release 13, 6 Nov 2026): measured in the browser on the fake world.
const pro = sessionAs("pro-token", "u-pro", "pro@example.com");

async function resultsFit(page: Page) {
  const day = page.getByTestId("results-day").first();
  await expect(day.locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
  return day.locator(".k-tbl-wrap").evaluate((w) => {
    const names = [...w.querySelectorAll(".res-name")].filter((n) => getComputedStyle(n).display !== "none").map((n) => {
      const r = n.getBoundingClientRect(), text = n.textContent ?? "";
      // the share of the name in view: its box over the width it needs
      return { text, shown: Math.min(1, r.width / Math.max(1, (n as HTMLElement).scrollWidth)), width: r.width };
    });
    const heads = [...w.querySelectorAll("thead th")].filter((th) => getComputedStyle(th).display !== "none").map((th) => th.getBoundingClientRect().right);
    return { scroll: w.scrollWidth, client: w.clientWidth, right: w.getBoundingClientRect().right, heads, names };
  });
}

for (const width of [1024, 1280, 1366, 1440]) {
  test(`LIVE5-002: every column of a results day is in view at ${width} px and no company name is cut to a few letters`, async ({ page }, info) => {
    test.skip(info.project.name === "phone", "desktop widths");
    await page.setViewportSize({ width, height: 900 });
    const errors = await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called", pro);
    const fit = await resultsFit(page);
    expect(fit.scroll, "the table scrolls sideways").toBeLessThanOrEqual(fit.client + 1);
    for (const r of fit.heads) expect(r, "a column past the table's edge").toBeLessThanOrEqual(fit.right + 1);
    expect(fit.names.length).toBeGreaterThan(0);
    for (const n of fit.names) expect(n.width, `"${n.text}" cut to ${Math.round(n.width)} px`).toBeGreaterThanOrEqual(Math.min(96, n.width / Math.max(0.01, n.shown)) - 1);
    await sane(page, errors);
  });
}

test("LIVE5-001: after the close every results row carries a price and the footer names the session's day", async ({ page }) => {
  const errors = await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called", pro);
  const note = page.getByTestId("results-prices");
  await expect(note).toBeVisible({ timeout: 30_000 });
  // the fake world's market trades at its moment: the footer says so; with no quote the rows show their stored close, in grey
  await expect(note).toContainText(/Prices as of|Prices are each company's last close/);
  await expect.poll(async () => page.locator("[data-testid=results-day] tbody tr td.k-brief").evaluateAll((tds) =>
    tds.filter((td) => /^\s*[–-]\s*$/.test(td.textContent ?? "")).length), { timeout: 30_000 }).toBe(0);
  await sane(page, errors);
});

test("LIVE5 partial: the landing page on a phone is under 9,000 px, its long blocks one fold away, and nothing is lost", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "a phone's width");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator("h1").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2500);
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  expect(h, "the landing page's length on a phone").toBeLessThan(9000);
  for (const label of ["Options, more Trade tools and the markets", "See a sample company page", "What Free includes", "The three steps"]) {
    const fold = page.locator("details.lp-phone-fold").filter({ has: page.locator(":scope > summary", { hasText: label }) }).first();
    await expect(fold).toHaveCount(1);
    await fold.locator(":scope > summary").click();
    await expect(fold).toHaveAttribute("open", "");
  }
  await expect(page.getByText("Paper trading trial: 1 strategy for 5 market days").first()).toBeVisible();
  await expect(page.getByTestId("markets-launch")).toHaveCount(0);                    // LIVE5-007: no floating button over it
});
