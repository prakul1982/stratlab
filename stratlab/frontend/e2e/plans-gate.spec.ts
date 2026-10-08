import { expect, test, type Page } from "@playwright/test";

// Plans gate from day one (the owner's decision, 7 Oct): signed in as Free, Basic and Pro on pages holding a paid
// feature, the lock shows (with the plan, and how to ask for early access while paid plans aren't on sale), the server
// refuses the action with that same honest message, and the plan that includes it works. Users load-60 to load-65
// (load-N is Free, Basic or Pro by N % 3).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const HINT = "ask us at support@stratlab.studio for early access";

type Plan = "free" | "basic" | "pro";
const user = (plan: Plan, phone: boolean) => 60 + (phone ? 3 : 0) + ({ free: 0, basic: 1, pro: 2 } as const)[plan];

async function signIn(page: Page, n: number) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer load-${n}` }, data: { level: "some", focus: "both" } });
  const session = { ...base, access_token: `load-${n}`, user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  return errors;
}

const call = (page: Page, n: number, method: "GET" | "POST" | "PUT", path: string, data?: object) =>
  page.request.fetch(`${API}${path}`, { method, headers: { Authorization: `Bearer load-${n}` }, ...(data ? { data } : {}) });

/** One gated page: the page, what its plan is, and an action the server refuses below that plan. */
const CASES: { path: string; ready: RegExp; plan: Plan; feature: string; action: [("GET" | "POST" | "PUT"), string, object?] }[] = [
  { path: "/research/scan", ready: /Trend scan/, plan: "basic", feature: "scans", action: ["PUT", "/research/scan/alerts", { on: true }] },
  { path: "/trade/replay", ready: /Chart replay/i, plan: "basic", feature: "chart_replay", action: ["POST", "/trade/replay", { instrument: "CRYPTO:BTC-USD", tf: "1d", random: true }] },
  { path: "/invest/breadth", ready: /breadth/i, plan: "basic", feature: "breadth", action: ["POST", "/invest/breadth/alerts", { group: "nifty50", level: 50 }] },
  { path: "/money/us-tax", ready: /US/, plan: "pro", feature: "us_tax", action: ["GET", "/money/us-tax/schedule-fa.csv?cy=2025"] },
];
const RANK: Record<Plan, number> = { free: 0, basic: 1, pro: 2 };

for (const who of ["free", "basic", "pro"] as Plan[]) {
  test(`plans gate: signed in on ${who}, each gated page shows its lock or works`, async ({ page }, info) => {
    test.setTimeout(150_000);
    const phone = info.project.name === "phone";
    const n = user(who, phone);
    const errors = await signIn(page, n);
    const me = await (await call(page, n, "GET", "/me")).json();
    expect(me.plan, "the fake user's plan").toBe(who);
    for (const c of CASES) {
      await page.goto(c.path);
      const main = page.locator("main");
      await expect(main.getByRole("heading", { level: 1 }).first()).toHaveText(c.ready, { timeout: 30_000 });
      await page.waitForTimeout(600);
      const lock = main.locator(".plan-note");
      const r = await call(page, n, ...c.action);
      if (RANK[who] < RANK[c.plan]) {
        // the lock says which plan, and how to get it while paid plans aren't on sale
        await expect(lock.first(), `${c.path} on ${who}`).toBeVisible();
        await expect(lock.first()).toContainText(c.plan === "pro" ? "Pro" : "Basic");
        await expect(lock.first()).toContainText(HINT);
        expect(await lock.count(), "one note, not two").toBe(1);
        // the server refuses it, with the same honest words
        expect(r.status(), `${c.action[1]} on ${who}`).toBe(402);
        const d = (await r.json()).detail;
        expect(d.code).toBe("upgrade_required");
        expect(d.message).toContain(HINT);
      } else {
        await expect(lock, `${c.path} on ${who}: no lock`).toHaveCount(0);
        expect(r.status(), `${c.action[1]} on ${who}`).not.toBe(402);
      }
    }
    // the menu marks whole pages that are locked (desktop: the menu is always open)
    if (!phone) {
      await page.goto("/research/scan");
      const entry = page.locator("aside.sidebar").getByRole("link", { name: /Trend scan/ });
      await expect(entry).toBeVisible({ timeout: 30_000 });
      if (who === "free") await expect(entry.locator(".side-lock")).toHaveAttribute("data-plan", "Basic");
      else await expect(entry.locator(".side-lock")).toHaveCount(0);
    }
    const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
    expect(errors).toEqual([]);
  });
}

test("plans gate: Pricing and Plans say paid plans open soon, never that paid features are open to everyone", async ({ page }, info) => {
  const n = user("free", info.project.name === "phone");
  await signIn(page, n);
  await page.goto("/plans");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { level: 1, name: "Plans" })).toBeVisible({ timeout: 30_000 });
  await expect(main).toContainText("Basic and Pro aren't on sale yet");
  await expect(main).toContainText("support@stratlab.studio");
  await expect(main).not.toContainText(/every feature is (open|unlocked)|open to everyone until/i);
  await expect(main.getByText("Opens soon")).toHaveCount(2);
});

test("plans gate: while plans can't be bought, a lock offers 'Tell me when plans open', kept per person and counted for Admin", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const n = user("free", phone) + 6;                                   // load-66 / load-69: a Free user of its own
  const admin = { Authorization: "Bearer admin-token" };
  const count = async () => (await (await page.request.get(`${API}/admin/overview`, { headers: admin })).json()).stats.plan_interest as number;
  const errors = await signIn(page, n);
  await call(page, n, "GET", "/me");
  await page.request.delete(`${API}/me/plan-interest`, { headers: { Authorization: `Bearer load-${n}` } });
  await page.goto("/research/scan");
  const lock = page.locator("main .plan-note").first();
  await expect(lock).toContainText(HINT, { timeout: 30_000 });
  await expect(lock.getByRole("link", { name: "See plans" }), "a dead-end link while nothing can be bought").toHaveCount(0);
  await lock.getByRole("button", { name: "Tell me when plans open" }).click();
  await expect(lock).toContainText("You're on the list");
  expect((await (await call(page, n, "GET", "/me/plan-interest")).json()).registered).toBe(true);
  expect(await count(), "Admin counts the person (the desktop and phone runs share one list, so no exact total)").toBeGreaterThanOrEqual(1);
  await page.reload();
  await expect(page.locator("main .plan-note").first()).toContainText("You're on the list", { timeout: 30_000 });
  // the Plans page shows the same answer, and Undo takes them off
  await page.goto("/plans");
  const note = page.getByRole("note", { name: "Paid plans aren't on sale yet" });
  await expect(note).toContainText("You're on the list", { timeout: 30_000 });
  await note.getByRole("button", { name: "Undo" }).click();
  await expect(note.getByRole("button", { name: "Tell me when plans open" })).toBeVisible();
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});
