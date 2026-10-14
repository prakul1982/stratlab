import { expect, test, type Browser, type Page, type Route } from "@playwright/test";

// Round 13 Safari review (R13S): what the app draws on a phone and on an iPad. The answers a test depends on are fixed
// here (the fake world's background jobs can't change them), and nothing waits on the time of day.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];

async function open(page: Page, path: string, mocks: Mock[] = []) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", async (r) => {
    const u = new URL(r.request().url());
    const call = ["fetch", "xhr"].includes(r.request().resourceType());
    for (const [re, body] of call ? mocks : []) {
      if (re.test(u.pathname + u.search)) {
        if (typeof body === "function") return (body as (r: Route) => Promise<void>)(r);
        return r.fulfill({ status: 200, body: JSON.stringify(body), contentType: "application/json" });
      }
    }
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(path);
  return errors;
}

/** An iPad Pro 11 in portrait: 834 wide, a finger for a pointer. */
async function ipad(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 834, height: 1194 }, hasTouch: true, isMobile: false });
  return { ctx, page: await ctx.newPage() };
}

// ---------- R13S-002 and R13S-003: the Invest home's red flags card ----------
const FEED_DOWN = { rows: [], problems: ["TCS: The exchange feed isn't answering right now. Try again in a minute."], days: 90, alerts: false, send_at: "18:30" };

test("R13S-002: when the filings feed doesn't answer, the card says it couldn't read the company, never 'you hold none'", async ({ page }) => {
  const errors = await open(page, "/invest", [[/\/research\/filings$/, FEED_DOWN]]);
  const card = page.getByTestId("invest-redflags-failed");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText("Couldn't read TCS's filings right now.");
  await expect(page.getByText("You hold or watch no India stocks yet")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("R13S-002: a failed request says the same, and the card tries again when asked", async ({ page }) => {
  let calls = 0;
  const errors = await open(page, "/invest", [[/\/research\/filings$/, async (r: Route) => {
    calls += 1;
    if (calls === 1) return r.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "filings_unavailable", message: "The exchange is not answering." } }) });
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rows: [], problems: [], days: 90, alerts: false, send_at: "18:30" }) });
  }]]);
  const card = page.getByTestId("invest-redflags-failed");
  await expect(card).toContainText("Couldn't read your companies' filings right now.", { timeout: 30_000 });
  await card.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("You hold or watch no India stocks yet")).toBeVisible();
  expect(calls).toBe(2);
  expect(errors.filter((e) => !/503|filings_unavailable|not answering/.test(e))).toEqual([]);
});

test("R13S-003: until the plan is known the card shows its skeleton, never the Basic-plan note", async ({ page }) => {
  const seen: string[] = [];
  const errors = await open(page, "/invest", [
    [/\/me$/, async (r: Route) => { await new Promise((ok) => setTimeout(ok, 2500)); await r.fallback(); }],
    [/\/research\/filings$/, { rows: [], problems: [], days: 90, alerts: false, send_at: "18:30" }],
  ]);
  const timer = setInterval(() => { void page.getByText(/are on the Basic plan/).count().then((n) => { if (n) seen.push("note"); }).catch(() => undefined); }, 100);
  await expect(page.getByText("Red flags in your holdings and watchlist")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("You hold or watch no India stocks yet")).toBeVisible({ timeout: 30_000 });
  clearInterval(timer);
  expect(seen, "the Basic-plan note showed while the plan was loading").toEqual([]);
  expect(errors).toEqual([]);
});

// ---------- R13S-005: nothing under 16px that Safari would zoom ----------
test("R13S-005: on a phone every field is 16px or more", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the phone project");
  test.setTimeout(180_000);
  const small: string[] = [];
  for (const path of ["/options", "/holdings", "/trade/replay", "/money/tax-tools", "/settings", "/research", "/alerts"]) {
    await open(page, path);
    await expect(page.locator("main")).toBeVisible();
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(500);
    small.push(...await page.evaluate((p) => Array.from(document.querySelectorAll<HTMLElement>("main input, main select, main textarea"))
      .filter((el) => {
        const t = (el as HTMLInputElement).type;
        if (["checkbox", "radio", "range", "file", "hidden", "color", "submit", "button"].includes(t)) return false;
        const b = el.getBoundingClientRect();
        return b.width > 1 && b.height > 1 && getComputedStyle(el).visibility !== "hidden";
      })
      .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
      .map((el) => `${p} ${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}.${el.className} ${getComputedStyle(el).fontSize}`), path));
  }
  expect(small, "fields Safari would zoom to").toEqual([]);
});

// ---------- R13S-006, R13S-008, R13S-011: an iPad in portrait ----------
test("R13S-006: the billing switch's long label stays inside its pill", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "makes its own iPad window");
  const { ctx, page } = await ipad(browser);
  const priced = await (await fetch(`${process.env.E2E_API}/pricing`)).json();
  priced.offer = { ...priced.offer, mode: "paid", payments: true, yearly: true };         // yearly billing on sale, so the switch shows
  const onSale = (o: Record<string, unknown>) => ({ ...o, mode: "paid", payments: true, yearly: true });
  await open(page, "/plans", [[/\/pricing$/, priced], [/\/me$/, async (r: Route) => {
    const res = await r.fetch();
    const me = await res.json();
    return r.fulfill({ response: res, json: { ...me, offer: onSale(me.offer ?? {}) } });
  }]]);
  const seg = page.getByRole("radiogroup", { name: "Billing period" });
  await expect(seg).toBeVisible({ timeout: 30_000 });
  const out = await seg.evaluate((el) => {
    const box = el.getBoundingClientRect();
    return Array.from(el.querySelectorAll("button")).filter((b) => b.getBoundingClientRect().right > box.right + 0.5 || b.scrollWidth > b.clientWidth + 1).map((b) => b.textContent);
  });
  expect(out).toEqual([]);
  await ctx.close();
});

test("R13S-008: a Trade tile's status wraps instead of being cut off", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "makes its own iPad window");
  const { ctx, page } = await ipad(browser);
  await open(page, "/trade", [[/\/trade\/journal/, { stats: {}, trades: [], open: [] }]]);
  await expect(page.locator(".space-card-foot").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  const cut = await page.evaluate(() => Array.from(document.querySelectorAll<HTMLElement>(".space-card-foot"))
    .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1).map((el) => el.textContent));
  expect(cut).toEqual([]);
  await ctx.close();
});

test("R13S-007: the company page's More menu stays on the screen", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "makes its own iPad window");
  const { ctx, page } = await ipad(browser);
  await open(page, "/research/IN/RELIANCE");
  const more = page.getByRole("button", { name: /^More/ }).first();
  await expect(more).toBeVisible({ timeout: 45_000 });
  await more.click();
  const menu = page.getByRole("menu").first();
  await expect(menu).toBeVisible();
  const box = (await menu.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(834);
  await ctx.close();
});

test("R13S-011: on an iPad the price chart's buttons, the screener's sort headers and the table links are 44px", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "makes its own iPad window");
  test.setTimeout(120_000);
  const { ctx, page } = await ipad(browser);
  await open(page, "/research/IN/RELIANCE");
  await expect(page.locator(".pc-bar button").first()).toBeVisible({ timeout: 45_000 });
  expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches), "a touch screen").toBe(true);
  const small = async () => page.evaluate(() => Array.from(document.querySelectorAll<HTMLElement>(".pc-bar button, .pc-bar .k-chip, .k-th-sort, .k-table td a, .k-table th a"))
    .filter((el) => { const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.height < 43.5; })
    .map((el) => `${el.className || el.tagName} "${(el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 24)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(await small(), "chart controls under 44px").toEqual([]);
  await page.goto("/research/screens");
  await expect(page.locator(".k-th-sort").first()).toBeVisible({ timeout: 45_000 });
  expect(await small(), "screener controls under 44px").toEqual([]);
  await ctx.close();
});

// ---------- R13S-009: dates in words ----------
test("R13S-009: the screener's 'About this data' writes when the list was gathered in words, in India's time", async ({ page }) => {
  const errors = await open(page, "/research/screens", [[/\/research\/screens\/(run|meta)/, async (r: Route) => {
    const res = await r.fetch();
    return r.fulfill({ response: res, json: { ...(await res.json()), index_at: "2026-10-09T20:58:22+00:00" } });
  }]]);
  await expect(page.locator(".k-th-sort").first()).toBeVisible({ timeout: 45_000 });
  await page.getByRole("main").getByRole("button", { name: /About/ }).first().click();
  await expect(page.getByText("List gathered as of 10 Oct 2026, 02:28 IST")).toBeVisible();
  await expect(page.getByText(/2026-10-09T20:58/)).toHaveCount(0);
  expect(errors).toEqual([]);
});

// ---------- R13S-016: a date that doesn't exist ----------
test("R13S-016: typing 31/02/2026 says there is no such day, not how to write a date", async ({ page }) => {
  await open(page, "/trade/replay");
  const box = page.getByRole("textbox", { name: "Start date" });
  await expect(box).toBeVisible({ timeout: 45_000 });
  await box.fill("31/02/2026");
  await expect(page.getByText("There is no 31 February 2026.")).toBeVisible();
  await expect(page.getByText("Write the date day first")).toHaveCount(0);
  await box.fill("tomorrow");
  await expect(page.getByText("Write the date day first, like 14 Aug 2025 or 14/08/2025.")).toBeVisible();
});
