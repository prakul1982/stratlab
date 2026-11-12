import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { sessionAs, open, sane, settle, API, HOLDINGS_FILES, TRADEBOOKS } from "./pages-kit";

// The MONEY lane (Instinct deep QA, 1–2 Nov): what a file upload does to what's saved, said plainly, and the first click
// on a money form doing what it says. Each test signs in as its own fake Pro account per project (money-N in
// tests/fake_db.py), so nothing saved here meets another spec or the other project's run.

const as = (n: number, phone: boolean) => { const i = n * 2 + (phone ? 1 : 0); return { token: `money-${i}`, id: `u-money-${i}`, email: `money${i}@example.com` }; };
const auth = (u: ReturnType<typeof as>) => ({ Authorization: `Bearer ${u.token}` });
const counter = (page: Page, path: string, method = "POST") => {
  let n = 0;
  page.on("request", (r) => { if (r.method() === method && new URL(r.url()).pathname === path) n++; });
  return () => n;
};

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

test("MONEY-2: a holdings file adds by default; Start again asks first, naming what it replaces", async ({ page, request }, info) => {
  const u = as(0, info.project.name === "phone");
  expect((await request.delete(`${API}/holdings`, { headers: auth(u) })).ok()).toBeTruthy();
  const kite = "zerodha_kite_holdings.csv";
  const first = await request.post(`${API}/holdings/import`, { headers: auth(u),
    data: { filename: kite, data: readFileSync(HOLDINGS_FILES + kite).toString("base64"), mode: "replace" } });
  expect(first.ok()).toBeTruthy();
  const held = (await first.json()).holdings.rows.length;
  expect(held).toBe(4);
  const imports = counter(page, "/holdings/import");
  const errors = await open(page, "/holdings", "By sector", sessionAs(u.token, u.id, u.email));
  await settle(page);
  const table = page.getByRole("table", { name: "Positions" });
  // R15 #4 (changed on purpose): Add or Start again shows only once a file is picked
  await expect(page.getByRole("radio", { name: "Add to my holdings" })).toHaveCount(0);

  // Start again: the dialog names the count, and Cancel sends nothing
  await page.getByLabel("Holdings file").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  await expect(page.getByRole("radio", { name: "Add to my holdings" })).toBeChecked();
  await page.getByRole("radio", { name: "Start again with this file" }).click();
  await page.getByRole("button", { name: "Read this file" }).click();
  const ask = page.getByRole("dialog", { name: "Start again with this file?" });
  await expect(ask).toContainText(`This replaces your ${held} holdings with the stocks in upstox_holdings.csv.`);
  await ask.getByRole("button", { name: "Cancel" }).click();
  await expect(ask).toHaveCount(0);
  await page.waitForTimeout(500);
  expect(imports(), "a cancelled replace sends nothing").toBe(0);
  await expect(table.getByText("SBIN", { exact: true })).toBeVisible();

  // the same file again, confirmed: the old stocks go
  await page.getByLabel("Holdings file").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  await page.getByRole("radio", { name: "Start again with this file" }).click();
  await page.getByRole("button", { name: "Read this file" }).click();
  await ask.getByRole("button", { name: "Replace my holdings" }).click();
  await expect(page.getByText("Read as an Upstox file")).toBeVisible({ timeout: 30_000 });
  await expect(table.getByText("BHARTIARTL", { exact: true })).toBeVisible();
  await expect(table.getByText("SBIN", { exact: true })).toHaveCount(0);

  // back to Add (the default after a reload too): no question, the file's stocks join the others
  await page.reload();
  await expect(table.getByText("BHARTIARTL", { exact: true })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Holdings file").setInputFiles(HOLDINGS_FILES + kite);
  await expect(page.getByRole("radio", { name: "Add to my holdings" })).toBeChecked();
  await page.getByRole("button", { name: "Read this file" }).click();
  await expect(page.getByText("Read as a Zerodha Kite file")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(table.getByText("SBIN", { exact: true })).toBeVisible();
  await expect(table.getByText("BHARTIARTL", { exact: true })).toBeVisible();
  await sane(page, errors);
});

test("MONEY-6a/1: a file with good and bad lines says exactly what was saved and each line left out, never a failure", async ({ page, request }, info) => {
  const u = as(1, info.project.name === "phone");
  expect((await request.delete(`${API}/holdings`, { headers: auth(u) })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "No holdings yet", sessionAs(u.token, u.id, u.email));
  await settle(page);
  // Instinct's file: lower-case column names, one good line and each kind of bad one
  const csv = "symbol,quantity,avg_price\nINFY,10,1500\nSBIN,notanumber,abc\n,7,500\nTATAMOTORS,-5,800\nFAKESYM123,3,100\n";
  await page.getByLabel("Holdings file").setInputFiles({ name: "lower.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("1 stock saved.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("4 lines couldn't be matched (below).")).toBeVisible();
  const missed = page.getByRole("table", { name: "Lines that couldn't be matched" });
  for (const [line, why] of [["3", /"notanumber" isn't a number/], ["4", /No stock symbol/], ["5", /below 0/], ["6", /FAKESYM123|no listed company|isn't/i]] as const) {
    await expect(missed.getByRole("row").filter({ has: page.getByRole("rowheader", { name: line, exact: true }) }).getByText(why).first()).toBeVisible();
  }
  await page.getByText("Show the 1 stock saved from this file").click();
  const saved = page.getByRole("table", { name: "Stocks saved from this file" });
  await expect(saved.getByText("INFY", { exact: true })).toBeVisible();
  await expect(page.getByTestId("upload-problem")).toHaveCount(0);
  await expect(page.getByText(/couldn't be read|could not be read/)).toHaveCount(0);
  await expect(page.getByRole("table", { name: "Positions" }).getByText("INFY", { exact: true })).toBeVisible();
  await sane(page, errors);
});

test("MONEY-6a: a refused file shows the columns that are read and the broker files", async ({ page, request }, info) => {
  const u = as(2, info.project.name === "phone");
  expect((await request.delete(`${API}/holdings`, { headers: auth(u) })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "No holdings yet", sessionAs(u.token, u.id, u.email));
  await settle(page);
  await page.getByLabel("Holdings file").setInputFiles({ name: "notes.csv", mimeType: "text/csv", buffer: Buffer.from("these,are,not\nmy,holdings,at all\n") });
  await expect(page.getByTestId("upload-problem")).toBeVisible({ timeout: 30_000 });
  const how = page.getByTestId("holdings-format");
  await expect(how).toContainText("Symbol (or ISIN), Quantity and Average price");
  await expect(how).toContainText("Zerodha");
  await expect(page.getByText("No holdings yet")).toBeVisible();
  await sane(page, errors);
});

test("MONEY-6b/6c: tax tools › dividends: a file over two years uploads, shows its own name, and deletes, with no crash", async ({ page, request }, info) => {
  const u = as(3, info.project.name === "phone");
  expect((await request.delete(`${API}/money/dividends`, { headers: auth(u) })).ok()).toBeTruthy();
  // held stocks too, Indian and US, as Instinct's account had: the year's estimate and the declared ones ahead are shown beside the file's
  const held = "Symbol,Quantity,Average price\nINFY,10,1500\nTCS,5,3000\n";
  expect((await request.post(`${API}/holdings/import`, { headers: auth(u), data: { filename: "h.csv", data: Buffer.from(held).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  expect((await request.put(`${API}/holdings`, { headers: auth(u), data: { changes: [{ op: "add", symbol: "AAPL", qty: 3, avg: 150, market: "US" }] } })).ok()).toBeTruthy();
  const errors = await open(page, "/money/tax-tools", "Tax tools", sessionAs(u.token, u.id, u.email));
  await settle(page);
  // Instinct's file: INFY ₹250 this year (FY 2026-27) and TCS ₹55 last year (FY 2025-26)
  const csv = "Date,Symbol,Amount\n2026-06-10,INFY,250\n2026-01-16,TCS,55\n";
  await page.getByLabel("Dividend file").setInputFiles({ name: "dividends.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("2 dividends added.")).toBeVisible({ timeout: 30_000 });
  const year = page.getByRole("region", { name: "Dividends for the year" });
  await expect(year).toBeVisible();
  await expect(year.getByText("Saved from dividends.csv.")).toBeVisible();                 // the file's own name
  await expect(page.getByText(/ran into a problem/)).toHaveCount(0);
  // the same lines in a file of another name: the note names the file just read, and that its lines were there already
  await page.getByLabel("Dividend file").setInputFiles({ name: "again.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("again.csv: 0 dividends added, 2 already there from an earlier file (skipped).")).toBeVisible({ timeout: 30_000 });
  await expect(year.getByText("Saved from dividends.csv.")).toBeVisible();
  // another year and back, then the delete (each year says what it is beside its name since Release 42; updated on purpose)
  await year.getByLabel("Financial year").selectOption({ label: "FY 2026-27 (this year)" });
  await expect(year.getByLabel("Dividend income")).toHaveText("₹250");
  await year.getByLabel("Financial year").selectOption({ label: "FY 2025-26 (being filed)" });
  await expect(year.getByLabel("Dividend income")).toHaveText("₹55");
  await expect(page.getByText(/ran into a problem/)).toHaveCount(0);
  await year.getByRole("button", { name: "Delete uploaded dividends" }).click();
  await page.getByRole("dialog", { name: "Delete the dividends you uploaded?" }).getByRole("button", { name: "Delete uploaded dividends" }).click();
  await expect(page.getByText("Your uploaded dividends are deleted.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/ran into a problem/)).toHaveCount(0);
  await expect(page.getByLabel("Dividend file")).toBeAttached();
  await sane(page, errors);
});

test("MONEY-3: the ITR PDF pack downloads on the first click of a fresh page, says Making it… meanwhile, and says a failure", async ({ page, request }, info) => {
  const u = as(4, info.project.name === "phone");
  expect((await request.delete(`${API}/tax`, { headers: auth(u) })).ok()).toBeTruthy();
  expect((await request.post(`${API}/tax/import?filename=zerodha_console_tradebook.csv&mode=add`, {
    headers: { ...auth(u), "Content-Type": "application/octet-stream" }, data: readFileSync(TRADEBOOKS + "zerodha_console_tradebook.csv") })).ok()).toBeTruthy();
  // the pack takes a moment, as a first one does on the live server
  await page.route("**/money/itr/export**", async (r) => { await new Promise((ok) => setTimeout(ok, 1200)); await r.fallback(); });
  const errors = await open(page, "/money/itr", "Your year, laid out for the return", sessionAs(u.token, u.id, u.email));
  await settle(page);
  const pdf = page.getByRole("button", { name: /PDF pack for your CA/ });
  await expect(pdf).toBeEnabled({ timeout: 30_000 });
  const got = page.waitForEvent("download");
  await pdf.click();                                                       // once
  await expect(page.getByRole("button", { name: /Making it…/ })).toBeVisible();
  const dl = await got;
  expect(dl.suggestedFilename()).toMatch(/CA-pack\.pdf$/);
  expect((await readFileSync(await dl.path()).subarray(0, 5)).toString()).toBe("%PDF-");
  await expect(pdf).toBeEnabled();
  // a failure is said, and the button is back
  await page.unroute("**/money/itr/export**");
  await page.route("**/money/itr/export**", (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { message: "The pack couldn't be made just now." } }) }));
  await pdf.click();
  await expect(page.getByText("The pack couldn't be made just now.")).toBeVisible({ timeout: 15_000 });
  await expect(pdf).toBeEnabled();
  expect(errors).toEqual([]);
});

test("MONEY-3: a new alert is set on the first click, and Enter in the picked stock box sends it too", async ({ page, request }, info) => {
  const u = as(5, info.project.name === "phone");
  for (const a of (await (await request.get(`${API}/alerts`, { headers: auth(u) })).json()).alerts ?? []) await request.delete(`${API}/alerts/${a.id}`, { headers: auth(u) });
  const errors = await open(page, "/alerts", "Your stock alerts", sessionAs(u.token, u.id, u.email));
  await settle(page);
  const made = counter(page, "/alerts");
  await page.getByRole("button", { name: "New alert" }).click();
  const dialog = page.getByRole("dialog", { name: "New alert" });
  const stock = dialog.getByRole("combobox", { name: "Stock" });
  await stock.fill("RELIANCE");
  await dialog.getByRole("listbox", { name: "Suggestions" }).getByRole("option", { name: /RELIANCE/ }).first().click();
  await dialog.getByLabel("Alert me when").selectOption("price_above");
  await dialog.getByLabel(/Price level/).fill("99999");
  await dialog.getByRole("button", { name: "Set alert" }).click();                 // once
  await expect(dialog).toHaveCount(0, { timeout: 15_000 });
  await expect(page.locator(".alert-row", { hasText: "RELIANCE" })).toBeVisible();
  expect(made(), "one click, one request").toBe(1);

  // the keyboard: pick TCS, type a level, then Enter in the stock box sends the form at once
  await page.getByRole("button", { name: "New alert" }).click();
  await stock.fill("TCS");
  await dialog.getByRole("listbox", { name: "Suggestions" }).getByRole("option", { name: /TCS/ }).first().click();
  await dialog.getByLabel("Alert me when").selectOption("price_above");
  await dialog.getByLabel(/Price level/).fill("99999");
  await stock.press("Enter");
  await expect(dialog).toHaveCount(0, { timeout: 15_000 });
  await expect(page.locator(".alert-row", { hasText: "TCS" })).toBeVisible();
  expect(made()).toBe(2);
  await sane(page, errors);
});

test("MONEY-4: the first stock added by hand replaces 'No holdings yet' at once; adding it again says the merge", async ({ page, request }, info) => {
  const u = as(6, info.project.name === "phone");
  expect((await request.delete(`${API}/holdings`, { headers: auth(u) })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "No holdings yet", sessionAs(u.token, u.id, u.email));
  await settle(page);
  const add = async (qty: string, avg: string) => {
    await page.getByRole("combobox", { name: "NSE symbol or BSE code" }).fill("TCS");
    await page.getByRole("listbox", { name: "Suggestions" }).getByRole("option", { name: /TCS/ }).first().click();
    await page.getByLabel("Quantity").fill(qty);
    await page.getByLabel(/Average price/).fill(avg);
    await page.getByRole("button", { name: "Add", exact: true }).click();
  };
  await add("5", "3000");
  await expect(page.getByText("TCS added.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("No holdings yet")).toHaveCount(0);
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.getByText("TCS", { exact: true })).toBeVisible();
  await add("10", "3300");
  await expect(page.getByText("TCS was already held (5), so the 10 are added to it: 15 now.")).toBeVisible({ timeout: 30_000 });
  await expect(table.getByRole("row", { name: /TCS/ })).toContainText("15");
  await sane(page, errors);
});

test("MONEY-4: a stopped paper session is listed as a card, not a shut 'Stopped sessions (1)'", async ({ page, request }, info) => {
  const u = as(7, info.project.name === "phone");
  await request.delete(`${API}/live/sessions`, { headers: auth(u) });
  const EMA = { name: "M4 trend", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }], exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }],
    risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: auth(u), data: { name: "M4 trend", question: "q", strategy: EMA, instrument: "CRYPTO:BTC-USD" } })).json();
  const run = await request.post(`${API}/live/sessions`, { headers: auth(u), data: { notebook_id: nb.id, strategy: EMA, instrument: "CRYPTO:BTC-USD", name: "M4 trend", capital: 10000 } });
  expect(run.ok()).toBeTruthy();
  const sid = (await run.json()).id;
  // open the running session's page, then stop it there
  const errors = await open(page, `/paper/${sid}`, "M4 trend", sessionAs(u.token, u.id, u.email));
  await settle(page);
  expect((await request.post(`${API}/live/sessions/${sid}/stop`, { headers: auth(u) })).ok()).toBeTruthy();
  await page.goto("/paper");
  await expect(page.getByText(/None running/)).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".k-sess", { hasText: "M4 trend" })).toBeVisible();          // the fold is open, its card in it
  expect(errors).toEqual([]);
});
