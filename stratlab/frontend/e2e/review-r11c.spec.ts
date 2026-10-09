import { expect, test, type Page, type Route } from "@playwright/test";

// Round 11 review of the core strategy product (9 Oct 2026): what the app draws, on the reviewer's examples. Every answer
// a test depends on is fixed here or made through the fake world's API, so none waits on one of its jobs having run.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
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

const SMA = (fast: number, slow: number) => ({ l: { t: "sma", p: fast }, op: "xa", r: { t: "sma", p: slow } });

// ---------- R11C-001, R11C-005: answers and rule edits keep the name and the stated stop ----------
test("notebook: default answers keep the person's name and the 3% stop the words gave (R11C-001, R11C-005)", async ({ page, request }, info) => {
  const strategy = { name: "TCS SMA Crossover", tf: "1d", text: "Buy when the 20-day SMA crosses above the 50-day SMA. Stop loss 3%.",
    entry: [SMA(20, 50)], exit: [], risk: { capital: 500000, riskPct: 1, sl: 3, tgt: 0, brokerage: 20, slippage: 0.05 } };
  const name = `R test TCS SMA 20/50 ${info.project.name}`;
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name, strategy, instrument: "CRYPTO:BTC-USD" } })).json();
  await request.put(`${API}/notebooks/${nb.id}`, { headers: admin, data: { gaps: { mentioned: ["instrument"], notes: [], instName: null, usedAI: true, fallback: "" } } });
  const puts: Record<string, unknown>[] = [];
  page.on("request", (r) => { if (r.method() === "PUT" && r.url().endsWith(`/notebooks/${nb.id}`)) puts.push(r.postDataJSON()); });
  const errors = await open(page, `/n/${nb.id}`);
  const card = page.getByRole("region", { name: "Questions about your idea" });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).not.toContainText("How big a loss will you accept");          // the words said 3%
  await card.getByRole("button", { name: "Use the default answers" }).click();
  await expect(card).toContainText("Every detail is filled in.");
  await expect.poll(() => puts.some((b) => "strategy" in b), { timeout: 10_000 }).toBe(true);
  await expect.poll(async () => (await (await request.get(`${API}/notebooks/${nb.id}`, { headers: admin })).json()).strategy.risk.sl).toBe(3);
  const saved = await (await request.get(`${API}/notebooks/${nb.id}`, { headers: admin })).json();
  expect(saved.name).toBe(name);
  expect(puts.filter((b) => "name" in b)).toEqual([]);
  await expect(page.getByRole("textbox", { name: "Notebook name" })).toHaveValue(name);
  expect(errors).toEqual([]);
});

// ---------- R11C-006: a trend filter beside another condition defaults to a state ----------
test("notebook: 'price above the 200-day SMA' beside RSI under 30 defaults to any time it's above (R11C-006)", async ({ page, request }, info) => {
  const strategy = { name: "RSI dip", tf: "1d", text: "Buy when RSI 14 is below 30 and price is above the 200-day SMA",
    entry: [{ l: { t: "rsi", p: 14 }, op: "lt", r: { t: "num", v: 30 } }, { l: { t: "price" }, op: "gt", r: { t: "sma", p: 200 } }],
    exit: [{ l: { t: "rsi", p: 14 }, op: "xa", r: { t: "num", v: 55 } }], risk: { capital: 500000, riskPct: 1, sl: 2, tgt: 0, brokerage: 20, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `RSI dip ${info.project.name}`, strategy, instrument: "CRYPTO:BTC-USD" } })).json();
  await request.put(`${API}/notebooks/${nb.id}`, { headers: admin, data: { gaps: { mentioned: ["instrument", "exit", "tf", "sl", "tgt", "riskPct"], notes: [], instName: null, usedAI: true, fallback: "" } } });
  const errors = await open(page, `/n/${nb.id}`);
  const card = page.getByRole("region", { name: "Questions about your idea" });
  await expect(card).toContainText("Buy only when it first crosses above, or any time it's above?", { timeout: 30_000 });
  const dflt = card.locator(".k-starter", { has: page.getByText("Default", { exact: true }) });
  await expect(dflt).toHaveCount(1);
  await expect(dflt).toContainText("Any time it's above");
  await card.getByRole("button", { name: "Use the default answers" }).click();
  await expect.poll(async () => (await (await request.get(`${API}/notebooks/${nb.id}`, { headers: admin })).json()).strategy.entry[1].op).toBe("gt");
  expect(errors).toEqual([]);
});

// ---------- R11C-003: a long trade list says it is the newest, and adds up ----------
test("experiment: 'Every trade' says newest 200 of all and the line for the rest makes the total (R11C-003)", async ({ page, request }, info) => {
  // in every day, out the next: hundreds of trades over five years
  const strategy = { name: "Fast flips", tf: "1d", entry: [{ l: { t: "price" }, op: "gt", r: { t: "num", v: 1 } }],
    exit: [], risk: { capital: 10000, sl: 0, tgt: 0, maxBars: 1, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `Many trades ${info.project.name}`, strategy, instrument: "CRYPTO:BTC-USD" } })).json();
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 1825 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  const exp = (await run.json()).experiment;
  expect(exp.stats.n, "trades the rules made").toBeGreaterThan(200);
  const errors = await open(page, `/n/${nb.id}/e/${exp.v}`);
  const trades = page.getByRole("region", { name: "Every trade", exact: true });
  await expect(trades.getByTestId("trades-caption")).toContainText(`Newest 200 of ${exp.stats.n.toLocaleString("en-IN")} closed`, { timeout: 30_000 });
  await expect(trades.getByTestId("trades-reconcile")).toContainText("add up to the total P&L");
  await expect(trades.locator("tfoot")).toContainText(`${(exp.stats.n - 200).toLocaleString("en-IN")} earlier closed trade`);
  expect(exp.trades_omitted).toBe(exp.stats.n - 200);
  const listed = exp.trades.reduce((n: number, t: { pnl: number }) => n + t.pnl, 0);
  expect(listed + exp.omitted_pnl).toBeCloseTo(exp.stats.pnl, 0);
  expect(errors).toEqual([]);
});

// ---------- R11C-002, R11C-011: a stopped paper session keeps its position; orders by their candle ----------
test("paper: a session stopped with a position open keeps it, valued at the last price (R11C-002, R11C-011)", async ({ page }) => {
  const inst = { id: "US:AAPL", symbol: "AAPL", market: "US", currency: "USD", tz: "America/New_York", type: "EQ" };
  const strategy = { name: "R test AAPL paper 5m", tf: "5m", entry: [{ l: { t: "price" }, op: "gt", r: { t: "sma", p: 20 } }], exit: [],
    entryJoin: "all", side: "long", risk: { capital: 10000, riskPct: 1, sl: 1, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const snap = { id: "p1", name: "R test AAPL paper 5m", status: "stopped", stop_reason: "Stopped by you.", instrument: inst, strategy,
    started_at: "2026-10-09T17:30:00+00:00", stopped_at: "2026-10-09T18:10:00+00:00", last_price: 335.88,
    bars: [{ t: "2026-10-09T13:55:00-04:00", o: 335, h: 335.3, l: 334.9, c: 335.1 }, { t: "2026-10-09T14:00:00-04:00", o: 335.1, h: 335.4, l: 334.8, c: 335.18 }],
    overlays: {}, oscillators: {},
    events: [{ t: "2026-10-09T14:00:00-04:00", side: "buy", px: 335.35, qty: 29, why: "Entry rule" }],
    equity_curve: [{ t: "2026-10-09T14:05:00-04:00", eq: 10000.45 }, { t: "2026-10-09T14:10:00-04:00", eq: 10016.39 }],
    account: { capital: 10000, equity: 10016.39, cash: 275.87, qty: 29, entry: 335.35, stop: 332.0, target: null, side: "long",
      unrealised: 15.37, valued_at: 335.88, realised: 0, trades: 0, wins: 0 }, orders: [] };
  const errors = await open(page, "/paper/p1", [
    [/\/live\/sessions\/p1$/, snap],
    [/\/live\/sessions$/, [{ id: "p1", name: snap.name, instrument: inst, status: "stopped", started_at: snap.started_at }]],
  ]);
  const account = page.getByRole("list", { name: "Paper account" });
  await expect(account).toContainText("$10,016", { timeout: 30_000 });
  await expect(account).toContainText("+0.16%");
  await expect(account).toContainText("29 at $335.35");
  await expect(account).not.toContainText("−97");
  await expect(page.locator(".stopped-open")).toContainText("valued at the last price before the stop, $335.88");
  await expect(page.getByText("The chart fills in as candles close.")).toHaveCount(0);       // the chart stays
  await expect(page.locator(".order-head").first()).toContainText("14:00–14:05 candle");       // filled at the 14:05 close
  expect(errors).toEqual([]);
});

// ---------- R11C-007: USDINR from stale prices ----------
test("options: USDINR priced from last trades says so, flags an impossible fly, and keeps quarter paise (R11C-007)", async ({ page }) => {
  const q = (ltp: number) => ({ bid: null, ask: null, ltp, oi: 0, volume: 0, ts: "2026-10-09T06:00:00+00:00" });
  const leg = (side: "sell" | "buy", opt: "CE" | "PE", strike: number, fill: number) =>
    ({ side, opt, lots: 1, strike, sym: `USDINR26OCT${strike}${opt}`, quote: q(fill), fill, from_last: true });
  const base_ = { spot: 96.1, atm: 96, step: 0.25, expiry: "2026-10-16", lot: 1000, freeze: 0, units: 1, margin_one: 1200, margin: 1200,
    strikes: [94.75, 95, 95.75, 96, 96.5, 97, 97.5], tick: 0.0025, from_last: 4, charges: null, model: null, greeks: null };
  const condor = { ...base_, impossible: null, legs: [leg("sell", "CE", 96.5, 0.2), leg("sell", "PE", 95.75, 0.25), leg("buy", "CE", 97.5, 0.05), leg("buy", "PE", 94.75, 0.1)] };
  const fly = { ...base_, impossible: "These prices make money at every price at expiry: the premium taken in is more than the most the legs can pay out. Real bids and asks don't allow that, so at least one price here is out of date.",
    legs: [leg("sell", "CE", 96, 0.9), leg("sell", "PE", 96, 0.9), leg("buy", "CE", 97, 0.1), leg("buy", "PE", 95, 0.3)] };
  const UNDERLYINGS = [{ exchange: "NFO", name: "NIFTY", venue: "NSE", lot: 65, freeze: 1800, popular: true, index: true, expiries: ["2026-10-13"] },
    { exchange: "CDS", name: "USDINR", venue: "NSE currency", lot: 1000, freeze: 0, popular: true, index: false, expiries: ["2026-10-16"] }];
  let n = 0;
  const errors = await open(page, "/options", [[/\/options\/underlyings/, UNDERLYINGS], [/\/options\/preview/, async (r) => r.fulfill({ json: [condor, fly][Math.min(n++, 1)] })]]);
  await expect(page.getByRole("button", { name: "Price it now" })).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("button", { name: "Price it now" }).click();
  await expect(page.locator(".opt-stale")).toContainText("No live bid or ask: every leg is priced from its last traded price, which may be hours old.");
  await expect(page.getByTestId("opt-breakevens")).toContainText("Breaks even at 95.4500 and 96.8000");
  await expect(page.getByTestId("opt-expiry-note")).toContainText("16 Oct");
  await page.getByRole("button", { name: "Price again" }).click();
  await expect(page.locator(".opt-impossible")).toContainText("make money at every price at expiry");
  expect(errors).toEqual([]);
});

// ---------- R11C-015: a dead share link says so ----------
test("share: a link turned off says so, in the API's words (R11C-015)", async ({ page }) => {
  const errors = await open(page, "/verdict/NlpCFMRAhSA");
  await expect(page.getByText("This verdict isn't available")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("This link was turned off or never existed.")).toBeVisible();
  expect(errors).toEqual([]);
});
