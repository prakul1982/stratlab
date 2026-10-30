import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { sessionAs, open, sane, touchable, openWorking, API, HOLDINGS_FILES, settle, TRADEBOOKS, TAXPNL, MF } from "./pages-kit";

// My Holdings, the tax report, mutual funds and Tax tools, each driven from a file to its figures and back out.

test("my holdings: positions, sectors and facts per stock, then a broker file added", async ({ page, request }, info) => {
  // start from the owner's Zerodha file again: the other project's run of this test added a Groww file to the shared account
  const zerodha = "zerodha_console_holdings.xlsx";
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: "Bearer admin-token" },
    data: { filename: zerodha, data: readFileSync(HOLDINGS_FILES + zerodha).toString("base64"), mode: "replace" } })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "By sector");
  await settle(page);
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.getByText("RELIANCE", { exact: true })).toBeVisible();
  await expect(table.getByText("TINYCO", { exact: true })).toBeVisible();            // listed only on BSE
  await expect(page.getByText(/your Zerodha Console file/)).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Unrealised P&L", exact: true })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Trend", exact: true })).toHaveCount(0);                 // the extra columns wait behind a click
  if (info.project.name === "desktop") {                                                         // so the table fits a 1280px screen
    await page.setViewportSize({ width: 1280, height: 900 });
    const wrap = await table.evaluate((t) => ({ scroll: t.parentElement!.scrollWidth, width: t.parentElement!.clientWidth }));
    expect(wrap.scroll, "the positions table needs a sideways swipe at 1280px").toBeLessThanOrEqual(wrap.width + 1);
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  await page.getByRole("button", { name: /More columns/ }).click();
  await expect(table.getByText(/red flag/).first()).toBeVisible({ timeout: 30_000 });  // the QIP filing, once the facts arrive
  await expect(table.getByText(/Stage \d/).first()).toBeVisible();
  await page.reload();                                                                           // remembered on this device
  await expect(table.getByRole("columnheader", { name: "Trend", exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Recent filings")).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/\b(buy|sell|accumulate|avoid)\b/i);
  await page.getByRole("radio", { name: "Add to my holdings" }).click();
  await page.locator("input[type=file]").setInputFiles(HOLDINGS_FILES + "groww_holdings_statement.xlsx");
  await expect(page.getByText("Read as a Groww file")).toBeVisible({ timeout: 30_000 });   // matching a first file reads the stock lists
  const missed = page.getByRole("table", { name: "Lines that couldn't be matched" });
  await expect(missed.getByText(/INE000X01000/)).toBeVisible();
  await expect(table.getByText("INFY", { exact: true })).toBeVisible();
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});

test("my holdings: edit by hand and delete them all", async ({ page }, info) => {
  const errors = await open(page, "/holdings", "By sector");
  await settle(page);
  await page.getByRole("button", { name: "Edit RELIANCE" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit RELIANCE" });
  await expect(dialog.getByRole("button", { name: "Save" })).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Close" }).click();
  // the delete is answered here, so the shared fake account keeps its holdings for the other tests
  const empty = { rows: [], allocation: [], totals: { value: 0, invested: 0, pnl: null, pnl_pct: null, day: null, day_pct: null, count: 0, priced: 0 },
    source: null, updated_at: null, prices: true, limit: 300, facts_max: 40 };
  await page.route("**/holdings", (r) => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify(r.request().method() === "DELETE" ? { deleted: true } : empty) }));
  await page.getByRole("button", { name: "Delete my holdings" }).click();
  await page.getByRole("dialog", { name: "Delete my holdings?" }).getByRole("button", { name: "Delete my holdings" }).click();
  await expect(page.getByText("No holdings yet")).toBeVisible();
  await expect(page.getByText("Your holdings are deleted.")).toBeVisible();
  await sane(page, errors);
});

test("my holdings: add by hand from suggestions, an Indian stock with the keyboard, then a US one", async ({ page, request }, info) => {
  // each project signs in as its own user with no holdings, so the two runs don't add to the same account
  const n = info.project.name === "phone" ? 152 : 151;
  const [token, id, email] = [`load-${n}`, `u-load-${n}`, `load${n}@example.com`];
  expect((await request.delete(`${API}/holdings`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/holdings", "No holdings yet", sessionAs(token, id, email));
  await settle(page);
  const box = page.getByRole("combobox", { name: "NSE symbol or BSE code" });
  await box.fill("re");
  const list = page.getByRole("listbox", { name: "Suggestions" });
  const reliance = list.getByRole("option", { name: /Reliance/ }).first();
  await expect(reliance).toBeVisible();
  await expect(box).toHaveAttribute("aria-expanded", "true");
  const options = await list.getByRole("option").allInnerTexts();
  expect(options.length).toBeGreaterThan(0);
  expect(options.length).toBeLessThanOrEqual(8);
  expect(options[0]).toMatch(/\bRE/);                                             // symbols starting with what's typed come first
  const width = page.viewportSize()!.width;
  const b = (await list.boundingBox())!;
  expect(b.x).toBeGreaterThanOrEqual(0);
  expect(b.x + b.width, "the suggestions fit on the screen").toBeLessThanOrEqual(width + 1);
  if (info.project.name === "phone") await touchable(page);
  // the keyboard: down to Reliance, Enter picks it and fills the NSE symbol
  const at = options.findIndex((t) => /Reliance/.test(t));
  for (let i = 0; i <= at; i++) await box.press("ArrowDown");                 // nothing is marked until the first ↓ (R1-017)
  await expect(reliance).toHaveAttribute("aria-selected", "true");
  await box.press("Enter");
  await expect(box).toHaveValue("RELIANCE");
  await expect(list).toBeHidden();
  await page.getByLabel("Quantity").fill("5");
  await page.getByLabel(/Average price/).fill("2400");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("RELIANCE added.")).toBeVisible({ timeout: 30_000 });
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.getByText("RELIANCE", { exact: true })).toBeVisible();
  // a US stock: found by its name, valued in dollars
  await page.getByRole("radio", { name: "United States" }).click();
  const us = page.getByRole("combobox", { name: "US ticker" });
  await us.fill("apple");
  const apple = list.getByRole("option", { name: /Apple Inc/ });
  await expect(apple).toBeVisible();
  await expect(apple.getByText("US", { exact: true })).toBeVisible();
  await us.press("ArrowDown");                                                // nothing is marked until the first ↓, so Enter alone keeps what was typed
  await expect(apple).toHaveAttribute("aria-selected", "true");
  await us.press("Enter");
  await expect(us).toHaveValue("AAPL");
  await page.getByLabel("Quantity").fill("3");
  await page.getByLabel(/Average price/).fill("150");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("AAPL added.")).toBeVisible({ timeout: 30_000 });
  await expect(table.getByText("AAPL", { exact: true })).toBeVisible();
  await expect(table.getByRole("row", { name: /AAPL/ })).toContainText("$");
  const usLine = page.getByLabel("US stocks");
  await expect(usLine).toContainText("Sales of US stocks come from the trades");
  await expect(usLine, "RC2B-045: one US stock's dollar value is its row's, not said again in the line above").not.toContainText("invested $");
  // an exact symbol typed without picking still works
  await page.getByRole("radio", { name: "India (NSE/BSE)" }).click();
  await box.fill("INFY");
  await page.getByLabel("Quantity").fill("2");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("INFY added.")).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});

test("tax report: tradebooks from several brokers, one year's gains, lots below cost, downloads and delete", async ({ page, request }, info) => {
  // each project signs in as its own user and starts with no trades, so the two runs don't share tax data
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  expect((await request.delete(`${API}/tax`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/tax-report", "Capital gains on your shares", sessionAs(token, id, email));
  await settle(page);
  await expect(page.getByText("No trades yet")).toBeVisible();
  await expect(page.getByText(/not tax advice/).first()).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // three files, two brokers, one pick: what they added up to, with the line left out
  await page.locator("input[type=file]").setInputFiles(["upstox_tradebook.csv", "zerodha_tax_pnl.xlsx", "zerodha_console_tradebook.csv"].map((f) => TRADEBOOKS + f));
  await expect(page.getByText(/Read 3 files: 15 trades added/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("table", { name: "Lines left out" }).getByText(/Futures, options/)).toBeVisible();
  await expect(page.getByText(/15 trades from 3 files/)).toBeVisible();
  await expect(page.getByText("Estimate only.")).toHaveCount(1);                                  // once, at the top

  await page.getByRole("combobox", { name: "Financial year" }).selectOption("2024");
  await expect(page.getByRole("heading", { name: "How FY 2024-25 adds up" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Gains by rate" }).getByText("Long-term, sold from 23 Jul 2024")).toBeVisible();
  await expect(page.getByText("1 same-day round trip", { exact: false })).toBeVisible();          // INFY, kept apart
  const sales = page.getByRole("table", { name: "Realised sales" });
  await expect(sales.getByText("RELIANCE").first()).toBeVisible();
  await expect(sales.getByText("grandfathered")).toBeVisible();                                   // WIPRO, from the tax P&L
  // a laptop shows every column of the sales at once (LIVE1B-012: the purchase date was folded away at 1440px); a phone leads with what the tax works out from
  const wideScreen = (page.viewportSize()?.width ?? 0) >= 1280;
  await expect(sales.getByRole("columnheader", { name: "Bought", exact: true })).toHaveCount(wideScreen ? 1 : 0);
  await page.getByTestId("cols-tax-sales").click();                                                // the button flips it either way
  await expect(sales.getByRole("columnheader", { name: "Bought", exact: true })).toHaveCount(wideScreen ? 0 : 1);
  await expect(page.getByRole("table", { name: "Open lots below cost" }).getByText("TCS")).toBeVisible();
  await expect(page.getByText("Shares held on 31 Jan 2018")).toBeVisible();
  await page.getByRole("button", { name: "What is tax-loss harvesting?" }).click();
  await expect(page.getByRole("note").filter({ hasText: "wash-sale" })).toBeVisible();

  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/you should|we suggest|consider selling|sell now|recommend/i);
  expect(text).not.toMatch(/yahoo|finnhub|kite|screener/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await csv).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.csv");
  const pdf = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF summary" }).click();
  expect((await pdf).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.pdf");

  await page.getByRole("button", { name: "Delete my tax data" }).click();
  await page.getByRole("dialog", { name: "Delete my tax data?" }).getByRole("button", { name: "Delete my tax data" }).click();
  await expect(page.getByText("Your tax data is deleted.")).toBeVisible();
  await expect(page.getByText("No trades yet")).toBeVisible();
});

test("tax report: the tax P&L ZIP as the broker gives it, F&O included, checked against its summary, and the total tax", async ({ page, request }, info) => {
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  expect((await request.delete(`${API}/tax`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/tax-report", "Capital gains on your shares", sessionAs(token, id, email));
  await settle(page);
  await expect(page.locator("input[type=file]")).toHaveAttribute("accept", /\.zip/);
  await page.locator("input[type=file]").setInputFiles(TAXPNL + "zerodha_taxpnl_2024_2025.zip");
  await expect(page.getByText(/Read as a Zerodha tax P&L: 18 trades added/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/7 F&O, commodity and currency lines added up as business income/)).toBeVisible();
  await expect(page.getByText(/From the ZIP: Commodity \(2 lines\), Non-equity \(1 line\), Equity short term \(3 lines\), Equity long term \(2 lines\), Equity intraday \(3 lines\), F&O \(4 lines\), Currency \(1 line\)/)).toBeVisible();
  const check = page.getByRole("list", { name: "Totals checked against your broker's summary" });
  await expect(check.getByText(/the same as your broker's summary sheet/)).toHaveCount(10);
  await expect(check.getByText(/F&O turnover: ₹3,788 netted per contract/)).toBeVisible();
  // the non-equity file is read now (a gold ETF under its own rules), so nothing is left out
  await expect(page.getByRole("list", { name: "Files left out" })).toHaveCount(0);
  // the report opens on the year being filed (FY 2025-26 here) unless it has no trades: then on the latest year with trades,
  // saying why in one line, never a page of zeros first (R3-011)
  await expect(page.getByTestId("tax-moved-year")).toHaveText("No trades in FY 2025-26, the year being filed, so this is FY 2024-25, the latest year with trades.");
  await expect(page.getByRole("button", { name: "Show FY 2024-25" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "ETFs and gold bonds" }).getByText("Gold ETF")).toBeVisible();
  // the year with the sales
  await expect(page.getByRole("heading", { name: "How FY 2024-25 adds up" })).toBeVisible();
  await expect(page.getByText("2 same-day round trips", { exact: false })).toBeVisible();
  await expect(page.getByText("Estimate only.")).toHaveCount(1);
  await expect(page.getByText(/advance tax and TDS already paid aren't included/)).toBeVisible();

  // the total, at the top of the year, with where it comes from
  const total = page.getByRole("region", { name: "Total tax estimate" });
  await expect(total.getByRole("heading", { name: "Total tax estimate, FY 2024-25" })).toBeVisible();
  await expect(total.getByRole("table", { name: "Total tax breakdown" }), "the workings are folded until asked for (LIVE1B-010)").toBeHidden();
  const chips = total.getByRole("table", { name: "Where the tax comes from" });          // a table (RES-1): a row for each source
  await expect(chips.getByRole("row")).toHaveCount(5);                                      // the header and four sources
  for (const c of ["Capital gains", "Intraday", "F&O", "Other income"]) await expect(chips.getByRole("row").filter({ hasText: c })).toHaveCount(1);
  await expect(total.getByText(/no other income entered yet/)).toBeVisible();
  await total.getByText("How we got here").click();
  await expect(total.getByRole("table", { name: "Total tax breakdown" }).getByText("Estimated total tax")).toBeVisible();
  // F&O by segment, and the return and audit facts
  const segs = page.getByRole("table", { name: "F&O by segment" });
  for (const s of ["F&O", "Commodity", "Currency"]) await expect(segs.getByText(s, { exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "F&O by underlying" }).getByText("BANKNIFTY")).toBeVisible();
  await expect(page.getByRole("list", { name: "Returns and tax audit" }).getByText(/ITR-3/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // other income and the regime: saved, and the estimate follows
  await total.getByRole("textbox", { name: "Other income", exact: true }).fill("1500000");
  await total.getByRole("textbox", { name: "Of which salary", exact: true }).fill("1200000");
  await total.getByRole("radio", { name: "Old" }).click();
  await expect(total.getByRole("textbox", { name: "Deductions", exact: true })).toBeVisible();
  await total.getByRole("textbox", { name: "Deductions", exact: true }).fill("150000");
  if (info.project.name === "phone") await touchable(page);
  await total.getByRole("button", { name: "Save and update" }).click();
  await expect(page.getByText("Saved. The estimate is updated.")).toBeVisible();
  await expect(total.getByText(/^Old regime/)).toBeVisible();
  await expect(total.getByText(/With the same figures, the new regime works out to/)).toBeVisible();
  await openWorking(total);          // the steps in words are one fold under the table (LIVE1C-056)
  await expect(total.getByText(/Deductions you entered \(80C and the like\): ₹1,50,000/)).toBeVisible();
  const amount = await page.locator('span[aria-label="Total tax estimate"]').innerText();      // the summary at the top: the total is not printed twice (VR1-144)
  expect(Number(amount.replace(/[^\d]/g, ""))).toBeGreaterThan(100000);
  await expect(total.getByText(/Covers only the income you enter or import here/)).toBeVisible();
  await expect(total.getByText(/Rules for this year not yet confirmed/)).toHaveCount(0);
  await total.getByRole("link", { name: "Which return and whether a tax audit applies" }).click();
  await expect(page.getByRole("list", { name: "Returns and tax audit" })).toBeInViewport();
  await expect(page.locator("#tax-filing").getByRole("link", { name: "incometax.gov.in" })).toHaveAttribute("href", /incometax\.gov\.in/);

  // age and residency: both with their notes, saved per year, and the estimate follows
  await expect(total.getByRole("radio", { name: "Below 60", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(total.getByRole("radio", { name: "Yes", exact: true })).toHaveAttribute("aria-checked", "true");
  await total.getByRole("button", { name: "About age" }).click();
  await expect(page.getByText(/₹3 lakh from 60 to 79 and ₹5 lakh from 80/)).toBeVisible();
  await page.keyboard.press("Escape");
  await total.getByRole("button", { name: "About residency" }).click();
  await expect(page.getByText(/A non-resident gets no section 87A rebate/)).toBeVisible();
  await page.keyboard.press("Escape");
  await total.getByRole("radio", { name: "60–79", exact: true }).click();
  if (info.project.name === "phone") await touchable(page);
  await total.getByRole("button", { name: "Save and update" }).click();
  await expect(total.getByText(/resident, aged 60 to 79/)).toBeVisible();
  await openWorking(total);          // the steps in words are one fold under the table (LIVE1C-056)
  await expect(total.getByText(/the old regime's basic exemption is ₹3,00,000/)).toBeVisible();
  const senior = Number((await page.locator('span[aria-label="Total tax estimate"]').innerText()).replace(/[^\d]/g, ""));
  expect(senior).toBeLessThan(Number(amount.replace(/[^\d]/g, "")));
  await total.getByRole("radio", { name: "No", exact: true }).click();
  await total.getByRole("button", { name: "Save and update" }).click();
  await expect(total.getByText(/non-resident, aged 60 to 79/)).toBeVisible();
  await expect(total.getByText("TDS on NRI sales is deducted by the broker; this estimate does not reconcile TDS.").first()).toBeVisible();
  await expect(total.getByText(/Non-resident: no section 87A rebate/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await page.reload();
  await settle(page);
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByRole("textbox", { name: "Other income", exact: true })).toHaveValue("15,00,000");          // a saved amount is written the Indian way (RC2B-018)
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByRole("radio", { name: "60–79", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByRole("radio", { name: "No", exact: true })).toHaveAttribute("aria-checked", "true");

  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/you should|we suggest|recommend|better off|switch to/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await csv).suggestedFilename()).toBe("stratlab-tax-FY-2024-25.csv");
  expect((await request.delete(`${API}/tax`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
});

test("tax report: a file that isn't a tradebook gets a plain answer", async ({ page }) => {
  const errors = await open(page, "/tax-report", "Capital gains on your shares");
  await settle(page);
  await page.locator("input[type=file]").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  await expect(page.getByText(/looks like a holdings file/)).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);
});

test("mutual funds: a password-protected CAS read, holdings, allocation, gains by year, the tax report, and delete", async ({ page, request }, info) => {
  // each project signs in as its own user (both on Pro) and starts with no funds
  const [token, id, email] = info.project.name === "phone" ? ["load-74", "u-load-74", "load74@example.com"] : ["load-71", "u-load-71", "load71@example.com"];
  expect((await request.delete(`${API}/money/mutual-funds`, { headers: { Authorization: `Bearer ${token}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/money/mutual-funds", "Your mutual funds, in one place", sessionAs(token, id, email));
  await settle(page);
  await expect(page.getByText("No funds yet")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // the first time the costs are asked for, the TER disclosure is still being read: the card says so, then fills in
  let costCalls = 0;
  await page.route((u) => u.pathname === "/money/mutual-funds/costs", (r) => (costCalls++ === 0
    ? r.fulfill({ json: { state: "reading", full: true, plan: "Basic", schemes: [], unmatched: [], total: null, read_at: null, assumptions: [], disclaimer: "", as_of: "2026-10-04" } })
    : r.fallback()));

  // a synthetic statement (made-up investor and funds), locked with a password: first the wrong one
  await page.locator("input[type=file]").setInputFiles(MF + "synthetic_cas.pdf");
  await page.getByLabel("PDF password").fill("WRONG");
  await page.getByRole("button", { name: "Read my funds" }).click();
  await expect(page.getByText(/That password didn't open the PDF/)).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("PDF password").fill("ABCDE1234F");
  await page.getByRole("button", { name: "Read my funds" }).click();
  await expect(page.getByText(/5 transactions and 2 stamp duty or tax lines added/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Costs are being read; check back shortly.")).toBeVisible();
  await expect(page.getByLabel("PDF password")).toHaveCount(0);              // the password field goes with the file

  // MF-1 (RC2B-047): each scheme is one row of one list; its units, costs, return and sales are folded under it
  const schemes = page.getByRole("list", { name: "Schemes" });
  const flexi = schemes.getByRole("listitem").filter({ hasText: "Example Flexi Cap Fund - Direct Plan - Growth" });
  await expect(flexi).toHaveCount(1);
  await expect(schemes.getByText("Sample Short Duration Fund - Direct Plan - Growth")).toBeVisible();
  await expect(page.getByText("₹42,500").first()).toBeVisible();             // 1,100 units at 25 and 500 at 30
  await expect(page.getByText("Share of the current value, by each scheme's official category.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Schemes" }), "no second table of the same schemes").toHaveCount(0);

  await page.getByRole("combobox", { name: "Financial year" }).selectOption("2025");
  await expect(page.getByRole("table", { name: "Gains by rate" }).getByText("Short-term at your slab rate (debt and other funds)")).toBeVisible();
  await page.getByRole("combobox", { name: "Financial year" }).selectOption("2024");
  await expect(page.getByTestId("mf-sales-pointer")).toContainText("Each is listed under its scheme");
  // the year's sales are under their scheme, with every year it sold in
  await flexi.locator("summary").click();
  await expect(flexi.getByRole("table", { name: "Redemptions matched to purchases" }).getByText("grandfathered")).toBeVisible();

  // what the funds cost: the totals once, each fund's TER and rupees a year in its row, and both plans, the TER since bought and a category change in its fold
  await expect(page.getByRole("region", { name: "Costs and how you invested" }).getByText("₹185").first()).toBeVisible({ timeout: 30_000 });   // 143 + 42 a year
  await expect(flexi.getByText("₹143 a year")).toBeVisible();
  const costs = flexi.getByRole("region", { name: "What it costs" });
  await expect(costs.getByText("₹352")).toBeVisible();                       // the 1.28-point plan gap on ₹27,500
  await costs.getByText("Parts of the TER").first().click();
  await expect(costs.getByRole("row", { name: /^Brokerage and transaction costs 0\.08%/ })).toBeVisible();          // TABLE-SWEEP: a row of the parts' table
  const short = schemes.getByRole("listitem").filter({ hasText: "Sample Short Duration Fund - Direct Plan - Growth" });
  await short.locator("summary").click();
  await expect(short.getByText(/Category changed on 16 Mar 2026 \(2026 recategorisation\)/)).toBeVisible();

  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/you should|we suggest|recommend|better fund|switch to|rating/i);
  expect(text).not.toMatch(/yahoo|finnhub|kite|screener/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  // the tax report counts the same gains
  await page.goto("/tax-report");
  await expect(page.getByRole("region", { name: "Mutual funds" }).getByText(/redemption/)).toBeVisible({ timeout: 30_000 });

  await page.goto("/money/mutual-funds");
  await expect(schemes.getByText("Example Flexi Cap Fund - Direct Plan - Growth")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Delete my mutual fund data" }).click();
  await page.getByRole("dialog", { name: "Delete my mutual fund data?" }).getByRole("button", { name: "Delete my mutual fund data" }).click();
  await expect(page.getByText("Your mutual fund data is deleted.")).toBeVisible();
  await expect(page.getByText("No funds yet")).toBeVisible();
});

test("money tax tools: dividends from a file into the estimate, advance tax by date with reminders, and the long-term exemption", async ({ page, request }, info) => {
  // Pro in both projects: the amounts due by each date are a Pro feature (the phone project's own Pro user, load-299),
  // starting from no tax data
  const [token, id, email] = info.project.name === "phone" ? ["load-299", "u-load-299", "load299@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  const auth = { Authorization: `Bearer ${token}` };
  expect((await request.delete(`${API}/tax`, { headers: auth })).ok()).toBeTruthy();
  expect((await request.post(`${API}/tax/import?filename=zerodha_console_tradebook.csv&mode=add`, {
    headers: { ...auth, "Content-Type": "application/octet-stream" }, data: readFileSync(TRADEBOOKS + "zerodha_console_tradebook.csv") })).ok()).toBeTruthy();
  const now = new Date();
  const fy = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  expect((await request.put(`${API}/tax/inputs`, { headers: auth, data: { fy, regime: "new", other: 2000000, salary: 2000000, deductions: 0 } })).ok()).toBeTruthy();

  const errors = await open(page, "/money/tax-tools", "Tax tools", sessionAs(token, id, email));
  await settle(page);
  await expect(page.getByText(/not tax advice/).first()).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // dividends: a CSV of this year's, by company with the TDS the rule gives
  const csv = `Date,Symbol,Amount\n${fy}-04-06,INFY,12000\n${fy}-04-06,TCS,3000\n`;
  await page.getByLabel("Dividend file").setInputFiles({ name: "dividends.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("2 dividends added.")).toBeVisible({ timeout: 30_000 });
  const year = page.getByRole("region", { name: "Dividends for the year" });
  // the page opens on the year being filed now (the one before this year) when it has dividends; these are this year's
  await year.getByLabel("Financial year").selectOption(String(fy));
  await expect(year.getByText("From your files")).toBeVisible();
  await expect(year.getByLabel("Dividend income")).toHaveText("₹15,000");
  const byCompany = year.getByRole("table", { name: "Dividends by company" });
  await expect(byCompany.getByRole("row").filter({ hasText: "INFY" })).toContainText("₹1,200");        // 10% once over the threshold
  await expect(byCompany.getByRole("row").filter({ hasText: "TCS" })).toContainText("₹0");             // under it
  const inEstimate = page.getByRole("radiogroup", { name: "In the total tax estimate" });
  await expect(inEstimate.getByRole("radio", { name: "Include in the tax estimate" })).toHaveAttribute("aria-checked", "true");
  await inEstimate.getByRole("radio", { name: "Leave out" }).click();
  await expect(page.getByText("Left out of the total tax estimate.")).toBeVisible();
  await inEstimate.getByRole("radio", { name: "Include in the tax estimate" }).click();
  await expect(page.getByText("Included in the total tax estimate.")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  // advance tax: the four dates, the amounts after TDS and a payment, and reminders
  await page.getByRole("radio", { name: "Advance tax" }).click();
  await expect(page.getByRole("table", { name: "Due dates" }).locator("tbody tr")).toHaveCount(4);          // TABLE-SWEEP: the four dates are a table
  await expect(page.getByLabel("Tax for the year", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "TDS for the year" }).fill("50000");
  await page.getByRole("button", { name: "Add a payment" }).click();
  await page.getByRole("textbox", { name: "Payment 1 date" }).fill(`${fy}-06-15`);
  await page.getByLabel("Payment 1 amount").fill("20000");
  await page.getByRole("button", { name: "Save and update" }).click();
  await expect(page.getByText("Saved. The instalments are updated.")).toBeVisible();
  const instalments = page.getByRole("table", { name: "Instalments" });
  await expect(instalments.getByRole("row")).toHaveCount(5);
  await expect(instalments.getByRole("row").nth(1)).toContainText("₹20,000");
  const reminders = page.getByRole("radiogroup", { name: "Advance tax reminders" });
  await reminders.getByRole("radio", { name: "On" }).click();
  await expect(page.getByText(/Reminders on: 7 days and 1 day before each date/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await page.reload();
  await settle(page);
  await expect(page.getByRole("radiogroup", { name: "Advance tax reminders" }).getByRole("radio", { name: "On" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("textbox", { name: "TDS for the year" })).toHaveValue("50000");

  // the long-term exemption, with the lots below cost next to it
  await page.getByRole("radio", { name: "Long-term exemption" }).click();
  const ex = page.getByRole("region", { name: "Long-term exemption" });
  await expect(ex.getByText(/doesn't carry forward/)).toBeVisible();
  await expect(ex.getByLabel("Exemption used")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Open lots below cost" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Turning long-term" })).toBeVisible();
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/you should|we suggest|recommend|book (your )?gains|sell to|harvest/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  // the tax report links here, and its estimate for the year now counts the dividends
  await page.goto("/tax-report");
  await settle(page);
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByRole("link", { name: "Tax tools" })).toBeVisible();      // a line in the total's card, no card of its own (LIVE1B-011)
  await page.getByLabel("Financial year").selectOption(String(fy));
  await openWorking(page.getByRole("region", { name: "Total tax estimate" }));          // LIVE1C-056
  await expect(page.getByRole("region", { name: "Total tax estimate" }).getByText(/Dividends of ₹15,000 are income from other sources/)).toBeVisible();
  expect((await request.delete(`${API}/tax`, { headers: auth })).ok()).toBeTruthy();
});
