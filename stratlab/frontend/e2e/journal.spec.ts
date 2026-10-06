import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// Trade journal (Trade space): upload a broker's tax P&L ZIP, see the round trips, the verdict's checks on the real
// trades and the breakdowns, add a trade by hand, write a journal entry with a planned stop, and delete it all. Each
// project signs in as its own empty account.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const ZIP = path.resolve(process.cwd(), "../backend/tests/fixtures/taxpnl/zerodha_taxpnl_2024_2025.zip");

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
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(you should|buy|sell|accumulate|avoid)\b/i);
}

async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

test("trade journal: import a tax P&L, the checks, a hand-added trade, a journal entry and delete", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 184 : 181;
  const who = sessionFor(n);
  expect((await request.delete(`${API}/trade/journal`, { headers: { Authorization: `Bearer load-${n}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/trade/journal", "No trades yet", who);
  if (phone) await touchable(page);

  await page.getByLabel("Tradebook or tax P&L files").setInputFiles(ZIP);
  await expect(page.getByText("16 trade lines added")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "15 closed trades" })).toBeVisible();
  const verdict = page.getByRole("region", { name: "Verdict on your real trades" });
  await expect(verdict.getByText("Mixed evidence.")).toBeVisible();
  await expect(page.locator("[data-check=luck]").getByText(/With 15 trades, a 67% win rate could easily be luck/)).toBeVisible();
  await expect(page.locator("[data-check=costs]").getByText("Passed")).toBeVisible();
  await expect(page.getByRole("img", { name: /Running P&L after charges over 15 trades/ })).toBeVisible();

  await page.getByLabel("Break the P&L down by").selectOption("segment");
  const seg = page.getByRole("table", { name: "P&L by segment" });
  await expect(seg.getByText("Options")).toBeVisible();
  await expect(seg.getByText("Commodity")).toBeVisible();

  await page.getByRole("button", { name: "Add a trade by hand" }).click();
  const add = page.getByRole("dialog", { name: "Add a trade" });
  await add.getByLabel("Symbol").fill("HDFCBANK");
  await add.getByLabel("Quantity").fill("10");
  await add.getByLabel("Entry price").fill("4000");
  await add.getByLabel("Exit price").fill("4100");
  await add.getByRole("button", { name: "Add trade" }).click();
  await expect(page.getByText("Trade added.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "16 closed trades" })).toBeVisible();

  const trades = page.getByRole("table", { name: "Trades" });
  await trades.getByRole("button", { name: /^Journal: HDFCBANK/ }).click();
  const box = page.getByRole("dialog", { name: "Journal: HDFCBANK" });
  await box.getByLabel("Setup or strategy").fill("Breakout");
  await box.getByLabel("Planned stop").fill("3950");
  await box.getByRole("button", { name: "Calm" }).click();
  await box.getByRole("button", { name: "Exited early" }).click();
  if (phone) await touchable(page);
  await box.getByRole("button", { name: "Save" }).click();
  await expect(box).toHaveCount(0);
  await expect(trades.getByText("Breakout")).toBeVisible();
  await expect(trades.getByText(/^\+1\.\d+R$/)).toBeVisible();                        // ₹1,000 less charges on ₹500 of risk

  // the segment filter: only the options trades, then back; the tax report's totals sit under the trades
  const segs = page.getByRole("group", { name: "Segment" });
  await expect(segs.getByRole("button", { name: /^Options \(/ })).toBeVisible();
  await segs.getByRole("button", { name: /^Options \(/ }).click();
  await expect(page.getByRole("heading", { name: /^\d+ closed trades?$/ })).not.toHaveText("16 closed trades");
  await expect(page.getByRole("table", { name: "Trades" }).locator("tbody tr").first()).toContainText("Options");
  await segs.getByRole("button", { name: "All" }).click();
  await expect(page.getByRole("heading", { name: "16 closed trades" })).toBeVisible();

  // another market is its own set, in dollars
  await page.getByRole("button", { name: "Add a trade by hand" }).click();
  const us = page.getByRole("dialog", { name: "Add a trade" });
  await us.getByLabel("Symbol").fill("AAPL");
  await us.getByLabel("Segment").selectOption("us");
  await us.getByLabel("Quantity").fill("5");
  await us.getByLabel("Entry price").fill("200");
  await us.getByLabel("Exit price").fill("210");
  await us.getByRole("button", { name: "Add trade" }).click();
  await expect(page.getByText("Trade added.").first()).toBeVisible();
  const market = page.getByRole("radiogroup", { name: "Market" });
  await expect(market.getByRole("radio", { name: /^India/ })).toBeChecked();
  await market.getByRole("radio", { name: /^US stocks/ }).click();
  await expect(page.getByRole("heading", { name: "1 closed trade" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Trades" })).toContainText("$50");
  await expect(page.getByRole("table", { name: "Trades" })).not.toContainText("₹");
  await market.getByRole("radio", { name: /^India/ }).click();
  await expect(page.getByRole("heading", { name: "16 closed trades" })).toBeVisible();

  await page.getByLabel("Break the P&L down by").selectOption("tag");
  await expect(page.getByRole("table", { name: "P&L by setup" }).getByText("Breakout")).toBeVisible();
  await expect(page.getByText(/1 of 16 trades have a planned stop/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Paper vs real" })).toBeVisible();
  if (phone) await touchable(page);
  await sane(page, errors);

  await page.goto("/trade");
  await expect(page.locator("[data-trade='/trade/journal']").getByText(/16 closed trades/)).toBeVisible({ timeout: 20_000 });

  await page.goto("/trade/journal");
  await expect(page.getByRole("heading", { name: "16 closed trades" })).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Delete my journal" }).click();
  await page.getByRole("dialog", { name: "Delete my journal?" }).getByRole("button", { name: "Delete my journal" }).click();
  await expect(page.getByText("Your journal is deleted.")).toBeVisible();
  await expect(page.getByText("No trades yet")).toBeVisible();
  await sane(page, errors);
});
