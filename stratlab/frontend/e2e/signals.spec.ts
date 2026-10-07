import { expect, test, type Page } from "@playwright/test";

// Signal forward test (Trade space): make the secret webhook URL, start a signal session on a coin (crypto never closes,
// so the test doesn't depend on the clock), send a test signal from the page and a real one to the URL, see both in the
// signal log, and see a wrong URL and another session id refused. Each project signs in as its own Pro account.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, where: string, ready: string, who: ReturnType<typeof sessionFor>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(where);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(where);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

/** The page's words, leaving out code (the JSON format and the signal names, which are the alert's own words). */
async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").evaluate((m) => {
    const c = m.cloneNode(true) as HTMLElement;
    c.querySelectorAll("code, pre").forEach((x) => x.remove());
    return c.innerText;
  });
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /nseindia|yahoo|finnhub|coinbase|kite connect/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(you should|buy|sell|accumulate|avoid)\b/i);
}

test("signal forward test: the URL, a session, a test signal and a webhook signal in the log", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 221 : 218;                  // Pro accounts in the fake world
  const auth = { Authorization: `Bearer load-${n}` };
  for (const r of await (await request.get(`${API}/live/sessions`, { headers: auth })).json()) {
    if (r.status === "running") await request.post(`${API}/live/sessions/${r.id}/stop`, { headers: auth });
  }
  await request.delete(`${API}/live/sessions`, { headers: auth });
  await request.delete(`${API}/trade/signals/hook`, { headers: auth });

  const errors = await open(page, "/trade/signals", "No URL yet", sessionFor(n));
  await sane(page, errors);
  await page.getByRole("button", { name: "Make my URL" }).click();
  const box = page.getByRole("textbox", { name: "Webhook URL", exact: true });
  await expect(box).toHaveValue(/\/hooks\/signal\/[A-Za-z0-9_-]{43}$/);
  const hookUrl = await box.inputValue();
  await expect(page.getByText("Copy it now: it isn't shown again.")).toBeVisible();

  await page.getByLabel("Market").first().selectOption("CRYPTO");
  await page.getByRole("button", { name: "BTC/USD" }).first().click();
  await page.getByLabel("Paper capital").fill("100000");
  await page.getByRole("button", { name: "Start session" }).click();
  await expect(page.getByTestId("sg-name")).toHaveText(/BTC\/USD/, { timeout: 30_000 });
  const sid = await page.getByTestId("sg-id").innerText();
  await expect(page.getByTestId("sg-verdict-wait")).toHaveText("0 of 30 closed trades: the luck checks run once there are 30.");

  await page.getByLabel("Test quantity").fill("0.01");
  await page.getByRole("button", { name: "Send a test buy signal" }).click();
  await expect(page.getByTestId("sg-position")).toHaveText(/^Long 0\.01 at /);
  const log = page.getByRole("table", { name: "Signal log" });
  await expect(log.locator("tr[data-status=filled]")).toHaveCount(1);

  // the alert service's side: a signal to the secret URL, a wrong URL, another session id
  const sent = await request.post(hookUrl, { data: JSON.stringify({ session: sid, action: "exit", id: `e2e-${Date.now()}`, price: 1 }), headers: { "Content-Type": "text/plain" } });
  expect(sent.status()).toBe(200);
  expect((await sent.json()).status).toBe("filled");
  expect((await request.post(hookUrl.slice(0, -1) + (hookUrl.endsWith("A") ? "B" : "A"), { data: { session: sid, action: "exit" } })).status()).toBe(404);
  expect((await request.post(hookUrl, { data: { session: "00000000-0000-4000-8000-000000000000", action: "exit" } })).status()).toBe(404);
  expect((await request.post(hookUrl, { data: { session: sid, action: "buy", qty: 1, run: "anything" } })).status()).toBe(400);

  await page.reload();
  await expect(page.getByTestId("sg-position")).toHaveText("None", { timeout: 30_000 });
  await expect(page.getByRole("table", { name: "Signal log" }).locator("tr[data-status=filled]")).toHaveCount(2);
  await expect(page.getByRole("table", { name: "Closed trades" })).toBeVisible();
  await sane(page, errors);

  await page.getByRole("button", { name: "Stop session" }).click();
  await page.getByRole("dialog", { name: "Stop this session?" }).getByRole("button", { name: "Stop session" }).click();
  await expect(page.getByRole("button", { name: "Delete" })).toBeVisible();
  expect((await request.post(hookUrl, { data: { session: sid, action: "exit" } })).status()).toBe(409);

  await page.goto("/trade/signals");
  await expect(page.getByTestId("sg-hook")).toContainText("Last signal");
  await page.getByText("Signals that reached no session").click();
  await expect(page.getByText("No signal session with that id on this account.").first()).toBeVisible();
  await sane(page, errors);
});
