import { expect, test, type Page, type Route } from "@playwright/test";

// Lane su1 (owner, 16 Nov) on the fake world: (1) sign-in by email beside Google, hidden while /config.js leaves EMAIL_SIGNIN off
// and shown when it is on, with the sign-in service's answers mocked (nothing is emailed); (2) US dollar prices for US visitors on
// a visible "Prices in" switch, and a checkout whose amount is the one the page confirmed: rupees while dollar checkout is off or
// the server has no USD plans, dollars only when both are on.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SB = "https://demo.supabase.co/auth/v1";

/** The built app's config.js with these switches added. */
async function withConfig(page: Page, extra: Record<string, string>) {
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(extra)});\n` });
  });
}
const edited = (edit: (j: Record<string, any>) => Record<string, any>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};
/** /pricing on sale, at ₹90 to the dollar, with the USD row's plans on the server or not. */
const pricing = (usdPlans: boolean) => (j: Record<string, any>) => ({
  ...j, offer: { ...(j.offer ?? {}), mode: "paid", payments: true, yearly: true }, usd_inr: { rate: 90, fallback: false },
  currencies: { ...j.currencies, USD: { ...j.currencies.USD, basic: 8, pro: 20, basic_year: 80, pro_year: 200,
    charged_in: usdPlans ? "USD" : "INR", yearly_charged_in: usdPlans ? "USD" : "INR" } },
});
const onSale = (j: Record<string, any>) => ({ ...j, offer: { ...(j.offer ?? {}), payments: true, yearly: true }, billing_enabled: true });
const account = (i: number, provider = "google") => ({ token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r", access_token: `su1-${i}`,
  user: { id: `u-su1-${i}`, aud: "authenticated", email: `su1${i}@example.com`, role: "authenticated", app_metadata: { provider, providers: [provider] }, user_metadata: {} } });
async function signedIn(page: Page, i: number) {
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.onboarding.v1", "done"); localStorage.setItem("stratlab.tour.v1", "1"); }, account(i));
}
const errorsOf = (page: Page) => { const e: string[] = []; page.on("pageerror", (x) => e.push(x.message)); return e; };

test.use({ serviceWorkers: "block" });          // each visit reads the config.js the test gives, never one a service worker kept

test.describe("email sign-in", () => {
  test("switched off (as shipped): the sign-in page and the gate offer Google only, and Sign in goes straight to Google", async ({ page }) => {
    const errors = errorsOf(page);
    let authorize = "";
    await page.route(`${SB}/authorize**`, (r) => { authorize = r.request().url(); return r.fulfill({ status: 200, body: "signing in", contentType: "text/plain" }); });
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("email-signin")).toHaveCount(0);
    await expect(page.getByLabel("Sign in with email")).toHaveCount(0);
    await page.goto("/account");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Sign in to see/, { timeout: 30_000 });
    await expect(page.getByTestId("email-signin")).toHaveCount(0);
    await page.goto("/faq");
    await page.getByRole("banner").getByRole("button", { name: "Sign in", exact: true }).click();
    await expect.poll(() => authorize).toContain("provider=google");
    expect(errors).toEqual([]);
  });

  test("switched on: Sign in opens the page with both ways in; an emailed code signs in to the account, which says it was by email", async ({ page }, info) => {
    const errors = errorsOf(page);
    const i = info.project.name === "phone" ? 1 : 0;              // su1-0 and su1-1 sign in by email in the fake world
    await withConfig(page, { EMAIL_SIGNIN: "on" });
    const sent: Record<string, unknown>[] = [], verified: Record<string, unknown>[] = [];
    await page.route(`${SB}/otp**`, (r) => { sent.push(r.request().postDataJSON()); return r.fulfill({ status: 200, contentType: "application/json", body: "{}" }); });
    await page.route(`${SB}/verify**`, (r) => {
      const b = r.request().postDataJSON();
      verified.push(b);
      return b.token === "123456" ? r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(account(i, "email")) })
        : r.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ code: 403, error_code: "otp_expired", msg: "Token has expired or is invalid" }) });
    });
    await page.goto("/faq");
    await page.getByRole("banner").getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/login$/, { timeout: 30_000 });
    // Google first, then email, both in view
    const google = page.getByRole("button", { name: "Continue with Google" });
    const box = page.getByLabel("Sign in with email");
    await expect(google).toBeVisible();
    await expect(box).toBeVisible();
    expect((await google.boundingBox())!.y).toBeLessThan((await box.boundingBox())!.y);
    // a mistyped address is caught here, with nothing sent
    await box.fill("su1@example");
    await page.getByRole("button", { name: "Email me a code" }).click();
    await expect(page.getByTestId("email-error")).toContainText("doesn't look right");
    expect(sent).toHaveLength(0);
    await box.fill(`su1${i}@example.com`);
    await page.getByRole("button", { name: "Email me a code" }).click();
    await expect(page.getByTestId("email-sent")).toContainText(`su1${i}@example.com`);
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ email: `su1${i}@example.com`, create_user: true });
    // the next email waits a minute
    await expect(page.getByRole("button", { name: /^Send again in \d+s$/ })).toBeDisabled();
    // a wrong code says so; the right one signs in and the app opens
    const code = page.getByLabel("Sign-in code");
    await code.fill("000000");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByTestId("email-error")).toContainText("That code didn't work");
    await code.fill("123 456");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    // signed in: the app opens (a page load), with the session saved in this browser, back on the page where Sign in was pressed
    await expect.poll(() => page.evaluate(() => localStorage.getItem("sb-demo-auth-token")).catch(() => null), { timeout: 30_000 }).not.toBeNull();
    await expect(page).toHaveURL(/\/(faq|help)$/, { timeout: 30_000 });          // signed in, /faq is the Help page
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Help", { timeout: 30_000 });
    expect(verified.at(-1)).toMatchObject({ email: `su1${i}@example.com`, token: "123456", type: "email" });
    await page.goto("/account");
    await expect(page.getByText(`su1${i}@example.com`).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("dl")).toContainText("Email link");
    await expect(page.getByTestId("email-link-note")).toHaveCount(0);      // "sign-in is with Google now" is not said while email is on
    expect(errors).toEqual([]);
  });

  test("switched on: the gate offers email under Google, and the service's rate limit is said in words", async ({ page }) => {
    const errors = errorsOf(page);
    await withConfig(page, { EMAIL_SIGNIN: "on" });
    await page.route(`${SB}/otp**`, (r) => r.fulfill({ status: 429, contentType: "application/json",
      body: JSON.stringify({ code: 429, error_code: "over_email_send_rate_limit", msg: "email rate limit exceeded" }) }));
    await page.goto("/account");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Sign in to see/, { timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    await page.getByLabel("Sign in with email").fill("someone@example.com");
    await page.getByRole("button", { name: "Email me a code" }).click();
    await expect(page.getByTestId("email-error")).toContainText("Too many sign-in emails");
    await expect(page.getByTestId("email-sent")).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test.describe("US dollar prices", () => {
  test.describe("a US visitor", () => {
    test.use({ locale: "en-US", timezoneId: "America/New_York" });

    test("signed out: dollars on the switch, said as the region's, with the rupee charge; ₹ is one press away and kept", async ({ page }) => {
      const errors = errorsOf(page);
      await page.route(`${API}/pricing`, edited(pricing(false)));
      await page.goto("/plans");
      const basic = page.locator('.lp-price[data-plan="basic"]');
      await expect(basic.locator(".lp-amount")).toContainText("$8", { timeout: 30_000 });
      const sw = page.getByRole("radiogroup", { name: "Prices in" });
      await expect(sw.getByRole("radio", { name: "$ USD" })).toHaveAttribute("aria-checked", "true");
      await expect(page.getByTestId("cur-auto")).toContainText("American time zone");
      await expect(page.getByTestId("about-basic")).toHaveText("Charged as ₹699 in rupees");
      await expect(page.locator('.lp-price[data-plan="pro"] .lp-amount')).toContainText("$20");
      await expect(page.locator('.lp-price[data-plan="free"] .lp-amount')).toContainText("$0");
      await expect(page.getByTestId("usd-note")).toContainText("payment is in rupees for now");
      await page.getByRole("radio", { name: /^Yearly/ }).click();
      await expect(basic.locator(".lp-amount")).toContainText("$80");
      await expect(page.getByTestId("about-basic")).toHaveText("Charged as ₹6,999 in rupees");
      // rupees, kept for the next visit, and no "automatic" line once chosen
      await sw.getByRole("radio", { name: "₹ INR" }).click();
      await expect(basic.locator(".lp-amount")).toContainText("₹6,999");
      await expect(page.getByTestId("about-basic")).toHaveText("about $78");
      await expect(page.getByTestId("cur-auto")).toHaveCount(0);
      await page.reload();
      await expect(page.locator('.lp-price[data-plan="basic"] .lp-amount')).toContainText("₹699", { timeout: 30_000 });
      await expect(page.getByRole("radiogroup", { name: "Prices in" }).getByRole("radio", { name: "₹ INR" })).toHaveAttribute("aria-checked", "true");
      expect(errors).toEqual([]);
    });

    test("signed in, no dollar checkout: dollars shown, the confirm step and checkout are the rupee amount", async ({ page }, info) => {
      const errors = errorsOf(page);
      await page.addInitScript(() => {
        (window as any).Razorpay = class { constructor(o: unknown) { (window as any).__rz = o; } on() { /* no events */ } open() { (window as any).__opened = true; } };
      });
      let asked: Record<string, unknown> | null = null;
      await page.route(`${API}/billing/subscribe`, (r) => { asked = r.request().postDataJSON(); return r.fulfill({ status: 200, json: { subscription_id: "sub_test", key_id: "rzp_test", email: "", currency: "INR" } }); });
      await page.route(`${API}/pricing`, edited(pricing(true)));           // USD plans on the server, but USD_CHECKOUT is off
      await page.route(`${API}/me`, edited(onSale));
      await signedIn(page, info.project.name === "phone" ? 7 : 6);
      await page.goto("/plans");
      await expect(page.locator(".k-plan-price").nth(1)).toContainText("$8", { timeout: 30_000 });
      await expect(page.getByTestId("about-basic")).toHaveText("Charged as ₹699 in rupees");
      await page.getByRole("button", { name: "Upgrade to Basic" }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByTestId("plan-confirm")).toContainText(/Basic plan, billed monthly: ₹699( incl\. 18% GST)? \(shown as \$8; charged in rupees\), every month\./);
      await expect(dialog.getByTestId("plan-confirm")).toContainText("shows the amount in rupees");
      await dialog.getByRole("button", { name: /^Continue to payment · ₹699( incl\. 18% GST)?$/ }).click();
      await expect.poll(() => page.evaluate(() => (window as any).__opened === true), { timeout: 15_000 }).toBe(true);
      expect(asked).toMatchObject({ plan: "basic", period: "month", currency: "INR" });
      expect(errors).toEqual([]);
    });

    test("signed in, dollar checkout on and USD plans on the server: the dollar amount is confirmed and charged", async ({ page }, info) => {
      const errors = errorsOf(page);
      await withConfig(page, { USD_CHECKOUT: "on" });
      await page.addInitScript(() => {
        (window as any).Razorpay = class { constructor(o: unknown) { (window as any).__rz = o; } on() { /* no events */ } open() { (window as any).__opened = true; } };
      });
      let asked: Record<string, unknown> | null = null;
      await page.route(`${API}/billing/subscribe`, (r) => { asked = r.request().postDataJSON(); return r.fulfill({ status: 200, json: { subscription_id: "sub_test", key_id: "rzp_test", email: "", currency: "USD" } }); });
      await page.route(`${API}/pricing`, edited(pricing(true)));
      await page.route(`${API}/me`, edited(onSale));
      await signedIn(page, info.project.name === "phone" ? 9 : 8);
      await page.goto("/plans");
      await expect(page.locator(".k-plan-price").nth(2)).toContainText("$20", { timeout: 30_000 });
      await expect(page.getByTestId("about-pro")).toHaveCount(0);
      await expect(page.getByTestId("usd-note")).toContainText("charged in US dollars");
      await page.getByRole("button", { name: "Upgrade to Pro" }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByTestId("plan-confirm")).toContainText("Pro plan, billed monthly: $20, every month.");
      await expect(dialog.getByTestId("plan-confirm")).toContainText("shows the amount in USD");
      await dialog.getByRole("button", { name: "Continue to payment · $20" }).click();
      await expect.poll(() => page.evaluate(() => (window as any).__opened === true), { timeout: 15_000 }).toBe(true);
      expect(asked).toMatchObject({ plan: "pro", period: "month", currency: "USD" });
      expect(errors).toEqual([]);
    });

    test("signed in: a server that answers in rupees after dollars were confirmed opens no payment window", async ({ page }, info) => {
      const errors = errorsOf(page);
      await withConfig(page, { USD_CHECKOUT: "on" });
      await page.addInitScript(() => {
        (window as any).Razorpay = class { constructor() { /* nothing */ } on() { /* no events */ } open() { (window as any).__opened = true; } };
      });
      await page.route(`${API}/billing/subscribe`, (r) => r.fulfill({ status: 200, json: { subscription_id: "sub_test", key_id: "rzp_test", email: "", currency: "INR" } }));
      await page.route(`${API}/pricing`, edited(pricing(true)));
      await page.route(`${API}/me`, edited(onSale));
      await signedIn(page, info.project.name === "phone" ? 11 : 10);
      await page.goto("/plans");
      await expect(page.locator(".k-plan-price").nth(1)).toContainText("$8", { timeout: 30_000 });
      await page.getByRole("button", { name: "Upgrade to Basic" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Continue to payment · $8" }).click();
      await expect(page.getByText("The prices changed just now")).toBeVisible({ timeout: 15_000 });
      expect(await page.evaluate(() => (window as any).__opened === true)).toBe(false);
      expect(errors).toEqual([]);
    });
  });

  test.describe("an Indian visitor", () => {
    test.use({ locale: "en-IN", timezoneId: "Asia/Kolkata" });

    test("rupees first with the switch in view, and dollars when chosen", async ({ page }) => {
      const errors = errorsOf(page);
      await page.route(`${API}/pricing`, edited(pricing(false)));
      await page.goto("/");
      const sec = page.locator("#pricing");
      await sec.scrollIntoViewIfNeeded();
      await expect(sec.locator('.lp-price[data-plan="basic"] .lp-amount')).toContainText("₹699", { timeout: 30_000 });
      await expect(sec.getByTestId("about-basic")).toHaveText("about $8");
      const sw = sec.getByRole("radiogroup", { name: "Prices in" });
      await expect(sw.getByRole("radio", { name: "₹ INR" })).toHaveAttribute("aria-checked", "true");
      await expect(sec.getByTestId("cur-auto")).toHaveCount(0);
      await sw.getByRole("radio", { name: "$ USD" }).click();
      await expect(sec.locator('.lp-price[data-plan="basic"] .lp-amount')).toContainText("$8");
      await expect(sec.getByTestId("about-basic")).toHaveText("Charged as ₹699 in rupees");
      expect(errors).toEqual([]);
    });
  });
});
