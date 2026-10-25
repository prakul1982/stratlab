import { expect, test, type Page } from "@playwright/test";

// 24 Oct 2026 deep audit of notebooks after a run (DA-027 .. DA-041), as drawn: short trade cards on a phone, the compare
// chart on a date axis with both lines whole, the public link said on the page after a confirm, the notebook list's
// titles, and a run's trades as a CSV download. Signed in as the site owner (Pro), tour seen.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const EMA = (f: number, s: number) => ({ name: "DA2 EMA", tf: "1d", entry: [{ l: { t: "ema", p: f }, op: "xa", r: { t: "ema", p: s } }],
  exit: [{ l: { t: "ema", p: f }, op: "xb", r: { t: "ema", p: s } }], risk: { capital: 10000, sl: 0, tgt: 0, brokerage: 0, slippage: 0.05 } });

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab.onboarding.v1", "done");
  }, session);
  await page.goto(path);
  return errors;
}

async function notebook(request: import("@playwright/test").APIRequestContext, name: string) {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin,
    data: { name, question: "Does a 20/50 EMA cross on AAPL beat holding it, over five years of daily candles, after costs?", strategy: EMA(20, 50), instrument: "US:AAPL" } })).json();
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 1825 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  return { nb, exp: (await run.json()).experiment };
}

test("verdict: short trade cards on a phone, the trades as CSV, and a public link said on the page (DA-027, DA-033, DA-041)", async ({ page, request }, info) => {
  const { nb, exp } = await notebook(request, `DA2 verdict ${info.project.name}`);
  const errors = await open(page, `/n/${nb.id}/e/1`);
  await expect(page.locator(".verdict-head")).toBeVisible({ timeout: 30_000 });
  const trades = page.getByRole("region", { name: "Every trade", exact: true });
  const shortCards = trades.getByRole("radio", { name: "Short cards" });
  if (info.project.name === "phone") {
    await expect(shortCards).toHaveAttribute("aria-checked", "true");
    await expect(trades.locator("td[data-label='Qty']")).toHaveCount(0);           // when, then P&L and Return
    const h = await trades.locator("tbody tr").first().evaluate((el) => el.getBoundingClientRect().height);
    expect(h, "a short card").toBeLessThan(140);
    await trades.getByRole("radio", { name: "Every detail" }).click();
    await expect(trades.locator("td[data-label='Qty']").first()).toBeVisible();
  } else {
    await expect(shortCards).toHaveCount(0);
  }

  // Pro: the trades download as a CSV file, one row each
  const [dl] = await Promise.all([page.waitForEvent("download"), trades.getByRole("button", { name: "Download as CSV" }).click()]);
  expect(dl.suggestedFilename()).toMatch(/-v1-trades\.csv$/);
  const text = await (await import("node:fs/promises")).readFile((await dl.path())!, "utf8");
  expect(text.trim().split("\n").length - 1).toBe(exp.trades.length);

  // making the link says first what becomes public; then the page says it is public, with the link, until it's off
  await page.getByRole("button", { name: "Share verdict" }).click();
  await page.getByRole("menuitem", { name: "Make a public link" }).click();
  const ask = page.getByRole("dialog", { name: "Make a public link?" });
  await expect(ask).toContainText(`the notebook's name "${nb.name}"`);
  await expect(ask).toContainText("Your rules, capital, trades and notes stay private");
  await ask.getByRole("button", { name: "Make the link" }).click();
  const note = page.getByTestId("public-link-note");
  await expect(note).toContainText("This verdict is public.", { timeout: 30_000 });
  await expect(note.getByRole("link")).toHaveText(/\/v\/[A-Za-z0-9_-]{6,}$/);
  await page.getByRole("note", { name: "Public link" }).getByRole("button", { name: "Turn off" }).click();
  await page.getByRole("dialog", { name: "Turn off the public link?" }).getByRole("button", { name: "Turn it off" }).click();
  await expect(note).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("compare: a date axis, both runs drawn whole, the verdict's words and a count of checks (DA-031)", async ({ page, request }, info) => {
  const { nb } = await notebook(request, `DA2 compare ${info.project.name}`);
  await request.put(`${API}/notebooks/${nb.id}`, { headers: admin, data: { strategy: EMA(10, 30) } });
  expect((await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } })).ok()).toBeTruthy();
  const errors = await open(page, `/n/${nb.id}/compare?a=1&b=2`);
  const numbers = page.getByRole("table", { name: "Compared numbers" });
  await expect(numbers).toContainText("Worst fall", { timeout: 30_000 });
  await expect(numbers).not.toContainText("Worst drop");
  await expect(numbers).toContainText(/\d of 4/);
  await expect(numbers).not.toContainText("checks run");
  await expect(page.getByTestId("compare-windows")).toContainText("cover different dates");
  // the years on the axis are evenly spaced: each year the same width
  const ticks = await page.locator(".ch svg text").evaluateAll((els) => els.filter((e) => /^20\d\d$/.test(e.textContent ?? ""))
    .map((e) => (e as SVGTextElement).getBBox().x + (e as SVGTextElement).getBBox().width / 2));
  expect(ticks.length).toBeGreaterThanOrEqual(3);
  const gaps = ticks.slice(1).map((x, i) => x - ticks[i]);
  expect(Math.max(...gaps) / Math.min(...gaps)).toBeLessThan(1.15);
  expect(errors).toEqual([]);
});

test("notebooks: the name is the title, the question under it, and what it was tested on (DA-032)", async ({ page, request }, info) => {
  const { nb } = await notebook(request, `DA2 list ${info.project.name}`);
  const errors = await open(page, "/notebooks");
  const card = page.getByRole("region", { name: nb.name, exact: true });
  await expect(card.getByRole("link", { name: nb.name, exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(card.locator(".nb-question")).toHaveAttribute("title", /five years of daily candles/);
  await expect(card).toContainText("Tested on AAPL");
  await expect(card.getByRole("button", { name: `Pin ${nb.name} to the top` })).toContainText("Pin");
  expect(errors).toEqual([]);
});
