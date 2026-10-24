import { expect, test, type Page, type Route } from "@playwright/test";

// The deep audit of turning an idea into rules and running it (24 Oct 2026, DA-003, DA-008, DA-011, DA-020): the notebook page
// and the verdict page, on notebooks made through the fake world's API.
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


const EMA = { name: "Trend", tf: "1d", text: "Buy when the 10 EMA crosses above the 30 EMA, sell when it crosses back below. Trailing stop 5%.",
  entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }], exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }],
  risk: { capital: 10000, riskPct: 1, sl: 0, tgt: 0, trail: 5, brokerage: 0, slippage: 0.05 } };

// ---------- DA-003: nothing chosen to test on: Run waits for a choice, and says so ----------
test("notebook: Run with no market chosen is refused with a way to choose one (DA-003)", async ({ page, request }, info) => {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `No market ${info.project.name}`, strategy: EMA } })).json();
  const runs: string[] = [];
  page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith(`/notebooks/${nb.id}/experiments`)) runs.push(r.url()); });
  const errors = await open(page, `/n/${nb.id}`);
  const needs = page.getByTestId("run-needs-market");
  await expect(needs).toContainText("Choose what to test it on before you run it", { timeout: 30_000 });
  await page.getByRole("button", { name: /Run experiment v1/ }).click();
  await expect(page.getByRole("button", { name: "Choose market" }).first()).toBeVisible();
  expect(runs, "no run was sent").toEqual([]);
  await needs.getByRole("link", { name: "Choose market" }).click();
  await expect(page).toHaveURL(new RegExp(`/n/${nb.id}/market$`));
  expect(errors).toEqual([]);
});

// ---------- DA-008: a trailing stop is in the main rules ----------
test("notebook: a trailing stop asked for shows with the rules, not only under More settings (DA-008)", async ({ page, request }, info) => {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `Trail ${info.project.name}`, strategy: EMA, instrument: "CRYPTO:BTC-USD" } })).json();
  const errors = await open(page, `/n/${nb.id}`);
  const rules = page.getByRole("region", { name: "The rules" });
  await expect(rules.getByTestId("trail-line")).toContainText("Also close if the price falls 5% from its best since the trade opened", { timeout: 30_000 });
  await expect(rules).toContainText("with no stop loss and no target");          // no stop the idea didn't ask for
  expect(errors).toEqual([]);
});

// ---------- DA-011, DA-020: the questions go once a run exists, and the verdict headline is one sentence ----------
test("experiment: the question card is gone after a run, and the verdict's checks are their own line (DA-011, DA-020)", async ({ page, request }, info) => {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `Run ${info.project.name}`, strategy: EMA, instrument: "CRYPTO:BTC-USD" } })).json();
  await request.put(`${API}/notebooks/${nb.id}`, { headers: admin, data: { gaps: { mentioned: ["instrument"], notes: [], instName: null, usedAI: true, fallback: "" } } });
  const errors = await open(page, `/n/${nb.id}`);
  const card = page.getByRole("region", { name: "Questions about your idea" });
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText(/Question 1 of \d/);
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Experiments" })).toBeVisible({ timeout: 30_000 });
  await expect(card).toHaveCount(0);
  await page.goto(`/n/${nb.id}/e/1`);
  const head = page.locator(".verdict-head");
  await expect(head).toBeVisible({ timeout: 30_000 });
  expect(await head.textContent()).not.toContain(";");
  await expect(page.getByTestId("verdict-checks")).toContainText(/\S/);
  expect(errors).toEqual([]);
});
