import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// RC-6, the main review of the whole app as real people use it. The flows that broke, each driven in the browser:
// a ticker as another site writes it (TCS.NS) opens the company (RC6-001), a company typed under the wrong market is
// offered under the right one (RC6-002), and the pages whose first read fails offer Try again (RC6-004, RC6-005).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const who = (n: number, phone: boolean) => { const i = n + (phone ? 1 : 0); return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` }; };
type Who = ReturnType<typeof who>;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });

async function signIn(page: Page, u: Who, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: u.token, user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated", app_metadata: {}, user_metadata: {} } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}
const answer = (request: APIRequestContext, u: Who, focus = "invest", space = "invest") => request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus, space } });

test("RC6-001: /research/IN/TCS.NS opens TCS at TCS's own address, and the search finds it by that ticker", async ({ page, request }, info) => {
  const u = who(140, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/research/IN/TCS.NS");
  await expect(page).toHaveURL(/\/research\/IN\/TCS$/, { timeout: 30_000 });
  await expect(page.locator("main h1")).toContainText("Tata Consultancy", { timeout: 30_000 });
  await expect(page.getByText("No listed company called")).toHaveCount(0);
  // typed into the box, a ticker with its exchange finds the company
  await page.goto("/research");
  const box = page.getByRole("combobox").first();
  await box.fill("NSE:TCS");
  await expect(page.getByRole("option", { name: /Tata Consultancy/ }).first()).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("RC6-002: a US company typed under India is offered under the United States, not a dead end", async ({ page, request }, info) => {
  const u = who(142, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/research/IN/APPLE");
  await expect(page.getByText("No listed company called APPLE")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("isn't an NSE symbol or BSE code we know")).toBeVisible();
  const other = page.getByLabel("Matches in the United States");
  await expect(other.getByRole("link", { name: "AAPL" })).toBeVisible({ timeout: 30_000 });
  await other.getByRole("link", { name: "AAPL" }).click();
  await expect(page).toHaveURL(/\/research\/US\/AAPL$/);
  await expect(page.locator("main h1")).toContainText("Apple", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("RC6-005: the trend scan whose groups can't be read says so and Try again loads them", async ({ page, request }, info) => {
  const u = who(144, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/mine");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  let fail = true;
  await page.route(`${API}/research/scan/sets*`, (r) => (fail
    ? r.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error", headers: { "access-control-allow-origin": "*" } }) : r.fallback()));
  await page.goto("/research/scan");
  const state = page.getByText("The groups to scan couldn't be loaded");
  await expect(state).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Scan", exact: true })).toHaveCount(0);       // no Scan button to press on an empty box
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(state).toHaveCount(0);
  await expect(page.getByLabel("Group to scan")).toBeVisible();
  expect(errors.filter((e) => !/Internal Server Error|500/.test(e))).toEqual([]);
});

test("RC6-004: the invite page and the newsletter settings whose read fails offer Try again", async ({ page, request }, info) => {
  const u = who(146, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/mine");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  let fail = true;
  const down = (r: import("@playwright/test").Route) => (fail
    ? r.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error", headers: { "access-control-allow-origin": "*" } }) : r.fallback());
  await page.route(`${API}/me/referrals*`, down);
  await page.route(`${API}/me/newsletters*`, (r) => (r.request().method() === "GET" ? down(r) : r.fallback()));
  await page.goto("/invite");
  await expect(page.getByText("Your invite link isn't available right now")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Reload the page")).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByLabel("Your invite link")).toBeVisible({ timeout: 30_000 });
  fail = true;
  await page.goto("/settings");
  await expect(page.getByText("Couldn't load your newsletter settings")).toBeVisible({ timeout: 30_000 });
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("Couldn't load your newsletter settings")).toHaveCount(0);
  await expect(page.getByText("Market brief: India")).toBeVisible({ timeout: 30_000 });
  expect(errors.filter((e) => !/Internal Server Error|500/.test(e))).toEqual([]);
});

test("RC6-010: a holdings file that can't be read keeps its reason on the page beside the upload", async ({ page, request }, info) => {
  const u = who(148, info.project.name === "phone");
  await answer(request, u, "money", "money");
  const errors = await signIn(page, u, "/holdings");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Holdings file").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("these are not my holdings\n") });
  const why = page.getByTestId("upload-problem");
  await expect(why).toContainText("We couldn't find the holdings in that file", { timeout: 30_000 });
  await expect(page.locator(".toast")).toHaveCount(0, { timeout: 20_000 });          // the toast is gone; the reason is not
  await expect(why).toBeVisible();
  // a good file clears it
  const csv = "Stock Name,Quantity,Average Buy Price\nTCS,10,3200\nINFY,5,1450\n";
  await page.getByLabel("Holdings file").setInputFiles({ name: "paytm_style.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("2 stocks saved.")).toBeVisible({ timeout: 30_000 });
  await expect(why).toHaveCount(0);
  await expect(page.getByRole("cell", { name: /TCS/ }).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("RC6-014: deleting a notebook with a running paper session says the session stays", async ({ page, request }, info) => {
  const u = who(150, info.project.name === "phone");
  await answer(request, u, "trade", "trade");
  const EMA = { name: "R6 trend", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }], exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }],
    risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: auth(u), data: { name: "R6 trend", question: "q", strategy: EMA, instrument: "CRYPTO:BTC-USD" } })).json();
  const quiet = await (await request.post(`${API}/notebooks`, { headers: auth(u), data: { name: "R6 quiet", question: "q", strategy: { ...EMA, name: "R6 quiet" }, instrument: "CRYPTO:ETH-USD" } })).json();
  const run = await request.post(`${API}/live/sessions`, { headers: auth(u), data: { notebook_id: nb.id, strategy: EMA, instrument: "CRYPTO:BTC-USD", name: "R6 trend", capital: 10000 } });
  expect(run.ok()).toBeTruthy();
  const errors = await signIn(page, u, `/n/${nb.id}`);
  await expect(page.getByRole("link", { name: /Paper trading · open/ })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "More" }).first().click();
  await page.getByRole("menuitem", { name: "Delete notebook" }).click();
  const dlg = page.getByRole("dialog", { name: /Delete the notebook/ });
  await expect(dlg).toContainText("Its paper session is running and stays running");
  await expect(dlg.getByRole("link", { name: "Paper trading" })).toBeVisible();
  await dlg.getByRole("button", { name: "Cancel" }).click();
  // a notebook with no session says nothing of one
  await page.goto(`/n/${quiet.id}`);
  await expect(page.locator("main h1, main input").first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "More" }).first().click();
  await page.getByRole("menuitem", { name: "Delete notebook" }).click();
  await expect(page.getByRole("dialog", { name: /Delete the notebook/ })).not.toContainText("paper session");
  expect(errors).toEqual([]);
});
