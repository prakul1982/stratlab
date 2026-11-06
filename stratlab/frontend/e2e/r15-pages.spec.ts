import { expect, test } from "@playwright/test";
import { open, sane } from "./pages-kit";

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

// R15 (owner's screenshots of 7 Nov): page fixes. Each test names its item.

test("R15 #1: More in Money starts open, and still folds", async ({ page }) => {
  const errors = await open(page, "/money", "More in Money");
  const more = page.getByTestId("more-tools");
  const btn = more.getByRole("button", { name: /^More in Money/ });
  await expect(btn).toHaveAttribute("aria-expanded", "true");
  await expect(more.getByRole("table").first()).toBeVisible();
  await btn.click();
  await expect(btn).toHaveAttribute("aria-expanded", "false");
  await expect(more.getByRole("table").first()).toBeHidden();
  await sane(page, errors);
});

test("R15 #7: US stocks tax's Each sale in rupees shows the first 10 sales, then Show more", async ({ page }) => {
  // 13 sales in the year (the fake world has none): the page's own reply with rows put in
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/money/us-tax", async (r) => {
    const res = await r.fetch();
    const d = await res.json();
    const rate = { rate: 88.35, on: "2025-09-30", fallback: false };
    d.trades = [{ id: "t1", d: "2025-09-10", side: "B", sym: "SYM1", qty: 2, price: 500 }];
    if (Array.isArray(d.years) && d.years[0]) {
      d.fy = d.years[0].fy;
      d.years[0].rows = Array.from({ length: 13 }, (_, i) => ({ symbol: `SYM${i + 1}`, bought: "2025-09-10", sold: "2025-10-13", qty: 2, cost_usd: 1000, sale_usd: 1010,
        rate_buy: rate, rate_sell: rate, cost: 88350, indexed_cost: null, sale: 89234, gain: 884, term: "ST", rate: null, bucket: "slab" }));
      d.years[0].count = 13;
    }
    d.locked = false;
    await r.fulfill({ response: res, json: d });
  });
  const errors = await open(page, "/money/us-tax", "Each sale in rupees");
  const sales = page.getByRole("table", { name: "US sales in rupees" });
  await expect(sales.getByRole("row").filter({ hasText: /SYM\d+/ })).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 13.")).toBeVisible();
  await page.getByRole("button", { name: "Show 3 more" }).click();
  await expect(sales.getByRole("row").filter({ hasText: /SYM\d+/ })).toHaveCount(13);
  await sane(page, errors);
});
