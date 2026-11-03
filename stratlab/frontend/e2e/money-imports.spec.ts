import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { sessionAs, open, sane, settle, API, HOLDINGS_FILES } from "./pages-kit";

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
  await expect(page.getByRole("radio", { name: "Add to my holdings" })).toBeChecked();

  // Start again: the dialog names the count, and Cancel sends nothing
  await page.getByRole("radio", { name: "Start again with this file" }).click();
  await page.getByLabel("Holdings file").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  const ask = page.getByRole("dialog", { name: "Start again with this file?" });
  await expect(ask).toContainText(`This replaces your ${held} holdings with the stocks in upstox_holdings.csv.`);
  await ask.getByRole("button", { name: "Cancel" }).click();
  await expect(ask).toHaveCount(0);
  await page.waitForTimeout(500);
  expect(imports(), "a cancelled replace sends nothing").toBe(0);
  await expect(table.getByText("SBIN", { exact: true })).toBeVisible();

  // the same file again, confirmed: the old stocks go
  await page.getByLabel("Holdings file").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  await ask.getByRole("button", { name: "Replace my holdings" }).click();
  await expect(page.getByText("Read as an Upstox file")).toBeVisible({ timeout: 30_000 });
  await expect(table.getByText("BHARTIARTL", { exact: true })).toBeVisible();
  await expect(table.getByText("SBIN", { exact: true })).toHaveCount(0);

  // back to Add (the default after a reload too): no question, the file's stocks join the others
  await page.reload();
  await expect(page.getByRole("radio", { name: "Add to my holdings" })).toBeChecked({ timeout: 30_000 });
  await page.getByLabel("Holdings file").setInputFiles(HOLDINGS_FILES + kite);
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
  // another year and back, then the delete
  await year.getByLabel("Financial year").selectOption({ label: "FY 2025-26" });
  await expect(year.getByLabel("Dividend income")).toHaveText("₹55");
  await expect(page.getByText(/ran into a problem/)).toHaveCount(0);
  await year.getByRole("button", { name: "Delete uploaded dividends" }).click();
  await page.getByRole("dialog", { name: "Delete the dividends you uploaded?" }).getByRole("button", { name: "Delete uploaded dividends" }).click();
  await expect(page.getByText("Your uploaded dividends are deleted.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/ran into a problem/)).toHaveCount(0);
  await expect(page.getByLabel("Dividend file")).toBeAttached();
  await sane(page, errors);
});
