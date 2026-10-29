import { expect, test, type Page, type Route } from "@playwright/test";

// Item 34 (owner, 29 Oct): every price reads rupees first, the currency Razorpay charges, with the dollar figure beside it,
// "₹699 a month (about $8)", signed out and in, on /plans, the landing page, the paywall sentences and the subscribe step. A
// browser that says en-US in New York (LIVE1B-078: it read "$8 / $20" alone) gets the same. The checkout still asks for the
// rupee plan. The dollar figure is the app's USD/INR rate, fixed here at ₹90 so the figures are known.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
test.use({ locale: "en-US", timezoneId: "America/New_York" });

const edited = (edit: (j: Record<string, any>) => Record<string, any>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};
const onSale = (j: Record<string, any>) => ({ ...j, offer: { ...(j.offer ?? {}), payments: true, yearly: true }, billing_enabled: true });
const pricing = (j: Record<string, any>) => onSale({ ...j, usd_inr: { rate: 90, fallback: false } });

async function visit(page: Page, path: string, signedIn: number | false = false) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(`${API}/pricing`, edited(pricing));
  // an earlier visit's choice of dollars on this device is ignored
  await page.addInitScript(() => { localStorage.setItem("stratlab.currency", "USD"); localStorage.setItem("stratlab.tour.v1", "1"); });
  if (signedIn) {
    await page.route(`${API}/me`, edited(onSale));
    const n = signedIn;           // a fresh Free account of its own, one per project
    const session = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r", access_token: `load-${n}`,
      user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
    await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.onboarding.v1", "done"); }, session);
  }
  await page.goto(path);
  return errors;
}

test("/plans signed out, en-US browser: rupees first with the dollar beside each price, no dollars alone, no currency picker", async ({ page }) => {
  const errors = await visit(page, "/plans");
  const basic = page.locator('.lp-price[data-plan="basic"]');
  await expect(basic.locator(".lp-amount")).toContainText("₹699", { timeout: 30_000 });
  await expect(page.getByTestId("about-basic")).toHaveText("about $8");
  await expect(page.locator('.lp-price[data-plan="pro"] .lp-amount')).toContainText("₹1,999");
  await expect(page.getByTestId("about-pro")).toHaveText("about $22");
  await expect(page.locator('.lp-price[data-plan="free"] .lp-amount')).toContainText("₹0");
  await expect(page.getByTestId("about-free")).toHaveCount(0);
  // the year, too, and its saving
  await page.getByRole("radio", { name: /^Yearly/ }).click();
  await expect(page.locator('.lp-price[data-plan="basic"] .lp-amount')).toContainText("₹6,999");
  await expect(page.getByTestId("about-basic")).toHaveText("about $78");
  await expect(basic.locator(".lp-save")).toContainText(/Saves ₹[\d,]+ \(about \$\d+\) a year/);
  // never a dollar amount as a card's main price, no picker to switch to one, and the rate said once under the plans
  for (const amount of await page.locator(".lp-amount").allInnerTexts()) expect(amount).toMatch(/^₹/);
  await expect(page.getByLabel("Prices in")).toHaveCount(0);
  await expect(page.getByText("In India? Show prices in ₹")).toHaveCount(0);
  await expect(page.getByTestId("usd-note")).toContainText("at ₹90 to the dollar (today's rate)");
  expect(errors).toEqual([]);
});

test("the landing page's plans say the same for an en-US visitor", async ({ page }) => {
  const errors = await visit(page, "/");
  const sec = page.locator("#pricing");
  await sec.scrollIntoViewIfNeeded();
  await expect(sec.locator('.lp-price[data-plan="basic"] .lp-amount')).toContainText("₹699", { timeout: 30_000 });
  await expect(sec.getByTestId("about-basic")).toHaveText("about $8");
  await expect(sec).not.toContainText("$8 /");
  expect(errors).toEqual([]);
});

test("signed in: the Plans cards, the subscribe step and its checkout are in rupees, with the dollar figure beside them", async ({ page }, info) => {
  await page.addInitScript(() => {
    (window as any).Razorpay = class { constructor(o: unknown) { (window as any).__rz = o; } on() { /* no events */ } open() { (window as any).__opened = true; } };
  });
  let asked: Record<string, unknown> | null = null;
  await page.route(`${API}/billing/subscribe`, (r) => { asked = r.request().postDataJSON(); return r.fulfill({ status: 200, json: { subscription_id: "sub_test", key_id: "rzp_test", email: "", currency: "INR" } }); });
  const errors = await visit(page, "/plans", info.project.name === "phone" ? 276 : 273);          // two Free accounts no other spec uses
  await expect(page.locator(".k-plan-price").nth(1)).toContainText("₹699", { timeout: 30_000 });
  await expect(page.getByTestId("about-basic")).toHaveText("about $8");
  await expect(page.getByTestId("about-pro")).toHaveText("about $22");
  await expect(page.getByTestId("usd-note")).toContainText("charged in rupees");
  await page.getByRole("button", { name: "Upgrade to Basic" }).click();
  const confirm = page.getByRole("dialog").getByTestId("plan-confirm");
  await expect(confirm).toContainText(/Basic plan, billed monthly: ₹699( incl\. 18% GST)? \(about \$8\), every month\./);
  await expect(confirm).toContainText("shows the amount in rupees");
  await page.getByRole("dialog").getByRole("button", { name: /Continue to payment · ₹699/ }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__opened === true), { timeout: 15_000 }).toBe(true);
  expect(asked).toMatchObject({ plan: "basic", period: "month", currency: "INR" });           // the rupee plan, as before
  expect(errors).toEqual([]);
});
