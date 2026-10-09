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
  // the landing page's own heading, inside .lp (R8V-008: the start-up block's h1 now has the same words as the page's)
  await expect(page.locator(".lp").getByRole("heading", { name: /Test it, research it, track it/ })).toBeVisible({ timeout: 30_000 });
  return errors;
}

test("landing: the three spaces with Trade first, alerts, plans, FAQ and markets", async ({ page }) => {
  const errors = await open(page);
  const order = ["trade", "invest", "money", "alerts", "pricing", "faq"];
  for (const [id, heading] of [["trade", /From a sentence/], ["invest", /Start with any company/], ["money", /What you own/],
    ["alerts", /Hear about it/], ["pricing", /^Free (to start|during early access|until)|^Every Pro feature/], ["faq", /Good to know/]] as const) {
    const sec = page.locator(`section#${id}`);
    await expect(sec, id).toHaveCount(1);
    await expect(sec.getByRole("heading", { level: 2, name: heading })).toBeVisible();
  }
  // the sections, and the menu, go Trade, Invest, Money: the strategy lab is where StratLab began
  expect(await page.locator("main section[id]").evaluateAll((els) => els.map((e) => e.id).filter((id) => id !== "top"))).toEqual(order);
  await expect(page.locator('nav[aria-label="Sections"] a')).toHaveText(["Trade", "Invest", "Money", "Alerts", "Plans", "FAQ"]);
  await expect(page.locator(".lp-space")).toHaveText([/Trade/, /Invest/, /Money/]);
  await expect(page.locator(".lp-space .lp-space-art"), "each space shows a picture of itself").toHaveCount(3);
  await expect(page.locator("#trade .lp-options")).toContainText("Paper trade option structures");
  // what search engines and link previews show says the same
  await expect(page).toHaveTitle("StratLab: test it, research it, track it");
  for (const sel of ['meta[name="description"]', 'meta[property="og:description"]']) await expect(page.locator(sel)).toHaveAttribute("content", /trad/i);
  // what ships today, one line each
  // the long lists show a few and fold the rest ("12 more Trade tools"): open them, everything is still there
  const more = page.locator(".lp-more > summary");
  expect(await more.count(), "the tool lists fold").toBeGreaterThanOrEqual(3);
  for (const s of await more.all()) await s.click();
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
  // (R5V-019: options can be paper traded, not backtested, so the question says "backtest" and the answer starts with No)
  const options = page.locator("#faq details", { hasText: "Can I backtest options?" });
  await options.locator("summary").click();
  await expect(options).toContainText("NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and SENSEX");
  await expect(options).toContainText("What you can do today is paper trade options");
  // the invite rule, in the backend's own numbers (R5V-019: the owner's longer wording was one sentence nobody could follow;
  // unit/seo.test.mjs checks each number against app/invite_rewards.py)
  const invites = page.locator("#faq details", { hasText: "How do invite rewards work?" });
  await invites.locator("summary").click();
  await expect(invites).toContainText("You and a friend can each get a free month of Basic.");
  await expect(invites).toContainText("uses StratLab on 3 different days in their first 14 days");
  await expect(invites).toContainText("for your first 2 paying friends in 12 months");
  await expect(invites).toContainText("each further paying friend gives you 8 days free, up to 8 times in 12 months");
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
  // what's on sale is the server's one answer (plans.offer_state via /pricing): the fake world has no payments, so the
  // page says paid plans open soon, sells nothing and promises no invoices, renewals or yearly prices; and never that
  // paid features are open to everyone (they are locked by plan, payments on or not: the owner, 7 Oct)
  const offer = (await (await request.get(`${API}/pricing`)).json()).offer;
  expect(offer.mode).toBe("early");
  const pricing = page.locator("#pricing");
  await expect(pricing.getByRole("heading", { level: 2 })).toHaveText("Free to start. Paid plans open soon.");
  await expect(pricing).toContainText("Basic and Pro aren't on sale yet");
  await expect(pricing).toContainText(/ask us at support@stratlab\.studio for early access/i);
  await expect(pricing).not.toContainText(/every feature is open|open to everyone until/);
  expect(offer.free_now.backtests_per_month).toBe(plans.free.backtests_per_month);       // Free's own limits apply
  for (const id of ["basic", "pro"]) {
    await expect(page.locator(`.lp-price[data-plan="${id}"]`)).toContainText("Opens soon");
    await expect(page.locator(`.lp-price[data-plan="${id}"]`).getByRole("button")).toHaveCount(0);
  }
  await expect(pricing).not.toContainText(/Start with (Basic|Pro)|Cancel any time|GST invoice|Paying yearly/);
  await expect(pricing).toContainText("Rupee prices include 18% GST.");
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
      if (!b.width || !b.height || el.closest("p, li") || getComputedStyle(el).display === "inline" || el.classList.contains("skip-link")) return false;   // (the skip link is only there for the keyboard)
      return b.height < 40;                // a finger needs 40px (R5V-016; it was 32)
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
    expect(small, "controls too small to tap").toEqual([]);
  }
});

test("landing: no fake buttons, no card that looks picked, the bitcoin sign, and a menu on a phone", async ({ page }, info) => {
  const errors = await open(page);
  // the research sample's button is a real button that says it goes to Google, then opens the idea builder (the sample is
  // a made-up company, so the button names none) (R5V-002, R5V-011)
  const idea = page.locator(".lp-rmock").getByRole("button", { name: /Continue with Google to test it/ });
  await expect(idea).toBeVisible();
  expect(await page.locator(".lp-fake-btn").count()).toBe(0);
  // tags under the Money cards and the options card read as labels, not links: not blue, not bold
  const tag = page.locator("#money .lp-tag").first();
  await expect(tag).toBeVisible();
  const [weight, color, blue] = await tag.evaluate((el) => [getComputedStyle(el).fontWeight, getComputedStyle(el).color,
    getComputedStyle(document.querySelector(".lp-space-go")!).color]);
  expect(Number(weight)).toBeLessThan(600);
  expect(color).not.toBe(blue);
  // the three space cards have the same border: none looks selected
  const borders = await page.locator(".lp-space").evaluateAll((els) => els.map((e) => getComputedStyle(e).borderTopColor));
  expect(new Set(borders).size).toBe(1);
  // crypto's sign is drawn (the fonts' fallback drew the baht's ฿)
  const crypto = page.locator("#markets .lp-market", { hasText: "Crypto" });
  await expect(crypto.locator("svg.lp-btc")).toHaveCount(1);
  await expect(page.locator("#markets")).not.toContainText("฿");
  if (info.project.name === "phone") {
    await expect(page.locator('nav[aria-label="Sections"]')).toBeHidden();
    // its name is its visible word, and it is at least 40px to tap (R5V-016)
    const summary = page.locator(".lp-menu > summary");
    await expect(summary).toHaveText("Menu");
    expect((await summary.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    await summary.click();
    const menu = page.getByRole("navigation", { name: "Sections (menu)" });
    await expect(menu.getByRole("link")).toHaveText(["Trade", "Invest", "Money", "Alerts", "Plans", "FAQ"]);
    await page.keyboard.press("Escape");                                          // Esc closes it, and focus goes back to the button
    await expect(menu).toBeHidden();
    await expect(summary).toBeFocused();
    await summary.click();
    await expect(menu).toBeVisible();
    await page.locator("h1").click({ position: { x: 5, y: 5 } });                 // so does a tap outside
    await expect(menu).toBeHidden();
    await summary.click();
    await menu.getByRole("link", { name: "Plans" }).click();
    await expect(menu).toBeHidden();
    await expect(page.locator("#pricing")).toBeInViewport();
  } else await expect(page.locator(".lp-menu")).toBeHidden();
  expect(errors).toEqual([]);
});

test("landing: the sample cards are labelled illustrations of made-up companies, never a real company with invented numbers", async ({ page }) => {
  const errors = await open(page);
  const cards = page.locator(".lp-space .lp-space-art, .lp-rmock");
  await expect(cards).toHaveCount(4);
  for (const card of await cards.all()) {
    // the label is in the card, readable: body-sized ink, not 12px grey
    const label = card.locator(".lp-illus");
    await expect(label).toHaveText(/^Illustration: (a )?made-up/);
    const [size, color, muted] = await label.evaluate((el) => [parseFloat(getComputedStyle(el).fontSize), getComputedStyle(el).color,
      getComputedStyle(document.querySelector(".muted")!).color]);
    expect(size, "the illustration label's size").toBeGreaterThanOrEqual(13);
    expect(color, "the illustration label isn't the grey of fine print").not.toBe(muted);
    // no real company, ticker or exchange beside the made-up figures, and no "today" on a made-up price
    const text = await card.innerText();
    for (const bad of [/RELIANCE/i, /NVIDIA/i, /\bNVDA\b/, /\bNASDAQ\b/, /\bNSE\b/, /BTC/, /\btoday\b/i, /\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/])
      expect(text, `${bad} in a sample card`).not.toMatch(bad);
  }
  expect(errors).toEqual([]);
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
