import { expect, test, type Page, type Route } from "@playwright/test";

// Round 8 owner review of the live site (9 Oct 2026, India open): what the app draws, on the reviewer's examples. Every
// answer a test depends on is fixed here, so none waits on whether one of the fake world's background jobs has run.
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
const edited = (edit: (j: Record<string, any>) => Record<string, any>, wait = 0) => async (r: Route) => {
  const res = await r.fetch();
  const j = edit(await res.json());
  if (wait) await new Promise((ok) => setTimeout(ok, wait));
  return r.fulfill({ response: res, json: j });
};
const onSale = (j: Record<string, any>) => ({ ...j, offer: { ...(j.offer ?? {}), payments: true, yearly: true }, billing_enabled: true });

test("R7M-010: under View as Free the buy buttons are off before /me answers, and after", async ({ page }) => {
  let meAnswered = false;
  await page.route(`${API}/pricing`, edited(onSale));
  // /me takes its time, as it did cold on the live site: the buttons are drawn from the public prices meanwhile
  await page.route(`${API}/me`, edited(onSale, 4000));
  page.on("response", (r) => { if (r.url() === `${API}/me`) meAnswered = true; });
  let subscribed = false;
  await page.route(`${API}/billing/subscribe`, (r) => { subscribed = true; return r.fulfill({ status: 409, json: {} }); });
  const errors = await open(page, "/plans", owner, { "stratlab.viewas.v1": "free" });
  const buy = page.getByRole("button", { name: "Upgrade to Basic" });
  await expect(buy).toBeVisible({ timeout: 30_000 });
  expect(meAnswered, "the buttons were drawn before /me answered").toBe(false);
  await expect(buy).toBeDisabled();
  await expect(buy).toContainText("(off while viewing as Free)");
  await expect(page.getByRole("button", { name: "Upgrade to Pro" })).toBeDisabled();
  await expect.poll(() => meAnswered, { timeout: 20_000 }).toBe(true);
  await expect(buy).toBeDisabled();
  await expect(page.getByTestId("plans-viewas")).toContainText("turn it off to change your billing");
  await buy.click({ force: true, timeout: 2000 }).catch(() => undefined);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(subscribed).toBe(false);
  expect(errors).toEqual([]);
});

test("R8O-002: when the day's cap is the reason, the mood says so and offers no Ask again", async ({ page }) => {
  await page.route(/\/research\/pulse\/ai\?/, (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    unavailable: true, code: "research_ai_limit",
    message: "You've used today's 60 fresh AI reads on your plan. Reads already written for a company or the market still open, and the count starts again at midnight India time." }) }));
  const errors = await open(page, "/research/pulse");
  const off = page.locator(".ai-read-off").first();
  await expect(off).toContainText("today's fresh AI reads on your plan are used up", { timeout: 30_000 });
  await expect(off).toContainText("midnight India time");
  await expect(off.getByRole("button", { name: "Ask again" })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("R8O-002: Account says the day's fresh AI reads against the cap", async ({ page }) => {
  const errors = await open(page, "/account", visitor);
  const row = page.locator(".k-rows > div", { hasText: "Fresh AI reads today" });
  await expect(row).toContainText(/\d+ of 60 \(starts again at midnight India time\)/, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("R8O-002: Plans lists the fresh AI reads a day, Pro with no cap", async ({ page }) => {
  const errors = await open(page, "/plans", visitor, { "stratlab.currency": "INR" });
  const row = page.getByRole("row", { name: /Fresh AI reads a day/ });
  await expect(row).toContainText("60", { timeout: 30_000 });
  await expect(row).toContainText("Unlimited");
  expect(errors).toEqual([]);
});

test("R8O-007: a company page shows its numbers at once and its AI read when it has been written behind it", async ({ page }) => {
  let asked = 0;
  const read = { summary: "Runs refineries, a telecom network and retail stores.", facts: [], valuation_note: "", bull: ["Jio has 470 million users."], bear: [],
    segments: [], position: "", watch: [], ideas: [], generated_at: Date.now() / 1000 };
  await page.route("**/research/company/IN/RELIANCE/ai*", (r) => {
    asked += 1;
    expect(new URL(r.request().url()).searchParams.get("background")).toBe("true");
    return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(asked < 3 ? { pending: true } : read) });
  });
  const errors = await open(page, "/research/IN/RELIANCE");
  await expect(page.locator("h1")).toContainText(/Reliance/i, { timeout: 30_000 });
  await expect(page.locator(".ai-read")).toContainText("Reading the numbers");          // the page is up; the read is on its way
  await expect(page.locator(".ai-read")).toContainText("Runs refineries", { timeout: 15_000 });
  expect(asked).toBe(3);
  await expect(page).toHaveTitle(/^Reliance Industries.* \(RELIANCE\) ₹/);
  expect(errors).toEqual([]);
});

test("R8O-007: a page whose code never arrives says so after 15 seconds, with Reload", async ({ page }) => {
  test.setTimeout(60_000);
  await page.route(/\/assets\/PlansPage-[^/]+\.js$/, () => undefined);          // the request hangs: no answer, no error
  const errors = await open(page, "/plans");
  await expect(page.getByText("Opening…")).toBeVisible({ timeout: 15_000 });
  const slow = page.getByTestId("opening-slow");
  await expect(slow).toBeVisible({ timeout: 25_000 });
  await expect(slow).toContainText("This page is taking a long time to open");
  await expect(slow.getByRole("button", { name: "Reload" })).toBeVisible();
  await expect(page.locator("h1")).toHaveCount(1);
  expect(errors).toEqual([]);
});

test("R8O-006: a euro price charged in rupees says that charge in euros, and the note says the actual difference", async ({ page }) => {
  await page.route(`${API}/me`, edited(onSale));
  await page.route(`${API}/pricing`, edited((j) => onSale({
    ...j, invoice: { gst: true },
    currencies: { ...j.currencies, EUR: { symbol: "€", name: "Euro", basic: 8, pro: 19, basic_year: 80, pro_year: 190, charged_in: "INR", yearly_charged_in: "INR",
      converted: false, charge_about: { basic: 6.44, pro: 18.43, basic_year: 64.53, pro_year: 184.39 } } },
    countries: { ...j.countries, DE: "EUR" } })));
  const errors = await open(page, "/plans", visitor, { "stratlab.currency": "EUR" });
  await expect(page.getByTestId("charged-basic")).toContainText("Charged as ₹699 incl. GST (about €6.44 today) / month", { timeout: 30_000 });
  await expect(page.getByTestId("charged-pro")).toContainText("(about €18.43 today)");
  const main = page.locator("main");
  await expect(main).toContainText("about €6.44 for Basic and €18.43 for Pro at today's rate, not the EUR prices shown");
  await expect(main).not.toContainText("can differ slightly");
  expect(errors).toEqual([]);
});

test("R8O-009: the closing auction's headings follow the page's h1", async ({ page }) => {
  const errors = await open(page, "/trade/closing-auction");
  await expect(page.locator("h1")).toHaveText("Closing auction", { timeout: 30_000 });
  await expect(page.locator("main h2").first()).toBeVisible({ timeout: 30_000 });
  const levels = await page.locator("main h1, main h2, main h3, main h4").evaluateAll((els) => els.map((e) => Number(e.tagName[1])));
  for (let i = 1; i < levels.length; i++) expect(levels[i] - levels[i - 1], `heading ${i}: ${levels.join(",")}`).toBeLessThanOrEqual(1);
  expect(errors).toEqual([]);
});

test("R8O-009: a lazy page's tab has its title before its code arrives", async ({ page }) => {
  let release: () => void = () => undefined;
  const held = new Promise<void>((ok) => { release = ok; });
  await page.route(/\/assets\/Research-[A-Za-z0-9_-]+\.js$/, async (r) => { await held; return r.fallback(); });
  const errors = await open(page, "/research/rotation");
  await expect(page).toHaveTitle("Sector rotation · StratLab", { timeout: 15_000 });
  release();
  expect(errors).toEqual([]);
});
