import { expect, test, type Page } from "@playwright/test";

// Market events (Trade space): the dated list from the official calendars (the fake world's, made up around today: an
// MPC decision in three days, a Fed decision in 23, US CPI in nine, India CPI out three weeks ago with its figure, and
// index changes in a week with RELIANCE going into the Nifty 100), its filters, the reminder settings, sending the
// events to the Money calendar, the index badge on a company page and the line on the Invest home. Each project signs in
// as its own Basic account.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, where: string, ready: string, who: ReturnType<typeof sessionFor>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(where);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(where);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /nseindia|niftyindices|mospi|rbi\.org|yahoo|finnhub|kite connect/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(you should|buy|sell|accumulate|avoid|expected to|bullish|bearish)\b/i);
}

test("Market events: the dated list, filters, reminders, the Money calendar and an index badge", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 244 : 241;                   // Basic accounts in the fake world
  const who = sessionFor(n);
  const auth = { Authorization: `Bearer load-${n}` };
  await request.put(`${API}/me/prefs`, { headers: auth, data: { level: "some", focus: "both" } });     // no welcome questions
  expect((await request.put(`${API}/trade/events/prefs`, { headers: auth, data: { remind: false, money_calendar: false } })).ok()).toBeTruthy();

  const errors = await open(page, "/trade/events", "Every event", who);
  await expect(page.getByRole("heading", { name: "Market events", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Where this comes from" }).click();
  await expect(page.getByTestId("ev-asof")).toContainText(/Central bank \(MPC\) as of .*Index provider as of/);
  await page.keyboard.press("Escape");
  const week = page.getByTestId("ev-week");
  await expect(week.getByText("RBI policy decision (MPC)")).toBeVisible();
  await expect(week.getByText(/US consumer prices \(CPI\)/)).toHaveCount(0);      // nine days out
  // the month calendar: a dot for each kind, a day with the MPC decision lists it, and the keyboard moves between days
  const cal = page.getByRole("group", { name: "Market events", exact: true });
  const mpc = cal.getByRole("button", { name: /RBI policy decision \(MPC\)/ });
  if (!(await mpc.count())) await cal.getByRole("button", { name: "Next month" }).click();
  await expect(mpc.first()).toBeVisible();
  await expect(cal.getByRole("list", { name: "What the dots mean" })).toContainText("RBI");
  await mpc.first().click();
  await expect(cal.locator(".k-cal-panel")).toContainText("RBI policy decision (MPC)");
  await mpc.first().focus();
  await page.keyboard.press("ArrowRight");
  await expect(cal.locator(".k-cal-cell:focus")).toHaveCount(1);
  await expect(cal.locator(".k-cal-cell:focus")).not.toHaveAttribute("aria-label", /RBI policy decision/);

  // the list view: the figure of a past release
  await cal.getByRole("radio", { name: "List" }).click();
  await expect(page.getByTestId("ev-figure").filter({ hasText: "CPI inflation 4.82%" }).first()).toBeVisible();
  await expect(page.getByText("The month before: 4.45%").first()).toBeVisible();

  // filters
  await page.getByRole("group", { name: "Kind of event" }).getByRole("button", { name: "US Fed and data" }).click();
  await expect(page.locator(".ev-row[data-kind=rbi]")).toHaveCount(0);
  await expect(page.getByText("US Fed decision (FOMC)").first()).toBeVisible();
  await page.getByRole("group", { name: "Kind of event" }).getByRole("button", { name: "All" }).click();

  // index changes: the table and the badge
  const change = page.getByTestId("ev-index-change").first();
  await expect(change.getByRole("rowheader", { name: "Nifty 100" })).toBeVisible();
  await expect(change.getByRole("link", { name: "RELIANCE" })).toBeVisible();
  await sane(page, errors);

  // reminders (Basic) and the Money calendar
  const remind = page.getByRole("region", { name: "Reminders and your calendar" });
  await remind.getByLabel("Remind me of the events I pick").click();       // saved first, then ticked
  await expect(remind.getByLabel("Remind me of the events I pick")).toBeChecked();
  await expect(remind.getByLabel("When to remind")).toBeVisible();
  await remind.getByLabel(/Also show the kinds I picked/).click();
  await expect(remind.getByLabel(/Also show the kinds I picked/)).toBeChecked();
  await expect.poll(async () => (await (await request.get(`${API}/trade/events`, { headers: auth })).json()).prefs).toMatchObject({ remind: true, money_calendar: true });

  await page.goto("/money/calendar");
  await expect(page.getByTestId("mc-market")).toContainText("are in this calendar");
  await expect(page.getByText("RBI policy decision (MPC)").first()).toBeVisible({ timeout: 20_000 });

  await page.goto("/research/IN/RELIANCE");
  await expect(page.locator("[data-index-badges=RELIANCE]").getByText(/Joins NIFTY 100 from/)).toBeVisible({ timeout: 30_000 });

  await page.goto("/invest");
  await expect(page.getByTestId("invest-events").getByText("RBI policy decision (MPC)")).toBeVisible({ timeout: 20_000 });
  await sane(page, errors);
  await page.screenshot({ path: `test-results/market-events-${info.project.name}.png`, fullPage: true });
});

test("Market events in dark mode", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 246 : 243;
  await request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer load-${n}` }, data: { level: "some", focus: "both" } });
  await page.emulateMedia({ colorScheme: "dark" });
  const errors = await open(page, "/trade/events", "Every event", sessionFor(n));
  await expect(page.getByRole("region", { name: "Reminders and your calendar" })).toBeVisible();
  // the figure and the tags stay readable: their text colour differs from the card behind them
  await page.getByRole("radio", { name: "List" }).click();
  const [fg, bg] = await page.locator(".k-cal-kind").first().evaluate((el) => [getComputedStyle(el).color, getComputedStyle(el.closest(".k-card")!).backgroundColor]);
  expect(fg).not.toBe(bg);
  await sane(page, errors);
  await page.screenshot({ path: `test-results/market-events-dark-${info.project.name}.png`, fullPage: true });
});
