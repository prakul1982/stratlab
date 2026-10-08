import { expect, test, type Page } from "@playwright/test";

// Signed figures are coloured: a gain, a rise or a net long is green (k-up), a loss, a fall or a net short red (k-down),
// zero stays plain, and the sign (+ / −) or the ▲ / ▼ is still printed, so the colour never carries the meaning alone.
// With E2E_SHOTS=<folder> (and E2E_SHOT_TAG=before|after) the same pages are photographed in light and dark.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const SHOTS = process.env.E2E_SHOTS;
const TAG = process.env.E2E_SHOT_TAG ?? "after";

async function open(page: Page, path: string, ready: string) {
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
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  return errors;
}

test("positioning: every change and net figure carries the up or down colour, and keeps its sign", async ({ page }) => {
  const errors = await open(page, "/trade/positioning", "Participant-wise open interest");
  const main = page.locator("main");
  const table = main.getByTestId("part-table");
  // the change line under each cell: a plus is green, a minus red, anything else plain
  const changes = table.locator(".k-sub-line");
  expect(await changes.count(), "the table has change lines").toBeGreaterThan(5);
  const lines = await changes.evaluateAll((els) => els.map((el) => ({ text: (el.textContent ?? "").trim(), coloured: el.querySelector(".k-up, .k-down")?.className ?? "" })));
  let ups = 0, downs = 0;
  for (const { text, coloured } of lines) {
    if (/^\+/.test(text)) { expect(coloured, text).toContain("k-up"); ups++; }
    else if (/^−/.test(text)) { expect(coloured, text).toContain("k-down"); downs++; }
    else expect(coloured, text).toBe("");
  }
  expect(ups, "some changes are up").toBeGreaterThan(0);
  expect(downs, "some changes are down").toBeGreaterThan(0);
  // the net futures column: the number itself is coloured with its sign
  const nets = await table.locator("tbody tr").evaluateAll((rows) => rows.map((r) => {
    const el = r.querySelectorAll("td")[2]?.querySelector(":scope > .k-up, :scope > .k-down");
    return el ? { text: (el.textContent ?? "").trim(), cls: el.className } : null;
  }));
  expect(nets.filter(Boolean).length, "some net figures are coloured").toBeGreaterThan(1);
  for (const n of nets) if (n) expect(n.cls, n.text).toContain(n.text.startsWith("+") ? "k-up" : "k-down");
  // across the page, green is never a minus and red is never a plus
  for (const t of await main.locator(".k-up").allInnerTexts()) expect(t.trim(), "green is never a minus").not.toMatch(/^−/);
  for (const t of await main.locator(".k-down").allInnerTexts()) expect(t.trim(), "red is never a plus").not.toMatch(/^\+/);
  // the headline net and its change from the day before
  const net = main.getByTestId("part-figs").locator(".k-stat").first();
  await expect(net.locator(".k-stat-v")).toHaveClass(/k-(up|down)/);
  await expect(net.locator(".k-stat-d .k-up, .k-stat-d .k-down")).toContainText(/^[+−]/);
  await expect(net.locator(".k-stat-d")).toContainText("from the day before");
  // a level stays plain
  await expect(table.locator("tbody tr").first().locator("td").nth(1).locator(":scope > .k-up, :scope > .k-down")).toHaveCount(0);
  // the FII/DII cash figures are coloured by sign too
  await expect(main.locator("#pos-cash .k-stat-v.k-up, #pos-cash .k-stat-v.k-down").first()).toBeVisible();
  expect(errors).toEqual([]);
});

// ---- before / after pictures ----
const SHOT_PAGES: [string, string, string][] = [["positioning", "/trade/positioning", "Participant-wise open interest"], ["holdings", "/holdings", "By sector"], ["mine", "/mine", "Good "]];

for (const [name, path, ready] of SHOT_PAGES) {
  test(`pictures: ${name}`, async ({ page }, info) => {
    test.skip(!SHOTS, "set E2E_SHOTS to take pictures");
    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await open(page, path, ready);
      await page.screenshot({ path: `${SHOTS}/${TAG}-${name}-${scheme}-${info.project.name}.png`, fullPage: true });
    }
  });
}

test("pictures: an experiment result", async ({ page, request }, info) => {
  test.skip(!SHOTS, "set E2E_SHOTS to take pictures");
  const SMA = (p: number) => ({ name: "Colours", tf: "1d", entry: [{ l: { t: "price" }, op: "xa", r: { t: "sma", p } }],
    exit: [{ l: { t: "price" }, op: "xb", r: { t: "sma", p } }], risk: { capital: 10000, sl: 0, tgt: 0, brokerage: 0, slippage: 0.05 } });
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `Colours ${info.project.name}`, strategy: SMA(20), instrument: "CRYPTO:BTC-USD" } })).json();
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await open(page, `/n/${nb.id}/e/1`, "Every trade");
    await page.screenshot({ path: `${SHOTS}/${TAG}-experiment-${scheme}-${info.project.name}.png`, fullPage: true });
  }
});
