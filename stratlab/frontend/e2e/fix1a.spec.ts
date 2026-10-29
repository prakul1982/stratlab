import { expect, test, type Page } from "@playwright/test";

// FIX-1A: the live-site review LIVE-1A, proved on the pages as drawn: the notebook's Lab notes tab clear of the cards, the verdict's
// headline, numbers and next steps, the compare pages, the instrument search's groups, the options summary's breakevens and the
// forward test's Start button. Desktop and phone (the config runs both).
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const EMA = (a: number, b: number) => ({ name: "Fix1a", tf: "1d", entry: [{ l: { t: "ema", p: a }, op: "xa", r: { t: "ema", p: b } }],
  exit: [{ l: { t: "ema", p: a }, op: "xb", r: { t: "ema", p: b } }], risk: { capital: 100000, sl: 0, tgt: 0, brokerage: 0, slippage: 0.05 } });

async function open(page: Page, path: string, mock?: (u: URL) => unknown | undefined) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const u = new URL(r.request().url());
    const m = mock?.(u);
    if (m !== undefined) return r.fulfill({ status: 200, json: m });
    return u.hostname === "127.0.0.1" || u.hostname === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}

async function made(request: import("@playwright/test").APIRequestContext, name: string, strategy = EMA(10, 30)) {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name, strategy, instrument: "FX:EURUSD=X" } })).json();
  const run = await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } });
  expect(run.ok(), await run.text()).toBeTruthy();
  return nb as { id: string };
}

test("the notebook's Lab notes tab never lies over a card on a desktop window (LIVE1A-001)", async ({ page, request }, info) => {
  test.skip(info.project.name === "phone", "on a phone the notes are a bottom sheet");
  const nb = await made(request, "Fix1a notes");
  const errors = await open(page, `/n/${nb.id}`);
  const tab = page.getByTestId("lab-notes-btn");
  await expect(tab).toBeVisible({ timeout: 30_000 });
  const box = (await tab.boundingBox())!;
  const vw = page.viewportSize()!.width;
  expect(box.x + box.width, "the tab sits on the window's right edge").toBeGreaterThan(vw - 2);
  const overlaps = await page.evaluate((t) => Array.from(document.querySelectorAll("main .k-card")).filter((c) => {
    const r = c.getBoundingClientRect();
    return r.width && r.height && t.x < r.right && t.x + t.width > r.left && t.y < r.bottom && t.y + t.height > r.top;
  }).length, box);
  expect(overlaps, "cards the tab lies over").toBe(0);
  expect(errors).toEqual([]);
});

test("the verdict page: the loudest line is the verdict, the numbers and costs are full-width cards, the header and menus fit (LIVE1A-005/006/007/008/036)", async ({ page, request }, info) => {
  const nb = await made(request, `Fix1a verdict ${info.project.name}`);
  const e = (await (await request.get(`${API}/notebooks/${nb.id}`, { headers: admin })).json()).experiments[0];
  const errors = await open(page, `/n/${nb.id}/e/1`);
  const head = page.locator(".verdict-head");
  await expect(head).toBeVisible({ timeout: 30_000 });
  const text = (await head.innerText()).replace(/\s+/g, " ");
  if (e.verdict.verdict === "not_enough") expect(text).toMatch(/^Only \d+ trades?|^No (closed )?trades/i);
  if (/^Lost money after costs/i.test(e.verdict.headline.split("; ")[1] ?? "")) expect(text).toMatch(/^Lost money after costs/);
  expect(text, "a gap too big to read").not.toMatch(/\d{4,}\.\d points/);
  // the run's header line: no line starts with a dot
  const lede = await page.locator(".k-page-head, header").first().evaluate(() => {
    const p = Array.from(document.querySelectorAll("main .k-lede, main .k-page-head p")).find((x) => /Back to the notebook/.test(x.textContent ?? ""));
    if (!p) return [];
    const r = document.createRange(), t = p.firstChild;
    const lines: Record<number, string> = {};
    const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const s = n.textContent ?? "";
      for (let i = 0; i < s.length; i++) {
        r.setStart(n, i); r.setEnd(n, i + 1);
        const b = r.getClientRects()[0];
        if (b && s[i].trim()) lines[Math.round(b.top)] = (lines[Math.round(b.top)] ?? "") + s[i];
      }
    }
    void t;
    return Object.values(lines);
  });
  for (const l of lede) expect(l.trim().startsWith("·"), `a line of the header starts with a dot: ${l}`).toBeFalsy();
  // the numbers and the costs: two cards of one width, one over the other
  const numbers = page.getByRole("region", { name: "The numbers", exact: true }), keep = page.getByRole("region", { name: "What you'd keep", exact: true });
  const [bn, bk] = [(await numbers.boundingBox())!, (await keep.boundingBox())!];
  expect(Math.abs(bn.x - bk.x), "the two cards share their left edge").toBeLessThan(2);
  expect(Math.abs(bn.width - bk.width), "and their width").toBeLessThan(2);
  expect(bk.y).toBeGreaterThan(bn.y + bn.height - 2);
  // the next steps: on a phone one column of full-width buttons of at least 44px
  const steps = page.getByRole("toolbar", { name: "Next step" });
  if (info.project.name === "phone") {
    const btns = await steps.locator("button").evaluateAll((els) => els.filter((b) => b.getBoundingClientRect().width).map((b) => b.getBoundingClientRect()).map((r) => ({ w: Math.round(r.width), h: Math.round(r.height) })));
    expect(btns.length).toBeGreaterThan(1);
    expect(new Set(btns.map((b) => b.w)).size, "buttons of one width").toBe(1);
    for (const b of btns) expect(b.h).toBeGreaterThanOrEqual(44);
  }
  // the share menu is as wide as its items: none wraps
  await page.getByRole("button", { name: "Share verdict" }).click();
  const wrapped = await page.locator(".more-pop button").evaluateAll((els) => els.filter((b) => b.getBoundingClientRect().height > 44).map((b) => b.textContent));
  expect(wrapped, "menu items on two lines").toEqual([]);
  expect(errors).toEqual([]);
});

test("compare runs: the two selects fill their card and show a run's whole name (LIVE1A-009)", async ({ page, request }, info) => {
  const nb = await made(request, `Fix1a compare ${info.project.name}`);
  await request.put(`${API}/notebooks/${nb.id}`, { headers: admin, data: { strategy: EMA(12, 40) } });
  expect((await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 730 } })).ok()).toBeTruthy();
  const errors = await open(page, `/n/${nb.id}/compare?a=1&b=2`);
  const card = page.getByRole("region", { name: "Pick two runs", exact: true });
  await expect(card).toBeVisible({ timeout: 30_000 });
  const widths = await card.locator("select").evaluateAll((els) => els.map((s) => Math.round(s.getBoundingClientRect().width)));
  expect(widths.length).toBe(2);
  if (info.project.name !== "phone") for (const w of widths) expect(w, "a select across half the card").toBeGreaterThan(300);
  await expect(card.getByTestId("what-changed")).toBeVisible();
  expect(errors).toEqual([]);
});

test("the company compare page: no note runs out of its cell, and the AI read follows the figures (LIVE1A-048/049)", async ({ page }) => {
  const errors = await open(page, "/research/compare?region=IN&a=TCS&b=INFY");
  await expect(page.getByRole("heading", { name: "The numbers side by side" })).toBeVisible({ timeout: 30_000 });
  const overflow = await page.evaluate(() => Array.from(document.querySelectorAll("main td, main th")).filter((c) => {
    const cell = c.getBoundingClientRect();
    return Array.from(c.querySelectorAll("*")).some((x) => x.getBoundingClientRect().right > cell.right + 1);
  }).length);
  expect(overflow, "cells with text running past them").toBe(0);
  const ai = await page.getByRole("heading", { name: "AI comparison" }).boundingBox(), numbers = await page.getByRole("heading", { name: "The numbers side by side" }).boundingBox();
  expect(ai!.y, "the AI read is under the figures").toBeGreaterThan(numbers!.y);
  expect(errors).toEqual([]);
});

test("the instrument search lists a stock, its futures, then a few options, the rest behind one row (LIVE1A-004)", async ({ page }) => {
  const stock = { id: "NSE:RELIANCE", symbol: "RELIANCE", name: "Reliance Industries", market: "IN", type: "EQ", currency: "INR", exchange: "NSE" };
  const fut = { id: "NFO:RELIANCE26NOVFUT", symbol: "RELIANCE26NOVFUT", name: "RELIANCE futures", market: "IN", type: "FUT", currency: "INR", exchange: "NFO", expiry: "2026-11-26" };
  const opts = Array.from({ length: 14 }, (_, i) => ({ id: `NFO:O${i}`, symbol: `RELIANCE26NOV${1000 + i * 10}${i % 2 ? "PE" : "CE"}`, name: "RELIANCE options", market: "IN", type: i % 2 ? "PE" : "CE", currency: "INR", exchange: "NFO", expiry: "2026-11-26" }));
  const errors = await open(page, "/new", (u) => (u.pathname.endsWith("/instruments/search") ? [...opts, fut, stock] : undefined));
  await page.getByRole("combobox").first().fill("RELIANCE");
  const list = page.getByRole("listbox", { name: "Suggestions" });
  await expect(list).toBeVisible({ timeout: 15_000 });
  const rows = list.getByRole("option");
  await expect(rows.first()).toContainText("RELIANCE");
  await expect(rows.first()).not.toContainText("26NOV");                                    // the stock leads, the contracts follow
  await expect(list.getByText("Options", { exact: true })).toBeVisible();
  await expect(list.getByText("Futures", { exact: true })).toBeVisible();
  expect(await rows.count()).toBeLessThan(14);
  await list.getByRole("option", { name: /Show 8 more options/ }).click();
  expect(await list.getByRole("option").count()).toBe(16);
  expect(errors).toEqual([]);
});

test("the forward test's Start session button has a row of its own with its caption under it (LIVE1A-025)", async ({ page }) => {
  const errors = await open(page, "/trade/signals");
  const btn = page.getByRole("button", { name: "Start session" });
  await expect(btn).toBeVisible({ timeout: 30_000 });
  const check = page.getByLabel("Allow short positions");
  const [b, c] = [(await btn.boundingBox())!, (await check.boundingBox())!];
  expect(b.y, "the button is under the checkbox, not beside it").toBeGreaterThan(c.y + c.height - 2);
  const note = page.getByText("Pick an instrument first.");
  if (await note.count()) expect((await note.boundingBox())!.y).toBeGreaterThan(b.y + b.height - 2);
  expect(errors).toEqual([]);
});

test("choosing Your own data on the new-idea page opens the upload straight after the notebook is built (LIVE1A-057)", async ({ page }) => {
  const errors = await open(page, "/new");
  await page.getByRole("radio", { name: /Your own data/ }).or(page.getByRole("button", { name: /Your own data/ })).first().click();
  await expect(page.getByText("You'll upload your CSV of candles right after the notebook is created.")).toBeVisible();
  await page.locator("#idea").fill("Buy when price crosses above 50 SMA. Sell when price crosses below 50 SMA. Stop loss 4%.");
  await page.getByRole("button", { name: "Build my notebook" }).click();
  const keep = page.getByRole("button", { name: "Build with these rules" });
  await keep.waitFor({ timeout: 20_000 }).then(() => keep.click()).catch(() => undefined);
  await page.waitForURL(/\/n\/[^/]+\/market/, { timeout: 30_000 });
  await expect(page.getByText("Upload candles as a CSV")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Exports from charting sites, broker apps and Excel work as they are/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("the new-idea page offers the strategy import and the library once each (LIVE1A-003)", async ({ page }) => {
  const errors = await open(page, "/new");
  const main = page.locator("main");
  await expect(main.getByRole("heading", { name: "More you can do" })).toBeVisible({ timeout: 30_000 });
  expect(await main.getByText("Import a strategy", { exact: true }).count(), "Import a strategy on the page").toBeLessThanOrEqual(2);   // the header button and its own card (the dialog), not a third tile
  expect(await main.locator(".explore-card", { hasText: "Strategy library" }).count()).toBe(0);
  expect(await main.locator(".explore-card", { hasText: "Import a strategy" }).count()).toBe(0);
  expect(errors).toEqual([]);
});
