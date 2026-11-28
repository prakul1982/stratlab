import { expect, test, type Page } from "@playwright/test";
import { API, open, sessionAs } from "./pages-kit";

// price102 (owner, 28 Nov: "all ok to do", GTM P1 and P3): Plans shows the founding-member yearly prices while the server says they run
// (the old price struck through, the deadline, "for the first 100 members"), checkout sends the offer the page showed and a changed price
// opens no payment window; a student asks for the student price from Plans. Payments are on in these tests the way the other plan specs
// put them on (the fake world has no Razorpay keys): /me and /pricing say so, and the founding offer is the server's answer while its plans
// are set (backend tests/test_price102.py tests the server's side).
// (the server's words for it: backend offers.founding_words)
const FOUNDING = { open: true, until: "2026-12-31T18:29:00+00:00", seats: 100, prices: { basic: 4999, pro: 14999 }, was: { basic: 6999, pro: 19999 },
  deadline: "31 Dec 2026, 11:59 pm IST",
  line: "Founding-member prices for the first 100 members, until 31 Dec 2026, 11:59 pm IST: Basic ₹4,999 a year (was ₹6,999), Pro ₹14,999 a year (was ₹19,999). The price stays the same for as long as you renew. Monthly prices don't change.",
  note: { basic: "Founding-member price for the first 100 members, until 31 Dec 2026, 11:59 pm IST. Renews at ₹4,999 a year for as long as you keep it.",
    pro: "Founding-member price for the first 100 members, until 31 Dec 2026, 11:59 pm IST. Renews at ₹14,999 a year for as long as you keep it." },
  year: { basic: "₹4,999 a year (founding-member price until 31 Dec 2026, 11:59 pm IST, for the first 100 members; was ₹6,999)",
    pro: "₹14,999 a year (founding-member price until 31 Dec 2026, 11:59 pm IST, for the first 100 members; was ₹19,999)" } };
// one account per test, project and repeat (backend tests/fake_db.py: price102-0 to 59, so up to --repeat-each=10): a student request is kept per person, so a repeat on
// the same server (--repeat-each, a kept server) starts from no request
const who = (n: number, phone: boolean, repeat = 0) => { const i = (repeat * 3 + n) * 2 + (phone ? 1 : 0); return sessionAs(`price102-${i}`, `u-price102-${i}`, `price102${i}@example.com`); };

// R103: the first test failed once on a phone in the release's long run and passed alone: these pages are slow under that load, so each test
// has room for its many steps (nothing checked is less), and every step waits for the page's own state before it acts
test.describe.configure({ timeout: 120_000 });
// the cause of that failure, found by repeating it (R103): a test whose checks had all passed still failed when the page's own /me, asked again
// after the 409, was in this file's route as the test ended ("route.fetch: Target page ... has been closed"); routes still in flight at the end are
// let go
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

async function onSale(page: Page, founding: typeof FOUNDING | null) {
  for (const path of ["/me", "/pricing"]) {
    await page.route(`${API}${path}`, async (r) => {
      const res = await r.fetch();
      const j = await res.json();
      await r.fulfill({ response: res, json: { ...j, billing_enabled: true, yearly_enabled: true, offer: { ...(j.offer ?? {}), mode: "paid", payments: true, yearly: true, founding } } });
    });
  }
}

test("plans: the founding-member yearly prices, struck-through old prices and the deadline; a price that changed opens no checkout", async ({ page }, info) => {
  await onSale(page, FOUNDING);
  const sent: unknown[] = [];
  await page.route(`${API}/billing/subscribe`, async (r) => {
    sent.push(r.request().postDataJSON());
    await r.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: { code: "price_changed",
      message: "The price changed just now: the founding-member price has ended. Check the amount on the plan again, then subscribe." } }) });
  });
  const errors = await open(page, "/plans", "Compare the plans", who(0, info.project.name === "phone", info.repeatEachIndex));
  const banner = page.getByTestId("founding-banner");
  await expect(banner).toContainText("Founding-member prices for the first 100 members, until 31 Dec 2026, 11:59 pm IST: Basic ₹4,999 a year (was ₹6,999), Pro ₹14,999 a year (was ₹19,999).");
  // monthly prices don't change
  await expect(page.getByTestId("plan-card-basic").locator(".k-plan-price")).toContainText("₹699");
  await expect(page.getByTestId("was-basic")).toHaveCount(0);
  const basic = page.getByTestId("plan-card-basic");
  await expect(basic.getByRole("button", { name: "Upgrade to Basic" })).toBeEnabled({ timeout: 30_000 });     // the account has answered
  await banner.getByRole("button", { name: "See yearly prices" }).click();
  await expect(basic.locator(".k-plan-price")).toContainText("₹4,999");
  await expect(page.getByTestId("was-basic")).toHaveText("₹6,999");
  await expect(page.getByTestId("was-pro")).toHaveText("₹19,999");
  await expect(page.getByTestId("founding-basic")).toHaveText("Founding-member price for the first 100 members, until 31 Dec 2026, 11:59 pm IST. Renews at ₹4,999 a year for as long as you keep it.");
  await expect(page.getByTestId("about-basic")).toContainText("about $");            // the offer's own dollar figure
  await basic.getByRole("button", { name: "Upgrade to Basic" }).click();
  await expect(page.getByTestId("plan-confirm")).toContainText("₹4,999", { timeout: 15_000 });
  await expect(page.getByTestId("plan-confirm")).toContainText("at the founding-member price for as long as you renew");
  // the page asks for the account again after a 409, so it shows the price that applies now
  const refreshed = page.waitForResponse((r) => r.url() === `${API}/me` && r.request().method() === "GET", { timeout: 30_000 });
  await page.getByRole("button", { name: /Continue to payment · ₹4,999/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "The price changed just now: the founding-member price has ended." })).toBeVisible({ timeout: 15_000 });
  expect(sent).toEqual([{ plan: "basic", period: "year", currency: "INR", offer: "founding" }]);
  expect((await refreshed).ok()).toBe(true);
  expect(await page.evaluate(() => "Razorpay" in window && !!(window as unknown as { Razorpay?: unknown }).Razorpay)).toBe(false);
  expect(errors).toEqual([]);
});

test("plans: with the founding offer over, the yearly cards are the standard prices with nothing struck through", async ({ page }, info) => {
  await onSale(page, null);
  const errors = await open(page, "/plans", "Compare the plans", who(1, info.project.name === "phone", info.repeatEachIndex));
  await expect(page.getByTestId("founding-banner")).toHaveCount(0);
  await page.getByRole("radio", { name: /Yearly/ }).first().click();
  await expect(page.getByTestId("plan-card-basic").locator(".k-plan-price")).toContainText("₹6,999");
  await expect(page.getByTestId("was-basic")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("plans: a student asks for the student price, and the line then says the request waits for a check", async ({ page }, info) => {
  await onSale(page, FOUNDING);
  const errors = await open(page, "/plans", "Compare the plans", who(2, info.project.name === "phone", info.repeatEachIndex));
  const line = page.getByTestId("student-line");
  await expect(line).toContainText("Student? Basic is ₹2,499 a year for students, approved by hand");
  await page.getByTestId("student-apply").click();
  const dialog = page.getByRole("dialog", { name: "Student price for Basic" });
  await dialog.getByRole("button", { name: "Send the request" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Say which college or university you study at.");
  await dialog.getByLabel("College or university").fill("IIT Bombay");
  await dialog.getByLabel("College email").fill("student@iitb.ac.in");
  await dialog.getByRole("button", { name: "Send the request" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(line).toContainText("is waiting for a check");
  expect(errors).toEqual([]);
});
