import { expect, test } from "@playwright/test";
import { sessionAs, open, sane, touchable, answerLevel, ownUser, tab } from "./pages-kit";

// Alerts set from each place, the admin pages for data, rules and the market audit, and the market pages (breadth,
// positioning).

test("alerts: set one on a company page, then edit and delete it on the Alerts page", async ({ page }, info) => {
  const tag = `e2e ${info.project.name} ${Date.now()}`;             // both projects share the fake database
  const me = ownUser(info, 253, 256);
  let errors = await open(page, "/research/IN/RELIANCE", "Reliance", me);
  await answerLevel(page);
  await page.getByRole("button", { name: "Set alert" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Alert on RELIANCE" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Price level (₹)").fill("1");
  await dialog.getByLabel("Note for yourself").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Set alert" }).click();
  await expect(page.getByText(/already above ₹1/).first()).toBeVisible();   // the price is far above: it waits for a cross
  await sane(page, errors);

  errors = await open(page, "/alerts", "Your stock alerts", me);
  await answerLevel(page);
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Price crosses above ₹1");
  if (info.project.name === "phone") await touchable(page);
  await row.getByRole("button", { name: /Edit/ }).click();
  const edit = page.getByRole("dialog", { name: "Edit alert on RELIANCE" });
  await edit.getByLabel("Alert me when").selectOption("ma_below");
  await edit.getByLabel("Moving average", { exact: true }).selectOption("200");
  await edit.getByRole("button", { name: "Save alert" }).click();
  await expect(row).toContainText("Price crosses below its 200-day average");
  await row.getByRole("button", { name: /Delete/ }).click();
  await page.getByRole("dialog", { name: /Delete the alert on/ }).getByRole("button", { name: "Delete alert" }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await sane(page, errors);
});

test("alerts: a new one from the Alerts page, for any stock", async ({ page }, info) => {
  const tag = `e2e-new ${info.project.name} ${Date.now()}`;
  // a Pro user per project: run side by side (this file opens both projects at once), the owner's list refused the second as a twin
  const errors = await open(page, "/alerts", "Your stock alerts", ownUser(info, 173, 182));
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  // "Where alerts go" is offered once, and the Stock box takes the whole row, not a 190px sliver
  await expect(page.getByRole("link", { name: /Where alerts go/ }).or(page.getByRole("button", { name: /Where alerts go/ }))).toHaveCount(1);
  const stock = await page.getByLabel("Stock").evaluate((el) => ({ box: el.getBoundingClientRect().width, form: (el.closest("form") as HTMLElement).getBoundingClientRect().width }));
  expect(stock.box, "the Stock box is narrow").toBeGreaterThan(stock.form * 0.9);
  expect(await page.getByLabel("Stock").evaluate((el) => (el as HTMLInputElement).scrollWidth <= (el as HTMLInputElement).clientWidth), "its placeholder is clipped").toBe(true);
  await page.getByLabel("Stock").fill("TCS");
  await page.getByLabel("Alert me when").selectOption("move_either");
  await page.getByLabel("Move in a day (%)").fill("4");
  await page.getByLabel("Note for yourself").fill(tag);
  await page.getByLabel(/Repeat/).check();
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Moves 4% or more either way in a day");
  await expect(row).toContainText("Repeats");
  // Delete asks first: Cancel keeps the alert
  await row.getByRole("button", { name: /Delete/ }).click();
  await page.getByRole("dialog", { name: /Delete the alert on/ }).getByRole("button", { name: "Cancel" }).click();
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: /Delete/ }).click();
  await page.getByRole("dialog", { name: /Delete the alert on/ }).getByRole("button", { name: "Delete alert" }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await sane(page, errors);
});

test("alerts: Set alert on the watchlist offers its stocks", async ({ page }, info) => {
  const tag = `e2e-watch ${info.project.name} ${Date.now()}`;
  const me = ownUser(info, 259, 266);
  const errors = await open(page, "/research/watchlist?region=IN", "Companies you're watching", me);
  await answerLevel(page);
  // a watchlist of one, without changing the shared one other tests read
  await page.route("**/research/watchlist", (r) => r.request().method() === "GET"
    ? r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ region: "IN", symbol: "RELIANCE", name: "Reliance Industries" }] }) })
    : r.fallback());
  await page.reload();
  await page.getByRole("button", { name: "Set alert" }).click();
  const dialog = page.getByRole("dialog", { name: "Set an alert" });
  await expect(dialog.getByLabel("Stock")).toHaveValue("IN:RELIANCE");
  await dialog.getByLabel("Alert me when", { exact: true }).selectOption("high52");
  await dialog.getByLabel("Note for yourself").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await dialog.getByRole("button", { name: "Set alert" }).click();
  await expect(page.getByText("Alert set on RELIANCE.")).toBeVisible();
  await sane(page, errors);
  await open(page, "/alerts", "Your stock alerts", me);
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Makes a new 52-week high");
  await row.getByRole("button", { name: /Delete/ }).click();
  await page.getByRole("dialog", { name: /Delete the alert on/ }).getByRole("button", { name: "Delete alert" }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
});

test("alerts: one on bulk or block deals, India only", async ({ page }, info) => {
  const tag = `e2e-deal ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts", ownUser(info, 188, 194));      // its own users, as above
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("RELIANCE");
  await page.getByLabel("Alert me when").selectOption("deal");
  await expect(page.getByText("Checked once each evening against that day's exchange disclosures.", { exact: false })).toBeVisible();
  await page.getByLabel("Note for yourself").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("A bulk or block deal is reported");
  await row.getByRole("button", { name: /Delete/ }).click();
  await page.getByRole("dialog", { name: /Delete the alert on/ }).getByRole("button", { name: "Delete alert" }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Market", { exact: true }).selectOption("US");
  await expect(page.getByLabel("Alert me when").locator("option", { hasText: "bulk or block deal" })).toHaveCount(0);
  await sane(page, errors);
});

test("alerts: one on a stock entering or leaving a surveillance list, India only", async ({ page }, info) => {
  const tag = `e2e-surv ${info.project.name} ${Date.now()}`;
  const errors = await open(page, "/alerts", "Your stock alerts", ownUser(info, 197, 203));      // its own users, as above
  await answerLevel(page);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Stock").fill("INFY");
  await page.getByLabel("Alert me when").selectOption("surveillance");
  await expect(page.getByText("Checked twice each trading day against the exchange's surveillance lists", { exact: false })).toBeVisible();
  await page.getByLabel("Note for yourself").fill(tag);
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Set alert" }).click();
  const row = page.locator(".alert-row", { hasText: tag });
  await expect(row).toContainText("Enters or leaves an exchange surveillance list");
  await row.getByRole("button", { name: /Delete/ }).click();
  await page.getByRole("dialog", { name: /Delete the alert on/ }).getByRole("button", { name: "Delete alert" }).click();
  await expect(page.locator(".alert-row", { hasText: tag })).toHaveCount(0);
  await page.getByRole("button", { name: "New alert" }).click();
  await page.getByLabel("Market", { exact: true }).selectOption("US");
  await expect(page.getByLabel("Alert me when").locator("option", { hasText: "surveillance list" })).toHaveCount(0);
  await sane(page, errors);
});

test("admin: exchange holidays show every market's source, coverage and next holiday", async ({ page }, info) => {
  const errors = await open(page, "/admin/data", "Exchange holidays");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 3000 }).catch(() => undefined);   // asked once, if not yet
  const panel = page.locator("section", { has: page.getByRole("heading", { name: "Exchange holidays" }) });
  const table = panel.getByRole("table", { name: "Holidays by market" });
  for (const name of ["India (NSE/BSE)", "MCX", "Currency F&O", "US", "UK", "Europe", "Japan", "Commodities", "Crypto", "Forex"])
    await expect(table.getByRole("rowheader", { name, exact: true })).toBeVisible();
  await expect(table.getByText("No exchange holidays: trades 24/7")).toHaveCount(1);
  await expect(table.getByText("No exchange holidays: trades on weekdays")).toHaveCount(1);
  await expect(table.getByText("Built-in calendar rules")).toHaveCount(5);
  await expect(table.getByText("Exchange's own list, read daily")).toHaveCount(3);
  await expect(panel.getByRole("button", { name: "Read the exchange's list now" })).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("admin: rates and rules show each area's review, the source watch and every rule", async ({ page }, info) => {
  const errors = await open(page, "/admin/quality", "Rates and rules");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 3000 }).catch(() => undefined);   // asked once, if not yet
  const panel = page.getByTestId("rules-panel");
  for (const area of ["Trading costs", "Income tax", "Interest rates", "Market rules", "Surveillance lists"])
    await expect(panel.getByRole("rowheader", { name: area, exact: true })).toBeVisible();
  for (const src of ["SEC fee rate", "PPF rate", "NSE circulars on charges and contract rules"]) await expect(panel.getByText(src, { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: /Show all \d+ rules/ }).click();
  await expect(panel.getByRole("rowheader", { name: /US SEC fee \(Section 31\)/ })).toBeVisible();
  await expect(panel.getByText("$20.60 a million on sells")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("admin: fund costs (TER) shows its last read in Data and jobs and reads again on request", async ({ page }, info) => {
  let reads = 0;
  await page.route((u) => u.pathname === "/admin/ter/read", (r) => { reads++; return r.fallback(); });
  const errors = await open(page, "/admin/data", "Fund costs (TER)");
  const row = page.getByRole("row", { name: /Fund costs \(TER\)/ });
  await expect(row.getByRole("button", { name: "Read now: Fund costs (TER)" })).toBeVisible({ timeout: 30_000 });
  // a read of its own first: the world reads TER only when a page asks for fund costs, so run alone (or before the mutual
  // funds specs) nothing had been read yet and the log said "Not yet"
  await row.getByRole("button", { name: "Read now: Fund costs (TER)" }).click();
  await expect.poll(() => reads).toBe(1);
  await expect(row.getByRole("button", { name: "Read now: Fund costs (TER)" })).toBeEnabled({ timeout: 30_000 });
  await row.getByRole("button", { name: "Log of Fund costs (TER)" }).click();
  await expect(page.getByRole("dialog", { name: "Fund costs (TER): log" })).toContainText(/3 schemes for/, { timeout: 30_000 });
  await page.keyboard.press("Escape");
  await row.getByRole("button", { name: "Read now: Fund costs (TER)" }).click();
  await expect.poll(() => reads).toBe(2);
  await expect(row.getByRole("button", { name: "Read now: Fund costs (TER)" })).toBeEnabled({ timeout: 30_000 });
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("admin: the whole-market audit tells facts and companies not checked yet apart, and re-checks those", async ({ page }, info) => {
  const sent: object[] = [];
  const row = (symbol: string, name: string, level: string, area: string, detail: string) => ({ symbol, name, seconds: 1, issues: [{ level, area, detail }] });
  const refused = "Not checked yet: the exchange feed refused the request (403). It is checked again later.";
  const rows = [row("BSE:543210", "Tiny Co Ltd", "pending", "Documents", refused), row("BSE:543211", "Small Co Ltd", "pending", "Documents", refused),
    row("NEWCO", "New Co Ltd", "fact", "Numbers", "Only 2 years of annual results so far: listed, demerged or first reporting recently")];
  const summary = { companies: 3, clean: 1, mismatches: 0, gaps: 0, errors: 0, facts: 1, pending: 2, avg_seconds: 1, slowest: [],
    by_area: { Documents: { mismatch: 0, gap: 0, error: 0, fact: 0, pending: 2 }, Numbers: { mismatch: 0, gap: 0, error: 0, fact: 1, pending: 0 } } };
  const state = (retrying: boolean, india: boolean) => ({ enabled: true, listed: 3, checked: 3, due: retrying ? 2 : 0, current: null, eta_hours: null,
    list_at: null, list_error: null, new_listings: [], pending: india ? 2 : 0, rows: india ? rows : [], summary: india ? summary : { ...summary, companies: 0 },
    full: { running: retrying, since: retrying ? new Date().toISOString() : null, done_at: null, left: retrying ? 2 : 0, checked: null, pending_only: retrying } });
  let retrying = false;
  await page.route((u) => u.pathname === "/admin/audit/market", async (r) => {
    const req = r.request();
    const body = req.method() === "POST" ? req.postDataJSON() : null;
    if (body) { sent.push(body); retrying = true; }
    const india = body ? (body.region ?? "IN") === "IN" : new URL(req.url()).searchParams.get("region") !== "US";
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state(retrying && india, india)) });
  });
  const errors = await open(page, "/admin/quality", "Whole market: India");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 3000 }).catch(() => undefined);   // asked once, if not yet
  const india = page.locator("section", { hasText: "Whole market: India" });
  await expect(india.getByText("0 gaps · 0 errors · 1 fact · 2 not checked yet")).toBeVisible();
  await india.getByRole("button", { name: "Facts", exact: true }).click();
  await expect(india.getByText("Only 2 years of annual results so far")).toBeVisible();
  await india.getByRole("button", { name: "Not checked yet", exact: true }).click();
  await expect(india.getByText("Tiny Co Ltd")).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await india.locator("summary", { hasText: "Manage this check" }).click();                  // the check's buttons are behind one fold (LIVE1C-020)
  await india.getByRole("button", { name: "Re-check the 2 not checked yet" }).click();
  await expect.poll(() => sent).toEqual([{ region: "IN", retry: true }]);
  await expect(india.getByText("Re-checking companies not checked yet:")).toBeVisible();
  await sane(page, errors);
});

test("admin: the whole-market audit starts, pauses, resets, re-checks one company and shows BSE waiting", async ({ page }, info) => {
  const sent: Record<string, unknown>[] = [];
  const err = { symbol: "ACME", name: "Acme Ltd", seconds: 2, issues: [{ level: "error", area: "Numbers", detail: "Revenue or profit missing for Mar 2024", since: new Date(Date.now() - 3 * 86400e3).toISOString() }] };
  const summary = (n: number) => ({ companies: n, clean: 0, mismatches: 1, gaps: 1, errors: n ? 1 : 0, facts: 0, pending: 0, avg_seconds: 2, slowest: [],
    by_area: n ? { Numbers: { mismatch: 1, gap: 1, error: 1, fact: 0, pending: 0 } } : {} });
  let s = { enabled: false, paused: "off", listed: 5058, checked: 3844, due: 0, current: null, eta_hours: null, rate_per_hour: 0, list_at: null, list_error: null,
    full: { running: true, since: new Date(Date.now() - 7 * 3600e3).toISOString(), done_at: null, left: 1214, checked: 3844, everything: true, pending_only: false },
    monthly: { on: true, last: "2026-10", next: "2026-11-01" },
    ages: { open: 40, today: 6, days_1_2: 4, days_3_7: 10, over_a_week: 20, oldest_days: 19 },
    retry: { waiting: 1868, due: 0, next: new Date(Date.now() + 40 * 60e3).toISOString(), gap_hours: 1, batch: 20 },
    bse: { refusing: true, waiting: 1868 }, pending: 1911, new_listings: [], rows: [err], summary: summary(1) } as Record<string, unknown>;
  await page.route((u) => u.pathname === "/admin/audit/market", async (r) => {
    const req = r.request();
    const body = req.method() === "POST" ? req.postDataJSON() : null;
    const us = body ? body.region === "US" : new URL(req.url()).searchParams.get("region") === "US";
    if (body && !us) {
      sent.push(body);
      if ("on" in body) s = { ...s, enabled: body.on, paused: body.on ? null : "off" };
      if (body.reset) s = { ...s, enabled: true, paused: null, checked: 0, due: 5058, rate_per_hour: 0, rows: [], summary: summary(0),
        full: { running: true, since: new Date().toISOString(), done_at: null, left: 5058, checked: 0, everything: true, pending_only: false } };
      if ("monthly" in body) s = { ...s, monthly: { on: body.monthly, last: "2026-10", next: body.monthly ? "2026-11-01" : null } };
    }
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(us ? { ...s, bse: undefined, rows: [], summary: summary(0), full: { ...(s.full as object), running: false } } : s) });
  });
  const errors = await open(page, "/admin/quality", "Whole market: India");
  await page.getByRole("button", { name: /I've done a bit/ }).click({ timeout: 3000 }).catch(() => undefined);
  const india = page.locator("section", { hasText: "Whole market: India" });
  // paused, and why; a clear Start button
  await expect(india.getByText("Paused: switched off. Press Start to check companies.")).toBeVisible();
  await expect(india.getByText(/Full check: 3,844 of 5,058 done/)).toBeVisible();
  await expect(india.getByRole("progressbar", { name: "Full check India" })).toBeVisible();
  await expect(india.getByText("1 mismatch", { exact: true })).toBeVisible();
  await expect(india.getByText("1 gap · 1 error")).toBeVisible();
  await expect(india.getByText(/BSE is refusing requests from this server; 1,868 companies waiting/)).toBeVisible();
  await expect(india.getByText("Next full check: 1 Nov")).toBeVisible();
  // the problems standing say how long they have stood (MS1-004)
  await expect(india.getByTestId("audit-ages")).toContainText("Problems standing: 40 (6 found today, 14 up to a week old, 20 over a week old) · the oldest for 19 days.");
  if (info.project.name === "phone") await touchable(page);
  await india.getByRole("button", { name: "Start the India check" }).click();
  await expect(india.getByRole("button", { name: "Pause the India check" })).toBeVisible();
  await expect.poll(() => sent).toEqual([{ region: "IN", on: true }]);
  // an error row: its reason, and a re-check of that one company
  await india.getByRole("button", { name: "Errors", exact: true }).click();
  await expect(india.getByText("Revenue or profit missing for Mar 2024")).toBeVisible();
  await expect(india.getByTestId("audit-age")).toHaveText(" · open 3 days");
  await india.getByRole("button", { name: "Re-check Acme Ltd" }).click();
  await expect.poll(() => sent.at(-1)).toEqual({ region: "IN", recheck: "ACME" });
  // the monthly check can be switched off (its buttons are behind one fold, LIVE1C-020)
  await india.locator("summary", { hasText: "Manage this check" }).click();
  await india.getByRole("checkbox", { name: "Full re-check on the 1st of each month" }).click();
  await expect(india.getByText("Only new listings, until you reset")).toBeVisible();
  // reset asks first, in the page (never the browser's own box): Cancel does nothing, confirming clears and starts from 0
  const boxes: string[] = [];
  page.on("dialog", (d) => { boxes.push(d.message()); void d.dismiss(); });
  await india.getByRole("button", { name: "Reset and check everything again" }).click();
  const ask = page.getByRole("dialog", { name: "Check every India company again?" });
  await expect(ask).toContainText("This clears every stored result for India");
  await ask.getByRole("button", { name: "Cancel" }).click();
  await expect(ask).toHaveCount(0);
  expect(sent.some((b) => b.reset)).toBe(false);
  await india.getByRole("button", { name: "Reset and check everything again" }).click();
  await page.getByRole("dialog", { name: "Check every India company again?" }).getByRole("button", { name: "Reset and check again" }).click();
  await expect.poll(() => sent.at(-1)).toEqual({ region: "IN", reset: true });
  await expect(india.getByText(/Full check: 0 of 5,058 done/)).toBeVisible();
  expect(boxes, "no browser box opened").toEqual([]);
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);
});

test("market breadth: today's numbers, small charts, sectors, groups and ranges; facts only, no provider names", async ({ page }, info) => {
  const errors = await open(page, "/invest/breadth", "Rose / fell");
  const today = page.getByTestId("breadth-today");
  // MOOD-1: the figures are one table: a measure, its day, the day before, the change (with ▲/▼ and a sign)
  await expect(today.getByRole("rowheader", { name: /Above 50-day average/ })).toBeVisible();
  for (const head of [/^\d+ \w+$/, "Change"]) await expect(today.getByRole("columnheader", { name: head }).first()).toBeVisible();
  await expect(today.locator(".k-delta").first()).toContainText(/[▲▼]/);
  const charts = page.getByTestId("breadth-charts");
  await expect(charts.getByRole("heading", { name: "Advance/decline line" })).toBeVisible();
  for (const name of ["Above the 50- and 200-day averages", "New 52-week highs and lows", "McClellan oscillator", "Stocks up 4% or more and down 4% or more, each day",
    "Sectors: share above the 50-day average", "Breadth thrust measure", "TRIN"]) await expect(charts.getByRole("heading", { name })).toBeVisible();
  // the index is its own small chart: no chart has a second scale
  await expect(charts.getByRole("heading", { name: /^NIFTY 500/ })).toBeVisible();
  expect(await charts.locator("svg[role=img]").count()).toBeGreaterThanOrEqual(9);
  // R24-011, R79-008: above the live card the chip names the day-by-day figures; with no live card, their day. The demo's
  // live card is live or final by the clock (just after 15:30 IST it is final), so either wording is right whenever this runs
  await expect(page.getByText(/Daily figures to|Last close|Prices as of/).first()).toBeVisible();
  // each figure and chart explains itself
  await charts.getByRole("button", { name: "About McClellan oscillator" }).click();
  await expect(page.getByRole("note")).toContainText("39-day");
  // the sector table and the counts behind the charts
  await expect(page.getByRole("table", { name: /Share of each sector/ }).locator("tbody tr").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "The last 20 trading days" })).toBeVisible();
  // a hover shows the day's numbers on the bars
  await charts.locator("svg[aria-label^='New 52-week highs']").hover();
  await expect(page.locator(".chart-tip")).toContainText("new highs");
  // an alert on the share above the 50-day average, from the bell on its row: added (the row then says the level), listed, deleted
  const level = info.project.name === "phone" ? "45" : "55";            // the two projects share one account
  await today.getByTestId("breadth-alert-open").click();
  const box = page.getByRole("dialog", { name: "Alert on the share above the 50-day average" });
  await box.getByLabel(/crosses$/).fill(level);
  await box.getByRole("button", { name: "Add alert" }).click();
  await expect(box.getByRole("cell", { name: `${level}%`, exact: true })).toBeVisible();
  await box.getByRole("button", { name: `Delete the alert at ${level}% on NIFTY 500` }).click();
  await expect(box.getByRole("cell", { name: `${level}%`, exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  // a shorter range, then another group (the US), keep the page whole
  const ranges = page.getByRole("group", { name: "History charts' range" });
  const ticks = () => charts.locator(".ch").first().locator("svg.ch-svg text.ch-tick").allTextContents();
  const before = (await ticks()).join("|");
  await ranges.getByRole("button", { name: "3M" }).click();
  await expect.poll(async () => (await ticks()).join("|"), "the 3M button redraws the charts").not.toBe(before);
  await expect(ranges.getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Group of stocks").selectOption("us_large");
  await expect(charts.getByRole("heading", { name: /^SPY \(an S&P 500 fund\)/ })).toBeVisible();
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub|nseindia/i);      // "Screener" alone is a menu entry
  expect(text).not.toMatch(/\b(buy|sell|bullish|bearish|you should|accumulate|overbought|oversold)\b/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);

  // a neighbouring tab of Market today (IA-1) and the Invest home lead here
  await page.goto("/research/rotation");
  await tab(page, info.project.name === "phone", "Market today", "Breadth");
  await expect(page).toHaveURL(/\/invest\/breadth/);
  await page.goto("/invest");
  await expect(page.getByTestId("breadth-card")).toContainText("Above 50-day average");
});

test("market breadth on the Free plan: today's numbers, and the charts behind Basic", async ({ page }) => {
  // as the server answers a Free account once payments are live (the fake world has every feature open)
  await page.route("**/invest/breadth?*", async (r) => {
    const res = await r.fetch();
    const body = await res.json();
    await r.fulfill({ response: res, json: { ...body, locked: true, history: null, sectors: null, thrusts: null } });
  });
  const errors = await open(page, "/invest/breadth", "Rose / fell", sessionAs("free-token", "u-free", "free@example.com"));
  await expect(page.getByTestId("breadth-locked")).toContainText("on the Basic plan");
  await expect(page.getByTestId("breadth-charts")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "History charts' range" })).toHaveCount(0);
  await sane(page, errors);
});

test("positioning: participants, cash flows, PCR, the chain by strike and the history; facts only", async ({ page }, info) => {
  const errors = await open(page, "/trade/positioning", "Participant-wise open interest");
  const main = page.locator("main");
  await expect(main.getByTestId("part-status")).toContainText("As of");
  for (const who of ["client", "dii", "fii", "pro", "total"]) await expect(main.locator(`tr[data-participant="${who}"]`)).toBeVisible();
  await expect(main.getByText("FII index futures, net")).toBeVisible();
  // both sides of the futures: the long and the short share, adding up to 100
  await expect(main.getByText("FII index futures, long share")).toBeVisible();
  await expect(main.getByTestId("split-fii")).toHaveCount(0);                                     // the split is a click away in the table
  await main.getByTestId("cols-pos-part").click();
  const split = await main.getByTestId("split-fii").innerText();
  const [lo, sh] = (split.match(/[\d.]+(?=%)/g) ?? []).map(Number);
  expect(lo + sh).toBeCloseTo(100, 1);
  const sidesRow = main.getByTestId("part-figs").locator("tbody tr").filter({ has: page.getByTestId("sides-fig") });
  await expect(sidesRow).toContainText(/long share\s*[\d.]+%\s*[\d.]+% short/);        // VR1-070: the long share as the figure, the short side in its note
  await expect(sidesRow).toContainText(/[+−][\d.]+ pts from the previous trading day/);
  // a figure is three rows shared with its neighbours (label, number, note): nothing in one draws over the next
  const overlaps = await main.locator(".k-stat").evaluateAll((figs) => figs.flatMap((f) => {
    const rows = Array.from(f.children).map((c) => c.getBoundingClientRect()).filter((b) => b.height > 0);
    return rows.slice(1).flatMap((b, i) => (b.top < rows[i].bottom - 1 ? [`${(f.textContent ?? "").slice(0, 40)}: row ${i + 2} over row ${i + 1}`] : []));
  }));
  expect(overlaps, "figures drawn over themselves").toEqual([]);
  // where the numbers come from and how much is stored, in a line per section
  await expect(main.getByTestId("part-source")).toContainText("end-of-day participant-wise file");
  await expect(main.getByTestId("part-source")).toContainText(/\d+ trading days since/);
  await expect(main.getByTestId("cash-source")).toContainText("provisional FII/DII figures");
  await expect(main.getByTestId("pcr-source")).toBeVisible();
  // stock futures and options from the same file
  await main.getByRole("radio", { name: "Stock F&O", exact: true }).click();
  await expect(main.getByTestId("part-table")).toHaveAttribute("data-segment", "stk");
  await expect(main.getByText("FII stock futures, net")).toBeVisible();
  await expect(main.getByRole("columnheader", { name: "Stock F&O" })).toBeVisible();
  await main.getByRole("radio", { name: "Index F&O", exact: true }).click();
  await main.getByRole("radio", { name: "Volume", exact: true }).click();
  await expect(main.getByRole("columnheader", { name: "Futures bought", exact: true })).toBeVisible();
  await expect(main.getByRole("columnheader", { name: "Futures bought / sold" })).toBeVisible();
  await expect(main.locator("#pos-cash").getByRole("row", { name: /^FII\/FPI/ })).toBeVisible();          // the cash market is a table: who, net, bought, sold
  const pcr = main.getByTestId("pcr-table");
  for (const n of ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]) await expect(pcr.locator(`tr[data-pcr="${n}"]`)).toBeVisible({ timeout: 30_000 });
  await expect(pcr.locator('tr[data-pcr="NIFTY"]').getByTestId("pcr-expiry")).toHaveText(/\d/);     // the expiry, under the index's name
  // both tables fit their cards without a sideways swipe on a laptop
  const wide = await main.locator("[data-testid=part-table], [data-testid=pcr-table]").evaluateAll((ts) => ts.map((t) => t.parentElement!.scrollWidth - t.parentElement!.clientWidth));
  if (info.project.name === "desktop") expect(wide.every((w) => w <= 1), `tables wider than their cards: ${wide}`).toBe(true);
  const facts = main.getByTestId("chain-facts");
  await expect(facts.getByText("Max pain, near the money")).toBeVisible({ timeout: 30_000 });   // DB-012
  await expect(facts.getByText(/IV percentile/)).toBeVisible();
  await expect(facts.locator(".strike-chart svg path").first()).toBeVisible();
  await expect(facts).toContainText("IST");
  await facts.getByRole("radio", { name: "Change", exact: true }).click();
  await expect(facts.locator(".strike-chart svg path").first()).toBeVisible();
  await main.getByRole("group", { name: "Index", exact: true }).getByRole("button", { name: "BANKNIFTY" }).click();
  // the live chain's spot (55,000), or, with the market shut, the newest recording's close near it: which one depends on the hour
  await expect(main.getByTestId("chain-facts")).toContainText(/spot 5[45],\d{3}/, { timeout: 30_000 });
  await main.getByText("Show the strikes as a table").click();
  await expect(main.getByRole("columnheader", { name: "Call OI" })).toBeVisible();
  // the history (the owner is on Pro): each participant's positions and each index's PCR and IV by day
  await expect(main.getByText("FII: index futures, net (contracts)")).toBeVisible({ timeout: 30_000 });
  await expect(main.getByText("FII: index futures, long share (% of long + short)")).toBeVisible();
  await expect(main.getByTestId("history-source")).toContainText("Participant files:");
  await expect(main.getByText("NIFTY ATM implied volatility (%)")).toBeVisible();
  await expect(main.getByTestId("chain-history-source")).toContainText("recorded NIFTY's chain since");
  await main.getByRole("group", { name: "Participant" }).getByRole("button", { name: "Client" }).click();
  await expect(main.getByText("Client: index futures, net (contracts)")).toBeVisible();
  await main.getByRole("radiogroup", { name: "Long share of" }).getByRole("radio", { name: "Stock futures" }).click();
  await expect(main.getByText("Client: stock futures, long share (% of long + short)")).toBeVisible();
  // an index with nothing recorded yet says so instead of an empty chart
  await main.getByRole("group", { name: "Index for the chain history" }).getByRole("button", { name: "MIDCPNIFTY" }).click();
  await expect(main.getByTestId("chain-history-source")).toContainText(/MIDCPNIFTY/);
  const text = await main.innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener|finnhub|nseindia/i);
  expect(text).not.toMatch(/\b(bullish|bearish|support|resistance|you should|buy now|sell now)\b/i);
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
});

test("positioning: a missing cash number says why instead of a dash", async ({ page }) => {
  const reason = "The last try (4 Oct 2026, 21:04 IST) didn't get them: The exchange feed refused the request (403). Try again later.";
  await page.route("**/trade/positioning?*", async (r) => {
    const res = await r.fetch();
    const body = await res.json();
    await r.fulfill({ response: res, json: { ...body, cash: { status: "none", as_of: null, expected: "2026-10-01", reason } } });
  });
  await sane(page, await open(page, "/trade/positioning", "Positioning"));
  await expect(page.getByTestId("cash-status")).toContainText("No cash numbers stored yet. The last try");
});

test("positioning: a link on the Trade home (no card), a link from the Options page, its own page with no tabs back to Options", async ({ page }, info) => {
  await sane(page, await open(page, "/trade", "Straddles, strangles"));
  await expect(page.getByTestId("positioning-card"), "the numbers show on the Positioning page only").toHaveCount(0);
  await expect(page.getByTestId("positioning-link").getByRole("link", { name: "Positioning" })).toHaveAttribute("href", "/trade/positioning");
  await page.goto("/options");
  await expect(page.getByTestId("positioning-card"), "the card shows in one place only").toHaveCount(0);       // the Options page links to Positioning instead
  await page.getByRole("link", { name: "open Positioning" }).click();
  await expect(page).toHaveURL(/\/trade\/positioning$/);
  await expect(page.getByRole("heading", { name: "Positioning", level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Options" })).toHaveCount(0);       // its own menu entry, no tabs
  if (info.project.name === "phone") await touchable(page);
});
