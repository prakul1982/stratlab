import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Account (/account), Settings (/settings), Get the app (/app): who you are, your plan and invoices, how you sign in and
// where your data lives; then where alerts and emails go, what you see first, the theme, the files StratLab reads and the
// connection check. Each run signs in as its own new user, on desktop and phone.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SHOTS = process.env.E2E_SHOTS;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|amfi|nseindia/i;
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const who = (n: number, phone: boolean) => { const i = n + (phone ? 3 : 0); return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` }; };
type Who = ReturnType<typeof who>;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });

async function signIn(page: Page, request: APIRequestContext, u: Who, path: string, provider: string | null = "google") {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("dialog", (d) => { errors.push(`a browser dialog opened: ${d.message()}`); void d.dismiss(); });     // the page asks in its own dialogs
  await request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus: "both" } });     // skip the welcome questions
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: u.token, user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated",
    app_metadata: provider ? { provider } : {}, user_metadata: { full_name: "Asha Rao" } } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}

async function sane(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, PROVIDERS]) expect(text).not.toMatch(bad);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main a, main select, main input:not([type=checkbox])")).filter((el) => {
    const b = el.getBoundingClientRect();
    return b.width && b.height && !el.closest("p, li, .info-btn, .k-label-row, .k-linkcard") && !el.matches(".info-btn") && getComputedStyle(el).display !== "inline" && b.height < 32;
  }).map((el) => `${el.tagName} "${(el.textContent || "").trim().slice(0, 30)}"`));
  expect(small, "controls too small to tap").toEqual([]);
}

const shot = async (page: Page, name: string, phone: boolean) => {
  if (!SHOTS) return;
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${SHOTS}/${name}-${phone ? "400-light" : "1300-dark"}.png`, fullPage: true });
};

test("account: profile, plan and usage, invoices, sign-in and your data", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const u = who(263, phone);
  const errors = await signIn(page, request, u, "/account");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { level: 1, name: "Account" })).toBeVisible({ timeout: 30_000 });
  for (const h of ["Profile", "Plan and usage", "Invoices", "Sign-in and security", "Your data"]) await expect(main.getByRole("heading", { name: h })).toBeVisible();

  // who you are, as the app knows it
  const profile = main.locator("#profile");
  await expect(profile).toContainText("Asha Rao");
  await expect(profile).toContainText(u.email);
  await expect(profile.getByText("Signed in with")).toBeVisible();
  await expect(profile).toContainText("Google");
  await expect(main.locator("#plan")).toContainText("Backtests this month");
  await expect(main.getByText("Details on your invoices")).toBeVisible();

  // features that used to sit on this page have their own pages now
  for (const gone of [/Telegram/, /Newsletters/, /Emails from StratLab/, /On your phone/, /Invite friends/, /Connection check/, /What you see first/]) await expect(main).not.toContainText(gone);
  await expect(main.getByRole("heading", { name: "AI assistant" })).toHaveCount(0);

  // your data: each kind links to the page that holds its own delete button
  const data = main.locator("#data");
  for (const [title, href] of [["My Holdings", "/holdings"], ["Tax report", "/tax-report"], ["Mutual funds", "/money/mutual-funds"], ["Net worth", "/money/net-worth"], ["Notebooks and experiments", "/notebooks"], ["Stock alerts", "/alerts"]])
    await expect(data.getByRole("link", { name: new RegExp(`^${title}`) })).toHaveAttribute("href", href);
  await expect(main.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");

  // sign out everywhere asks in the page, and Cancel leaves you signed in
  await main.getByRole("button", { name: "Sign out everywhere" }).click();
  const ask = page.getByRole("dialog", { name: "Sign out on every device?" });
  await expect(ask).toContainText("every other phone or computer");
  await ask.getByRole("button", { name: "Cancel" }).click();
  await expect(ask).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("sb-demo-auth-token"))).not.toBeNull();
  await sane(page, errors, phone);
  await shot(page, "account", phone);

  // signing out everywhere ends the session on this device too
  await main.getByRole("button", { name: "Sign out everywhere" }).click();
  await page.getByRole("dialog", { name: "Sign out on every device?" }).getByRole("button", { name: "Sign out everywhere" }).click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("sb-demo-auth-token"))).toBeNull();
});

test("account: Sign out ends this session, and cancelling a plan asks in the page", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const u = who(269, phone);
  let cancelled = 0;
  await page.route(`${API}/billing/cancel`, async (r) => { cancelled++; await r.fulfill({ status: 200, contentType: "application/json", body: "{}" }); });
  await page.route(`${API}/me`, async (r) => {          // this person pays for Basic, so Cancel subscription is offered
    const res = await r.fetch();
    const me = await res.json();
    await r.fulfill({ response: res, json: { ...me, paid_plan: "basic", billing: { ...me.billing, subscribed_plan: "basic", status: "active", cancel_at_period_end: false, renews_or_ends: "2026-11-05T00:00:00Z" } } });
  });
  const errors = await signIn(page, request, u, "/account");
  const main = page.locator("main");
  await expect(main.getByText("Renews on")).toBeVisible({ timeout: 30_000 });
  await main.getByRole("button", { name: "Cancel subscription" }).click();
  const ask = page.getByRole("dialog", { name: "Cancel your subscription?" });
  await expect(ask).toContainText("You keep your plan until the end of the period you've paid for (5 Nov 2026)");
  await ask.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(ask).toHaveCount(0);
  expect(cancelled, "nothing was cancelled yet").toBe(0);
  await main.getByRole("button", { name: "Cancel subscription" }).click();
  await page.getByRole("dialog", { name: "Cancel your subscription?" }).getByRole("button", { name: "Cancel subscription" }).click();
  await expect.poll(() => cancelled).toBe(1);
  await sane(page, errors, phone);

  await main.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("sb-demo-auth-token"))).toBeNull();
});

test("settings: notifications keep their settings, with the alerts, StratLab emails and newsletters in one place", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const u = who(275, phone);
  const errors = await signIn(page, request, u, "/settings");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible({ timeout: 30_000 });
  const nav = main.getByRole("radiogroup", { name: "Settings sections" });
  await expect(nav.getByRole("radio")).toHaveText(["Notifications", "Experience", "Connected accounts", "Connection check"]);
  await expect(nav.getByRole("radio", { name: "Notifications" })).toHaveAttribute("aria-checked", "true");
  for (const h of [/^Alerts/, /^Newsletters/]) await expect(main.getByRole("heading", { name: h })).toBeVisible({ timeout: 30_000 });
  await expect(main.getByRole("heading", { name: "Emails from StratLab" })).toBeVisible();

  // alerts: what to send and where, one Save, the same call as before
  await main.getByRole("checkbox", { name: "A short report after each market closes" }).uncheck();
  await main.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Alert settings saved." })).toBeVisible();
  await expect.poll(async () => (await (await request.get(`${API}/me`, { headers: auth(u) })).json()).alerts).toMatchObject({ daily_report: false });
  await expect(main.getByRole("link", { name: "Get the app" })).toHaveAttribute("href", "/app");

  // StratLab emails: tips and reminders
  const tips = main.getByRole("checkbox", { name: "Tips and reminders" });
  await expect(tips).toBeChecked();
  await tips.uncheck();
  await expect(page.getByRole("status").filter({ hasText: "Tips and reminders are off." })).toBeVisible();
  await expect.poll(async () => (await (await request.get(`${API}/me/emails`, { headers: auth(u) })).json()).tips).toBe(false);

  // newsletters: a Seg per brief, saved on each change
  const india = main.getByRole("radiogroup", { name: "Market brief: India" });
  await expect(india.getByRole("radio")).toHaveCount(3);
  await india.getByRole("radio", { name: "Weekly" }).click();
  await expect(india.getByRole("radio", { name: "Weekly" })).toHaveAttribute("aria-checked", "true");
  await expect.poll(async () => (await (await request.get(`${API}/me/newsletters`, { headers: auth(u) })).json()).market_in).toBe("weekly");
  await expect(main.getByRole("link", { name: "Read past issues" })).toHaveAttribute("href", "/news");
  await sane(page, errors, phone);
  await shot(page, "settings-notifications", phone);

  // old links still land here: the newsletters card, and the section follows the address
  await page.goto("/settings#newsletters");
  await expect(main.getByRole("heading", { name: /^Newsletters/ })).toBeInViewport({ timeout: 30_000 });
  await expect(nav.getByRole("radio", { name: "Notifications" })).toHaveAttribute("aria-checked", "true");
});

test("settings: what you see first, theme, connected accounts and the connection check", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const u = who(281, phone);
  const errors = await signIn(page, request, u, "/settings#experience");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { name: "What you see first" })).toBeVisible({ timeout: 30_000 });
  const nav = main.getByRole("radiogroup", { name: "Settings sections" });
  await expect(nav.getByRole("radio", { name: "Experience" })).toHaveAttribute("aria-checked", "true");

  // focus and experience save with the same call as before
  await main.getByRole("radiogroup", { name: "What you're here for" }).getByRole("radio", { name: "Invest" }).click();
  await expect.poll(async () => (await (await request.get(`${API}/me`, { headers: auth(u) })).json()).prefs).toMatchObject({ focus: "invest", space: "invest" });
  await main.getByRole("radiogroup", { name: "Experience" }).getByRole("radio", { name: "I do this actively" }).click();
  await expect.poll(async () => (await (await request.get(`${API}/me`, { headers: auth(u) })).json()).prefs.level).toBe("pro");
  await expect(main).toContainText("Every tool in view");

  // theme
  const theme = main.getByRole("radiogroup", { name: "Theme" });
  await theme.getByRole("radio", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await theme.getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await theme.getByRole("radio", { name: "Same as my device" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
  await sane(page, errors, phone);
  await shot(page, "settings-experience", phone);

  // connected accounts: files you upload, with when each changed; no broker login
  await nav.getByRole("radio", { name: "Connected accounts" }).click();
  await expect(page).toHaveURL(/\/settings#accounts$/);
  const cards = main.locator("#accounts");
  await expect(cards.getByRole("link", { name: /^My Holdings/ })).toHaveAttribute("href", "/holdings");
  await expect(cards.getByRole("link", { name: /^Mutual funds statement/ })).toHaveAttribute("href", "/money/mutual-funds");
  await expect(cards.getByRole("link", { name: /^Broker tradebooks/ })).toHaveAttribute("href", "/tax-report");
  await expect(cards).toContainText(/Nothing uploaded yet|updated/);
  await expect(cards).not.toContainText("Checking…", { timeout: 30_000 });
  await sane(page, errors, phone);
  await shot(page, "settings-accounts", phone);

  // connection check
  await nav.getByRole("radio", { name: "Connection check" }).click();
  await main.getByRole("button", { name: "Run check" }).click();
  for (const t of ["Signed in", "StratLab server", "Your account"]) await expect(main.locator(".k-line-text", { hasText: t }).first()).toBeVisible({ timeout: 30_000 });
  await expect(main.getByRole("button", { name: "Run check" })).toBeEnabled({ timeout: 30_000 });
  await sane(page, errors, phone);
  await shot(page, "settings-check", phone);
});

test("get the app: install and phone notifications have their own page", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const errors = await signIn(page, request, who(287, phone), "/app");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { level: 1, name: "Get the app" })).toBeVisible({ timeout: 30_000 });
  await expect(main.getByRole("heading", { name: "Install StratLab" })).toBeVisible();
  await expect(main.getByRole("heading", { name: "Notifications on this device" })).toBeVisible();
  await expect(main.getByRole("button", { name: /Turn on notifications|Send a test/ })).toBeVisible();
  await sane(page, errors, phone);
  await shot(page, "app", phone);
});

test("the alerts page points at Settings for where alerts go and what to send", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const errors = await signIn(page, request, who(245, phone), "/alerts");
  await expect(page.locator("main").getByRole("heading", { name: "Your stock alerts" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main").getByRole("link", { name: "Where alerts go and what to send" })).toHaveAttribute("href", "/settings#notifications");
  await page.locator("main").getByRole("link", { name: "Where alerts go and what to send" }).click();
  await expect(page).toHaveURL(/\/settings#notifications$/);
  await expect(page.locator("main").getByRole("heading", { name: /^Alerts/ })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("invite: the link has its own page", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const errors = await signIn(page, request, who(239, phone), "/invite");
  await expect(page.locator("main").getByLabel("Your invite link")).toHaveValue(/\/\?ref=/, { timeout: 30_000 });
  await sane(page, errors, phone);
  await shot(page, "invite", phone);
});

test("assistant: its own page, no longer a section of Account", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const errors = await signIn(page, request, who(257, phone), "/assistant");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { level: 1, name: "AI assistant" })).toBeVisible({ timeout: 30_000 });
  await expect(main).toContainText("No key can place a real order");
  await expect(main.getByRole("heading", { name: /^Your assistants/ })).toBeVisible({ timeout: 30_000 });
  await expect(main.getByRole("heading", { name: "What your assistants did" })).toBeVisible();
  await sane(page, errors, phone);
  await shot(page, "assistant", phone);
});
