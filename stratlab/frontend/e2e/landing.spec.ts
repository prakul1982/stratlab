import { expect, test, type Page } from "@playwright/test";

// The public landing page, signed out: the four feature groups, plans that say exactly what the server's plans.py
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
  await expect(page.getByRole("heading", { name: /Know the company/ })).toBeVisible({ timeout: 30_000 });
  return errors;
}

test("landing: the four feature groups, plans, FAQ and markets", async ({ page }) => {
  const errors = await open(page);
  for (const [id, heading] of [["research", /Start with any company/], ["portfolio", /What you own/], ["strategy", /From a sentence/],
    ["alerts", /Hear about it/], ["pricing", /Free to start/], ["faq", /Good to know/]] as const) {
    const sec = page.locator(`section#${id}`);
    await expect(sec, id).toHaveCount(1);
    await expect(sec.getByRole("heading", { level: 2, name: heading })).toBeVisible();
  }
  // what ships today, one line each
  const research = page.locator("#research");
  for (const t of ["Company pages", "Deep dive", "Results calendar", "Corporate actions", "Deals and insider trades", "Surveillance lists",
    "Filings and red flags", "Screens", "Stage 2 scan", "Sector rotation"]) await expect(research.getByText(t, { exact: true })).toBeVisible();
  const portfolio = page.locator("#portfolio");
  for (const t of ["My Holdings", "Tax report", "Share cards and invites"]) await expect(portfolio.getByText(t, { exact: true })).toBeVisible();
  await expect(portfolio).toContainText("Zerodha");
  await expect(portfolio).toContainText("Groww");
  await expect(portfolio).toContainText("ZIP");
  for (const t of ["Walk-forward test", "Options, live", "Paper trading", "Strategy library"]) await expect(page.locator("#strategy").getByText(t, { exact: true })).toBeVisible();
  await expect(page.locator("#markets .lp-market")).toHaveCount(11);
  for (const t of ["Stock alerts", "Results and corporate actions", "Newsletters"]) await expect(page.locator("#alerts").getByText(t, { exact: true })).toBeVisible();
  await expect(page.locator("#faq details")).not.toHaveCount(0);
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
