import { expect, test, type Page } from "@playwright/test";

// A brand-new user's first session, end to end: arrive by an invite link, answer the welcome questions, see the
// first steps, run a backtest and paper trade it, look up a company (its deals and corporate actions), set an alert,
// import holdings and apply a bonus (then undo it), filter with a screen, choose newsletters, find the invite link
// and the plans. Each project signs in as its own new account (fake users load-201 and load-204, made today).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const EMA = { name: "Trend follower", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
  exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }],
  risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };

/** No crash, nothing wider than the screen, no broken numbers, no advice words, and (on a phone) big enough to tap. */
async function check(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /yahoo|finnhub|screener\.in|kite connect/i]) {
    expect(text, `"${bad}" on the page`).not.toMatch(bad);
  }
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

/** Answer the experience question if it shows. */
async function level(page: Page) {
  const ask = page.getByRole("dialog", { name: /How much .* have you done/ });
  await ask.waitFor({ timeout: 4000 }).then(() => ask.getByRole("button", { name: /done a bit/ }).click()).catch(() => undefined);
  await expect(ask).toHaveCount(0);
}

test("a new user's first session, from the invite link to the plans", async ({ page, request }, info) => {
  test.setTimeout(240_000);
  const phone = info.project.name === "phone";
  const [token, id, email] = phone ? ["load-204", "u-load-204", "load204@example.com"] : ["load-201", "u-load-201", "load201@example.com"];
  const auth = { Authorization: `Bearer ${token}` };
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: token, user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);

  // 1. arrives through a friend's invite link, signed in: the welcome question, then Home with the first steps
  // (the Pro test user's link: the owner's own invite counts are checked by another test)
  const code = (await (await request.get(`${API}/me/referrals`, { headers: { Authorization: "Bearer pro-token" } })).json()).code;
  await page.goto(`/?ref=${code}`);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  await expect(welcome).toBeVisible({ timeout: 30_000 });
  if (phone) await check(page, errors, phone);
  // one short step: the experience is asked on the same card, already on the middle answer
  await expect(welcome.getByRole("radio", { name: "I've done a bit" })).toHaveAttribute("aria-checked", "true");
  await welcome.getByRole("button", { name: /All of it/ }).click();
  await level(page);
  await expect(page.getByText("Your first steps")).toBeVisible({ timeout: 30_000 });
  await expect(page, "all of it opens My space").toHaveURL(/\/mine$/);
  await expect.poll(async () => (await (await request.get(`${API}/me/referrals`, { headers: auth })).json()).code, "the newcomer has a link of their own").toBeTruthy();
  expect(new URL(page.url()).search, "the invite code leaves the address").toBe("");
  await check(page, errors, phone);

  // 2. a backtest from a notebook, then paper trading it
  const nb = await (await request.post(`${API}/notebooks`, { headers: auth,
    data: { name: "My first idea", question: "Does the cross work?", strategy: EMA, instrument: "CRYPTO:BTC-USD" } })).json();
  await page.goto(`/n/${nb.id}`);
  await page.getByRole("button", { name: /Run experiment v1/ }).click();
  await expect(page.locator(".verdict-head")).toBeVisible({ timeout: 60_000 });
  await check(page, errors, phone);
  await page.goto(`/n/${nb.id}`);
  await page.getByRole("button", { name: "Paper trade" }).click();
  await expect(page).toHaveURL(/\/paper\/[^/]+$/, { timeout: 30_000 });
  await expect(page.locator("main")).toContainText(/Trend follower|My first idea/, { timeout: 30_000 });
  await check(page, errors, phone);

  // 3. a company: its deals and insider trades, its corporate actions, then an alert on it
  await page.goto("/research/IN/TCS");
  await expect(page.locator("#deals")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#corporate-actions").getByText(/dividend/i).first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Set alert" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Alert on TCS" });
  await dialog.getByLabel("Price level (₹)").fill("1");
  await dialog.getByRole("button", { name: "Set alert" }).click();
  await expect(page.getByText(/already above ₹1/).first()).toBeVisible();
  await check(page, errors, phone);

  // 4. holdings from a broker CSV: dividends, and the TCS bonus applied and undone
  await page.goto("/holdings");
  await expect(page.getByText("No holdings yet")).toBeVisible({ timeout: 30_000 });
  await page.locator("input[type=file]").setInputFiles({ name: "holdings.csv", mimeType: "text/csv",
    buffer: Buffer.from("Symbol,Quantity,Average price\nTCS,12,3520\nRELIANCE,50,2400\n") });
  const notice = page.getByText(/TCS had a 1:1 bonus on .*: your quantity is now 24/);
  await expect(notice).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Dividends" })).toBeVisible();
  await check(page, errors, phone);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText(/TCS: quantity 24/)).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("TCS is back to 12 shares.")).toBeVisible();

  // 5. a screen, the newsletters, the invite link and the plans
  await page.goto("/research/screens?region=IN");
  await expect(page.getByText(/\d+ of \d+ companies match/)).toBeVisible({ timeout: 30_000 });
  await check(page, errors, phone);
  await page.goto("/settings#newsletters");
  await expect(page.getByRole("heading", { name: /Newsletters/ })).toBeVisible({ timeout: 30_000 });
  await page.goto("/invite");
  await expect(page.getByLabel("Your invite link")).toHaveValue(/\/\?ref=[A-Za-z0-9_-]{12}$/);
  await expect(page.getByTestId("friends-joined")).toHaveText(/^0 friends joined/);
  await check(page, errors, phone);
  await page.goto("/plans");
  await expect(page.getByRole("heading", { name: "Plans" })).toBeVisible({ timeout: 30_000 });
  await check(page, errors, phone);

  // the invite was counted for the friend, and the newcomer's reward waits for them to be active on 3 days
  const rewards = await (await request.get(`${API}/admin/invite-rewards`, { headers: { Authorization: "Bearer admin-token" } })).json();
  expect(rewards.waiting).toBeGreaterThanOrEqual(1);
});
