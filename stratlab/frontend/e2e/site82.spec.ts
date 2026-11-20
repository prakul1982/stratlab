import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// site82 (Release 82) on the fake world, desktop and phone. Every layout-shift check holds the slow part of the page back on purpose, so it
// holds on any machine and any fonts (CI has none of this machine's): the page must keep the room, not win a race.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const ZIP = path.resolve(process.cwd(), "../backend/tests/fixtures/taxpnl/zerodha_taxpnl_2024_2025.zip");

/** An address as production serves it: the build's own page (dist/<path>/index.html), which vite preview serves only with the slash. */
async function servedAsLive(page: Page, p: string) {
  await page.route((u) => u.pathname === p, (r) => r.request().resourceType() === "document"
    ? r.fulfill({ status: 200, contentType: "text/html", body: readFileSync(new URL(`../dist${p}/index.html`, import.meta.url), "utf8") })
    : r.fallback());
}

async function signedIn(page: Page, token: string) {
  const known: Record<string, [string, string]> = { "free-token": ["u-free", "free@example.com"], "pro-token": ["u-pro", "u-pro@example.com"], "admin-token": ["u-admin", "owner@example.com"] };
  const [id, email] = known[token] ?? [`u-${token}`, `${token.replace("-", "")}@example.com`];
  const user = { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} };
  await page.addInitScript(([t, u]) => {
    try {
      localStorage.setItem("sb-demo-auth-token", JSON.stringify({ access_token: t, token_type: "bearer", expires_in: 3600, expires_at: 4102444800, refresh_token: "r", user: u }));
      localStorage.setItem("stratlab.tour.v1", "1");
      localStorage.setItem("stratlab.consent.v1", "no");
    } catch { /* none */ }
  }, [token, user] as const);
  await page.route(`${API}/me`, async (r) => { const res = await r.fetch(); await r.fulfill({ response: res, json: { ...(await res.json()), established: true } }); });
}

async function countShifts(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __moves: number };
    w.__moves = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) w.__moves += e.value;
    }).observe({ type: "layout-shift", buffered: true });
  });
}
const shifts = (page: Page) => page.evaluate(() => (window as unknown as { __moves: number }).__moves);
const held = (page: Page, re: RegExp, ms: number) => page.route(re, async (r) => { await new Promise((ok) => setTimeout(ok, ms)); await r.fallback(); });
const box = (page: Page, sel: string) => page.locator(sel).evaluateAll((es) => es.map((e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; }));

test.use({ serviceWorkers: "block" });

// LIVE19B-002: on a phone the Monthly/Yearly switch was stretched to the row with "Monthly" filling half and "Yearly · about 2 months free"
// squeezed to the edge, and "₹ INR / $ USD" sat alone at 118px on the row under it. Both switches take the row now, each choice an equal half.
test("visitor /plans on a phone: the billing and currency switches are one width, each choice an equal half, and nothing moves", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "a phone's layout");
  await servedAsLive(page, "/plans");
  await countShifts(page);
  await page.route(`${API}/pricing`, async (r) => {
    const res = await r.fetch(); const j = await res.json();
    await new Promise((ok) => setTimeout(ok, 800));
    await r.fulfill({ response: res, json: { ...j, offer: { ...(j.offer ?? {}), mode: "paid", payments: true, yearly: true, promo_until: null }, invoice: { gst: false } } });
  });
  await page.goto("/plans");
  const segs = page.locator(".lp-period .k-seg");
  await expect(segs).toHaveCount(2, { timeout: 30_000 });
  await expect(page.locator(".lp-price").first()).toBeVisible();
  const row = (await box(page, ".lp-period"))[0];
  const [bill, cur] = await box(page, ".lp-period .k-seg");
  expect(Math.abs(bill.w - cur.w), "the two switches are one width").toBeLessThanOrEqual(2);
  expect(bill.w, "and take the row").toBeGreaterThanOrEqual(row.w - 4);
  for (const s of [0, 1]) {
    const b = await box(page, `.lp-period .k-seg >> nth=${s} >> button`);
    expect(Math.abs(b[0].w - b[1].w), `switch ${s}: equal halves`).toBeLessThanOrEqual(2);
    expect(b[0].h, `switch ${s}: one row`).toBeLessThanOrEqual(52);
  }
  await page.waitForTimeout(800);
  expect(await shifts(page), "nothing moved when the prices came").toBeLessThan(0.005);
});

// LIVE19B-008: the journal's "Trades up to …" row was inserted under the lede once the trades came (phone CLS 0.059), and its "Add to my trades
// / Replace imported trades" switch was 248px and stacked while the tax report's is the card's width.
test("trade journal on a phone: the as-of row is there from the first frame and the upload card's controls are the card's width", async ({ page, request }, info) => {
  test.skip(info.project.name !== "phone", "a phone's layout");
  const token = "site82-0";
  const auth = { Authorization: `Bearer ${token}` };
  await request.delete(`${API}/trade/journal`, { headers: auth });
  const up = await request.post(`${API}/trade/journal/import?filename=z.zip&mode=add`, { headers: { ...auth, "Content-Type": "application/octet-stream" }, data: readFileSync(ZIP) });
  expect(up.ok()).toBeTruthy();
  await signedIn(page, token);
  await countShifts(page);
  await held(page, /\/trade\/journal\?/, 2500);
  await page.goto("/trade/journal");
  await expect(page.getByText(/^Trades up to /)).toBeVisible({ timeout: 30_000 });
  const switchBox = (await box(page, ".j-bring .k-card-actions > .k-seg"))[0];
  const card = (await box(page, ".j-bring"))[0];
  expect(switchBox.w, "the switch is the card's width less its padding").toBeGreaterThan(card.w - 70);
  const btns = await box(page, ".j-bring .k-card-actions > .btn");
  expect(new Set(btns.map((b) => b.w)).size, "the buttons are one width").toBe(1);
  await page.waitForTimeout(600);
  expect(await shifts(page), "nothing moved when the trades came").toBeLessThan(0.01);
});

// LIVE19B-006: the options builder on a phone: "Other underlyings (238)…" was inserted under the index chips at 5.1 s and the expiry switch
// turned from a row into three full-width rows, pushing the page down (CLS 0.038).
test("options builder on a phone: the underlyings list and the expiry row hold their place while the underlyings come", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "a phone's layout");
  await signedIn(page, "site82-1");
  await countShifts(page);
  await held(page, /\/options\/underlyings/, 2500);
  await page.goto("/options");
  const other = page.getByRole("combobox", { name: "Other underlyings" });
  await expect(other).toBeVisible({ timeout: 30_000 });
  await expect(other).toBeDisabled();
  await expect(other).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByTestId("opt-expiry-note")).toBeVisible();
  const ex = await box(page, ".k-expiry > .k-seg button");
  expect(new Set(ex.map((b) => b.w)).size, "the expiry choices are one width, one under another").toBe(1);
  await page.waitForTimeout(600);
  expect(await shifts(page), "nothing moved when the underlyings came").toBeLessThan(0.01);
});

// LIVE19B-007: /holdings at 1440: the import card stood under a second loading card ("Opening your sectors and positions…") and was pushed down
// when By sector and Positions replaced it (CLS 0.052).
test("holdings: nothing under the second loading card moves when the sectors and positions come", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "measured at 1440 as live");
  await signedIn(page, "admin-token");
  await countShifts(page);
  await held(page, /\/holdings\/corp-actions/, 2500);
  await page.goto("/holdings");
  await expect(page.getByRole("heading", { name: "By sector" })).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  expect(await shifts(page), "nothing moved").toBeLessThan(0.01);
});

// LIVE19B-009: a Free reader's scan page drew one lock message at the top over "Opening…", then the page's own, different one lower down, and
// the first went: CLS 0.085. One message, drawn once, where it stays.
test("trend scan on Free: one lock message, drawn once in its place", async ({ page }) => {
  await signedIn(page, "site82-12");
  await countShifts(page);
  await held(page, /\/assets\/Research-[\w-]+\.js$/, 2000);
  const seen = new Set<string>();
  await page.exposeFunction("__note", (t: string) => { seen.add(t); });
  await page.addInitScript(() => {
    new MutationObserver(() => document.querySelectorAll("main .plan-note").forEach((n) => (window as unknown as { __note: (t: string) => void }).__note((n.textContent ?? "").slice(0, 20))))
      .observe(document, { childList: true, subtree: true });
  });
  await page.goto("/research/scan");
  await expect(page.getByRole("heading", { level: 1, name: "Trend scan" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("main .plan-note")).toHaveCount(1);
  await page.waitForTimeout(800);
  expect([...seen].length, `lock messages seen: ${[...seen].join(" | ")}`).toBe(1);
  expect(await shifts(page), "nothing moved").toBeLessThan(0.01);
});

// LIVE19B-003: on a cold launch public/early.js came after the app's own first calls, and asked them again: /public/data-online, /notebooks,
// /markets (and Trade's strip) went out twice. Held back here past the app's start, it asks nothing.
test("signed-in first load: each startup read goes out once, even when early.js comes after the app's own calls", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the same code on both");
  await signedIn(page, "site82-2");
  await held(page, /\/early\.js$/, 3000);
  const asked: string[] = [];
  page.on("request", (r) => { if (r.url().startsWith(API)) asked.push(r.url().slice(API.length)); });
  await page.goto("/trade");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(4000);
  for (const p of ["/public/data-online", "/notebooks", "/markets", "/trade/vix?brief=true"]) expect(asked.filter((a) => a === p).length, `${p} asked`).toBeLessThanOrEqual(1);
});

// LIVE19A-011: the results calendar's search sat under the filters, which come with the page's figures: it moved 265px down when they came
// (CLS 0.038 live). Every day's table also has the same columns at the same places.
test("results: nothing moves when the figures come, and the day tables' columns line up", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "measured at 1440 as live");
  await signedIn(page, "site82-3");
  await countShifts(page);
  await held(page, /\/research\/results\?/, 2000);
  await page.goto("/research/results?region=US");
  const days = page.getByTestId("results-day");
  await expect(days.first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  expect(await shifts(page), "nothing moved").toBeLessThan(0.01);
  const xs = await days.evaluateAll((ds) => ds.map((d) => Array.from(d.querySelectorAll("thead th")).map((th) => Math.round(th.getBoundingClientRect().left)).join(",")));
  expect(new Set(xs).size, `column starts per day: ${xs.join(" | ")}`).toBe(1);
});
