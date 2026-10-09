import { expect, test, type Page, type Route } from "@playwright/test";

// Round 9 review of the broker, reliability and the US session (9 Oct 2026): what the app draws, on the reviewer's examples.
// Every answer a test depends on is fixed here (the fake world's background jobs can't change it), and the clock is a fixed
// instant: 09:33 in New York on Friday 9 Oct 2026, three minutes after the US open.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const US_OPEN = "2026-10-09T13:33:00Z";
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];

async function open(page: Page, path: string, mocks: Mock[] = [], who = { token: "admin-token", id: "u-admin", email: "owner@example.com" }, now: string | null = US_OPEN) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (now) await page.clock.setFixedTime(new Date(now));
  await page.route("**/*", async (r) => {
    const u = new URL(r.request().url());
    const call = ["fetch", "xhr"].includes(r.request().resourceType());
    for (const [re, body] of call ? mocks : []) {
      if (re.test(u.pathname + u.search)) {
        if (typeof body === "function") return (body as (r: Route) => Promise<void>)(r);
        return r.fulfill({ status: 200, body: JSON.stringify(body), contentType: "application/json" });
      }
    }
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: who.token, user: { id: who.id, aud: "authenticated", email: who.email, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(path);
  return errors;
}

const fresh = (n: number) => ({ token: `load-${n}`, id: `u-load-${n}`, email: `load${n}@example.com` });

/** The S&P 500's stored breadth, as of the 8 Oct close, with the 9 Oct count still to come (the US has no live view). */
function sp500(): Record<string, unknown> {
  const figure = (value: number) => ({ value, prev: value, change: 0 });
  const heads = ["adv", "dec", "unch", "ad_ratio", "pct20", "pct50", "pct200", "highs", "lows", "up4", "down4", "stage2", "mcclellan", "summation", "thrust", "trin", "stocks"];
  const today = Object.fromEntries(heads.map((k) => [k, figure(k === "adv" ? 281 : k === "dec" ? 218 : k === "stocks" ? 503 : 52.4)]));
  const group = { id: "sp500", name: "S&P 500", region: "US", index_name: "SPY (an S&P 500 fund)" };
  return {
    group, groups: [group], today: { day: "2026-10-08", prev_day: "2026-10-07", ...today }, as_of: "2026-10-08", since: "2024-10-01", range: "all",
    help: {}, status: null, locked: true, plan_needed: "Basic", history: null, sectors: null, thrusts: null, live: null,
    pending: { day: "2026-10-09", due: "5:45 PM ET", during: true },
  };
}

test("R9R-007: US breadth during the US session is the latest close, with when today's count comes", async ({ page }) => {
  const errors = await open(page, "/invest/breadth", [[/\/invest\/breadth\?/, sp500()]]);
  const card = page.getByTestId("breadth-today");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText("Latest close 8 Oct · today's count comes after 5:45 PM ET");
  await expect(card).not.toContainText("Today's numbers");
  expect(errors).toEqual([]);
});

test("R9R-008: the Invest home's United States tab shows the S&P 500 and US cards, and says what has no US version", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => asked.push(new URL(r.url()).pathname + new URL(r.url()).search));
  const errors = await open(page, "/invest", [[/\/invest\/breadth\?/, sp500()]]);
  await expect(page.getByText("Red flags in your holdings and watchlist")).toBeVisible({ timeout: 30_000 });   // India first
  await page.getByRole("radio", { name: "$ United States" }).click();
  const card = page.getByTestId("breadth-card");
  await expect(card).toContainText("S&P 500", { timeout: 30_000 });
  await expect(page.getByTestId("breadth-card-when")).toHaveText("Latest close 8 Oct · today's count comes after 5:45 PM ET");
  await expect(page.getByText("US results today")).toBeVisible();
  await expect(page.getByTestId("invest-us-redflags")).toContainText("none to show for US companies");
  await expect(page.getByText("Red flags in your holdings and watchlist")).toHaveCount(0);
  // the breadth card asked for a US group, and the results for the US only
  expect(asked.some((p) => /\/invest\/breadth\?group=sp500/.test(p))).toBe(true);
  expect(asked.filter((p) => /\/research\/results\?region=US/.test(p)).length).toBeGreaterThan(0);
  // and back: India's cards come back
  await page.getByRole("radio", { name: "₹ India" }).click();
  await expect(page.getByText("Red flags in your holdings and watchlist")).toBeVisible();
  await expect(page.getByTestId("invest-us-redflags")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("R9R-010: My space reads the calendars after its first screen's figures, not all at once", async ({ page }) => {
  const seen: { path: string; at: number }[] = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (["fetch", "xhr"].includes(r.resourceType())) seen.push({ path: u.pathname, at: Date.now() }); });
  const errors = await open(page, "/mine");
  await expect(page.getByTestId("mine-home")).toBeVisible({ timeout: 30_000 });
  await page.waitForRequest(/\/money\/calendar\?/, { timeout: 15_000 });
  const first = (re: RegExp) => seen.find((s) => re.test(s.path))?.at ?? Infinity;
  const worth = first(/\/money\/net-worth$/), holdings = first(/\/holdings$/), calendar = first(/\/money\/calendar$/), results = first(/\/research\/results$/);
  expect(worth).toBeLessThan(Infinity);
  expect(holdings).toBeLessThan(Infinity);
  expect(calendar - worth, "the calendar waits for the figures at the top").toBeGreaterThan(500);
  expect(results - worth, "the results wait too").toBeGreaterThan(500);
  // and they do arrive: the card fills in
  await expect(page.getByTestId("mine-coming")).toBeVisible();
  expect(errors).toEqual([]);
});

test("R9R-003: an empty funds page claims no NAV date", async ({ page }) => {
  const errors = await open(page, "/money/mutual-funds", [], fresh(272));
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/mutual funds/i, { timeout: 30_000 });
  await expect(page.getByText("Upload your statement")).toBeVisible();
  await expect(page.locator("main")).not.toContainText("NAVs up to");
  expect(errors).toEqual([]);
});

test("R9R-011: net worth says one thing about stocks in its lede and in its empty state", async ({ page }) => {
  const errors = await open(page, "/money/net-worth", [], fresh(278));
  await expect(page.getByRole("heading", { level: 1, name: "Net worth" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main .k-lede").first()).toContainText("your stocks from My Holdings and mutual funds from your statement (both added on their own)");
  await expect(page.getByText("Nothing added yet")).toBeVisible();
  await expect(page.locator("main")).toContainText("are added to the total on their own once you have some there");
  await expect(page.locator("main")).not.toContainText("are counted on their own");
  expect(errors).toEqual([]);
});
