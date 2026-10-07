import { expect, test, type Page } from "@playwright/test";

// The Options builder's preview on the Free plan: the charges to open and close the structure, line by line, the
// breakevens before and after them, and the charges as a share of the premium and of the most it can make. The live
// option feed is offline in the fake world, so the underlyings and the priced preview are served here; the numbers
// are the ones options/charges.py gives for these fills (tests/test_option_charges.py works them by hand).
const SHOTS = process.env.SHOTS_DIR ?? "test-results";
const session = { access_token: "free-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-free", aud: "authenticated", email: "free@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

const quote = (bid: number, ask: number) => ({ bid, ask, ltp: (bid + ask) / 2, oi: 100000, ts: "2026-10-05T04:00:00+00:00" });
const leg = (side: "sell" | "buy", opt: "CE" | "PE", strike: number, fill: number) =>
  ({ side, opt, lots: 1, strike, sym: `NIFTY26O06${strike}${opt}`, quote: quote(fill, fill + 0.5), fill });
const base = { spot: 22410, atm: 22400, step: 50, expiry: "2026-10-06", lot: 65, freeze: 1800, units: 1, margin_one: 120000, margin: 120000,
  strikes: [22300, 22350, 22400, 22450, 22500], spot_ts: "2026-10-05T04:00:00+00:00" };
const items = (a: number[]) => ["Brokerage", "STT", "Exchange charges", "SEBI fee", "Stamp duty", "GST"]
  .map((label, i) => ({ key: ["brokerage", "stt", "exchange", "sebi", "stamp", "gst"][i], label, amount: a[i] }));

const STRADDLE = { ...base, legs: [leg("sell", "CE", 22400, 150), leg("sell", "PE", 22400, 120)],
  charges: { total: 135.84, orders: 4, brokerage_per_order: 20, freeze: 1800, items: items([80, 26.33, 12.33, 0.04, 0.53, 16.63]),
    credit: true, premium: 17550, premium_after: 17414.16, pct_of_premium: 0.774, max_profit: 17550, max_profit_after: 17414.16,
    pct_of_max_profit: 0.774, max_loss: null, max_loss_after: null, breakevens: [22130, 22670], breakevens_after: [22132.09, 22667.91],
    rates_as_of: "2026-04-01" } };
// a call spread 100 points wide bought for 99.5: ₹32.50 at most before charges of ₹125.18
const SPREAD = { ...base, legs: [leg("buy", "CE", 22400, 150), leg("sell", "CE", 22500, 50.5)],
  charges: { total: 125.18, orders: 4, brokerage_per_order: 20, freeze: 1800, items: items([80, 19.55, 9.16, 0.03, 0.39, 16.05]),
    credit: false, premium: 6467.5, premium_after: null, pct_of_premium: 1.94, max_profit: 32.5, max_profit_after: -92.68,
    pct_of_max_profit: 385.15, max_loss: -6467.5, max_loss_after: -6592.68, breakevens: [22499.5], breakevens_after: [], rates_as_of: "2026-04-01" } };
// a long put: its best is at a price of zero, (22,400 - 120) x 65, never "Unlimited"
const PUT = { ...base, legs: [leg("buy", "PE", 22400, 120)],
  charges: { total: 65.62, orders: 2, brokerage_per_order: 20, freeze: 1800, items: items([40, 11.7, 5.48, 0.02, 0.23, 8.19]),
    credit: false, premium: 7800, premium_after: null, pct_of_premium: 0.8413, max_profit: 1448200, max_profit_after: 1448134.38,
    pct_of_max_profit: 0.0045, max_loss: -7800, max_loss_after: -7865.62, breakevens: [22280], breakevens_after: [22278.99], rates_as_of: "2026-04-01" } };
const UNDERLYINGS = [{ exchange: "NFO", name: "NIFTY", venue: "NSE", lot: 65, freeze: 1800, popular: true, index: true, expiries: ["2026-10-06"] }];

async function open(page: Page, previews: unknown[]) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let n = 0;
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    if (u.pathname.endsWith("/options/underlyings")) return r.fulfill({ status: 200, json: UNDERLYINGS });
    if (u.pathname.endsWith("/options/preview")) return r.fulfill({ status: 200, json: previews[Math.min(n++, previews.length - 1)] });
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto("/options");
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByRole("button", { name: "Price it now" })).toBeEnabled({ timeout: 30_000 });
  return errors;
}

async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

test("options builder: charges to open and close, and breakevens after them, on the Free plan", async ({ page }, info) => {
  const errors = await open(page, [STRADDLE, SPREAD, PUT]);
  await page.getByRole("button", { name: "Price it now" }).click();
  const box = page.getByTestId("opt-charges");
  await expect(box).toBeVisible();
  await expect(box).toContainText("Charges to open and close₹135.84");
  // a short straddle's most it can make is its premium: one figure, not the same one twice
  await expect(box).toContainText("Share of the premium (also the most it can make)0.77%");
  await expect(box).not.toContainText("Share of the most it can make");
  await expect(box).toContainText("Premium kept after charges₹17,414.16");
  await expect(page.getByTestId("opt-breakevens")).toContainText("Breaks even at 22,130 and 22,670 before charges. After charges: 22,132 and 22,668.");
  await expect(page.getByTestId("opt-max-profit")).toContainText("₹17,550₹17,414 after charges");
  await expect(page.getByTestId("opt-max-loss")).toContainText("Unlimited");
  // the second line on the payoff chart is the same payoff after charges
  await expect(page.locator("svg[aria-label='Profit or loss at expiry across prices'] path[stroke-dasharray]").first()).toBeAttached();

  // line by line, folded until asked for
  const lines = box.locator("details.opt-charge-lines");
  await expect(lines.locator("table")).toBeHidden();
  await lines.locator("summary").click();
  await expect(lines.locator("tbody tr, tfoot tr")).toHaveText(["Brokerage₹80.00", "STT₹26.33", "Exchange charges₹12.33", "SEBI fee₹0.04", "Stamp duty₹0.53", "GST₹16.63", "Total₹135.84"]);
  await expect(lines).toContainText("4 orders at ₹20 brokerage each; orders above 1,800 units go in slices");
  await expect(lines).toContainText("Rates as of 1 Apr 2026.");

  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide, "the page scrolls sideways").toBeLessThanOrEqual(1);
  if (info.project.name === "phone") {
    await touchable(page);
    expect((await lines.locator("summary").boundingBox())!.height, "the fold's summary is too small to tap").toBeGreaterThanOrEqual(32);
  }
  await box.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/breakeven-straddle-${info.project.name}.png`, fullPage: false });

  // a spread whose charges are bigger than the most it can make: no breakeven after charges, said plainly
  await page.getByRole("button", { name: "Price again" }).click();
  await expect(page.getByTestId("opt-breakevens")).toContainText("Breaks even at 22,500 before charges. After charges it doesn't break even at any price.");
  await expect(box).toContainText("Share of the most it can make385.15%");
  await expect(box).toContainText("Most it can make after charges−₹92.68");
  await expect(box).not.toContainText("Premium kept");
  await expect(page.getByTestId("opt-max-loss")).toContainText("−₹6,468−₹6,593 after charges");
  await box.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/breakeven-spread-${info.project.name}.png`, fullPage: false });

  // a long put: bounded at a price of zero, so the tile gives the amount, and the note says it's off the chart
  await page.getByRole("button", { name: "Price again" }).click();
  await expect(page.getByTestId("opt-max-profit")).toContainText("₹14,48,200₹14,48,134 after charges");
  await expect(page.getByTestId("opt-max-loss")).toContainText("−₹7,800−₹7,866 after charges");
  await expect(box).toContainText("Share of the most it can makeunder 0.01%");
  await expect(page.getByTestId("opt-breakevens")).toContainText("The most it can make is reached at 0, outside the chart.");
  await page.getByTestId("opt-max-profit").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/breakeven-put-${info.project.name}.png`, fullPage: false });
  expect(errors, "uncaught errors in the page").toEqual([]);
});
