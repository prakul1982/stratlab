import { expect, test, type Page } from "@playwright/test";

// An experiment's page tells one consistent story: one block of next steps, the open trade counted the same way in the
// header and the trade list, the unseen-data parts adding up to the trades, forex quoted to 5 decimals without a volume
// panel, and the "All" range keeping the daily candles the rules ran on. Signed in as the site owner, tour seen.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const SMA = (p: number) => ({ name: "Experiment page", tf: "1d", entry: [{ l: { t: "price" }, op: "xa", r: { t: "sma", p } }],
  exit: [{ l: { t: "price" }, op: "xb", r: { t: "sma", p } }], risk: { capital: 10000, sl: 0, tgt: 0, brokerage: 0, slippage: 0.05 } });

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}

test("experiment page: one next-step block, counts that add up, forex decimals and no forex volume", async ({ page, request }, info) => {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin,
    data: { name: `FX page ${info.project.name}`, strategy: SMA(20), instrument: "FX:EURUSD=X" } })).json();
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  const exp = (await run.json()).experiment;
  // no weekend candles for a weekday market
  for (const t of exp.trades) expect(new Date(`${t.entry_t.slice(0, 10)}T12:00:00Z`).getUTCDay() % 6, `${t.entry_t} is a weekend`).not.toBe(0);
  const errors = await open(page, `/n/${nb.id}/e/1`);
  await expect(page.locator(".verdict-head")).toBeVisible({ timeout: 30_000 });

  // one place for what to do next
  await expect(page.getByRole("region", { name: "Next step", exact: true })).toHaveCount(1);
  await expect(page.getByText("What to try next")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Next experiment →" })).toHaveCount(0);

  // the verdict states the comparison with buying and holding
  await expect(page.locator(".k-verdict-hero")).toContainText("buying and holding over the same period");

  // the open trade is counted the same way in the header and the trade list
  const open_ = exp.trades.filter((t: { exit_t: string | null }) => !t.exit_t).length;
  const closed = exp.trades.length - open_;
  const counted = `${closed} trade${closed === 1 ? "" : "s"}${open_ ? ` + ${open_} still open` : ""}`;
  await expect(page.locator(".k-page").first()).toContainText(counted);
  const trades = page.getByRole("region", { name: "Every trade", exact: true });
  await expect(trades).toContainText(`${closed} closed${open_ ? ` + ${open_} still open` : ""} · P&L and Return after costs`);

  // the unseen-data parts add up to the closed trades
  const unseen = exp.verdict.checks.find((c: { id: string }) => c.id === "unseen").data;
  expect(unseen.built_trades + unseen.unseen_trades).toBe(closed);

  // forex quoted to 5 decimals, and no volume for spot forex
  await expect(trades.locator("td").filter({ hasText: /^\$\d\.\d{5}$/ }).first()).toBeVisible();
  const chart = page.locator(".pc-foot").first();
  await expect(chart.getByRole("button", { name: "Vol" })).toHaveCount(0);

  // "All" keeps the daily candles the rules ran on
  await page.getByRole("radio", { name: "All" }).click();
  await expect(page.locator(".pc-legend").first()).toContainText("Daily");
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("running an unchanged experiment again is refused without spending one", async ({ request }, info) => {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin,
    data: { name: `Rerun ${info.project.name}`, strategy: SMA(10), instrument: "CRYPTO:BTC-USD" } })).json();
  expect((await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 365 } })).ok()).toBeTruthy();
  const again = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 365 } });
  expect(again.status()).toBe(409);
  expect((await again.json()).detail.code).toBe("unchanged");
});
