import { expect, test, type Page, type Route } from "@playwright/test";

// Round 13 review: the US close and the US brief, watched live on Fri 9 Oct 2026. What the app draws, on the reviewer's
// examples. Every answer a test depends on is fixed here, or the fake world's own answer edited, so none waits on a job.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];

async function open(page: Page, where: string, mocks: Mock[] = []) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
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
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(where);
  return errors;
}

const edited = (edit: (j: Record<string, any>) => Record<string, any>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};

// ---------- R13-004: the US tab opens the US brief ----------
test("briefs: switching to the US tab before the day's US issue exists opens the latest US brief, highlighted (R13-004)", async ({ page }, info) => {
  test.skip(info.project.name.includes("mobile") || (page.viewportSize()?.width ?? 1280) < 901, "the reading pane sits beside the list on a wide screen");
  const india = { id: "market.IN.2026-10-09", kind: "market", region: "IN", day: "2026-10-09", weekly: false,
    subject: "Market Brief India, Fri 9 Oct: NIFTY 50 +1.30%", summary: "NIFTY 50 +1.30% today.", sections: [], html: "", at: "2026-10-09T16:19+05:30" };
  const us = { id: "market.US.2026-10-08", kind: "market", region: "US", day: "2026-10-08", weekly: false,
    subject: "Market Brief US, Thu 8 Oct: S&P 500 −0.47%", summary: "S&P 500 −0.47% today.", sections: [], html: "", at: "2026-10-08T16:34-04:00" };
  const row = (i: typeof india) => ({ id: i.id, kind: "market", region: i.region, day: i.day, weekly: false, subject: i.subject, preview: i.summary });
  const errors = await open(page, "/news?tab=IN&issue=market.IN.2026-10-09", [
    [/\/news\/market\.IN\.2026-10-09$/, india], [/\/news\/market\.US\.2026-10-08$/, us],
    [/\/news\?kind=market&region=IN/, { issues: [row(india)] }], [/\/news\?kind=market&region=US/, { issues: [row(us)] }],
  ]);
  const pane = page.locator(".news-issue");
  await expect(pane).toContainText("Market brief · India", { timeout: 30_000 });
  await page.getByRole("radio", { name: "Market brief: US" }).or(page.getByRole("button", { name: "Market brief: US" })).first().click();
  await expect(pane).toContainText("Market brief · US", { timeout: 15_000 });
  await expect(pane).not.toContainText("India");
  await expect(page.getByRole("button", { name: /Market Brief US, Thu 8 Oct/ })).toHaveAttribute("aria-current", "true");
  // the stamp is the close the numbers are of (R13-003), never the time the issue was built
  await expect(page.getByTestId("news-stamp")).toHaveText("Prices and numbers as of the 16:00 ET close of 8 Oct 2026");
  expect(errors).toEqual([]);
});

// ---------- R13-002: no live quote, no price ----------
test("options: USDINR with no bid, no ask and nothing traded says 'No live quote' and isn't priced (R13-002)", async ({ page }) => {
  const q = { bid: null, ask: null, ltp: 1.1025, oi: 0, volume: 0, ts: "2026-10-09T16:50:49" };
  const leg = (opt: "CE" | "PE") => ({ side: "sell", opt, lots: 1, strike: 96.75, sym: `USDINR26O1696.75${opt}`, quote: q, fill: null, no_live: true, rule: "at the money", pick: null });
  const preview = { spot: 96.76, atm: 96.75, step: 0.125, expiry: "2026-10-16", lot: 1000, freeze: 0, units: 1, margin_one: 1689.13, margin: 1689.13,
    strikes: [96.5, 96.625, 96.75, 96.875, 97], tick: 0.0025, from_last: 0, spot_from: "spot", no_live: 2, impossible: null, charges: null, model: null, greeks: null,
    no_live_text: "No live quote: USDINR's options on NSE currency have no bid or ask and nothing traded today, so the last prices shown can be weeks old. The structure isn't priced until there is a live quote.",
    legs: [leg("CE"), leg("PE")] };
  const UNDERLYINGS = [{ exchange: "CDS", name: "USDINR", venue: "NSE currency", lot: 1000, freeze: 0, popular: true, index: false, expiries: ["2026-10-16"] },
    { exchange: "NFO", name: "NIFTY", venue: "NSE", lot: 65, freeze: 1800, popular: true, index: true, expiries: ["2026-10-13"] }];
  const errors = await open(page, "/options", [[/\/options\/underlyings/, UNDERLYINGS], [/\/options\/preview/, preview]]);
  await expect(page.getByRole("button", { name: "Price it now" })).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("radio", { name: "USDINR", exact: true }).or(page.getByRole("button", { name: "USDINR", exact: true })).first().click();
  await page.getByRole("button", { name: "Price it now" }).click();
  await expect(page.locator(".opt-no-live")).toContainText("No live quote");
  await expect(page.getByTestId("opt-spot-line")).toContainText("USDINR ₹96.7600 (the spot rate: the future has no live quote)");
  await expect(page.getByTestId("payoff-chart")).toHaveCount(0);
  await expect(page.getByText("no live quote", { exact: true })).toHaveCount(2);          // each leg's "Fill now"
  expect(errors).toEqual([]);
});

// ---------- R13-001: BRK.B's page is BRK-B's ----------
test("company: /research/US/BRK.B moves to BRK-B and asks only for BRK-B (R13-001)", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/research/company/US/")) asked.push(decodeURIComponent(u.pathname)); });
  const errors = await open(page, "/research/US/BRK.B");
  await expect(page).toHaveURL(/\/research\/US\/BRK-B$/, { timeout: 30_000 });
  await expect.poll(() => asked.length, { timeout: 15_000 }).toBeGreaterThan(0);
  expect(asked.every((p) => p.startsWith("/research/company/US/BRK-B")), asked.join(", ")).toBe(true);
  expect(errors).toEqual([]);
});

// ---------- R13-009: a revised day is said ----------
test("breadth: an earlier day the latest run changed says so beside the numbers (R13-009)", async ({ page }) => {
  const errors = await open(page, "/invest/breadth", [[/\/invest\/breadth\?/, edited((j) => ({ ...j, live: null, pending: null,
    revised: [{ day: j.today?.prev_day ?? "2026-10-08", before: { adv: 337, dec: 163, unch: 1 }, after: { adv: 338, dec: 163, unch: 1 } }] }))]]);
  // one short line in the headline card, the details behind its (i) (DE-023)
  const note = page.getByTestId("breadth-revised");
  await expect(note).toContainText("An earlier day's count was revised", { timeout: 30_000 });
  await note.getByRole("button", { name: "About the revision" }).click();
  await expect(note).toContainText("revised: 338 rose, 163 fell, 1 unchanged (was 337, 163, 1)");
  expect(errors).toEqual([]);
});
