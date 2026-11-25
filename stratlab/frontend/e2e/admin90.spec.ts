import { expect, test, type Page } from "@playwright/test";

// Lane admin90 (owner, 25 Nov: "can you do a admin cleanup and check"): every Users header sorts, addresses break after their "@" and
// never inside a word, no stray profile row is listed as a user, the counts say when they were read, Needs your attention's words start
// on one line, an empty list is one line and not a table of headers, and a research run's repeats are counted, not listed twenty times.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

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
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(300);
  return errors;
}

test("admin90 Users: every header sorts, addresses break only after the @, no stray row, and no sessions is one line", async ({ page }, info) => {
  const errors = await open(page, "/admin/users", "Paper trading now");
  const table = page.getByRole("table", { name: "Users" });
  await expect(table).toBeVisible({ timeout: 30_000 });
  // the stray "files:u-admin" row the fake world's net worth pass made (a profile with no email) is not a user
  await expect(table.getByText("files:u-admin")).toHaveCount(0);
  if (info.project.name !== "phone") {
    for (const name of ["Sort Email", "Sort Plan", "Sort Joined", "Sort Last active", /^Sort Experiments/, /^Sort AI builds/]) {
      await expect(table.locator("thead").getByRole("button", { name })).toHaveCount(1);
    }
    // Email sorts A to Z on a click
    await table.locator("thead").getByRole("button", { name: "Sort Email" }).click();
    await page.waitForTimeout(300);
    const emails = (await table.locator("tbody .adm-email").allInnerTexts()).map((t) => t.replace(/\s+/g, ""));
    expect(emails.length).toBeGreaterThan(3);
    const az = new Intl.Collator("en-IN", { numeric: true, sensitivity: "base" });        // A to Z as the table sorts words (load9 before load10)
    expect(emails).toEqual([...emails].sort((a, b) => az.compare(a, b)));
  }
  // an address wraps, if at all, after its "@": the part from the "@" is on one line
  const split = await page.evaluate(() => [...document.querySelectorAll(".adm-email")].slice(0, 12).filter((el) => {
    const text = el.textContent ?? "", at = text.indexOf("@");
    if (at < 0) return false;
    const r = document.createRange(), node = [...el.childNodes].find((n) => n.nodeType === 3 && (n.textContent ?? "").startsWith("@"));
    if (!node) return true;
    r.selectNodeContents(node);
    const tops = new Set([...r.getClientRects()].map((x) => Math.round(x.top)));
    return tops.size > 1;
  }).map((el) => el.textContent));
  expect(split, "addresses broken inside their domain").toEqual([]);
  // no paper trading session: one line, not a table of headers over nothing
  await expect(page.getByTestId("sessions-none")).toBeVisible();
  await expect(page.getByRole("table", { name: "Paper trading sessions" })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("admin90 Overview: the counts say when they were read, and Needs your attention's words start on one line", async ({ page }) => {
  const errors = await open(page, "/admin", "Needs your attention");
  await expect(page.getByTestId("counted-at")).toContainText(/^Counted \d+ \w{3}, \d\d:\d\d IST/);
  const lefts = await page.locator(".adm-todo-body").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)));
  expect(lefts.length).toBeGreaterThan(1);
  expect(new Set(lefts).size, `the items' words start at ${lefts.join(", ")}`).toBe(1);
  expect(errors).toEqual([]);
});

test("admin90 Data and jobs: the research run's repeats are counted once, and Money's empty invoice year is one line", async ({ page }) => {
  const errors = await open(page, "/admin/data", "Background jobs");
  const run = page.getByTestId("blog-run");
  await expect(run).toBeVisible({ timeout: 30_000 });
  await expect(run).not.toContainText("theme unchanged, theme unchanged");
  await page.goto("/admin/money");
  await expect(page.getByText("No invoices in this financial year yet.", { exact: false })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("table", { name: "Invoices" })).toHaveCount(0);
  expect(errors).toEqual([]);
});
