import { expect, test, type Page, type Request } from "@playwright/test";

// Lane conv101 (owner, 27 Nov: "I need to make money now") on the fake world: a visitor can try one idea, sees the facts-not-advice line and
// the plans' cancel terms, opens a verdict that held up, gets no editing controls; the pages the server draws send one pageview through the
// site's own /ingest, and never from a robot, a Do Not Track browser or a device marked as StratLab's own; StratLab's own accounts send nothing.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const KEY = "phc_conv101TestKey";

/** A person's browser, not an automated one (analytics stays off for a test browser, as review-r5's and analytics.spec's tests say). */
const person = (page: Page) => page.addInitScript(() => {
  Object.defineProperty(Navigator.prototype, "webdriver", { get: () => false });
  Object.defineProperty(Navigator.prototype, "userAgentData", { get: () => undefined });
  Object.defineProperty(Navigator.prototype, "userAgent", { get: () => "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36" });
});

/** The fake world's company page as the site serves it (the site's own address, which forwards /stocks to the API, as vercel.json does), with
 * the beacon tag the API adds when POSTHOG_KEY is set (the fake world has none). */
async function stockPageWithBeacon(page: Page, sent: string[]) {
  await page.route((u) => u.pathname === "/stocks/in/RELIANCE", async (r) => {
    const res = await r.fetch();
    const body = (await res.text()).replace("</body>", `<script src="/stocks/pv.js" data-k="${KEY}" data-kind="stock" defer></script></body>`);
    await r.fulfill({ response: res, body, headers: { ...res.headers(), "content-security-policy": "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'" } });
  });
  await page.route((u) => u.pathname.startsWith("/ingest/"), (r) => { sent.push(r.request().postData() || ""); return r.fulfill({ status: 200, json: { status: "Ok" } }); });
}

test.describe("T1, T2: a pageview from the pages the server draws", () => {
  test("one $pageview to /ingest with the page's kind, the address without its query, and the app's own anonymous ID", async ({ page }) => {
    const sent: string[] = [];
    await person(page);
    await stockPageWithBeacon(page, sent);
    await page.goto("/stocks/in/RELIANCE?utm_source=insta&email=a@b.com");
    await expect.poll(() => sent.length, { timeout: 15_000 }).toBe(1);
    const ev = JSON.parse(sent[0]);
    expect(ev.event).toBe("$pageview");
    expect(ev.api_key).toBe(KEY);
    expect(ev.properties.page_kind).toBe("stock");
    expect(new URL(ev.properties.$current_url).pathname).toBe("/stocks/in/RELIANCE");
    expect(ev.properties.$current_url).not.toContain("?");
    expect(ev.properties.utm_source).toBe("insta");
    expect(JSON.stringify(ev)).not.toContain("a@b.com");
    expect(ev.properties.$process_person_profile).toBe(false);
    const stored = await page.evaluate((k) => JSON.parse(localStorage.getItem(`ph_${k}_posthog`) || "{}"), KEY);
    expect(stored.distinct_id).toBe(ev.distinct_id);
    expect(ev.properties.$session_id).toBe(stored.$sesid[1]);
    // the page's ways into the app sit under the price and carry where they came from
    const top = page.locator("[data-cta-top] a").first();
    await expect(top).toHaveText("Free sign-in: test a strategy on RELIANCE");
    await expect(top).toHaveAttribute("href", /from=stock/);
    await expect(top).toBeInViewport();
  });

  test("nothing from a robot, a Do Not Track browser, or a device marked with ?internal=1 (which says so and stays marked)", async ({ page }) => {
    const sent: string[] = [];
    await stockPageWithBeacon(page, sent);
    await page.goto("/stocks/in/RELIANCE");                       // a test browser: navigator.webdriver
    await page.waitForTimeout(1500);
    expect(sent).toEqual([]);
    await person(page);
    await page.addInitScript(() => Object.defineProperty(Navigator.prototype, "doNotTrack", { get: () => "1" }));
    await page.goto("/stocks/in/RELIANCE");
    await page.waitForTimeout(1500);
    expect(sent).toEqual([]);
    expect(await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("ph_")))).toEqual([]);
  });

  test("?internal=1 marks the device: a note on the page, no pageview now or later, and the app sends nothing either", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const sent: string[] = [];
    await person(page);
    await stockPageWithBeacon(page, sent);
    await page.goto("/stocks/in/RELIANCE?internal=1");
    await expect(page.locator("[data-internal-note]")).toHaveText("This device is now left out of StratLab's analytics.");
    await page.goto("/stocks/in/RELIANCE");
    await page.waitForTimeout(1500);
    expect(sent).toEqual([]);
    // the app on the same device: no PostHog request at all, even with a key
    const ph: Request[] = [];
    page.on("request", (r) => { if (/posthog|\/ingest\//.test(r.url())) ph.push(r); });
    await page.route("**/config.js", (r) => r.fulfill({ contentType: "application/javascript",
      body: `window.STRATLAB_CONFIG = {API_BASE:"${API}",SUPABASE_URL:"https://demo.supabase.co",SUPABASE_ANON_KEY:"demo",POSTHOG_KEY:"phc_test",POSTHOG_HOST:"/ingest"};` }));
    await page.goto("/");
    await expect(page.locator(".lp").getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(4500);
    expect(ph.map((r) => r.url())).toEqual([]);
    // ?internal=0 undoes it
    await page.goto("/?internal=0");
    await expect(page.locator("[data-internal-note]")).toHaveText("This device is counted in StratLab's analytics again.", { timeout: 30_000 });
    expect(await page.evaluate(() => localStorage.getItem("stratlab.internal"))).toBeNull();
    await ctx.close();
  });
});

test.describe("T2, T4: the app's analytics through the site's own address, and never for StratLab's own accounts", () => {
  test.use({ serviceWorkers: "block" });
  const config = `window.STRATLAB_CONFIG = {API_BASE:"${API}",SUPABASE_URL:"https://demo.supabase.co",SUPABASE_ANON_KEY:"demo",POSTHOG_KEY:"phc_test",POSTHOG_HOST:"/ingest"};`;

  test("a visitor's pageview goes to /ingest on the site, not to posthog.com", async ({ page }) => {
    const sent: Request[] = [];
    await person(page);
    await page.route("**/config.js", (r) => r.fulfill({ contentType: "application/javascript", body: config }));
    await page.route("**/ingest/**", (r) => { sent.push(r.request()); return r.fulfill({ status: 200, json: { status: 1 } }); });
    page.on("request", (r) => { if (/posthog\.com/.test(r.url())) sent.push(r); });
    await page.goto("/");
    await expect(page.locator(".lp").getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
    await expect.poll(() => sent.length, { timeout: 20_000 }).toBeGreaterThan(0);
    expect(sent.every((r) => new URL(r.url()).pathname.startsWith("/ingest/"))).toBe(true);
    expect(sent.some((r) => /posthog\.com/.test(r.url()))).toBe(false);
  });

  test("the owner's account (an admin, by the server's word) sends nothing, and its device is marked", async ({ page }) => {
    const sent: string[] = [];
    await person(page);
    await page.route("**/config.js", (r) => r.fulfill({ contentType: "application/javascript", body: config }));
    await page.route("**/ingest/**", (r) => { sent.push(r.request().postData() || ""); return r.fulfill({ status: 200, json: { status: 1 } }); });
    await page.addInitScript(() => {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: 4102444800,
        refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } }));
      localStorage.setItem("stratlab.tour.v1", "1");
    });
    await page.goto("/research");
    await page.getByText("What brings you here?").waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
    await expect(page.getByText("Companies").filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
    await expect.poll(() => page.evaluate(() => localStorage.getItem("stratlab.internal")), { timeout: 15_000 }).toBe("1");
    await page.waitForTimeout(4000);
    expect(sent.filter((b) => /"\$pageview"|"event"/.test(b))).toEqual([]);
  });
});

test.describe("P1: try one idea without an account", () => {
  test("from the landing page: open, pick, run, see the verdict with its checks, and the way to keep it is a free account", async ({ page }) => {
    await page.goto("/");
    const open = page.getByTestId("guest-open");
    await open.scrollIntoViewIfNeeded();
    await open.click();
    const tool = page.getByTestId("guest-try");
    await expect(tool).toBeVisible({ timeout: 30_000 });
    await tool.getByRole("radio", { name: "20/50 EMA cross" }).click();
    await tool.getByRole("radio", { name: "RELIANCE" }).click();
    await expect(tool.locator(".gt-rule")).toContainText("20-day exponential average crosses above the 50-day");
    await tool.getByRole("button", { name: "Run the test" }).click();
    const res = page.getByTestId("guest-result");
    await expect(res).toBeVisible({ timeout: 60_000 });
    await expect(res).toContainText("Reliance Industries (RELIANCE)");
    await expect(res.locator(".gt-headline")).not.toBeEmpty();
    await expect(res.locator(".badge")).toHaveCount(await res.locator(".lp-checklist .spread").count());
    await expect(res.locator(".gt-stats .k-delta").first()).toHaveText(/^[▲▼] [+−]\d/);
    await expect(res.getByRole("button", { name: "Sign up free with Google" })).toBeVisible();
    await expect(res).toContainText("Real test, not saved");
  });

  test("/new for a visitor: the sign-in, and one idea to try right there, with the stock a company page named picked", async ({ page }) => {
    await page.goto("/new?market=IN&symbol=TCS&from=stock");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Sign in to see the idea builder", { timeout: 30_000 });
    const tool = page.getByTestId("gate-try").getByTestId("guest-try");
    await expect(tool).toBeVisible({ timeout: 30_000 });
    await expect(tool.getByRole("radio", { name: "TCS" })).toHaveAttribute("aria-checked", "true");
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem("stratlab.from") || "{}").v)).toBe("stock");
  });
});

test.describe("P4, P6, P7, P10: the landing page and the plans", () => {
  test("the hero's no-sign-in proof opens a verdict that held up; the facts-not-advice line is in the first screen", async ({ page }) => {
    await page.goto("/");
    const trust = page.getByTestId("trust-line");
    await expect(trust).toContainText("not a SEBI-registered investment adviser or research analyst", { timeout: 30_000 });
    await expect(trust).toBeVisible();
    expect(await page.locator(".lp-hero").innerText()).not.toMatch(/facts/i);      // the hero names no "facts" (VR5-owner-2)
    const proof = page.getByTestId("hero-proof");
    await expect(proof).toHaveText("See a verdict that held up, no sign-in");
    await expect(proof).toHaveAttribute("href", /^\/library\/seed-/, { timeout: 15_000 });
    await proof.click();
    await expect(page).toHaveURL(/\/library\/seed-/);
    await expect(page.getByText(/passed|held up/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveTitle(/· StratLab$/);
  });

  test("the plans: each paid button names its plan, with cancel and refund terms beside it, and the trust line", async ({ page }) => {
    // plans on sale (the fake world's offer says "opens soon", where a card has no button to stand beside)
    await page.route(`${API}/pricing`, async (r) => {
      const res = await r.fetch();
      const body = await res.json();
      await r.fulfill({ response: res, json: { ...body, offer: { ...body.offer, mode: "paid", payments: true, yearly: true } } });
    });
    await page.goto("/plans");
    await expect(page.getByTestId("cancel-note-basic")).toHaveText("Cancel any time · full refund if you ask within 7 days", { timeout: 30_000 });
    await expect(page.getByTestId("cancel-note-pro")).toBeVisible();
    await expect(page.getByTestId("plans-trust")).toContainText("SEBI-registered");
    await expect(page.locator('.lp-price[data-plan="basic"] button')).not.toHaveText(/see plans/);
  });

  test("a visitor on the public library sees no Move section or Close section controls", async ({ page }) => {
    await page.goto("/library");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(1000);
    await expect(page.getByRole("button", { name: /^(Move section|Section menu|Close section)$/ })).toHaveCount(0);
  });

  test("the home page's tab says what StratLab is", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Backtest trading ideas on Indian and US stocks · StratLab", { timeout: 30_000 });
  });
});

test.describe("P8: a gentle upgrade prompt", () => {
  test("a Free account at 3 of its 5 backtests this month is told once, with what Basic gives and a way to the plans", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: "free-token", token_type: "bearer", expires_in: 86400, expires_at: 4102444800,
        refresh_token: "r", user: { id: "u-free", aud: "authenticated", email: "free@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } }));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.consent.v1", "no");
    });
    await page.route(`${API}/me`, async (r) => {
      const res = await r.fetch();
      const me = await res.json();
      await r.fulfill({ response: res, json: { ...me, plan: "free", established: true, view_as: null, usage: { ...me.usage, backtests_used: 3, backtests_limit: 5 } } });
    });
    await page.goto("/research");
    await page.getByText("What brings you here?").waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
    await expect(page.getByText("You've used 3 of your 5 free backtests this month (2 left). Basic gives 100 a month.")).toBeVisible({ timeout: 30_000 });
    // once a month on this browser
    await page.reload();
    await page.waitForTimeout(3000);
    await expect(page.getByText("You've used 3 of your 5 free backtests this month")).toHaveCount(0);
  });
});
