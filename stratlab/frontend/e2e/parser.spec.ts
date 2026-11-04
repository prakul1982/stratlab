import { expect, test, type Page } from "@playwright/test";

// 57.1 (Instinct deep QA, 1 Nov: "the core promise"): the AI idea reader is never silently wrong. The fake world's AI gives the
// two answers the live site gave Instinct (tests/fake_ai_writer.py); the notebook must show the rules the words state, say what
// was assumed, and ask "Which stock or index?" when none is named, with a search right in the card.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };

async function open(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
    localStorage.setItem("stratlab.lastMarket", "IN");
  }, session);
  await page.goto("/new");
  return errors;
}

async function build(page: Page, idea: string) {
  await page.locator("#idea").fill(idea);
  await page.getByRole("button", { name: "Build my notebook" }).click();
  await page.waitForURL(/\/n\/[^/]+$/, { timeout: 30_000 });
  const card = page.getByRole("region", { name: "Questions about your idea" });
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

const line = (card: ReturnType<Page["getByRole"]>, text: string) => card.getByTestId("read-as").locator("li", { hasText: text });

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

test("parser: no instrument named, the pronoun exit read from the words, assumptions marked, and Which stock or index? asked (57.1)", async ({ page }) => {
  const errors = await open(page);
  const card = await build(page, "Buy when the 20 EMA crosses above the 50 EMA, sell when it crosses back below, 3% stop loss.");
  // the AI said "Price crosses EMA 20 and Price crosses EMA 50" / "Price below EMA 20 or EMA 50": the words' rules stand, stated
  await expect(line(card, "Buy when EMA 20 crosses above EMA 50")).toHaveAttribute("data-mark", "stated");
  await expect(line(card, "Sell when EMA 20 crosses below EMA 50")).toHaveAttribute("data-mark", "stated");
  await expect(line(card, "Stop loss 3%")).toHaveAttribute("data-mark", "stated");
  await expect(card.getByTestId("read-as")).not.toContainText("Price");
  // what the words don't say: marked, and said
  await expect(line(card, "Daily candles")).toHaveAttribute("data-mark", "assumed");
  await expect(line(card, "Daily candles")).toContainText("Assumed");
  await expect(card.getByTestId("read-assumed")).toContainText("Daily candles: your words give no candle length.");
  await expect(line(card, "Which stock or index")).toContainText("Asked below");
  await expect(card).toContainText("The buy rule was read from your words: EMA 20 crosses above EMA 50. The AI had read it differently.");
  // the NIFTY 50 the AI picked unasked is not used: the first question asks, with a search
  await expect(card.getByRole("heading", { name: "Which stock or index?" })).toBeVisible();
  await expect(page.getByText("Pick a market and instrument")).toBeVisible();
  const search = card.getByRole("combobox", { name: "Search a stock or index" }).or(card.getByLabel("Search a stock or index"));
  await search.first().fill("RELIANCE");
  await card.getByRole("option", { name: /RELIANCE/ }).first().click();
  await expect(card.getByRole("heading", { name: "Which stock or index?" })).toHaveCount(0);
  await expect(line(card, "Which stock or index")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("parser: with NIFTY 50 named, 'sell when it crosses back below' keeps the buy rule's lines in order (57.1)", async ({ page }) => {
  const errors = await open(page);
  const card = await build(page, "Buy NIFTY 50 when the 20 EMA crosses above the 50 EMA, sell when it crosses back below.");
  // the AI said "EMA 50 crosses below Price"
  await expect(line(card, "Sell when EMA 20 crosses below EMA 50")).toHaveAttribute("data-mark", "stated");
  await expect(card.getByTestId("read-as")).not.toContainText("EMA 50 crosses below");
  await expect(line(card, "Buy when EMA 20 crosses above EMA 50")).toHaveAttribute("data-mark", "stated");
  await expect(line(card, "Stop loss 2%")).toHaveAttribute("data-mark", "assumed");        // the default stop: the words set none
  await expect(card.getByTestId("read-assumed")).toContainText("A 2% stop loss: your words set none.");
  await expect(line(card, "Which stock or index")).toHaveCount(0);
  await expect(card.getByRole("heading", { name: "Which stock or index?" })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("parser: a 200-day average on 15-minute candles runs on daily closes, says so, and the name says what runs (LIVE3-004)", async ({ page }) => {
  const errors = await open(page);
  // the live AI made it a 200-candle SMA on 15-minute candles, named "BankNifty 200 EMA Long"
  const card = await build(page, "go long when price closes above the 200 day moving average, exit when it closes back under it, 15 minute candles on BANKNIFTY");
  await expect(line(card, "SMA 200 (daily)").first()).toHaveAttribute("data-mark", "stated");
  await expect(card.getByTestId("read-as")).not.toContainText("EMA");
  await expect(card.getByTestId("read-assumed")).toContainText("The 200-day SMA is worked out on daily candles (each completed day's close); the trades are on 15-minute candles.");
  await expect(page.getByRole("heading", { level: 1, name: /^BANKNIFTY SMA 200 daily( \d+)?$/ })).toBeVisible();      // (" 2": the other project's copy, same account)
  await expect(page.getByText("BankNifty 200 EMA Long")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("parser: the notebook's name is the instrument and the rules, never a fuzzy word (LIVE3-005)", async ({ page }) => {
  const errors = await open(page);
  await build(page, "Buy RELIANCE when RSI drops below 30 and sell when it goes back above 70");
  await expect(page.getByRole("heading", { level: 1, name: /^RELIANCE RSI 30\/70( \d+)?$/ })).toBeVisible();
  await expect(page.getByText("Relevance")).toHaveCount(0);
  expect(errors).toEqual([]);
});
