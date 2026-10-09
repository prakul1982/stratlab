import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

// Round 11 review of the live site (9 Oct 2026): what the app draws, on the reviewer's examples. Every answer a test depends on
// is fixed here, so none waits on whether one of the fake world's jobs has run.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const ZIP = path.resolve(process.cwd(), "../backend/tests/fixtures/taxpnl/zerodha_taxpnl_2024_2025.zip");
const base = { token_type: "bearer", expires_in: 86400, expires_at: 4102444800, refresh_token: "r" };
type Mock = [RegExp, unknown | ((r: Route) => Promise<void>)];
type User = { token: string; id: string; email: string };
const owner: User = { token: "admin-token", id: "u-admin", email: "owner@example.com" };

async function open(page: Page, where: string, mocks: Mock[] = [], user: User = owner) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", async (r) => {
    const u = new URL(r.request().url());
    const call = ["fetch", "xhr"].includes(r.request().resourceType());       // the page's own address is never an answer
    for (const [re, body] of call ? mocks : []) {
      if (re.test(u.pathname + u.search)) {
        if (typeof body === "function") return (body as (r: Route) => Promise<void>)(r);
        return r.fulfill({ status: 200, body: JSON.stringify(body), contentType: "application/json" });
      }
    }
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: user.token, user: { id: user.id, aud: "authenticated", email: user.email, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } };
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(where);
  return errors;
}

/** The fake world's own answer for a request, changed by `edit`. */
const edited = (edit: (j: Record<string, any>) => Record<string, any>) => async (r: Route) => {
  const res = await r.fetch();
  return r.fulfill({ response: res, json: edit(await res.json()) });
};

// ---------- R11P-010: a zero change is flat ----------
test("My space: USD/INR that rounds to no change says Unchanged, with no arrow (R11P-010)", async ({ page }) => {
  const candles = ["2026-10-07", "2026-10-08", "2026-10-09"].map((d, i) => ({ t: `${d}T00:00:00+05:30`, o: 96.7, h: 96.9, l: 96.6, c: [96.9, 96.7599, 96.76][i], v: 0 }));
  const errors = await open(page, "/mine", [[/\/chart\/candles\/FX(%3A|:)USDINR/, { currency: "INR", source: "x", tf: "1d", more: false, candles }]]);
  const fx = page.locator('.mine-mkt[data-market="usdinr"]');
  await expect(fx.locator(".mine-mkt-v")).toHaveText("96.76", { timeout: 30_000 });
  const delta = fx.locator(".k-delta");
  await expect(delta).toHaveText(/Unchanged\s*0\.00%/);
  await expect(delta).not.toContainText("Up");
  await expect(delta).not.toContainText("▲");
  await expect(delta).not.toContainText("▼");
  expect(errors).toEqual([]);
});

// ---------- R11P-006: the holiday count ----------
test("Admin: holidays that all came from the exchange are not 'added by you' (R11P-006)", async ({ page }) => {
  const calendar = (byHand: string[]) => edited((j) => ({
    ...j, server: { ...j.server, calendar: { ...(j.server?.calendar ?? {}), known_until: "2026-12-31", covered_until: "2027-12-31", days_left: 448,
      added: Array.from({ length: 20 }, (_, i) => `2027-${String((i % 12) + 1).padStart(2, "0")}-${String(10 + Math.floor(i / 12)).padStart(2, "0")}`),
      by_hand: byHand, auto: { at: "2026-10-09T10:00:00+00:00", tried_at: "2026-10-09T10:00:00+00:00", error: null, count: 20 } } } }));
  let errors = await open(page, "/admin/data", [[/\/admin\/overview/, calendar([])]]);
  const panel = page.locator("section", { has: page.getByRole("heading", { name: "Exchange holidays" }) });
  await expect(panel).toContainText("20 saved, all from the exchange.", { timeout: 30_000 });
  await expect(panel).not.toContainText("added by you");
  expect(errors).toEqual([]);
  await page.unrouteAll({ behavior: "ignoreErrors" });
  errors = await open(page, "/admin/data", [[/\/admin\/overview/, calendar(["2027-03-22", "2027-03-23"])]]);
  await expect(panel).toContainText("20 saved: 18 from the exchange, 2 added by you.", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

// ---------- R11P-007: System's AI lines ----------
test("Admin System: a provider out of credit is marked and last in 'Who is asked', and a long link is cut (R11P-007)", async ({ page }) => {
  const now = Date.now() / 1000;
  const url = "https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai%3Fmodal%3Dadd-credit-card%26x%3D" + "a".repeat(140);
  const provider = (name: string, label: string, extra: Record<string, unknown> = {}) => ({
    name, label, configured: true, missing: [], key_url: `https://example.com/${name}`, free: "Free: plenty.", terms: "ok", note: "",
    variables: [`${name.toUpperCase()}_API_KEY`], model_variable: `${name.toUpperCase()}_MODEL`, state: "ok", state_text: "Working.",
    quota: { limited: false, reset_at: null, remaining: null, remaining_at: null }, last_ok: now - 60, last_error: null, last_used_model: "m",
    pinned: null, pinned_by: null, ranked_at: now - 7200, rank_error: null, discovered: 3, skipped: {}, probing: false, models: [], blocked: [], ...extra });
  const view = {
    providers: [
      provider("huggingface", "Hugging Face", { state: "warn", state_text: "Free credit was used up when its models were last measured; it resets on its own.",
        quota: { limited: true, reset_at: null, remaining: null, remaining_at: null }, rank_error: "stopped measuring: the free credit is used up" }),
      provider("vercel", "Vercel", { state: "warn", state_text: `403: AI Gateway requires a valid credit card on file. Visit ${url} to add one.` }),
      provider("groq", "Groq"),
    ],
    routes: { quick: { label: "Idea builder and quick answers", budget_s: 30, steps: [
      { provider: "groq", label: "Groq", model: "llama-3.3-70b-versatile", ready: true, out_of_credit: false },
      { provider: "huggingface", label: "Hugging Face", model: "some/model", ready: true, out_of_credit: true }] } },
    cache: { entries: 0, hits: 0, misses: 0 }, rerank_every_hours: 6, last_failure: null,
  };
  const errors = await open(page, "/admin/system", [[/\/admin\/ai$/, view]]);
  const panel = page.locator("section[aria-label='AI']");
  await expect(panel.getByText(/Groq · llama-3.3-70b-versatile → Hugging Face · some\/model \(out of credit\)/)).toBeVisible({ timeout: 30_000 });
  const hf = panel.locator(".ai-provider", { hasText: "Hugging Face" });
  await expect(hf.getByText("Check", { exact: true })).toBeVisible();
  await expect(hf).not.toContainText("Working");
  const vercel = panel.locator(".ai-provider", { hasText: "Vercel" });
  const text = await vercel.innerText();
  expect(text).toContain("https://vercel.com/d?to=");
  expect(text).not.toContain("a".repeat(100));                                // the 150-character link is cut
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

// ---------- R11P-009: the journal's dots ----------
test("Trade journal: the strength-of-evidence dots have a role for their label (axe aria-prohibited-attr, R11P-009)", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 262 : 260;
  const user: User = { token: `load-${n}`, id: `u-load-${n}`, email: `load${n}@example.com` };
  expect((await request.delete(`${API}/trade/journal`, { headers: { Authorization: `Bearer ${user.token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/trade/journal", [], user);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  await welcome.waitFor({ timeout: 4000 }).then(() => welcome.getByRole("button", { name: /^All of it/ }).click()).catch(() => undefined);
  await page.getByLabel("Tradebook or tax P&L files").setInputFiles(ZIP);
  await expect(page.getByText("16 trade lines added")).toBeVisible({ timeout: 30_000 });
  const dots = page.locator(".dots");
  await expect(dots).toHaveAttribute("role", "img", { timeout: 30_000 });
  await expect(dots).toHaveAttribute("aria-label", /\d/);
  const r = await new AxeBuilder({ page }).withRules(["aria-prohibited-attr"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((x) => x.target.join(" ")).join(", ")}`)).toEqual([]);
  expect(errors).toEqual([]);
  await request.delete(`${API}/trade/journal`, { headers: { Authorization: `Bearer ${user.token}` } });
});
