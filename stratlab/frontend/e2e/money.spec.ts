import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// The Money space: the money calendar (list, month, own dates, the private feed) and the instrument badges in My
// Holdings, on desktop and phone. Each project signs in as its own fake user, so the two runs never share data.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const HOLDINGS_FILES = new URL("../../backend/tests/fixtures/holdings/", import.meta.url).pathname;

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, path: string, ready: string, n: number) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(path);
  // the welcome question (one step): answering it opens that space's home, so come back to the page after
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(buy|sell|accumulate|avoid)\b/i);
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

const day = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

test("money calendar: tax dates, an own date added, the month view and the private feed", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 158 : 155;          // Pro users of the fake database, one per project
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.delete(`${API}/money/calendar`, { headers: auth })).ok()).toBeTruthy();
  expect((await request.post(`${API}/money/calendar/events`, { headers: auth, data: { date: day(3), title: "Rent goes up", amount: 52000, repeat: "none" } })).ok()).toBeTruthy();
  const errors = await open(page, "/money/calendar", "Tax due dates, results and dividends", n);
  const list = page.getByRole("list", { name: "Money dates" });
  // the next 90 days in view; the past week's dates folded under one line below them
  const card = page.locator("section", { has: page.getByRole("group", { name: "View" }) });
  const past = card.locator("details.earlier", { hasText: "The past week" });
  if (await past.count()) {
    await expect(past).not.toHaveAttribute("open", "");
    await expect(card.getByRole("list", { name: "The past week's dates" })).toHaveCount(0);
    await past.locator("summary").click();
    await expect(card.getByRole("list", { name: "The past week's dates" })).toBeVisible();
  }
  await expect(card.getByText(/Advance tax, .* instalment/).first()).toBeVisible();             // one falls in any 97 days
  await expect(list.getByText("Rent goes up")).toBeVisible();
  await expect(list.getByText("₹52,000")).toBeVisible();

  // a date of one's own, from the form
  await page.getByLabel("Date", { exact: true }).fill(day(10));
  await page.getByLabel("Name").fill("Car insurance premium");
  await page.getByLabel("Repeats").selectOption("yearly");
  await page.getByRole("button", { name: "Add to calendar" }).click();
  await expect(list.getByText("Car insurance premium")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("list", { name: "Your dates" }).getByText("every year")).toBeVisible();

  // only one category
  await page.getByRole("group", { name: "Show" }).getByRole("button", { name: "Tax" }).click();
  await expect(list.getByText("Rent goes up")).toHaveCount(1);
  await page.getByRole("group", { name: "Show" }).getByRole("button", { name: "Your events" }).click();
  await expect(list.getByText("Rent goes up")).toHaveCount(0);
  await page.getByRole("group", { name: "Show" }).getByRole("button", { name: "Your events" }).click();

  // the month: today's cell opens its dates below
  await page.getByRole("group", { name: "View" }).getByRole("button", { name: "Month" }).click();
  const month = page.locator(".mc-month");
  await expect(month).toBeVisible();
  await month.locator(".mc-cell.today").click();
  await expect(page.getByRole("list", { name: "Money dates" }).or(page.getByText("Nothing in these dates."))).toBeVisible();
  const busy = month.locator(".mc-cell:has(.mc-dot)");
  if (await busy.count()) {                                   // a day with dates opens them below the month
    await busy.first().click();
    await expect(page.getByRole("list", { name: "Money dates" })).toBeVisible();
  }
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  // the private feed: works without signing in, leaves amounts out, and stops when turned off
  await page.getByRole("button", { name: "Make a private link" }).click();
  const link = page.getByLabel("Your calendar link");
  await expect(link).toHaveValue(/\/money\/calendar\/feed\/[\w-]{40,}\.ics$/);
  const url = await link.inputValue();
  const ics = await request.get(url);
  expect(ics.status()).toBe(200);
  expect(ics.headers()["content-type"]).toContain("text/calendar");
  const body = (await ics.text()).replace(/\r\n /g, "");
  expect(body).toContain("BEGIN:VCALENDAR");
  expect(body).toContain("SUMMARY:Rent goes up");
  expect(body).not.toContain("Amount:");
  if (info.project.name === "phone") await touchable(page);
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Turn off" }).click();
  await expect(page.getByRole("button", { name: "Make a private link" })).toBeVisible();
  expect((await request.get(url)).status()).toBe(404);
  await sane(page, errors);
});

test("money calendar: reachable from the menu", async ({ page }, info) => {
  const n = info.project.name === "phone" ? 158 : 155;
  const errors = await open(page, "/holdings", "Your stocks", n);
  if (info.project.name === "phone") await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "Money calendar" }).click();
  await expect(page).toHaveURL(/\/money\/calendar$/);
  await expect(page.getByRole("heading", { name: "Money calendar" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("my holdings: ETFs, REITs and gold bonds get a type badge", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 164 : 161;
  const file = "zerodha_console_holdings.xlsx";                // has NIFTYBEES, an equity ETF
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: `Bearer load-${n}` },
    data: { filename: file, data: readFileSync(HOLDINGS_FILES + file).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  const csv = "Symbol,ISIN,Name,Qty,Avg price\nSGBMAY29I-GB,IN0020210079,,4,4800\nEMBASSY,INE041025011,Embassy Office Parks REIT,20,360\n";
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: `Bearer load-${n}` },
    data: { filename: "more.csv", data: Buffer.from(csv).toString("base64"), mode: "add" } })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "By sector", n);
  const table = page.getByRole("table", { name: "Positions" });
  const row = (s: string) => table.getByRole("row").filter({ has: page.getByText(s, { exact: true }) });
  await expect(row("NIFTYBEES").locator(".badge", { hasText: "Equity ETF" })).toBeVisible();
  await expect(row("SGBMAY29I-GB").locator(".badge", { hasText: "Gold bond" })).toBeVisible();
  await expect(row("EMBASSY").locator(".badge", { hasText: "REIT" })).toBeVisible();
  await expect(row("RELIANCE").locator(".badge[class*='kind-']")).toHaveCount(0);
  await expect(page.getByText("Sovereign Gold Bonds").first()).toBeVisible();                     // grouped, not "Not classified"
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});
