import { expect, test, type Page } from "@playwright/test";

// Net worth (Money): add entries of each sort, see the totals, the allocation and the as-of dates, work out a loan
// prepayment, download the CSV and delete it all. Each project signs in as its own empty account.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, path: string, ready: string, who: ReturnType<typeof sessionFor>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
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
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
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

const iso = (d: Date) => d.toISOString().slice(0, 10);

test("net worth: add assets, a loan and a policy, prepay arithmetic, CSV and delete", async ({ page, request }, info) => {
  const n = info.project.name === "phone" ? 172 : 171;
  const who = sessionFor(n);
  expect((await request.delete(`${API}/money/net-worth`, { headers: { Authorization: `Bearer load-${n}` } })).ok()).toBeTruthy();
  const errors = await open(page, "/money/net-worth", "Nothing added yet", who);
  if (info.project.name === "desktop") await expect(page.getByRole("link", { name: "Net worth" }).first()).toBeVisible();   // in the menu

  const kind = page.getByLabel("What is it?");
  await page.getByLabel("Amount (₹)").fill("2,50,000");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Savings and cash added.")).toBeVisible();
  const totals = page.getByLabel("Totals");
  await expect(totals.getByText("₹2,50,000").first()).toBeVisible();

  const year = new Date();
  await kind.selectOption("fd");
  await page.getByLabel("Name (optional)").fill("Bank FD");
  await page.getByLabel("Amount deposited (₹)").fill("100000");
  await page.getByLabel("Interest rate (% a year)").fill("7");
  await page.getByLabel("Start date").fill(iso(new Date(year.getFullYear() - 1, year.getMonth(), 1)));
  await page.getByLabel("Maturity date").fill(iso(new Date(year.getFullYear() + 1, year.getMonth(), 1)));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const assets = page.getByRole("table", { name: "Assets" });
  await expect(assets.getByText("Bank FD")).toBeVisible();
  await expect(assets.getByText(/Matures .*: ₹1,14,/)).toBeVisible();                   // two years at 7%, every quarter

  await kind.selectOption("loan");
  await page.getByLabel("Kind").selectOption("home");
  await page.getByLabel("Amount borrowed, or owed on a card (₹)").fill("3000000");
  await page.getByLabel("Interest rate (% a year)").fill("8.5");
  await page.getByLabel("Tenure in months (empty for a card)").fill("240");
  await page.getByLabel("Loan start date").fill(iso(new Date(year.getFullYear() - 2, 0, 10)));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const loans = page.getByRole("table", { name: "Loans" });
  await expect(loans.getByText("₹26,035")).toBeVisible();                              // the EMI on ₹30 lakh, 20 years at 8.5%

  await kind.selectOption("policy");
  await page.getByLabel("Insurer").fill("Some Insurer");
  await page.getByLabel("Premium (₹)").fill("15000");
  const due = new Date(); due.setDate(due.getDate() + 20);
  await page.getByLabel("Next premium due").fill(iso(due));
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("table", { name: "Insurance policies" }).getByText(/due in (19|20|21) days/)).toBeVisible();
  await expect(page.getByText("Premiums a year:")).toBeVisible();

  await expect(page.getByRole("list", { name: "Assets by class" }).getByText("FDs and RDs")).toBeVisible();
  await expect(page.getByText(/Worked out as of/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);

  await loans.getByRole("button", { name: /^Prepay/ }).click();
  const box = page.getByRole("dialog", { name: /Prepay/ });
  await box.getByLabel("Prepay (₹)").fill("500000");
  await box.getByRole("button", { name: "Work it out" }).click();
  await expect(box.getByText("Same EMI, shorter loan:")).toBeVisible();
  await expect(box.getByText("Same end date, smaller EMI:")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await box.getByRole("button", { name: "Close" }).click();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toMatch(/^stratlab-net-worth-.*\.csv$/);
  await sane(page, errors);

  await assets.getByRole("button", { name: "Edit Bank FD" }).click();
  const edit = page.getByRole("dialog", { name: "Edit: Fixed deposit" });
  await edit.getByLabel("Amount deposited (₹)").fill("200000");
  await edit.getByRole("button", { name: "Save" }).click();
  await expect(assets.getByText(/Matures .*: ₹2,29,/)).toBeVisible();

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Delete my net worth data" }).click();
  await expect(page.getByText("Nothing added yet")).toBeVisible();
  await expect(page.getByText("Your net worth data is deleted.")).toBeVisible();
  await sane(page, errors);
});
