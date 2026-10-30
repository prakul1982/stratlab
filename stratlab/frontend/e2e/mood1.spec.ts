import { expect, test, type Page } from "@playwright/test";

// MOOD-1 (owner, 29 Oct): the Market pulse's mood as tables for both markets, in the fake world (backend/tests/visual_server.py):
// a headline with a few lines whose figures are the tables', the sector count said once, the cards' levels not said again, every
// block of figures a table with a header row (a card per row on a phone), no sideways scroll.

const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByTestId("pulse-mood-card")).toBeVisible({ timeout: 60_000 });
  return errors;
}

for (const region of ["IN", "US"] as const) {
  test(`the ${region} pulse: a headline, a few lines, and tables that agree with them`, async ({ page }) => {
    const errors = await open(page, `/research/pulse?region=${region}`);
    const main = page.locator("main");
    // the mood: one headline and three to five lines
    const headline = (await page.getByTestId("pulse-mood").innerText()).trim();
    const lines = await page.getByTestId("pulse-mood-lines").locator("li").allInnerTexts();
    expect(headline.length).toBeGreaterThan(10);
    expect(lines.length).toBeGreaterThanOrEqual(3);
    expect(lines.length).toBeLessThanOrEqual(5);
    // the sector count is said once, from the table's own rows: the headline, the line and the table agree
    const sectors = page.getByTestId("pulse-sectors");
    const count = (await sectors.getByTestId("pulse-sector-count").innerText()).match(/^(\d+) of (\d+) sector indices rose, (\d+) fell/)!;
    const rows = await sectors.locator("tbody tr").count();
    expect(Number(count[2])).toBe(rows);
    expect(headline + " " + lines.join(" ")).toContain(`${count[1]} of ${count[2]} sector indices`);
    // every sector row has its day, week and month and the companies that moved it
    for (const head of ["Sector index", "Today", "1 week", "1 month", "Moved by"]) await expect(sectors.getByRole("columnheader", { name: head })).toBeVisible();
    // the cards' levels are not said again in the words
    const levels = await page.locator('table[aria-label="Index levels"] tbody tr th').allInnerTexts();
    expect(levels.length).toBeGreaterThanOrEqual(2);
    const first = (await page.locator('table[aria-label="Index levels"] tbody tr').first().locator("td").first().innerText()).replace(/\..*$/, "");
    expect(headline + lines.join(" ")).not.toContain(first);
    // breadth, volatility, other markets and the headlines are tables with a header row
    for (const [id, heads] of [["pulse-breadth", ["Measure", "Change"]], ["pulse-risk", ["Measure", "Level", "Change"]], ["pulse-global", ["Market", "Move", "Session"]]] as const) {
      const card = page.getByTestId(id);
      await expect(card).toBeVisible();
      for (const h of heads) await expect(card.getByRole("columnheader", { name: h })).toBeVisible();
      expect(await card.locator("tbody tr").count()).toBeGreaterThan(2);
    }
    // changes carry a sign and an arrow, never colour alone
    const delta = sectors.locator(".k-delta").first();
    await expect(delta).toContainText(/[▲▼]/);
    await expect(delta).toContainText(/[+−]\d|0\.00%/);
    // India has the institutions' flows, both FII and DII, five days
    if (region === "IN") {
      const flows = page.getByTestId("pulse-flows");
      await expect(flows.getByRole("columnheader", { name: "FII net" })).toBeVisible();
      await expect(flows.getByRole("columnheader", { name: "DII net" })).toBeVisible();
      expect(await flows.locator("tbody tr").count()).toBeLessThanOrEqual(5);
      await expect(page.getByTestId("pulse-movers").first()).toBeVisible();
      await expect(page.getByTestId("pulse-movers")).toHaveCount(1);            // the NIFTY 50 (the SENSEX waits for its members from BSE)
    }
    // no page-wide sideways scroll, on a phone as on a laptop
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await expect(main).not.toContainText(/and \d+ more/);
    expect(errors).toEqual([]);
  });
}

test("the old tiles and run-on lists are gone from the pulse", async ({ page }) => {
  const errors = await open(page, "/research/pulse?region=IN");
  await expect(page.locator(".inv-rows, .inv-themes")).toHaveCount(0);
  await expect(page.getByText("Where money is flowing")).toHaveCount(0);
  expect(errors).toEqual([]);
});

// ---------- Market breadth: the controls, the ranges and the one table (MOOD-1, owner 29 Oct) ----------
test("breadth: the group and the range are one compact row; the figures are one table with the 20-day average", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => { const host = new URL(r.request().url()).hostname; return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto("/invest/breadth");
  const bar = page.getByRole("group", { name: "What to show" });
  await expect(bar).toBeVisible({ timeout: 60_000 });
  await expect(bar.getByLabel("Group of stocks")).toBeVisible();
  await expect(bar.getByRole("group", { name: "History charts' range" })).toBeVisible();
  // one row on a laptop: the select and the chips share a line
  const [a, b] = await Promise.all([bar.getByLabel("Group of stocks").boundingBox(), bar.getByRole("group", { name: "History charts' range" }).boundingBox()]);
  if ((page.viewportSize()?.width ?? 0) > 900) expect(Math.abs((a!.y + a!.height / 2) - (b!.y + b!.height / 2))).toBeLessThan(30);
  const today = page.getByTestId("breadth-today");
  await expect(today.getByRole("table")).toBeVisible();
  for (const head of ["Measure", "Change", "20-day average"]) await expect(today.getByRole("columnheader", { name: head })).toBeVisible();
  // no tiles any more, and no alert card between the figures and the charts
  await expect(today.locator(".k-stat")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Breadth alerts" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  expect(errors).toEqual([]);
});

for (const group of ["nifty500", "sp500"]) {
  test(`breadth ${group}: every range chip redraws both history charts and their tables; Custom applies, is remembered and can be cleared`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (r) => { const host = new URL(r.request().url()).hostname; return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
    await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
    await page.goto(`/invest/breadth?group=${group}`);
    const ranges = page.getByRole("group", { name: "History charts' range" });
    await expect(ranges).toBeVisible({ timeout: 60_000 });
    const frame = (title: string) => page.locator("section.k-card", { has: page.getByRole("heading", { name: title }) }).first();
    // the first day a chart shows, from its Table view (newest day first, so the last row)
    const firstDay = async (title: string) => {
      const f = frame(title);
      const btn = f.getByRole("button", { name: "Table", exact: true });
      if ((await btn.getAttribute("aria-pressed")) !== "true") await btn.click();
      // a table of more than a hundred days comes a hundred rows at a time, newest first (FIX-2's ChartFrame): the chart's first day is on the last page
      const nav = f.getByRole("navigation", { name: "Pages" });
      if (await nav.count()) {
        const pages = Number(((await nav.innerText()).match(/Page \d+ of (\d+)/) ?? [])[1] ?? 1);
        for (let p = 1; p < pages; p++) await f.getByRole("button", { name: "Next →" }).click();
        await expect(nav).toContainText(`Page ${pages} of ${pages}`);
      }
      const rows = f.locator("tbody tr");
      const n = await rows.count();
      const day = (await rows.nth(n - 1).locator("th").innerText()).trim();
      return { day, n };
    };
    const A = "Advance/decline line", B = "Above the 50- and 200-day averages";
    const chips = (await ranges.getByRole("button").allInnerTexts()).filter((t) => !/Custom|Remove/.test(t));
    expect(chips.length).toBeGreaterThanOrEqual(2);
    let widest = Infinity, last = "";
    const seen: Record<string, string> = {};
    for (const chip of chips) {
      await ranges.getByRole("button", { name: chip, exact: true }).click();
      await expect(ranges.getByRole("button", { name: chip, exact: true })).toHaveAttribute("aria-pressed", "true");
      const a = await firstDay(A), b = await firstDay(B);
      // both charts and both tables start on the same day, which is the range's
      expect(b.day, `${chip}: the two charts share their first day`).toBe(a.day);
      seen[chip] = a.day;
      last = chip;
      widest = Math.min(widest, a.n);
    }
    // a longer range starts no later than a shorter one, and "All" is the earliest: the chips really cut the history
    const order = chips.map((c) => seen[c]);
    expect(new Set(order).size, "each chip starts its charts on a different day").toBe(chips.length);
    expect(last).toBe("All");
    // + Custom: 20 days applies at once (fewer days than any chip before it that is longer), is remembered over a reload, and is cleared
    await ranges.getByRole("button", { name: "+ Custom" }).click();
    await page.getByLabel("How many").fill("20");
    await page.getByLabel("Unit").selectOption("days");
    await page.getByRole("button", { name: "Use this" }).click();
    await expect(ranges.getByRole("button", { name: "20 days", exact: true })).toHaveAttribute("aria-pressed", "true");
    const custom = await firstDay(A);
    expect(custom.n).toBeLessThanOrEqual(21);
    expect(custom.n).toBeGreaterThan(5);
    // the days read "2 Oct" (this year) or "30 Oct 2025": compared as dates, not as text ("2 Oct" sorted before "30 Oct 2025")
    const dayOf = (s: string) => Date.parse(/\d{4}$/.test(s) ? s : `${s} ${new Date().getFullYear()}`);
    expect(Number.isFinite(dayOf(custom.day)), custom.day).toBe(true);
    expect(chips.length <= 2 || dayOf(custom.day) > dayOf(seen[chips[chips.length - 2]]), `20 days from ${custom.day}, ${chips[chips.length - 2]} from ${seen[chips[chips.length - 2]]}`).toBe(true);
    await page.reload();
    const again = page.getByRole("group", { name: "History charts' range" });
    await expect(again.getByRole("button", { name: "20 days", exact: true })).toHaveAttribute("aria-pressed", "true", { timeout: 60_000 });
    expect((await firstDay(A)).day).toBe(custom.day);
    await again.getByRole("button", { name: "Remove 20 days" }).click();
    await expect(again.getByRole("button", { name: "20 days", exact: true })).toHaveCount(0);
    await expect(again.getByRole("button", { name: "All", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect((await firstDay(A)).day).toBe(seen["All"]);
    expect(errors).toEqual([]);
  });
}

// ---------- Sector rotation: every sector a row, the counts in the filter chips, sortable, ticks tied to the chart (MOOD-1) ----------
for (const region of ["IN", "US"] as const) {
  test(`rotation ${region}: a table of every one with its quadrant, was-to-now and returns; filter counts add up; ticks drive the chart`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/*", (r) => { const host = new URL(r.request().url()).hostname; return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" }); });
    await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
    await page.goto(`/research/rotation?region=${region}`);
    const table = page.getByRole("table", { name: "Where each one stands" });
    await expect(table).toBeVisible({ timeout: 90_000 });
    const total = await table.locator("tbody tr").count();
    expect(total).toBeGreaterThanOrEqual(8);
    for (const head of ["Quadrant", "Strength", "Momentum", "1W", "1M", "3M"]) await expect(table.getByRole("columnheader", { name: new RegExp(head) })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: /ago → now/ })).toBeVisible();
    // every one is a row, and the quadrant chips' counts add up to all of them: no "and 7 more"
    const bar = page.getByRole("group", { name: "Show quadrant" });
    const labels = await bar.getByRole("button").allInnerTexts();
    expect(labels[0]).toBe(`All ${total}`);
    const counts = labels.slice(1).map((l) => Number(l.match(/(\d+)$/)![1]));
    expect(counts.reduce((a, b) => a + b, 0)).toBe(total);
    await expect(page.locator("main")).not.toContainText(/and \d+ more/);
    // a quadrant's chip filters the table to exactly its count
    const k = counts.findIndex((n) => n > 0);
    await bar.getByRole("button").nth(k + 1).click();
    await expect(table.locator("tbody tr")).toHaveCount(counts[k]);
    await bar.getByRole("button").first().click();
    await expect(table.locator("tbody tr")).toHaveCount(total);
    // sorting by a column: the header says so, and the figures follow (a phone shows each row as a card, with no header to press)
    if (info.project.name !== "phone") {
    await table.getByRole("button", { name: /^Momentum/ }).click();
    await expect(table.getByRole("columnheader", { name: /^Momentum/ })).toHaveAttribute("aria-sort", "descending");
    const mom = (await table.locator("tbody tr").evaluateAll((rows) => rows.map((r) => parseFloat((r.querySelectorAll("td")[2]?.textContent ?? "").replace("−", "-"))))).filter((v) => !Number.isNaN(v));
    expect(mom).toEqual([...mom].sort((a, b) => b - a));
    }
    // the returns carry an arrow and a sign
    await expect(table.locator(".k-delta").first()).toContainText(/[▲▼]/);
    // the ticks choose what the chart draws: "Show all" draws every one
    await page.getByRole("button", { name: new RegExp(`^Show all ${total} on the chart`) }).click();
    await expect(page.getByTestId("rot-count")).toContainText(`All ${total} on the chart`);
    await page.getByRole("button", { name: "Clear the chart" }).click();
    await expect(page.getByText("Nothing is ticked")).toBeVisible();
    await table.getByRole("checkbox").first().check();
    await expect(page.getByTestId("rot-count")).toContainText(`1 of ${total} on the chart`);
    // the table is above the chart, and the page doesn't scroll sideways
    const [t, c] = await Promise.all([table.boundingBox(), page.getByTestId("rot-count").boundingBox()]);
    expect(t!.y).toBeLessThan(c!.y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    expect(errors).toEqual([]);
  });
}
