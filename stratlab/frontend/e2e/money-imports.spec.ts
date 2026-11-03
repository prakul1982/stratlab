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
