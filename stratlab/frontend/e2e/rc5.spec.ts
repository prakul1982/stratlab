import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// RC-5, the main review of the whole app as real people use it. The flows that broke, each driven in the browser:
// the tour's second step on a phone points at the magnifier (RC5-002), a deep dive that fails to open can be tried again
// (RC5-001), and the search finds Bajaj Auto under its own symbol (RC5-003).
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

test("RC5-002: on a phone the tour's second step rings the magnifier, not the page's heading where the menu's button was", async ({ page, request }, info) => {
  test.skip(info.project.name !== "phone", "the phone's menu");
  const u = who(277, true);
  await answer(request, u);
  const errors = await signIn(page, u, "/mine");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => window.dispatchEvent(new Event("stratlab:tour")));
  const tour = page.getByRole("dialog", { name: "A quick tour" });
  await expect(tour).toBeVisible();
  await tour.getByRole("button", { name: "Next" }).click();
  await expect(tour).toContainText("Ask or do anything");
  await expect(page.locator("aside.sidebar.open")).toHaveCount(0);
  const ring = page.locator(".k-coach-ring");
  const magnifier = page.getByRole("button", { name: "Search or ask anything" });
  await expect(ring).toBeVisible();
  await expect.poll(async () => {
    const [r, m] = [await ring.boundingBox(), await magnifier.boundingBox()];
    return r && m ? Math.max(Math.abs(r.x - (m.x - 4)), Math.abs(r.y - (m.y - 4))) : 999;
  }, "the ring sits on the magnifier").toBeLessThanOrEqual(3);
  expect(errors).toEqual([]);
});

test("RC5-001: a deep dive that fails to open says so and Try again opens it", async ({ page, request }, info) => {
  const u = who(283, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/mine");
  await expect(page.locator("main h1")).toBeVisible({ timeout: 30_000 });
  let fail = true;
  await page.route(`${API}/research/deep/TCS*`, (r) => (fail && r.request().method() === "GET" && !r.request().url().includes("/deck")
    ? r.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error", headers: { "access-control-allow-origin": "*" } }) : r.fallback()));
  await page.goto("/research/IN/TCS/deep");
  const state = page.getByText("The deep dive couldn't be opened");
  await expect(state).toBeVisible({ timeout: 30_000 });
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(state).toHaveCount(0);
  await expect(page.locator("main h1")).toContainText("business, capex and growth");
  await expect(page.getByText("Reading the reported numbers")).toHaveCount(0, { timeout: 30_000 });
  expect(errors.filter((e) => !/Internal Server Error|500/.test(e))).toEqual([]);
});

test("RC5-003: searching Bajaj Auto offers BAJAJ-AUTO, and its page opens", async ({ page, request }, info) => {
  const u = who(285, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/research");
  const box = page.getByRole("combobox").first();
  await box.fill("bajaj auto");
  const pick = page.getByRole("option", { name: /Bajaj Auto/ }).first();
  await expect(pick).toBeVisible({ timeout: 30_000 });
  await expect(pick).toContainText("BAJAJ-AUTO");
  await pick.click();
  await expect(page).toHaveURL(/\/research\/IN\/BAJAJ-AUTO$/);
  await expect(page.locator("main h1")).toContainText("Bajaj Auto", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("RC5-004: an IPO address no issue has says so, with no Try again", async ({ page, request }, info) => {
  const u = who(279, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/invest/ipos/no-such-issue");
  await expect(page.getByText("That IPO isn't on the list").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Try again" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "← All IPOs" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("RC5-005: with nowhere to send alerts the Alerts page says it once, in whole sentences", async ({ page, request }, info) => {
  const u = who(265, info.project.name === "phone");
  await answer(request, u);
  const errors = await signIn(page, u, "/alerts");
  const summary = page.getByTestId("alerts-summary");
  await expect(summary).toBeVisible({ timeout: 30_000 });
  await expect(summary).toContainText("Shown on this page only");
  await expect(summary).not.toContainText("Sent by");
  const main = page.locator("main");
  // one explanation of why nothing is sent, not the same one twice
  expect(await main.getByText(/listed here and nowhere else/).count()).toBe(1);
  await expect(main.getByText("Alerts go to your email once you've confirmed")).toHaveCount(0);
  expect(errors).toEqual([]);
});
