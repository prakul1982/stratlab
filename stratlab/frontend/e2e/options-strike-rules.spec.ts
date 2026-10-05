import { expect, test, type Page } from "@playwright/test";

// Picking option strikes by rule (closest delta, a delta range, premium, a share of the ATM straddle) in the Options
// builder, and the India VIX entry filter; then a session's page with the rule's reason in the order log and the lines
// the VIX filter left. The live option feed is offline in the fake world, so the underlyings, the priced preview and the
// session are served here, in the server's shapes (backend/tests/test_strike_rules.py checks the server's side).
const SHOTS = process.env.SHOTS_DIR ?? "test-results";
const ADVICE = /\b(recommend|should (?:buy|sell)|best strike|good trade|probability of profit)\b/i;
const sessionAs = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });

const LOT = 65;
const quote = (mid: number) => ({ bid: +(mid - 0.25).toFixed(2), ask: +(mid + 0.25).toFixed(2), ltp: mid, oi: 120000, ts: "2026-10-05T05:12:00+00:00" });
const PREVIEW = {
  spot: 25010, atm: 25000, step: 50, expiry: "2026-10-08", expiries: ["2026-10-08", "2026-10-13"], lot: LOT, freeze: 1800, units: 1,
  margin_one: 98000, margin: 98000, strikes: Array.from({ length: 41 }, (_, i) => 24000 + 50 * i), spot_ts: "2026-10-05T05:12:00+00:00",
  legs: [
    { side: "sell", opt: "CE", lots: 1, strike: 25400, sym: "NIFTY26O0825400CE", quote: quote(38.5), fill: 38.25,
      rule: "model delta nearest 0.20", pick: "CE 25,400 picked: model delta 0.21, nearest to 0.20" },
    { side: "sell", opt: "PE", lots: 1, strike: 24650, sym: "NIFTY26O0824650PE", quote: quote(49.6), fill: 49.35,
      rule: "premium nearest ₹50.00", pick: "PE 24,650 picked: premium ₹49.60, nearest to ₹50.00" },
  ],
  charges: null, model: null, greeks: null,
};

const SID = "sess-rules-1";
const t0 = "2026-10-05T09:31:00+05:30";
const SNAP = {
  id: SID, name: "NIFTY 0.2 delta strangle", kind: "options", status: "running", instrument: { symbol: "NIFTY options", exchange: "NFO", underlying: "NIFTY", type: "OPTIONS" },
  strategy: { name: "NIFTY 0.2 delta strangle", structure: "custom", exchange: "NFO", underlying: "NIFTY", expiry: "current", offsetUnit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1, pick: "delta", delta: 0.2 }, { side: "sell", opt: "PE", offset: 0, lots: 1, pick: "delta", delta: 0.2 }],
    timing: { entry: "09:30", lastEntry: "14:45", squareoff: "15:15", maxEntries: 1, cooldown: 0 },
    risk: { stopType: "credit_pct", stop: 30, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
    recenter: { enabled: false, every: 30, threshold: 2, roll: "shorts" }, sizing: { mode: "lots", lots: 1, capital: 500000, safety: 0.98 },
    costs: { brokerage: 20, slippageTicks: 0, freeze: 0 }, notes: "", signal: null, vix: { min: 11, max: 18 } },
  started_at: "2026-10-05T08:55:00+05:30", spot: 25010, last_tick_at: t0, fresh: true, feed_connected: true, expiry: "2026-10-08", lot: LOT, note: "",
  legs: [{ sym: "NIFTY26O0825400CE", opt: "CE", side: "sell", strike: 25400, qty: LOT, entry: 38.25, mark: 37.9, open: true, pnl: 22.75 },
    { sym: "NIFTY26O0824600PE", opt: "PE", side: "sell", strike: 24600, qty: LOT, entry: 41.1, mark: 40.4, open: true, pnl: 45.5 }],
  position: { opened: "2026-10-05T10:02:00+05:30", center: 25000, spot_in: 25010, credit: 5157.5, mtm: 68.25, costs: 61.2, net: 7.05, best: 120, worst: -40,
    rolls: 0, units: 1, orders: 2, expiry: "2026-10-08", dir: null },
  events: [
    { t: t0, kind: "skip", vix: 18.4, why: "Skipped: India VIX 18.40, above 18" },
    { t: "2026-10-05T10:02:00+05:30", side: "sell", qty: LOT, px: 38.25, why: "Entry", sym: "NIFTY26O0825400CE", strike: 25400, opt: "CE", slices: 1,
      pick: "CE 25,400 picked: model delta 0.21, nearest to 0.20" },
    { t: "2026-10-05T10:02:00+05:30", side: "sell", qty: LOT, px: 41.1, why: "Entry", sym: "NIFTY26O0824600PE", strike: 24600, opt: "PE", slices: 1,
      pick: "PE 24,600 picked: model delta −0.19, nearest to −0.20" },
  ],
  trades: [], equity_curve: [], signal: null,
  account: { capital: 500000, equity: 500007, cash: 500000, realised: 0, today: 0, halted: false, entries_today: 1, trades: 0, wins: 0, unrealised: 7.05 },
};

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const previews: { strategy: { legs: { pick?: string }[]; vix?: unknown } }[] = [];
  await page.route("**/*", async (r) => {
    const u = new URL(r.request().url());
    const p = u.pathname;
    if (p.endsWith("/options/underlyings")) return r.fulfill({ json: [{ exchange: "NFO", name: "NIFTY", venue: "NSE", lot: LOT, freeze: 1800, popular: true, index: true, expiries: PREVIEW.expiries }] });
    if (p.endsWith("/options/preview")) { previews.push(r.request().postDataJSON()); return r.fulfill({ json: PREVIEW }); }
    if (p.endsWith(`/live/sessions/${SID}`)) return r.fulfill({ json: SNAP });
    if (p.endsWith("/options/greeks")) return r.fulfill({ status: 503, json: { detail: { code: "data_offline", message: "Offline" } } });
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.removeItem("stratlab.options.draft.v1"); }, sessionAs("pro-token", "u-pro", "pro@example.com"));
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return { errors, previews };
}

async function noSideScroll(page: Page) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide, "the page scrolls sideways").toBeLessThanOrEqual(1);
}

test("options builder: legs picked by delta and premium, and the India VIX entry filter", async ({ page }, info) => {
  const { errors, previews } = await open(page, "/options");
  await page.getByText("Edit legs").click();
  // leg 1: the call nearest 0.20 delta; leg 2: the put nearest a ₹50 premium
  await page.getByLabel("Leg 1 strike by").selectOption("delta");
  await expect(page.getByLabel("Leg 1 delta")).toHaveValue("0.2");
  await page.getByLabel("Leg 2 strike by").selectOption("premium");
  await page.getByLabel("Leg 2 premium", { exact: true }).fill("50");
  await expect(page.locator(".legs-box summary")).toContainText("Sell Δ 0.20 CE · Sell ≈ ₹50 PE");
  await expect(page.getByText("A rule picks its strike from the live quotes when the session enters")).toBeVisible();
  // a delta range needs both ends
  await page.getByLabel("Leg 1 strike by").selectOption("delta_range");
  await expect(page.getByLabel("Leg 1 delta, high end")).toHaveValue("0.3");
  await page.getByLabel("Leg 1 strike by").selectOption("delta");

  // the India VIX filter: a band, sent with the structure
  const vix = page.getByTestId("vix-filter");
  await vix.getByRole("checkbox").check();
  await expect(vix.getByLabel("Lowest (0 = none)")).toHaveValue("11");
  await vix.getByLabel("Highest (0 = none)").fill("20");

  await page.getByRole("button", { name: "Price it now" }).click();
  const picks = page.getByTestId("leg-picks");
  await expect(picks).toContainText("Leg 1: CE 25,400 picked: model delta 0.21, nearest to 0.20");
  await expect(picks).toContainText("Leg 2: PE 24,650 picked: premium ₹49.60, nearest to ₹50.00");
  await expect(page.locator("table.legs tbody tr").first()).toContainText("25400");
  const sent = previews[previews.length - 1].strategy;
  expect(sent.legs.map((l) => l.pick)).toEqual(["delta", "premium"]);
  expect(sent.vix).toEqual({ min: 11, max: 20 });

  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(ADVICE);
  await noSideScroll(page);
  expect(errors).toEqual([]);
  await page.screenshot({ path: `${SHOTS}/strike-rules-${info.project.name}.png`, fullPage: false });
});

test("an options session: the rule's reason under each order, and the entries the VIX filter held back", async ({ page }, info) => {
  const { errors } = await open(page, `/options/s/${SID}`);
  await expect(page.getByText("NIFTY 0.2 delta strangle").first()).toBeVisible();
  await expect(page.locator(".rules-strip")).toContainText("Sell Δ 0.20 CE, Sell Δ 0.20 PE");
  await expect(page.getByTestId("rule-vix")).toHaveText("Enter only while India VIX is between 11 and 18");
  await page.getByText("Orders in this trade").click();
  await expect(page.getByTestId("order-pick").first()).toHaveText("CE 25,400 picked: model delta 0.21, nearest to 0.20");
  await expect(page.getByTestId("order-pick")).toHaveCount(2);
  await page.getByText("Entries the India VIX filter held back").click();
  await expect(page.getByTestId("vix-skips")).toContainText("Skipped: India VIX 18.40, above 18");
  await noSideScroll(page);
  expect(errors).toEqual([]);
  await page.screenshot({ path: `${SHOTS}/strike-rules-session-${info.project.name}.png`, fullPage: false });
});
