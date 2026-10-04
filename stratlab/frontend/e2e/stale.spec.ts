import { expect, test, type Page } from "@playwright/test";

// Finished things never look current: on the paper trading pages, the options sessions list and the alerts page,
// what is running or happened today comes first, and what is over (stopped sessions, earlier orders, alerts that fired
// before today) folds under one "Earlier"-style line with a count, closed until opened and never deleted.
// Every page here is drawn from saved answers at a fixed moment: Monday 5 Oct 2026, 13:00 in India.
const NOW = "2026-10-05T07:30:00+00:00";
test.use({ timezoneId: "Asia/Kolkata" });

const session = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r", access_token: "admin-token",
  user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string, answers: Record<string, unknown>, ready: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.clock.setFixedTime(new Date(NOW));
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    const api = ["fetch", "xhr"].includes(r.request().resourceType());      // the page itself at /alerts is not the API's /alerts
    const hit = api && Object.keys(answers).find((k) => u.pathname.endsWith(k));
    if (hit) return r.fulfill({ status: 200, body: JSON.stringify(answers[hit]), contentType: "application/json" });
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");      // a first visit asks what the person came for
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

/** No crash, nothing wider than the screen, every control big enough for a finger on a phone. */
async function sane(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide, "the page scrolls sideways").toBeLessThanOrEqual(1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text).not.toMatch(bad);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main a, main details.earlier > summary"))
    .filter((el) => { const b = el.getBoundingClientRect(); return b.width && b.height && b.height < 32 && !el.closest("p, td, .info-btn") && getComputedStyle(el).display !== "inline"; })
    .map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 30)}"`));
  expect(small, "controls too small to tap").toEqual([]);
}

const shot = (page: Page, name: string, project: string) => page.screenshot({ path: `test-results/stale-${name}-${project}.png`, fullPage: true });

// ---------- paper trading ----------
const inst = (symbol: string, type = "EQ") => ({ id: `NSE:${symbol}`, symbol, exchange: "NSE", market: "IN", currency: "INR", type });
const row = (id: string, name: string, status: string, symbol = "RELIANCE", type = "EQ") =>
  ({ id, name, instrument: inst(symbol, type), status, started_at: "2026-09-01T03:45:00+00:00", stopped_at: status === "stopped" ? "2026-09-20T10:00:00+00:00" : null, stop_reason: null });
const rows = [row("p1", "Reliance breakout", "running"), row("p2", "TCS pullback", "stopped", "TCS"), row("p3", "Infosys trend", "stopped", "INFY"),
  row("p4", "HDFC dip", "stopped", "HDFCBANK")];

const ev = (t: string, side: "buy" | "sell", px: number, why: string, pnl?: number) => ({ t, side, qty: 10, px, why, ...(pnl != null ? { pnl } : {}) });
const single = {
  id: "p1", name: "Reliance breakout", status: "running", instrument: inst("RELIANCE"), started_at: "2026-09-01T03:45:00+00:00",
  strategy: { name: "Breakout", tf: "15m", text: "", entry: [], exit: [], entryJoin: "all", risk: { capital: 100000 } },
  last_price: 2950, last_tick_at: NOW, feed_connected: true,
  bars: Array.from({ length: 30 }, (_, i) => ({ t: new Date(Date.parse(NOW) - (30 - i) * 900_000).toISOString(), o: 2900 + i, h: 2905 + i, l: 2895 + i, c: 2900 + i * 2 })),
  overlays: {}, equity_curve: [{ t: "2026-09-01T04:00:00+00:00", eq: 100000 }, { t: NOW, eq: 101500 }],
  account: { capital: 100000, equity: 101500, cash: 72000, qty: 10, entry: 2940, stop: 2900, target: 3050, unrealised: 100, realised: 1400, trades: 3, wins: 2 },
  events: [
    ev("2026-09-10T04:15:00+00:00", "buy", 2800, "Entry"), ev("2026-09-11T06:00:00+00:00", "sell", 2900, "Target", 1000),
    ev("2026-09-20T04:15:00+00:00", "buy", 2850, "Entry"), ev("2026-09-21T06:00:00+00:00", "sell", 2810, "Stop loss", -400),
    ev("2026-10-01T04:15:00+00:00", "buy", 2860, "Entry"), ev("2026-10-01T09:00:00+00:00", "sell", 2940, "Exit rules", 800),
    ev("2026-10-05T05:00:00+00:00", "buy", 2940, "Entry"),
  ],
  orders: [],
};

test("paper trading: running sessions first, the stopped ones folded with a count", async ({ page }, info) => {
  const errors = await open(page, "/paper", { "/live/sessions": rows, "/live/overview": { currencies: [], sessions: [] } }, "Paper trading");
  await expect(page.getByRole("button", { name: /Reliance breakout/ })).toBeVisible();
  const fold = page.locator("details.earlier", { hasText: "Stopped sessions" });
  await expect(fold.locator("summary")).toContainText("Stopped sessions (3)");
  await expect(page.getByRole("button", { name: /TCS pullback/ })).toHaveCount(0);        // folded: not drawn
  await sane(page, errors, info.project.name === "phone");
  await shot(page, "paper-list", info.project.name);
  await fold.locator("summary").click();
  await expect(page.getByRole("button", { name: /TCS pullback/ })).toBeVisible();
  await expect(fold.getByRole("button", { name: "Clear stopped sessions" })).toBeVisible();
});

test("paper trading: a stopped session opened from the link shows with its fold open", async ({ page }) => {
  const stopped = { ...single, id: "p2", name: "TCS pullback", status: "stopped", instrument: inst("TCS") };
  await open(page, "/paper/p2", { "/live/sessions": rows, "/live/sessions/p2": stopped }, "TCS pullback");
  await expect(page.locator("details.earlier", { hasText: "Stopped sessions" })).toHaveAttribute("open", "");
  await expect(page.getByRole("button", { name: /TCS pullback/ })).toHaveAttribute("aria-current", "true");
});

test("paper session: today's orders in view, the earlier ones folded with their P&L", async ({ page }, info) => {
  const errors = await open(page, "/paper/p1", { "/live/sessions": rows, "/live/sessions/p1": single }, "Orders today");
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Orders today" }) });
  await expect(card.locator(".order-group")).toHaveCount(1);
  await expect(card.locator(".order-head").first()).toContainText("Entry");
  await expect(card.locator(".order-sym")).toHaveText(["RELIANCE"]);
  const fold = card.locator("details.earlier");
  await expect(fold.locator("summary")).toContainText("Earlier orders (6)");
  await expect(fold.locator("summary")).toContainText("₹1,400 on closed trades");
  await sane(page, errors, info.project.name === "phone");
  await shot(page, "paper-session", info.project.name);
  await fold.locator("summary").click();
  await expect(fold.locator(".order-group")).toHaveCount(6);
  await expect(fold.locator(".order-head").first()).toContainText("Exit rules");          // newest first
});

test("paper session: nothing today says so in one line", async ({ page }) => {
  await open(page, "/paper/p1", { "/live/sessions": rows, "/live/sessions/p1": { ...single, events: single.events.slice(0, 6) } }, "Orders today");
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Orders today" }) });
  await expect(card).toContainText("No orders today.");
  await expect(card.locator("details.earlier summary")).toContainText("Earlier orders (6)");
});

test("group session: today's orders in view, the earlier ones folded", async ({ page }, info) => {
  const g = (t: string, sym: string, side: "buy" | "sell", why: string, pnl?: number) => ({ ...ev(t, side, 1500, why, pnl), sym });
  const group = {
    id: "g1", name: "Nifty 50 momentum", kind: "group", status: "running", instrument: { symbol: "NIFTY 50", market: "IN", currency: "INR", maxOpen: 5 },
    strategy: { tf: "15m", risk: { capital: 500000 } }, started_at: "2026-09-01T03:45:00+00:00", last_tick_at: NOW, feed_connected: true,
    members: [{ symbol: "TCS", id: "NSE:TCS", price: 3900, trades: 2, pnl: 1200, position: null }], skipped: [],
    events: [g("2026-09-15T04:15:00+00:00", "TCS", "buy", "Entry"), g("2026-09-16T06:00:00+00:00", "TCS", "sell", "Target", 1200),
      g("2026-10-05T04:15:00+00:00", "INFY", "buy", "Entry"), g("2026-10-05T04:15:00+00:00", "WIPRO", "buy", "Entry")],
    equity_curve: [{ t: "2026-09-01T04:00:00+00:00", eq: 500000 }, { t: NOW, eq: 501200 }],
    account: { capital: 500000, equity: 501200, realised: 1200, unrealised: 0, open: 0, max_open: 5, halted: false, today: 0, trades: 1, wins: 1 },
  };
  const errors = await open(page, "/paper/g1", { "/live/sessions": rows, "/live/sessions/g1": group }, "Orders today");
  const card = page.locator("section", { has: page.getByRole("heading", { name: "Orders today" }) });
  await expect(card.locator(".order-group")).toHaveCount(1);                       // the two entries sent together, one line
  await expect(card.locator(".order-sym")).toHaveText(["INFY", "WIPRO"]);
  await expect(card.locator("details.earlier summary")).toContainText("Earlier orders (2)");
  await sane(page, errors, info.project.name === "phone");
  await shot(page, "group-session", info.project.name);
});

// ---------- options sessions list ----------
test("options: running sessions first, the stopped ones folded", async ({ page }, info) => {
  const opt = [row("o1", "Short straddle", "running", "NIFTY", "OPTIONS"), row("o2", "Iron fly", "stopped", "NIFTY", "OPTIONS"),
    row("o3", "Strangle", "stopped", "BANKNIFTY", "OPTIONS")];
  const errors = await open(page, "/options", { "/live/sessions": opt }, "Your options sessions");
  const list = page.locator("section", { has: page.getByRole("heading", { name: "Your options sessions" }) });
  await expect(list.getByRole("link", { name: /Short straddle/ })).toBeVisible();
  await expect(list.locator("details.earlier summary")).toContainText("Stopped sessions (2)");
  await expect(list.getByRole("link", { name: /Iron fly/ })).toHaveCount(0);
  await list.locator("details.earlier summary").click();
  await expect(list.getByRole("link", { name: /Iron fly/ })).toBeVisible();
  await sane(page, errors, info.project.name === "phone");
});

// ---------- alerts ----------
const alert = (id: string, symbol: string, status: "active" | "triggered", triggered_at: string | null, text: string) => ({
  id, region: "IN", symbol, kind: "price", op: "above", value: 3000, period: null, repeat: false, note: null, status,
  created_at: "2026-09-01T03:45:00+00:00", triggered_at, fired: status === "triggered" ? 1 : 0, last_text: status === "triggered" ? `${symbol} crossed ₹3,000` : null, text,
});

test("alerts: the ones on first, today's fired ones next, the ones that fired before today folded", async ({ page }, info) => {
  const answers = { "/alerts": { active: [alert("a1", "RELIANCE", "active", null, "Price crosses above ₹3,000")],
    triggered: [alert("a2", "TCS", "triggered", "2026-10-05T05:00:00+00:00", "Price crosses above ₹3,000"),
      alert("a3", "INFY", "triggered", "2026-09-20T05:00:00+00:00", "Price crosses above ₹3,000"),
      alert("a4", "WIPRO", "triggered", "2026-09-02T05:00:00+00:00", "Price crosses above ₹3,000")],
    limit: 10, count: 1, channels: ["push"], email: null, email_confirmed: false } };
  const errors = await open(page, "/alerts", answers, "Your stock alerts");
  const fired = page.locator("section", { has: page.getByRole("heading", { name: "Fired today" }) });
  await expect(fired.getByRole("link", { name: "TCS" })).toBeVisible();
  const fold = fired.locator("details.earlier");
  await expect(fold.locator("summary")).toContainText("Fired earlier (2)");
  await expect(page.getByRole("link", { name: "INFY" })).toHaveCount(0);
  await sane(page, errors, info.project.name === "phone");
  await shot(page, "alerts", info.project.name);
  await fold.locator("summary").click();
  await expect(fold.getByRole("link", { name: "INFY" })).toBeVisible();
  await expect(fold.getByRole("link", { name: "WIPRO" })).toBeVisible();
});
