import { expect, test, type Page } from "@playwright/test";

// The public landing page, signed out: the three spaces (Trade first), alerts, plans that say exactly what the server's plans.py
// enforces, the FAQ, and nothing a public page must never say (data sources, advice words).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

test.use({ timezoneId: "Asia/Kolkata" });     // an Indian visitor: prices in rupees

async function open(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Test it, research it, track it/ })).toBeVisible({ timeout: 30_000 });
  return errors;
}

test("landing: the three spaces with Trade first, alerts, plans, FAQ and markets", async ({ page }) => {
  const errors = await open(page);
  const order = ["trade", "invest", "money", "alerts", "pricing", "faq"];
  for (const [id, heading] of [["trade", /From a sentence/], ["invest", /Start with any company/], ["money", /What you own/],
    ["alerts", /Hear about it/], ["pricing", /Free to start/], ["faq", /Good to know/]] as const) {
    const sec = page.locator(`section#${id}`);
    await expect(sec, id).toHaveCount(1);
    await expect(sec.getByRole("heading", { level: 2, name: heading })).toBeVisible();
  }
  // the sections, and the menu, go Trade, Invest, Money: the strategy lab is where StratLab began
  expect(await page.locator("main section[id]").evaluateAll((els) => els.map((e) => e.id).filter((id) => id !== "top"))).toEqual(order);
  await expect(page.locator('nav[aria-label="Sections"] a')).toHaveText(["Trade", "Invest", "Money", "Alerts", "Pricing", "FAQ"]);
  await expect(page.locator(".lp-space")).toHaveText([/Trade/, /Invest/, /Money/]);
  await expect(page.locator(".lp-space .lp-space-art"), "each space shows a picture of itself").toHaveCount(3);
  await expect(page.locator("#trade .lp-options")).toContainText("Paper trade option structures");
  // what search engines and link previews show says the same
  await expect(page).toHaveTitle("StratLab: test it, research it, track it");
  for (const sel of ['meta[name="description"]', 'meta[property="og:description"]']) await expect(page.locator(sel)).toHaveAttribute("content", /trad/i);
  // what ships today, one line each
  const research = page.locator("#invest");
  for (const t of ["Company pages", "Deep dive", "Results calendar", "Corporate actions", "Deals and insider trades", "Surveillance lists",
    "Filings and red flags", "Screens", "Stage 2 scan", "Sector rotation", "Market breadth", "Price charts", "ETF price vs NAV"]) await expect(research.getByText(t, { exact: true })).toBeVisible();
  const portfolio = page.locator("#money");
  for (const t of ["My Holdings", "Tax report", "Mutual funds", "Fund costs", "Net worth", "Tax tools", "US stocks in Indian tax", "ITR-ready export", "Money calendar",
    "Share cards and invites"]) await expect(portfolio.getByText(t, { exact: true })).toBeVisible();
  await expect(portfolio).toContainText("Zerodha");
  await expect(portfolio).toContainText("Groww");
  await expect(portfolio).toContainText("ZIP");
  await expect(portfolio).toContainText("Not a filed return");
  for (const t of ["Walk-forward test", "Options, live", "Paper trading", "Strategy library", "Positioning", "Trade journal", "Greeks and what-if", "After charges", "F&O changes"]) await expect(page.locator("#trade").getByText(t, { exact: true })).toBeVisible();
  await expect(page.locator("#markets .lp-market")).toHaveCount(11);
  for (const t of ["Stock alerts", "Results and corporate actions", "Market breadth", "Advance tax", "Money calendar", "Newsletters", "F&O changes", "ETF price vs NAV"]) await expect(page.locator("#alerts").getByText(t, { exact: true })).toBeVisible();
  // the grids stay full: four research tools a row, three alerts a row, Money's cards in pairs
  expect(await page.locator("#invest .lp-tool").count() % 4).toBe(0);
  expect(await page.locator("#alerts .lp-tool").count() % 3).toBe(0);
  expect(await page.locator("#money .lp-beyond-card").count() % 2).toBe(0);
  await expect(page.locator("#faq details")).not.toHaveCount(0);
  expect(await page.locator("#faq details").count(), "the FAQ stays short").toBeLessThanOrEqual(10);
  // the option chains StratLab records, as the server records them
  const options = page.locator("#faq details", { hasText: "Can I test options strategies?" });
  await options.locator("summary").click();
  await expect(options).toContainText("NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and SENSEX");
  // the invite rule, as the owner wrote it
  const invites = page.locator("#faq details", { hasText: "How do invite rewards work?" });
  await invites.locator("summary").click();
  await expect(invites).toContainText("Invite friends, both get a month of Basic.");
  await expect(invites).toContainText("for each of your first 2 friends who subscribe. After that, every friend who subscribes gives you 25% off a month (about a week extra).");
  await expect(portfolio).not.toContainText("12 free months");
  expect(errors).toEqual([]);
});

test("landing: the plans match the server's plans exactly", async ({ page, request }) => {
  const plans = await (await request.get(`${API}/plans`)).json();
  await open(page);
  for (const id of ["free", "basic", "pro"]) {
    const card = page.locator(`.lp-price[data-plan="${id}"]`);
    await expect(card).toBeVisible();
    await expect(card.locator(".lp-amount")).toContainText(`₹${plans[id].price.toLocaleString("en-IN")}`);
    const p = plans[id];
    await expect(card).toContainText(`${p.stock_alerts} stock alerts`);
    if (p.backtests_per_month != null) await expect(card).toContainText(`${p.backtests_per_month} backtests`);
    else await expect(card).toContainText("Unlimited backtests");
  }
  await expect(page.locator('.lp-price[data-plan="free"]')).toContainText(`up to ${plans.free.holdings} holdings`);
  await expect(page.locator('.lp-price[data-plan="basic"]')).toContainText(`${plans.basic.screens} saved screens, ${plans.basic.holdings} holdings`);
  await expect(page.locator('.lp-price[data-plan="pro"]')).toContainText(`Paper trade ${plans.pro.live_limit} strategies`);
  await expect(page.locator("#pricing")).toContainText(`Paying yearly in rupees: Basic ₹${plans.basic.price_year.toLocaleString("en-IN")}, Pro ₹${plans.pro.price_year.toLocaleString("en-IN")}.`);
  await expect(page.locator('.lp-price[data-plan="free"]')).toContainText(`${plans.free.mf_schemes} mutual funds and ${plans.free.networth_items} net worth entries`);
  await expect(page.locator('.lp-price[data-plan="free"]')).toContainText(`your last ${plans.free.journal_trades} trades`);
  // each space's paid tools on the card of the plan that adds them (tests/test_plan_copy.py checks every one)
  await expect(page.locator('.lp-price[data-plan="basic"]')).toContainText("full trade journal");
  await expect(page.locator('.lp-price[data-plan="pro"]')).toContainText("ITR-ready");
  for (const card of await page.locator(".lp-price").all()) expect(await card.locator("li").count()).toBeLessThanOrEqual(9);
});

test("landing: facts only, no data sources, fits the screen", async ({ page }) => {
  await open(page);
  const text = await page.locator("body").innerText();
  // the user's own broker (Zerodha, Groww…) is fine to name; where the data comes from never is
  for (const bad of [/\bKite\b/, /Yahoo/i, /Screener\.in/i, /Finnhub/i, /Coinbase/i, /Wikipedia/i, /Google News/i, /\bEDGAR\b/]) expect(text, `${bad} on the landing page`).not.toMatch(bad);
  for (const bad of [/\bstrong buy\b/i, /\btarget price\b/i, /\bundervalued\b/i, /\bovervalued\b/i, /\bbest stocks\b/i, /\bmultibagger\b/i, /\baccumulate\b/i,
    /\bNaN\b/, /\bundefined\b/, /\[object Object\]/]) expect(text, `${bad} on the landing page`).not.toMatch(bad);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  // on a phone every button and stand-alone link is big enough for a finger
  if (width < 700) {
    const small = await page.evaluate(() => Array.from(document.querySelectorAll("button, a, summary, [role=button]")).filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
    expect(small, "controls too small to tap").toEqual([]);
  }
});

test("landing: dark mode draws on a dark background", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript(() => { try { localStorage.setItem("stratlab-theme", "dark"); } catch { /* storage off */ } });
  await open(page);
  const bg = await page.evaluate(() => getComputedStyle(document.querySelector(".lp")!).backgroundColor);
  const [r, g, b] = (bg.match(/\d+/g) ?? ["255", "255", "255"]).map(Number);
  expect((r + g + b) / 3, `background ${bg}`).toBeLessThan(80);
  await expect(page.locator("#pricing .lp-price")).toHaveCount(3);
});
