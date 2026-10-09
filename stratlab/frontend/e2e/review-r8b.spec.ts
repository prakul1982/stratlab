import { expect, test, type Page, type Route } from "@playwright/test";

// Round 8B review of the live site at India's close (9 Oct 2026): what the app draws, on the reviewer's examples. Every
// answer a test depends on is fixed here (the fake world's background jobs can't change it), and the clock is a fixed
// instant: 19:05 IST on Friday 9 Oct 2026, after the close and before the evening's numbers.
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
const EVENING = "2026-10-09T13:35:00Z";              // 19:05 IST
const PENDING = { day: "2026-10-09", due: "18:30 IST" };
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];

async function open(page: Page, path: string, mocks: Mock[] = [], now: string | null = EVENING) {
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
  const session = { ...base, access_token: "admin-token", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(path);
  return errors;
}

/** The fake world's own answer for a request, changed by `edit`. */
const edited = (edit: (j: Record<string, any>) => Record<string, any>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};
const lastDay = (j: Record<string, any>) => ({ ...j, live: null, pending: PENDING, as_of: "2026-10-08",
  today: j.today ? { ...j.today, day: "2026-10-08" } : j.today });

// ---------- R8B-002: the paper overview's worst day and deepest fall ----------
test("the paper overview gives the worst day and the deepest fall from the whole run (R8B-002)", async ({ page }) => {
  const overview = { currencies: [{ currency: "INR", sessions: 1, capital: 5000000, equity: 4831323, pnl: -168677, today: 42608, open_value: 0,
    worst_day: { date: "2026-10-05", pnl: -101891 }, best_day: { date: "2026-10-09", pnl: 42608 }, max_drawdown_pct: -5.41,
    deepest_fall: { pnl: -270494, pct: -5.41, date: "2026-10-09" },
    curve: [{ t: "2026-10-05", pnl: -101891 }, { t: "2026-10-08", pnl: -211285 }, { t: "2026-10-09", pnl: -168677 }] }],
    sessions: [{ id: "s1", name: "Iron fly", kind: "options", currency: "INR", open_value: 0, today: 42608, pnl: -168677, capital: 5000000 }] };
  const running = [{ id: "s1", name: "Iron fly", status: "running", started_at: "2026-10-05T03:50:00+00:00", stopped_at: null, stop_reason: null,
    instrument: { id: "NSE:NIFTY 50", symbol: "NIFTY 50", exchange: "NSE", market: "IN", currency: "INR", type: "INDEX" } }];
  const errors = await open(page, "/paper", [[/\/live\/overview$/, overview], [/\/live\/sessions$/, running]]);
  const strip = page.getByRole("list", { name: "Totals in INR" });
  await expect(strip).toContainText("Worst day", { timeout: 30_000 });
  await expect(strip).toContainText("5 Oct");
  await expect(strip).toContainText("−5.4%");
  await expect(strip).toContainText(/2,70,494 from the high point, 9 Oct/);
  expect(errors).toEqual([]);
});

// ---------- R8B-005: the PCR table says how many strikes it read ----------
test("the PCR table has a Strikes read column, not an All strikes read one that repeats the PCR (R8B-005)", async ({ page }) => {
  const pcr = [{ name: "NIFTY", exchange: "NFO", expiry: "2026-10-13", cycle: "weekly", pcr_oi: 1.09, pcr_vol: 0.97, pcr_near: 1.09, pcr_all: 1.09,
    strikes_read: 31, near_strikes: 15, spot: 22520.45, source: "live", at_close: true, as_of: "2026-10-09T15:41:00+05:30" }];
  const errors = await open(page, "/trade/positioning", [[/\/trade\/positioning\/pcr$/, { pcr }]]);
  const table = page.locator("#pos-pcr");
  await expect(table.getByRole("columnheader", { name: "Strikes read" })).toBeVisible({ timeout: 30_000 });
  await expect(table.getByRole("columnheader", { name: "All strikes read" })).toHaveCount(0);
  await expect(table.locator("tbody tr").first()).toContainText("31");
  expect(errors).toEqual([]);
});

// ---------- R8B-007: the facts line first, the AI's words under it ----------
test("a brief's page opens with the facts line and has the AI's words under it (R8B-007)", async ({ page }) => {
  const issue = { id: "market.IN.2026-10-09", kind: "market", region: "IN", day: "2026-10-09", weekly: false,
    subject: "Market Brief India, Fri 9 Oct: NIFTY 50 +1.30%", summary: "NIFTY 50 +1.30%; SENSEX +1.23%; NIFTY BANK +1.36% today.",
    ai_summary: "The NIFTY 50 closed at 22,520.45, up 1.30%.", sections: [], html: "", at: "2026-10-09T16:19+05:30" };
  const errors = await open(page, "/news?tab=IN&issue=market.IN.2026-10-09", [
    [/\/news\/market\.IN\.2026-10-09$/, issue],
    [/\/news\?kind=market/, { issues: [{ id: issue.id, kind: "market", region: "IN", day: issue.day, weekly: false, subject: issue.subject, preview: issue.summary }] }],
  ]);
  const ai = page.getByTestId("news-ai-summary");
  await expect(ai).toHaveText("The NIFTY 50 closed at 22,520.45, up 1.30%.", { timeout: 30_000 });
  await expect(page.locator(".news-issue .k-lede")).toHaveText(issue.summary);
  expect(errors).toEqual([]);
});

// ---------- R8B-008: "Latest: 8 Oct · 9 Oct due about 18:30 IST" ----------
test("breadth on the evening of 9 Oct says the newest day and when 9 Oct's is due, never 'Today's numbers · 8 Oct' (R8B-008)", async ({ page }) => {
  const errors = await open(page, "/invest/breadth", [[/\/invest\/breadth\?/, edited(lastDay)]]);
  const card = page.getByTestId("breadth-today");
  await expect(card).toContainText("Latest: 8 Oct · 9 Oct due about 18:30 IST", { timeout: 30_000 });
  await expect(card).not.toContainText("Today's numbers");
  expect(errors).toEqual([]);
});

test("the Invest card and the screener say it too (R8B-008)", async ({ page }) => {
  const errors = await open(page, "/invest", [[/\/invest\/breadth\?/, edited(lastDay)]]);
  await expect(page.getByTestId("breadth-card-when")).toHaveText("Latest: 8 Oct · 9 Oct due about 18:30 IST", { timeout: 30_000 });
  await page.goto("/research/screens");
  await page.route(/\/research\/screens\/run$/, edited((j) => ({ ...j, as_of: "2026-10-08", as_of_newest: "2026-10-08", pending: PENDING })));
  await page.reload();
  await expect(page.getByTestId("screens-pending")).toHaveText("Latest: 8 Oct · 9 Oct due about 18:30 IST", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

// ---------- R8B-010: the closing auction on a phone ----------
test("at 400 px the closing auction shows each stock's final price and gap without scrolling sideways (R8B-010)", async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 860 });
  const errors = await open(page, "/trade/closing-auction", [], null);
  const stocks = page.getByRole("region", { name: /F&O stocks/ });
  const head = stocks.locator("thead th");
  await expect(head.nth(0)).toHaveText("Stock", { timeout: 30_000 });
  await expect(head.nth(1)).toHaveText(/Final price|IEP/);
  await expect(head.nth(2)).toHaveText("Gap to reference");
  const box = await head.nth(2).boundingBox();
  expect(box && box.x + box.width).toBeLessThanOrEqual(400);
  expect(errors).toEqual([]);
});
