import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// Round 7, mail, payments, broker and reliability (9 Oct 2026): the Plans page that says nothing of GST while the invoice
// carries none, buy buttons that are off under View as, the invoice warning on Admin, the AI providers tile, the
// currencies with no exchange rate, "Loading" instead of the all-clear, Zerodha connected with nothing, the unsubscribe
// page in the site's look, why the journal differs from the tax report, and a leftover net-worth snapshot.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const ZIP = path.resolve(process.cwd(), "../backend/tests/fixtures/taxpnl/zerodha_taxpnl_2024_2025.zip");
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
type User = { token: string; id: string; email: string };
const owner: User = { token: "admin-token", id: "u-admin", email: "owner@example.com" };
const load = (n: number): User => ({ token: `load-${n}`, id: `u-load-${n}`, email: `load${n}@example.com` });

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
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  if (await welcome.waitFor({ timeout: 2500 }).then(() => true).catch(() => false)) {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await page.goto(where);
  }
  return errors;
}

const noSideways = async (page: Page) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
};

/** Payments on, as the live site has them (the fake world's plans aren't on sale). */
async function paymentsOn(page: Page) {
  await page.route(`${API}/me`, async (r) => {
    const res = await r.fetch();
    const j = await res.json();
    j.offer = { ...(j.offer ?? {}), payments: true, yearly: true };
    j.billing_enabled = true;
    await r.fulfill({ response: res, json: j });
  });
}

/** The server's Overview with something changed in its `server` part. */
async function overview(page: Page, change: (server: Record<string, any>) => void) {
  await page.route(`${API}/admin/overview`, async (r) => {
    const res = await r.fetch();
    const j = await res.json();
    change(j.server);
    await r.fulfill({ response: res, json: j });
  });
}

test("Plans: no word of GST while the invoice has none; the confirm step follows, and names the payment window (R7M-001, R6V-009)", async ({ page }) => {
  await paymentsOn(page);
  await page.route(`${API}/pricing`, async (r) => {
    const res = await r.fetch();
    const j = await res.json();
    await r.fulfill({ response: res, json: { ...j, invoice: { gst: false } } });          // the seller's GSTIN is empty: a plain invoice
  });
  let subscribed = false;
  await page.route(`${API}/billing/subscribe`, (r) => { subscribed = true; return r.fulfill({ status: 500, json: {} }); });
  const errors = await open(page, "/plans", load(297), { "stratlab.currency": "INR" });
  await page.getByRole("button", { name: "Upgrade to Basic" }).click({ timeout: 30_000 });
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByTestId("plan-confirm");
  await expect(confirm).toContainText(/Basic plan, billed monthly: ₹[\d,]+, every month\./);
  await expect(confirm).toContainText('The payment window that opens next is headed "StratLab · Basic, monthly" and shows the amount in rupees.');
  await expect(confirm).not.toContainText(/GST|shows the amount only/);
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator("main")).toContainText("Every payment gets an invoice in Account.");
  await expect(page.locator("main")).not.toContainText(/GST/);
  expect(subscribed).toBe(false);
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("Plans: with a GSTIN set the words are as before, and the window sentence is the new one (R7M-001, R6V-009)", async ({ page }) => {
  await paymentsOn(page);
  const errors = await open(page, "/plans", load(297), { "stratlab.currency": "INR" });
  await page.getByRole("button", { name: "Upgrade to Basic" }).click({ timeout: 30_000 });
  const confirm = page.getByRole("dialog").getByTestId("plan-confirm");
  await expect(confirm).toContainText(/Basic plan, billed monthly: ₹[\d,]+ incl\. 18% GST, every month\./);
  await expect(confirm).toContainText('headed "StratLab · Basic, monthly"');
  await expect(confirm).not.toContainText("shows the amount only");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator("main")).toContainText("Rupee prices include 18% GST, and every payment gets a GST invoice in Account.");
  expect(errors).toEqual([]);
});

test("Plans: under View as the upgrade buttons are off, with the reason, and nothing is asked of the server (R7M-010)", async ({ page }) => {
  await paymentsOn(page);
  let subscribed = false;
  await page.route(`${API}/billing/subscribe`, (r) => { subscribed = true; return r.fulfill({ status: 409, json: {} }); });
  const errors = await open(page, "/plans", owner, { "stratlab.viewas.v1": "free" });
  const buy = page.getByRole("button", { name: "Upgrade to Basic" });
  await expect(buy).toBeVisible({ timeout: 30_000 });
  await expect(buy).toBeDisabled();
  await expect(buy).toHaveAttribute("title", /^You're viewing as Free\. Plan changes and payments are off while View as is on/);
  await expect(page.getByTestId("plans-viewas")).toContainText("turn it off to change your billing");
  await expect(page.getByRole("button", { name: "Upgrade to Pro" })).toBeDisabled();
  await buy.click({ force: true, timeout: 2000 }).catch(() => undefined);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(subscribed).toBe(false);
  expect(errors).toEqual([]);
});

test("Admin: empty invoice seller details are a warning on Overview and Money, until they are filled in (R7M-001)", async ({ page }) => {
  // the fake world's seller has a GSTIN only: the other three are still said to be missing
  let errors = await open(page, "/admin/money");
  const notice = page.getByRole("status", { name: "Invoice seller details" });
  await expect(notice).toContainText("missing the legal name, address, state", { timeout: 30_000 });
  // nothing at all filled in
  await overview(page, (s) => { s.invoice_seller = { complete: false, missing: ["legal name", "address", "state", "GSTIN"], gst: false }; });
  errors = await open(page, "/admin");
  const todo = page.getByRole("region", { name: "Needs your attention" });
  await expect(todo).toContainText("The invoice seller details are empty. Until the GSTIN is set, every invoice is a plain one", { timeout: 30_000 });
  await expect(todo).not.toContainText("Nothing needs you");
  await todo.getByRole("link", { name: "Open Money" }).first().click();
  await expect(page.getByRole("status", { name: "Invoice seller details" })).toContainText("The invoice seller details are empty", { timeout: 30_000 });
  await page.getByRole("status", { name: "Invoice seller details" }).getByRole("button", { name: "Fill them in" }).click();
  await expect(page.getByRole("heading", { name: "Invoice details" })).toBeInViewport();
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("Admin: the AI providers tile counts what worked last (R7M-008)", async ({ page }) => {
  const row = (label: string, result: string) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result });
  await overview(page, (s) => {
    s.ai = [...["Groq", "Gemini", "OpenRouter", "Cloudflare", "NVIDIA"].map((n) => row(n, "working")),
      ...["Cerebras", "SambaNova", "Z.ai", "Vercel AI Gateway", "Hugging Face", "GitHub Models"].map((n) => row(n, "quota")), row("Mistral", "untested")];
  });
  const errors = await open(page, "/admin");
  await expect(page.getByText("5 of 12 working · 6 out of credit · 1 not tried yet")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/11 of 12 answering/)).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("Admin: while the status loads, Server errors says Loading and not that nothing has crashed (R7M-007)", async ({ page }) => {
  await page.route(`${API}/admin/overview`, async (r) => {
    await new Promise((done) => setTimeout(done, 3000));
    await r.fallback();
  });
  const errors = await open(page, "/admin/system");
  await expect(page.getByText("Loading the server errors…")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("No server errors")).toHaveCount(0);
  await expect(page.getByText("Nothing has crashed since the server last started")).toHaveCount(0);
  await expect(page.getByText(/^Server errors \(\d+ since the last restart/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Loading the server errors…")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("Admin: a currency with no exchange rate is flagged, not shown at a default price; the note is true (R7M-003)", async ({ page, request }) => {
  const row = (name: string, basic: number, extra: Record<string, unknown>) => ({ symbol: `${name} `, name, basic, pro: basic * 3, basic_year: basic * 10, pro_year: basic * 30, charged_in: "INR",
    auto: true, rate: null, plan_basic: null, plan_pro: null, plan_basic_year: null, plan_pro_year: null, ...extra });
  await page.route(`${API}/admin/prices`, (r) => r.fulfill({ json: { rates_at: "2026-10-09T00:00:00+00:00", rate_errors: ["NOK: no rate", "AUD: down"],
    currencies: { INR: row("Indian rupee", 699, {}), NOK: row("Norwegian krone", 64, { no_rate: true }), AUD: row("Australian dollar", 12, { rate: 58, no_rate: false }),
      SAR: row("Saudi riyal", 27, { rate: 25.81, no_rate: false }) } } }));
  const errors = await open(page, "/admin/money");
  const note = page.getByText(/^\s*Exchange rates read/);
  await expect(note).toContainText("Couldn't read: AUD (last rate kept).", { timeout: 30_000 });
  await expect(note).toContainText("No exchange rate yet for NOK: it isn't shown to visitors until one is read.");
  await expect(note).not.toContainText("NOK (last rate kept)");
  await expect(page.getByText("No rate: not shown to visitors")).toHaveCount(1);
  expect(errors).toEqual([]);
  // the server's own price list, with no rate read in the fake world, offers only the prices that need none
  const pricing = await (await request.get(`${API}/pricing`)).json();
  expect(Object.keys(pricing.currencies).sort()).toEqual(["EUR", "GBP", "INR", "USD"]);
  expect(pricing.invoice).toEqual({ gst: true });
});

test("Admin: the email previews say the briefs are real, and Data and jobs has a Newsletters row (R7M-004, R7M-005)", async ({ page }) => {
  let errors = await open(page, "/admin/emails");
  await expect(page.getByText("The market briefs are the newest real issues; the rest use made-up details.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("with made-up details. Nothing here is sent.")).toHaveCount(0);
  errors = errors.concat(await open(page, "/admin/data"));
  const row = page.locator("main").getByText("Newsletters", { exact: true }).first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main")).toContainText("India 4:15 PM IST and US 4:30 PM New York time");
  expect(errors).toEqual([]);
});

test("Holdings says Zerodha is connected and returned nothing, and the Zerodha card says when it was read (R7M-009)", async ({ page }) => {
  await page.route(`${API}/holdings`, (r) => r.fulfill({ json: {
    rows: [], allocation: [], totals: { value: 0, invested: 0, pnl: null, pnl_pct: null, day: null, day_pct: null, count: 0, priced: 0 }, source: null,
    updated_at: null, prices: true, limit: 50, facts_max: 40, zerodha: { live: true, count: 0, read_at: new Date(Date.now() - 600_000).toISOString() } } }));
  let errors = await open(page, "/holdings", load(297));
  const empty = page.getByText(/^Zerodha is connected; it returned 0 holdings at (\d{1,2} \w{3}, )?\d\d:\d\d IST\./);
  await expect(empty).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main")).not.toContainText("No holdings yet");
  await expect(page.locator("main")).not.toContainText("Connect Zerodha or your statement inbox once");
  await page.route(`${API}/connect`, async (r) => {
    const res = await r.fetch();
    const j = await res.json();
    await r.fulfill({ response: res, json: { ...j, kite: { ...j.kite, available: true, configured: true, connected: true, live: true, expired: false, count: 0, refreshed_label: "yesterday 23:00" } } });
  });
  errors = errors.concat(await open(page, "/settings#accounts", load(297)));
  await expect(page.getByTestId("kite-line")).toHaveText("Connected · last read yesterday 23:00 IST · 0 holdings", { timeout: 30_000 });
  await expect(page.getByTestId("kite-line")).not.toContainText(/tap to refresh|tomorrow/);
  expect(errors).toEqual([]);
});

test("The unsubscribe page has the site's look and points at Settings, not Account (R7M-004)", async ({ page }) => {
  await page.goto(`${API}/unsubscribe?t=preview`);
  await expect(page.getByRole("heading", { level: 1, name: "Unsubscribe (preview)" })).toBeVisible();
  await expect(page.locator("a.brand")).toBeVisible();                                    // the logo and word mark
  const look = await page.evaluate(() => ({
    bg: getComputedStyle(document.body).backgroundColor, h1: getComputedStyle(document.querySelector("h1")!).fontFamily,
    card: getComputedStyle(document.querySelector(".card")!).borderTopLeftRadius,
  }));
  expect(look.bg).toBe("rgb(245, 241, 232)");                                               // the site's paper
  expect(look.h1).toContain("Fraunces");
  expect(look.card).toBe("14px");
  const link = page.getByRole("link", { name: /Settings → Notifications/ });
  await expect(link).toHaveAttribute("href", /\/settings#notifications$/);
  await expect(page.locator("body")).not.toContainText("in Account");
  await noSideways(page);
});

test("Trade journal: it says why its numbers differ from the tax report, and no longer promises F&O it doesn't count (R7M-013)", async ({ page }, info) => {
  const n = info.project.name === "phone" ? 278 : 275;
  await page.route(`${API}/tax`, async (r) => {                                            // a tax report holding the same trades
    const res = await r.fetch();
    await r.fulfill({ response: res, json: { ...(await res.json()), trades: 38 } });
  });
  expect((await page.request.delete(`${API}/trade/journal`, { headers: { Authorization: `Bearer load-${n}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/trade/journal", load(n));
  await expect(page.getByRole("heading", { level: 1, name: "Trade journal" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main")).not.toContainText("Your broker's trades, equity, F&O, commodity and currency,");
  await expect(page.locator("main")).toContainText("F&O, commodity and currency from a tradebook or the tax P&L's trade-by-trade files");
  await page.getByLabel("Tradebook or tax P&L files").setInputFiles(ZIP);
  await expect(page.getByText("16 trade lines added")).toBeVisible({ timeout: 30_000 });
  const why = page.getByTestId("j-vs-tax");
  await expect(why.locator("summary")).toHaveText("Why these numbers differ from your tax report");
  await why.locator("summary").click();
  await expect(why).toContainText("one round trip per position closed");
  await expect(why).toContainText("every sale line on its own");
  await expect(why).toContainText(/Here: 15 closed round trips\./);
  expect(errors).toEqual([]);
  await page.request.delete(`${API}/trade/journal`, { headers: { Authorization: `Bearer load-${n}` } });
});

test("Net worth: a leftover snapshot with nothing entered is said and can be removed (R7M-012)", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 278 : 275;                       // Pro accounts in the fake world: the history is shown
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.delete(`${API}/money/net-worth`, { headers: auth })).ok()).toBeTruthy();
  const added = await request.post(`${API}/money/net-worth/items`, { headers: auth, data: { kind: "cash", name: "Test savings", value: 243481.78 } });
  expect(added.ok(), await added.text()).toBeTruthy();
  const id = (await added.json()).assets.find((a: { name: string }) => a.name === "Test savings").entry.id;
  expect((await request.delete(`${API}/money/net-worth/items/${id}`, { headers: auth })).ok()).toBeTruthy();       // the entry goes, its snapshot stays
  const errors = await open(page, "/money/net-worth", load(n));
  await expect(page.getByText("Nothing added yet")).toBeVisible({ timeout: 30_000 });
  const kept = page.getByRole("status", { name: "Kept history" });
  await expect(kept).toContainText("The history still holds a snapshot from earlier entries (latest ₹2,43,482 on");
  const snaps = page.getByTestId("nw-snapshots");
  await expect(snaps).toBeVisible();
  await expect(snaps.getByRole("button", { name: /^Remove the snapshot of/ })).toBeVisible();      // open: no click on the summary first
  await snaps.getByRole("button", { name: /^Remove the snapshot of/ }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove this snapshot" }).click();
  await expect(page.getByText("Snapshot removed.")).toBeVisible();
  await expect(page.getByTestId("nw-snapshots")).toHaveCount(0);
  await expect(page.getByRole("status", { name: "Kept history" })).toHaveCount(0);
  await expect(page.getByText("Nothing added yet")).toBeVisible();
  expect(errors).toEqual([]);
});
