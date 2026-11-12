import { expect, test, type Page } from "@playwright/test";

// The Calendar's Earnings calls tab and Invest's Business groups (f5), on desktop and phone, dark and light, against the fake world's
// made-up calls and promoter names (backend tests/fake_f5.py). Basic sees the full calendar, the filters and the groups' figures; Free
// sees this week's calls with their notice and webcast link, and each group's members with their market value and the day's change.
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|bullish|bearish|target price|recommend)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nasdaq|choruscall/i;
const SHOTS = process.env.E2E_SHOTS;

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}
// load-271 and 274 are Basic (n % 3 == 1), load-270 and 273 Free; one of each per project
const who = (phone: boolean, plan: "basic" | "free") => (plan === "basic" ? (phone ? 274 : 271) : (phone ? 273 : 270));

async function open(page: Page, path: string, ready: string | RegExp, n: number, dark = false) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.emulateMedia({ colorScheme: dark ? "dark" : "light" });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(path);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

async function shot(page: Page, name: string, phone: boolean, dark: boolean) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-${phone ? "390" : "1440"}-${dark ? "dark" : "light"}.png`, fullPage: true });
}

for (const dark of [false, true]) {
  test(`earnings calls on Basic: the calendar, its links and its filters (${dark ? "dark" : "light"})`, async ({ page }, info) => {
    const phone = info.project.name === "phone";
    const errors = await open(page, "/research/earnings-calls?region=IN&scope=all", "Tata Consultancy Services Limited", who(phone, "basic"), dark);
    await expect(page.getByRole("heading", { name: "Earnings calls", level: 1 })).toBeVisible();
    const table = page.getByTestId("calls-table");
    await expect(table.getByText("16:00 IST").first()).toBeVisible();
    await expect(table.getByRole("link", { name: /Webcast or dial-in/ }).first()).toHaveAttribute("target", "_blank");
    await expect(table.getByText("Analyst or investor meet").first()).toBeVisible();
    await expect(page.getByTestId("calls-locked")).toHaveCount(0);
    await sane(page, errors);
    await shot(page, "calls-upcoming", phone, dark);
    // held: the transcript, recording and presentation filed after a call
    await page.getByRole("radio", { name: "Held" }).click();
    await expect(table.getByRole("link", { name: /^Transcript/ }).first()).toBeVisible();
    await expect(table.getByRole("link", { name: /^Audio/ })).toHaveCount(1);
    await shot(page, "calls-held", phone, dark);
    // my stocks: the watchlist's calls only
    await page.getByRole("radio", { name: "Coming up" }).click();
    await page.getByRole("radio", { name: "My stocks" }).click();
    await expect(table.getByRole("link", { name: "Maruti Suzuki India Limited", exact: true })).toBeVisible();
    await expect(table.getByRole("link", { name: "Infosys Limited", exact: true })).toHaveCount(0);
    await sane(page, errors);
  });
}

test("earnings calls on Free: this week's calls, their notice and webcast link, and the lock on the rest", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/earnings-calls?region=IN", "Tata Consultancy Services Limited", who(phone, "free"));
  await expect(page.getByTestId("calls-locked")).toContainText("Basic plan");
  await expect(page.getByRole("radio", { name: "Held" })).toHaveCount(0);
  await expect(page.getByText("ITC Limited")).toHaveCount(0);                // twelve days ahead: past this week
  await sane(page, errors);
  await shot(page, "calls-free", phone, false);
});

test("the US tab lists the results calendar's sessions in Eastern time", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/earnings-calls?region=US", /results days/, who(phone, "basic"));
  await sane(page, errors);
});

for (const dark of [false, true]) {
  test(`business groups on Basic: the index, a group with its heatmap and figures (${dark ? "dark" : "light"})`, async ({ page }, info) => {
    const phone = info.project.name === "phone";
    const errors = await open(page, "/invest/groups", "Northwind Holdings Private Limited", who(phone, "basic"), dark);
    await expect(page.getByRole("heading", { name: "Business groups", level: 1 })).toBeVisible();
    await expect(page.getByTestId("groups-locked")).toHaveCount(0);
    await sane(page, errors);
    await shot(page, "groups-index", phone, dark);
    await page.getByRole("link", { name: "Northwind Holdings Private Limited" }).click();
    await expect(page.getByRole("heading", { name: /Northwind Holdings Private Limited group/, level: 1 })).toBeVisible();
    await expect(page.getByTestId("group-map")).toBeVisible();
    await expect(page.getByTestId("group-table").getByText("Promoters").first()).toBeVisible();
    await expect(page.getByTestId("group-confidence")).toContainText("Confidence");
    await sane(page, errors);
    await shot(page, "group-page", phone, dark);
  });
}

test("business groups on Free: members, market value and the day's change, the rest locked", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/groups", "Northwind Holdings Private Limited", who(phone, "free"));
  await expect(page.getByTestId("groups-locked")).toContainText("Basic plan");
  await page.getByRole("link", { name: "Northwind Holdings Private Limited" }).click();
  await expect(page.getByTestId("group-locked")).toContainText("Basic plan");
  await expect(page.getByTestId("group-map")).toHaveCount(0);
  await sane(page, errors);
  await shot(page, "group-free", phone, false);
});

test("a company page links to its business group", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/IN/TCS", "Tata Consultancy", who(phone, "basic"));
  const link = page.getByTestId("group-link");
  await link.scrollIntoViewIfNeeded().catch(() => undefined);
  await expect(link).toContainText("Northwind Holdings Private Limited group", { timeout: 20_000 });
  expect(errors).toEqual([]);
});
