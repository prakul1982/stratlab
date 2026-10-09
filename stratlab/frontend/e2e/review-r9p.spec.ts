import { expect, test, type Page, type Route } from "@playwright/test";

// Round 9 review of the live site (9 Oct 2026): plan views, payments, emails, Safari. What the app draws, on the reviewer's
// examples. Every answer a test depends on is fixed here, so none waits on whether one of the fake world's jobs has run.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
type User = { token: string; id: string; email: string };
const owner: User = { token: "admin-token", id: "u-admin", email: "owner@example.com" };
const visitor: User = { token: "load-297", id: "u-load-297", email: "load297@example.com" };

async function open(page: Page, where: string, user: User = owner, local: Record<string, string> = {}) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: user.token, user: { id: user.id, aud: "authenticated", email: user.email, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript(([s, extra]) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
    for (const [k, v] of Object.entries(extra as Record<string, string>)) localStorage.setItem(k, v);
  }, [session, local] as const);
  await page.goto(where);
  return errors;
}

/** The fake world's own answer for a request, changed by `edit`. */
const edited = (edit: (j: Record<string, any>) => Record<string, any>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};
const onSale = (j: Record<string, any>) => ({ ...j, offer: { ...(j.offer ?? {}), payments: true, yearly: true }, billing_enabled: true });

test("R9P-006 and R9P-007: the confirm step says what the rupee charge is in dollars, and Razorpay's window says it renews", async ({ page }) => {
  await page.addInitScript(() => {
    // the payment window, recorded instead of opened
    (window as any).Razorpay = class { constructor(o: unknown) { (window as any).__rz = o; } on() { /* no events */ } open() { (window as any).__opened = true; } };
  });
  await page.route(`${API}/me`, edited(onSale));
  await page.route(`${API}/pricing`, edited((j) => onSale({
    ...j, invoice: { gst: false },
    currencies: { ...j.currencies, USD: { symbol: "$", name: "US dollar", basic: 8, pro: 20, basic_year: 80, pro_year: 200, charged_in: "INR", yearly_charged_in: "INR",
      converted: false, charge_about: { basic: 7.23, pro: 20.67, basic_year: 72.38, pro_year: 206.82 } } } })));
  await page.route(`${API}/billing/subscribe`, (r) => r.fulfill({ status: 200, json: { subscription_id: "sub_test", key_id: "rzp_test", email: "", currency: "INR" } }));
  const errors = await open(page, "/plans", visitor, { "stratlab.currency": "USD" });
  await expect(page.getByTestId("charged-basic")).toContainText("Charged as ₹699 (about $7.23 today) / month", { timeout: 30_000 });
  await page.getByRole("button", { name: "Upgrade to Basic" }).click();
  const confirm = page.getByRole("dialog").getByTestId("plan-confirm");
  await expect(confirm).toContainText("Basic plan, billed monthly: ₹699 (about $7.23 today), every month.");       // the card's figure, not a second one
  await expect(confirm).toContainText("renews automatically");
  await page.getByRole("dialog").getByRole("button", { name: "Continue to payment" }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__opened === true), { timeout: 15_000 }).toBe(true);
  const rz = await page.evaluate(() => (window as any).__rz);
  expect(rz.name).toBe("StratLab · Basic, monthly");
  expect(rz.description).toMatch(/Renews every month until you cancel\.$/);                                      // the line Razorpay shows under the name
  expect(rz.subscription_id).toBe("sub_test");
  expect(errors).toEqual([]);
});

test("R9P-005: the owner viewing as Free sees the AI-reads cap of the viewed plan on Account", async ({ page }) => {
  const errors = await open(page, "/account", owner, { "stratlab.viewas.v1": "free" });
  const reads = page.locator(".k-rows > div", { hasText: "Fresh AI reads today" });
  await expect(reads).toContainText(/\d+ of 60 \(not enforced for you as an admin\)/, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("R9P-005: Account's AI builds line carries the daily cap a Pro plan has, as the Plans card does", async ({ page }) => {
  await page.route(`${API}/me`, edited((j) => ({ ...j, plan: "pro", paid_plan: "pro", usage: { ...j.usage, ai_limit: null, ai_builds_per_day: 200 } })));
  const errors = await open(page, "/account", visitor);
  const builds = page.locator(".k-rows > div", { hasText: "AI builds this month" });
  await expect(builds).toContainText(/\d+ \(unlimited; up to 200 a day\)/, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("R9P-008: when the app's own file will not download on the first load, the page ends on the Reload card, not a blank", async ({ page }) => {
  await page.route(/\/assets\/main-[^/]+\.js$/, (r) => r.abort("failed"));          // Safari's "Importing a module script failed"
  await open(page, "/account");
  const card = page.getByRole("alert").filter({ hasText: "Couldn't load StratLab." });
  await expect(card).toBeVisible({ timeout: 45_000 });                                // after boot.js's one automatic reload
  await expect(card.getByRole("button", { name: "Reload" })).toBeVisible();
});
