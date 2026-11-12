import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Owner-approved features of 12 Nov (lane f3), on the fake world:
// 1. Import a watchlist: paste symbols on the watchlist page (every plan; Free sees the file import's lock), or a CSV's column from Market
//    Watch (Basic and up); each is found, to confirm or not found, then "Add N to <list>".
// 2. "Report an error in this figure": the flag beside a Key numbers row opens a dialog filled in with the page and figure; the report is in
//    Admin → Feedback as a data error with its figure; marked fixed, the reporter gets a note in the app.
// Its own accounts (the fake world's f3-0 … f3-11: free, basic, pro in turn), one per test and project. F3_SHOTS=<folder> also saves
// screenshots of both dialogs in light and dark.
const API = process.env.E2E_API!;
const SHOTS = process.env.F3_SHOTS;
type Who = { token: string; id: string; email: string };
const who = (i: number): Who => ({ token: `f3-${i}`, id: `u-f3-${i}`, email: `f3${i}@example.com` });
const session = (w: Who) => ({ access_token: w.token, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id: w.id, aud: "authenticated", email: w.email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const ADMIN: Who = { token: "admin-token", id: "u-admin", email: "owner@example.com" };
const phoneOf = (info: { project: { name: string } }) => info.project.name === "phone";

async function reset(request: APIRequestContext, w: Who) {
  const auth = { Authorization: `Bearer ${w.token}` };
  const got = await (await request.get(`${API}/watch/lists`, { headers: auth })).json();
  for (const l of got.lists) if (!l.default) await request.delete(`${API}/watch/lists/${l.id}`, { headers: auth });
  await request.put(`${API}/watch/lists/default/items`, { headers: auth, data: { items: [] } });
}

async function open(page: Page, w: Who, path: string, dark = false) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(([s, d]) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    localStorage.setItem("stratlab-theme", d ? "dark" : "light");
  }, [session(w), dark] as const);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 2500 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}

async function shot(page: Page, name: string, info: { project: { name: string } }) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-${info.project.name}.png`, fullPage: false });
}

test("paste symbols on the watchlist page: found, to confirm, not found, then added; Free sees the file import's lock", async ({ page, request }, info) => {
  const w = who(phoneOf(info) ? 3 : 0);          // Free
  await reset(request, w);
  const errors = await open(page, w, "/research/watchlist?region=IN");
  await page.getByTestId("watch-import-line").getByRole("button", { name: "Import a watchlist" }).click({ timeout: 30_000 });
  const dlg = page.getByRole("dialog", { name: "Import a watchlist" });
  await expect(dlg.getByRole("radiogroup", { name: "Look in" })).toBeVisible({ timeout: 30_000 });
  await expect(dlg).toContainText("is on the Basic plan");                 // the file import's lock, in the app's lock wording
  await expect(dlg.getByTestId("watch-import-drop")).toHaveCount(0);
  await dlg.getByRole("textbox").fill("RELIANCE, tcs\ninfosys\nzzzq\nTCS");
  await shot(page, "import-paste", info);
  await dlg.getByRole("button", { name: "Check 4 symbols" }).click();
  await expect(dlg.getByTestId("watch-import-summary")).toContainText("2 found, 1 to confirm, 1 not found", { timeout: 30_000 });
  const rows = dlg.getByRole("table", { name: "What each symbol matched" });
  await expect(rows.getByRole("combobox", { name: "Which company is infosys?" })).toHaveValue("IN:INFY");
  await expect(rows).toContainText("Nothing in the lists matches");
  await shot(page, "import-results", info);
  await dlg.getByTestId("watch-import-add").click();
  await expect(dlg).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator(".toast")).toContainText("Added 3 to Watchlist.");
  const list = page.getByRole("table", { name: "Your watchlist" });
  for (const s of ["RELIANCE", "TCS", "INFY"]) await expect(list.getByRole("link", { name: s, exact: true })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
  await reset(request, w);
});

test("a CSV from Market Watch (Basic): pick the column, check, and add to a list of your own", async ({ page, request }, info) => {
  const w = who(phoneOf(info) ? 4 : 1);          // Basic
  await reset(request, w);
  const auth = { Authorization: `Bearer ${w.token}` };
  await request.post(`${API}/watch/lists`, { headers: auth, data: { name: "Imports" } });
  const errors = await open(page, w, "/research");
  if (page.viewportSize()!.width <= 900) await page.getByRole("button", { name: "Markets", exact: true }).click({ timeout: 30_000 });
  else await page.getByTestId("markets-launch").click({ timeout: 30_000 });
  const panel = page.getByTestId("market-watch");
  await panel.getByRole("button", { name: "Import symbols into a list" }).click({ timeout: 30_000 });
  const dlg = page.getByRole("dialog", { name: "Import a watchlist" });
  await expect(dlg.getByTestId("watch-import-drop")).toBeVisible({ timeout: 30_000 });
  await dlg.getByLabel("Choose a CSV or Excel file of symbols").setInputFiles({ name: "holdings.csv", mimeType: "text/csv",
    buffer: Buffer.from("Client ID,AB12\n\nInstrument,Qty.,Avg. cost\nRELIANCE,10,2400\nTCS,5,3000\nINFY,2,1500\n") });
  const column = dlg.getByRole("combobox", { name: /Column with the symbols in holdings\.csv/ });
  await expect(column).toBeVisible({ timeout: 30_000 });
  await expect(column.locator("option:checked")).toContainText("Instrument: RELIANCE, TCS, INFY");
  await shot(page, "import-file", info);
  await dlg.getByRole("button", { name: "Check 3 symbols" }).click();
  await expect(dlg.getByTestId("watch-import-summary")).toContainText("3 found", { timeout: 30_000 });
  await dlg.getByRole("combobox", { name: "Add to" }).selectOption({ label: "Imports" });
  await dlg.getByRole("button", { name: "Add 3 to Imports" }).click();
  await expect(dlg).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator(".toast")).toContainText("Added 3 to Imports.");
  const got = await (await request.get(`${API}/watch/lists`, { headers: auth })).json();
  expect(got.lists.find((l: { name: string }) => l.name === "Imports").items.map((i: { id: string }) => i.id)).toEqual(["IN:RELIANCE", "IN:TCS", "IN:INFY"]);
  expect(errors).toEqual([]);
  await reset(request, w);
});

test("report an error in a Key numbers figure: it reaches Admin → Feedback as a data error, and the fix is a note in the app", async ({ page, browser }, info) => {
  const w = who(phoneOf(info) ? 5 : 2);          // Pro
  const note = `The annual report says otherwise (${info.project.name} ${Date.now()})`;
  const errors = await open(page, w, "/research/IN/RELIANCE");
  const table = page.getByRole("table", { name: /^Key numbers: / }).first();
  await expect(table).toBeVisible({ timeout: 30_000 });
  const row = table.locator("tbody tr").first();
  await row.hover();
  const flag = row.getByRole("button", { name: /^Report an error in / });
  const figure = ((await flag.getAttribute("aria-label")) ?? "").replace("Report an error in ", "");
  await flag.click();
  const dlg = page.getByRole("dialog", { name: "Report an error" });
  await expect(dlg.getByTestId("figure-report-where")).toContainText("Key numbers");
  await expect(dlg.getByTestId("figure-report-figure")).toContainText(figure);
  await expect(dlg).toContainText("reported figures");                      // the source
  await dlg.getByRole("textbox").fill(note);
  await shot(page, "report-dialog", info);
  await dlg.getByRole("button", { name: "Send" }).click();
  await expect(dlg.getByTestId("figure-report-done")).toBeVisible({ timeout: 30_000 });
  await dlg.getByRole("button", { name: "Close", exact: true }).first().click();
  // a figure outside a scope (the company's facts) has no flag
  await expect(page.getByRole("table", { name: "Facts about the company" }).getByRole("button", { name: /^Report an error/ })).toHaveCount(0);

  // the admin sees it with its figure and marks it fixed
  const ctx = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: page.viewportSize() ?? undefined });
  const admin = await ctx.newPage();
  await open(admin, ADMIN, "/admin/feedback");
  const inbox = admin.getByRole("table", { name: "Feedback reports" }).getByRole("row").filter({ hasText: note });
  await expect(inbox).toBeVisible({ timeout: 30_000 });
  await expect(inbox).toContainText("Data error");
  await expect(inbox.getByTestId("feedback-figure")).toContainText(figure);
  await expect(inbox.getByTestId("feedback-figure")).toContainText("Key numbers");
  await inbox.getByRole("combobox").selectOption("fixed");
  await expect(admin.getByRole("table", { name: "Feedback reports" }).getByRole("row").filter({ hasText: note })).toContainText("Reporter told", { timeout: 30_000 });
  await ctx.close();

  // the reporter's next visit says so once
  await page.goto("/research");
  await expect(page.locator(".toast")).toContainText(/Fixed: .*which you reported|figures you reported were fixed/, { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("the dialogs in dark mode", async ({ page, request }, info) => {
  test.skip(!SHOTS, "screenshots only");
  const w = who(phoneOf(info) ? 7 : 6);
  await reset(request, w);
  await open(page, w, "/research/watchlist?region=IN", true);
  await page.getByTestId("watch-import-line").getByRole("button", { name: "Import a watchlist" }).click({ timeout: 30_000 });
  const dlg = page.getByRole("dialog", { name: "Import a watchlist" });
  await dlg.getByRole("textbox").fill("RELIANCE, tcs\ninfosys\nzzzq");
  await shot(page, "dark-import-paste", info);
  await dlg.getByRole("button", { name: "Check 4 symbols" }).click();
  await expect(dlg.getByTestId("watch-import-summary")).toBeVisible({ timeout: 30_000 });
  await shot(page, "dark-import-results", info);
  await dlg.getByRole("button", { name: "Back" }).click();
  await page.keyboard.press("Escape");
  await page.goto("/research/IN/RELIANCE");
  const row = page.getByRole("table", { name: /^Key numbers: / }).first().locator("tbody tr").first();
  await row.hover({ timeout: 30_000 });
  await shot(page, "dark-key-numbers-flag", info);
  await row.getByRole("button", { name: /^Report an error in / }).click();
  await shot(page, "dark-report-dialog", info);
});
