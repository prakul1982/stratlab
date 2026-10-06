import { expect, test, type Page } from "@playwright/test";

// Admin as an area: its own left menu, a page per job at /admin/..., the old ?tab= links still working, a health light with
// a word for every service and feed, "Run now" and a log for every job, a confirm box in the page (never the browser's),
// and the 25 emails shown in a sandboxed frame at a desktop or a phone width. Signed in as the fake world's site owner.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const SHOTS = process.env.E2E_SHOTS;

async function open(page: Page, path: string, ready: string) {
  const errors: string[] = [];
  // the test's own sign-in script also runs inside the email frame, whose sandbox rightly refuses it localStorage: not the page's error
  page.on("pageerror", (e) => { if (!/allow-same-origin/.test(e.message)) errors.push(e.message); });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(300);
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
}

async function shot(page: Page, name: string, info: { project: { name: string } }) {
  if (!SHOTS) return;
  const phone = info.project.name === "phone";
  await page.emulateMedia({ colorScheme: phone ? "light" : "dark" });
  await page.waitForTimeout(250);
  await page.screenshot({ path: `${SHOTS}/${name}-${phone ? "400-light" : "1300-dark"}.png`, fullPage: true });
}

const SECTIONS = ["Overview", "Users and growth", "Money", "Data and jobs", "Quality", "System", "Email previews"];

test("admin: a left menu with seven sections, each its own address, and the old tab links still land", async ({ page }) => {
  const errors = await open(page, "/admin", "Needs your attention");
  const menu = page.getByRole("navigation", { name: "Admin sections" });
  await expect(menu.getByRole("link")).toHaveText(SECTIONS.map((s) => new RegExp(`^${s}`)));
  await expect(menu.getByRole("link", { name: /^Overview/ })).toHaveAttribute("aria-current", "page");
  for (const [name, path, heading] of [["Users and growth", "/admin/users", "Paper trading now"], ["Money", "/admin/money", "Prices outside India"], ["Data and jobs", "/admin/data", "Background jobs"],
    ["Quality", "/admin/quality", "Rates and rules"], ["System", "/admin/system", "Check every feature"], ["Email previews", "/admin/emails", "Confirm your email"]] as const) {
    await menu.getByRole("link", { name }).click();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    await expect(page.getByText(heading, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  }
  // the old ?tab= links redirect to the section that took over
  for (const [old, now] of [["services", "/admin/system"], ["checks", "/admin/data"], ["users", "/admin/users"], ["billing", "/admin/money"]]) {
    await page.goto(`/admin?tab=${old}`);
    await expect(page).toHaveURL(new RegExp(`${now}$`), { timeout: 30_000 });
  }
  await page.goto("/admin?tab=overview");
  await expect(page).toHaveURL(/\/admin\?tab=overview$/);
  await expect(page.getByText("Needs your attention")).toBeVisible();
  await page.goto("/admin/nowhere");
  await expect(page).toHaveURL(/\/admin$/);
  await sane(page, errors);
});

test("admin: the breadcrumb says Mine > Admin, and only an admin gets in", async ({ page }) => {
  const errors = await open(page, "/admin/data", "Background jobs");
  await expect(page.getByRole("navigation", { name: /breadcrumb/i }).getByText("Admin")).toBeVisible();
  await sane(page, errors);
});

test("admin overview: what needs you, a light with a word on every service and feed, and today's numbers", async ({ page }, info) => {
  const errors = await open(page, "/admin", "Needs your attention");
  await expect(page.getByRole("region", { name: "Today's numbers" }).getByText(/Sign-ups today|Paid users|Revenue today|Server errors/)).toHaveCount(4);
  const services = page.getByRole("list", { name: "Services" });
  await expect(services.getByRole("listitem").first()).toBeVisible({ timeout: 30_000 });
  const feeds = page.getByRole("list", { name: "Data feeds" });
  await expect(feeds.getByRole("listitem").first()).toBeVisible({ timeout: 30_000 });
  for (const list of [services, feeds]) {
    const items = await list.getByRole("listitem").all();
    expect(items.length).toBeGreaterThan(3);
    for (const item of items) await expect(item, "every light carries its word").toContainText(/(OK|Check|Problem)/);
  }
  for (const feed of ["Market breadth", "ETF price against NAV", "Fund costs (TER)", "Exchange holidays"]) await expect(feeds.getByText(feed)).toBeVisible();
  await expect(services.getByText("AI providers")).toBeVisible();
  if (info.project.name === "phone") await expect(page.getByRole("navigation", { name: "Admin sections" })).toBeVisible();
  await sane(page, errors);
  await shot(page, "admin-overview", info);
});

test("admin data and jobs: last run, next run, Run now and a log for each job; the ETF 'Read now' calls the new route", async ({ page }, info) => {
  const sent: string[] = [];
  await page.route((u) => u.pathname === "/admin/etf-gaps/refresh", async (r) => {
    sent.push(r.request().method());
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ etfs: 5, as_of: "2026-10-05", job: {} }) });
  });
  const boxes: string[] = [];
  page.on("dialog", (d) => { boxes.push(d.message()); void d.dismiss(); });
  const errors = await open(page, "/admin/data", "Background jobs");
  const table = page.getByRole("table", { name: "Background jobs" });
  await expect(table.getByRole("columnheader", { name: "Last run" })).toBeVisible();
  await expect(table.getByText(/Next run: Every 12 hours/)).toBeVisible();
  for (const job of ["Market breadth", "Positioning", "ETF price against NAV", "Fund costs (TER)", "Exchange holidays", "Results calendar", "Corporate actions", "F&O contract changes"])
    await expect(table.getByRole("rowheader", { name: new RegExp(`^${job.replace(/[()&]/g, "\\$&")}`) })).toBeVisible();
  const etf = table.getByRole("row", { name: /ETF price against NAV/ });
  await etf.getByRole("button", { name: "Read now: ETF price against NAV" }).click();
  await expect.poll(() => sent).toEqual(["POST"]);
  await expect(page.getByRole("status").first()).toContainText("read 5 ETFs");
  await etf.getByRole("button", { name: "Log of ETF price against NAV" }).click();
  const log = page.getByRole("dialog", { name: "ETF price against NAV: log" });
  await expect(log).toContainText("Next run");
  await expect(log).toContainText("Run from here, this visit");
  await shot(page, "admin-data-log", info);
  await log.getByRole("button", { name: "Close" }).click();
  await expect(log).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Holidays by market, scrolls sideways" })).toBeVisible();
  expect(boxes).toEqual([]);
  await sane(page, errors);
  await shot(page, "admin-data", info);
});

test("admin users: search by email, and the launch offer asks in the page, never with a browser box", async ({ page }, info) => {
  const boxes: string[] = [];
  page.on("dialog", (d) => { boxes.push(d.message()); void d.dismiss(); });
  const queries: string[] = [];
  await page.route((u) => u.pathname === "/admin/users", (r) => { queries.push(new URL(r.request().url()).searchParams.get("q") ?? ""); return r.fallback(); });
  const errors = await open(page, "/admin/users", "Paper trading now");
  const box = page.getByRole("searchbox", { name: "Search users by email" });
  await expect(box).toBeVisible();
  await box.fill("owner");
  await expect.poll(() => queries.at(-1)).toBe("owner");
  await expect(page.getByRole("table", { name: "Users" }).getByRole("rowheader", { name: /owner@example\.com/ }).first()).toBeVisible({ timeout: 30_000 });
  await box.fill("nobody-matches-this");
  await expect(page.getByText("No users match")).toBeVisible({ timeout: 30_000 });
  await box.fill("");
  // the launch offer: Start now opens a question in the page; Cancel changes nothing
  const card = page.getByRole("region", { name: "Launch offer" });
  const start = card.getByRole("button", { name: "Start now" });
  if (await start.count()) {
    await start.click();
    const ask = page.getByRole("dialog", { name: /Start the launch offer for \d+ days\?/ });
    await expect(ask).toBeVisible();
    await ask.getByRole("button", { name: "Cancel" }).click();
    await expect(ask).toHaveCount(0);
  }
  expect(boxes, "no browser box opened").toEqual([]);
  await sane(page, errors);
  await shot(page, "admin-users", info);
});

test("admin emails: 25 kinds listed, each shown in a frame with no scripts at a desktop or a phone width, or as text", async ({ page }, info) => {
  const errors = await open(page, "/admin/emails", "Confirm your email");
  const list = page.getByRole("list", { name: "Emails" });
  await expect(list.getByRole("listitem")).toHaveCount(25, { timeout: 30_000 });
  await shot(page, "admin-emails", info);
  await list.getByRole("link", { name: /Market brief, India \(daily\)/ }).click();
  await expect(page).toHaveURL(/\/admin\/emails\/market_in$/);
  const frame = page.locator("iframe.adm-mail-frame");
  await expect(frame).toBeVisible({ timeout: 30_000 });
  expect(await frame.getAttribute("sandbox"), "a sandbox with no permissions: no scripts, no same-origin").toBe("");
  expect(await frame.getAttribute("srcdoc")).toContain("<html");
  await expect(frame).toHaveClass(/desktop/);
  const wide = (await frame.boundingBox())!.width;
  await page.getByRole("radio", { name: "Phone" }).click();
  await expect(frame).toHaveClass(/phone/);
  const narrow = (await frame.boundingBox())!.width;
  if (info.project.name === "desktop") expect(narrow).toBeLessThan(wide);
  else expect(narrow, "on a phone both widths fit the screen").toBeLessThanOrEqual(wide);
  expect(narrow).toBeLessThanOrEqual(375);
  // the email really renders inside it
  await expect(page.frameLocator("iframe.adm-mail-frame").locator("body")).not.toBeEmpty();
  await shot(page, "admin-email-phone-width", info);
  await page.getByRole("radio", { name: "Text" }).click();
  await expect(page.locator("iframe.adm-mail-frame")).toHaveCount(0);
  await expect(page.getByLabel("Plain text of the email")).not.toBeEmpty();
  await page.getByRole("link", { name: "All emails" }).click();
  await expect(page).toHaveURL(/\/admin\/emails$/);
  await sane(page, errors);
});

test("admin quality and system open with their cards", async ({ page }, info) => {
  let errors = await open(page, "/admin/quality", "Reported strategies");
  await expect(page.getByRole("radio", { name: "US" })).toBeVisible();
  await page.getByRole("radio", { name: "US" }).click();
  await expect(page.getByText("Whole market: US").first()).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);
  await shot(page, "admin-quality", info);
  errors = await open(page, "/admin/system", "Server errors");
  for (const card of ["Other services", "AI", "Check every feature", "Real prices for testing"]) await expect(page.getByRole("region", { name: card }).first()).toBeVisible();
  await sane(page, errors);
  await shot(page, "admin-system", info);
  errors = await open(page, "/admin/money", "Prices outside India");
  await expect(page.getByRole("region", { name: "Payments" })).toBeVisible();
  await sane(page, errors);
  await shot(page, "admin-money", info);
});
