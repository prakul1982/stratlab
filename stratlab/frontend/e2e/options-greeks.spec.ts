import { expect, test, type Page } from "@playwright/test";
import { greeks, scenario, type GreekModel, type ModelLeg } from "../src/lib/greeks";
import { payoff } from "../src/lib/options";

// The pricing model in the Options builder and on an options session's page: each leg's IV and Greeks with the net,
// the payoff today beside the one at expiry, the what-if sliders that re-price it in the browser, the roll preview, and
// the IV and Greeks for every strike in the chain. The live option feed is offline in the fake world, so the priced
// preview, the chain, the session and the model's answers are served here, worked out with the same pricing port the
// page uses (src/lib/greeks.ts, itself checked against the backend in unit/greeks.test.mjs).
const SHOTS = process.env.SHOTS_DIR ?? "test-results";
const sessionAs = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });

const SPOT = 25010, LOT = 65, R = 0.06, T = 3.25 / 365, BASIS = 1.0006, F = SPOT * BASIS;
const MODEL: GreekModel = { expiry: "2026-10-08", spot: SPOT, forward: +F.toFixed(4), basis: BASIS, forward_from: "parity", atm: 25000, t: T, days: 3.25,
  rate: R, atm_iv: 0.1125, as_of: "2026-10-05T10:42:00+05:30" };
// an iron fly: the 25,000 straddle sold, wings bought 400 points out
const FLY: [("buy" | "sell"), ("CE" | "PE"), number, number][] = [["sell", "CE", 25000, 0.11], ["sell", "PE", 25000, 0.115], ["buy", "CE", 25400, 0.12], ["buy", "PE", 24600, 0.135]];
const quote = (mid: number) => ({ bid: +(mid - 0.25).toFixed(2), ask: +(mid + 0.25).toFixed(2), ltp: +mid.toFixed(2), oi: 120000, ts: "2026-10-05T05:12:00+00:00" });
const per = (k: number, opt: "CE" | "PE", iv: number) => {
  const g = greeks(F, k, T, iv, opt, R);
  return { mid: g.price, iv, iv_from: "price" as const, delta: g.delta, gamma: g.gamma, theta: g.theta, vega: g.vega, model_price: g.price };
};
const legs = FLY.map(([side, opt, k, iv]) => {
  const g = per(k, opt, iv), fill = +(side === "sell" ? g.mid - 0.25 : g.mid + 0.25).toFixed(2);
  return { side, opt, lots: 1, strike: k, sym: `NIFTY26O08${k}${opt}`, quote: quote(g.mid), fill, g };
});
const modelLegs: ModelLeg[] = legs.map((l) => ({ side: l.side, opt: l.opt, strike: l.strike, qty: LOT, fill: l.fill, iv: l.g.iv, t: T, basis: BASIS }));
const now = scenario(modelLegs, SPOT, 0, 0, R);
const bare = { spot: SPOT, atm: 25000, step: 50, expiry: "2026-10-08", expiries: ["2026-10-08", "2026-10-13", "2026-10-20"], lot: LOT, freeze: 1800, units: 1,
  margin_one: 52000, margin: 52000, strikes: Array.from({ length: 41 }, (_, i) => 24000 + 50 * i), spot_ts: "2026-10-05T05:12:00+00:00",
  legs: legs.map(({ g: _g, ...l }) => l) };
const f = payoff({ ...bare, charges: null } as never);
const CHARGES = { total: 236.4, orders: 8, brokerage_per_order: 20, freeze: 1800, credit: true, premium: +f.credit.toFixed(2), premium_after: +(f.credit - 236.4).toFixed(2),
  pct_of_premium: 2.1, max_profit: f.maxProfit, max_profit_after: f.maxProfit! - 236.4, pct_of_max_profit: 2.1, max_loss: f.maxLoss, max_loss_after: f.maxLoss! - 236.4,
  items: [{ key: "brokerage", label: "Brokerage", amount: 160 }, { key: "stt", label: "STT", amount: 30.2 }, { key: "gst", label: "GST", amount: 46.2 }],
  breakevens: f.breakevens.map((x) => +x.toFixed(2)), breakevens_after: f.breakevens.map((x, i) => +(x + (i ? -3.6 : 3.6)).toFixed(2)), rates_as_of: "2026-04-01" };
const PREVIEW = { ...bare, charges: CHARGES, model: MODEL,
  greeks: { legs: legs.map((l) => l.g), model_legs: modelLegs, complete: true, net: { delta: now.delta, gamma: now.gamma, theta: now.theta, vega: now.vega, pnl: now.pnl } } };

// rolling the sold call up a strike: closed at its ask, the 25,050 call sold at its bid
const up = per(25050, "CE", 0.108);
const after = scenario([...modelLegs.slice(1), { ...modelLegs[0], strike: 25050, iv: 0.108 }], SPOT, 0, 0, R);
const ROLL = { leg: 0, spot: SPOT, close: { opt: "CE", strike: 25000, expiry: "2026-10-08", side: "buy", px: legs[0].quote.ask, sym: "NIFTY26O0825000CE" },
  open: { ...up, opt: "CE", strike: 25050, expiry: "2026-10-08", side: "sell", px: +(up.mid - 0.25).toFixed(2), sym: "NIFTY26O0825050CE" },
  premium: +((up.mid - 0.25 - legs[0].quote.ask) * LOT).toFixed(2), charges: { total: 61.35, orders: 2, items: [{ key: "brokerage", label: "Brokerage", amount: 40 }] },
  net: +((up.mid - 0.25 - legs[0].quote.ask) * LOT - 61.35).toFixed(2), before: now, after, complete: true, model: MODEL, model_to: MODEL };

const CHAIN = { expiry: "2026-10-08", expiries: bare.expiries, lot: LOT, spot: SPOT, atm: 25000, step: 50, freeze: 1800, model: MODEL,
  rows: Array.from({ length: 11 }, (_, i) => 24750 + 50 * i).map((k) => {
    const iv = 0.11 + Math.abs(k - 25000) / 25000;
    const c = per(k, "CE", iv), p = per(k, "PE", iv);
    return { strike: k, ce: quote(c.mid), pe: quote(p.mid), ce_g: c, pe_g: p };
  }) };

async function open(page: Page, path: string, extra: Record<string, unknown> = {}, whatif = true) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const rolls: unknown[] = [];
  await page.route("**/*", async (r) => {
    const u = new URL(r.request().url());
    const p = u.pathname;
    if (p.endsWith("/options/underlyings")) return r.fulfill({ json: [{ exchange: "NFO", name: "NIFTY", venue: "NSE", lot: LOT, freeze: 1800, popular: true, index: true, expiries: bare.expiries }] });
    if (p.endsWith("/options/preview")) return r.fulfill({ json: PREVIEW });
    if (p.endsWith("/options/chain")) return r.fulfill({ json: CHAIN });
    if (p.endsWith("/options/roll")) { rolls.push(r.request().postDataJSON()); return r.fulfill({ json: ROLL }); }
    for (const [k, v] of Object.entries(extra)) if (p.endsWith(k)) return r.fulfill({ json: v });
    if (p.endsWith("/me") && !whatif) {            // as the server answers a Free account once payments are live
      const res = await r.fetch();
      const me = await res.json();
      return r.fulfill({ response: res, json: { ...me, plan_info: { ...me.plan_info, features: { ...me.plan_info.features, options_whatif: false } } } });
    }
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const who = whatif ? sessionAs("pro-token", "u-pro", "pro@example.com") : sessionAs("free-token", "u-free", "free@example.com");
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return { errors, rolls };
}

async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

async function noSideScroll(page: Page) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide, "the page scrolls sideways").toBeLessThanOrEqual(1);
}

const todayLine = (page: Page) => page.locator("[data-testid=payoff-chart] path.ch-line[stroke='var(--series-3)']:not([stroke-dasharray])");
const num = (s: string) => Number(s.replace(/[₹,\s]/g, "").replace("−", "-"));

test("options builder: Greeks, the payoff today, what-if sliders and the roll preview", async ({ page }, info) => {
  const { errors, rolls } = await open(page, "/options");
  await page.getByRole("button", { name: "Price it now" }).click();
  const panel = page.getByTestId("opt-model");
  await expect(panel).toBeVisible();

  // every figure says it's a model estimate, with its inputs
  await expect(panel.getByTestId("model-inputs")).toContainText("Model estimates, not prices: Black-76 on the forward 25,025.01 (from put-call parity at 25,000)");
  await expect(panel.getByTestId("model-inputs")).toContainText("3.25 days to the 8 Oct expiry, rate 6%");
  await expect(panel).toContainText("Greeks, model estimate");
  const table = panel.getByTestId("greeks-table");
  await expect(table.locator("tbody tr")).toHaveCount(5);
  await expect(table.locator("tbody tr").first()).toContainText("Sold 25,000 CE11.0%");
  const delta0 = await panel.getByTestId("net-delta").innerText(), theta0 = await panel.getByTestId("net-theta").innerText();
  expect(num(delta0)).toBeCloseTo(now.delta, 1);
  expect(num(theta0)).toBeGreaterThan(0);                                       // a sold fly: time passing helps it

  // four curves: at expiry and today, each before and after charges
  for (const s of ["At expiry", "After charges", "Today (model)", "Today after charges (model)"])
    await expect(panel.getByRole("button", { name: `Series: ${s}`, exact: true })).toBeVisible();
  await expect(todayLine(page)).toHaveCount(1);
  const path0 = await todayLine(page).getAttribute("d");

  // the tooltip on the today curve says what it is
  const svg = panel.locator("svg.ch-svg");
  const box = (await svg.boundingBox())!;
  await svg.hover({ position: { x: box.width * 0.5, y: box.height * 0.5 } });
  await expect(page.locator(".ch-tip")).toContainText("today, model estimate");
  await expect(page.locator(".ch-tip")).toContainText("today after charges, model estimate");
  await page.mouse.move(0, 0);

  // the underlying up 2%: the P&L, the net delta and a what-if marker move; the today curve doesn't
  const pnl0 = await panel.getByTestId("whatif-pnl").locator(".k-stat-v").first().innerText();
  await panel.getByTestId("whatif-spot").fill("2");
  await expect(panel.getByTestId("whatif-spot-value")).toHaveText("+2% · 25,510");
  await expect(panel.getByTestId("net-delta")).not.toHaveText(delta0);
  await expect(panel.getByTestId("whatif-pnl").locator(".k-stat-v").first()).not.toHaveText(pnl0);
  await expect(panel).toContainText("Greeks, model estimate (NIFTY +2% at 25,510)");
  expect(await todayLine(page).getAttribute("d")).toBe(path0);

  // IV up 5 points: the today curve reprices
  await panel.getByTestId("whatif-iv").fill("5");
  await expect(panel.getByTestId("whatif-iv-value")).toHaveText("+5 vol pts");
  await expect.poll(() => todayLine(page).getAttribute("d")).not.toBe(path0);
  await expect(panel.getByRole("button", { name: "Series: Today (model)", exact: true })).toBeVisible();

  // a day on: theta has eaten into the premium, and the curve is labelled with the day
  await panel.getByTestId("whatif-days").fill("1");
  await expect(panel.getByRole("button", { name: "Series: In 1 day (model)", exact: true })).toBeVisible();
  await expect(panel.getByTestId("model-inputs")).toContainText("What-if: NIFTY +2% at 25,510, IV +5 pts, 1 day on; IV floored at 0.5%.");
  await noSideScroll(page);
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/greeks-whatif-${info.project.name}.png`, fullPage: false });

  // all the way to expiry: the today curve lies on the at-expiry one
  await panel.getByTestId("whatif-spot").fill("0");
  await panel.getByTestId("whatif-days").fill("3.25");
  await expect(panel.getByTestId("whatif-days-value")).toHaveText("to expiry");
  await expect(panel.getByRole("button", { name: "Series: At expiry, with the what-if (model)", exact: true })).toBeVisible();
  await expect(panel.getByTestId("net-theta")).toHaveText("₹0");

  // reset puts everything back
  await panel.getByTestId("whatif-reset").click();
  await expect(panel.getByTestId("net-delta")).toHaveText(delta0);
  await expect(panel.getByTestId("net-theta")).toHaveText(theta0);
  await expect.poll(() => todayLine(page).getAttribute("d")).toBe(path0);
  await expect(panel.getByTestId("whatif-spot-value")).toHaveText("0% · 25,010");

  // roll the sold call up a strike: premium, charges and the net Greeks before and after
  const fold = page.getByTestId("roll-fold");
  await fold.locator("summary").click();
  const roll = fold.getByTestId("roll-preview");
  await expect(roll.getByLabel("New strike")).toHaveValue("25050");
  await roll.getByRole("button", { name: "Preview the roll" }).click();
  const res = roll.getByTestId("roll-result");
  await expect(res).toContainText("Closes the sold 25,000 CE (8 Oct) at");
  await expect(res).toContainText("opens a sold 25,050 CE (8 Oct)");
  await expect(res).toContainText("Charges, two orders₹61.35");
  await expect(res.getByTestId("roll-net")).toContainText(`−₹${Math.abs(ROLL.net).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`);
  await expect(res.getByTestId("roll-delta")).toContainText(/Delta \(₹ per point\)−?[\d,.]+−?[\d,.]+[\d,.]+/);
  await expect(res.getByTestId("model-inputs")).toContainText("Model estimates");
  expect(rolls).toEqual([expect.objectContaining({ leg: 0, strike: 25050, to_expiry: "2026-10-08", expiry: "2026-10-08",
    legs: expect.arrayContaining([{ side: "sell", opt: "CE", strike: 25000, qty: LOT, fill: legs[0].fill }]) })]);
  // no advice: facts and model estimates only
  const text = await panel.innerText();
  expect(text).not.toMatch(/probability of profit|you should|\bbest\b|recommend/i);
  expect(text).not.toMatch(/kite|zerodha|yahoo|nseindia/i);
  if (info.project.name === "phone") await touchable(page);
  await noSideScroll(page);
  await res.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/greeks-roll-${info.project.name}.png`, fullPage: false });
  expect(errors, "uncaught errors in the page").toEqual([]);
});

test("options chain: IV and Greeks for every strike, labelled as model estimates", async ({ page }, info) => {
  const { errors } = await open(page, "/options");
  await page.locator("details.chain > summary").click();
  await page.getByRole("radio", { name: "IV and Greeks" }).click();
  const t = page.getByTestId("chain-greeks");
  await expect(t.locator("tbody tr")).toHaveCount(11);
  const atm = t.locator("tr.atm");
  await expect(atm).toContainText("11.0%");
  const cells = await atm.locator("td").allInnerTexts();
  expect(Number(cells[1])).toBeCloseTo(CHAIN.rows[5].ce_g.delta, 2);           // the call's delta
  expect(Number(cells[7].replace("−", "-"))).toBeCloseTo(CHAIN.rows[5].pe_g.delta, 2);
  await expect(page.locator("details.chain").getByTestId("model-inputs")).toContainText("Model estimates");
  await noSideScroll(page);
  // the wide table scrolls inside its card; the card itself stays on the screen
  const card = (await page.locator("details.chain").boundingBox())!;
  expect(card.x, "the chain card starts off the screen").toBeGreaterThanOrEqual(0);
  expect(card.x + card.width, "the chain card runs past the screen").toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  if (info.project.name === "phone") await touchable(page);
  await t.scrollIntoViewIfNeeded();
  expect((await page.locator("details.chain").boundingBox())!.x, "scrolling to the table moved the page sideways").toBeGreaterThanOrEqual(0);
  await page.screenshot({ path: `${SHOTS}/greeks-chain-${info.project.name}.png`, fullPage: false });
  expect(errors).toEqual([]);
});

test("options builder on Free: the Greeks and the today curve, the sliders and the roll preview behind Pro", async ({ page }) => {
  const { errors } = await open(page, "/options", {}, false);
  await page.getByRole("button", { name: "Price it now" }).click();
  const panel = page.getByTestId("opt-model");
  await expect(panel.getByTestId("whatif-locked")).toContainText("are on the Pro plan");
  await expect(panel.getByTestId("whatif")).toHaveCount(0);
  await expect(page.getByTestId("roll-fold")).toHaveCount(0);
  await expect(panel.getByTestId("greeks-net")).toBeVisible();
  await expect(todayLine(page)).toHaveCount(1);
  expect(errors).toEqual([]);
});

test("options session: the open trade's Greeks and payoff today, with the sliders", async ({ page }, info) => {
  const strategy = { name: "Iron fly", structure: "iron_fly", exchange: "NFO", underlying: "NIFTY", expiry: "current", offsetUnit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 }, { side: "buy", opt: "CE", offset: 8, lots: 1 }, { side: "buy", opt: "PE", offset: 8, lots: 1 }],
    timing: { entry: "09:30", lastEntry: "14:45", squareoff: "15:15", maxEntries: 1, cooldown: 0 },
    risk: { stopType: "none", stop: 0, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
    recenter: { enabled: false, every: 30, threshold: 2, roll: "shorts" }, sizing: { mode: "lots", lots: 1, capital: 500000, safety: 0.98 },
    costs: { brokerage: 20, slippageTicks: 0, freeze: 0 }, notes: "" };
  const snap = { id: "s9", name: "Iron fly", kind: "options", status: "running", instrument: { symbol: "NIFTY options", exchange: "NFO", underlying: "NIFTY" },
    strategy, started_at: "2026-10-05T03:55:00+00:00", spot: SPOT, fresh: true, feed_connected: true, expiry: "2026-10-08", lot: LOT, note: "",
    legs: legs.map((l) => ({ sym: l.sym, opt: l.opt, side: l.side, strike: l.strike, qty: LOT, entry: l.fill, mark: l.quote.ask, open: true, pnl: -16 })),
    position: { opened: "2026-10-05T04:00:00+00:00", center: 25000, spot_in: 25004, credit: f.credit, mtm: -64, costs: 118.2, net: -182.2, best: 120, worst: -300,
      rolls: 0, units: 1, orders: 4, expiry: "2026-10-08" },
    events: [], trades: [], equity_curve: [], signal: null,
    account: { capital: 500000, equity: 499817.8, cash: 500000, realised: 0, today: 0, halted: false, entries_today: 1, trades: 0, wins: 0, unrealised: -182.2 } };
  const held = { model: MODEL, spot: SPOT, legs: legs.map((l) => l.g), model_legs: modelLegs, complete: true,
    net: { delta: now.delta, gamma: now.gamma, theta: now.theta, vega: now.vega, pnl: now.pnl }, close_charges: { total: 101.3, orders: 4 } };
  const { errors } = await open(page, "/options/s/s9", { "/live/sessions/s9": snap, "/options/greeks": held });
  const box = page.getByTestId("session-model");
  await expect(box).toBeVisible();
  await expect(box.getByTestId("greeks-table").locator("tbody tr")).toHaveCount(5);
  await expect(box).toContainText("After charges takes off ₹118 paid so far and about ₹101 to close what's open.");
  const d0 = await box.getByTestId("net-delta").innerText();
  await box.getByTestId("whatif-spot").fill("-1.5");
  await expect(box.getByTestId("net-delta")).not.toHaveText(d0);
  await expect(box.getByTestId("whatif-spot-value")).toHaveText("−1.5% · 24,635");
  await expect(todayLine(page)).toHaveCount(1);
  await noSideScroll(page);
  if (info.project.name === "phone") await touchable(page);
  await box.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/greeks-session-${info.project.name}.png`, fullPage: false });
  expect(errors).toEqual([]);
});
