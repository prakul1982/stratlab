import { expect, test, type Page } from "@playwright/test";

// Lane c-f2: a company page's Peers, Financial statements and Shareholding history, on desktop and phone, for a Free, a Basic and a Pro
// account. The fake world (tests/visual_server.py company_tables_world) gives the Commodities companies six peers (the screens' index plus
// UltraTech, Ambuja and Orion Polymers), RELIANCE's fundamentals page its statements and five quarters of shareholding, and AAPL its SEC
// figures. Each test signs in as its own lane account (tests/fake_db.py cf2-N: 0-7 Free, 8-15 Basic, 16-23 Pro).
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|undervalued|overvalued|target price|rating)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|trendlyne|nseindia|tickertape/i;
const SHOTS = process.env.E2E_SHOTS;

function sessionFor(n: number) {
  return { access_token: `cf2-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-cf2-${n}`, aud: "authenticated", email: `cf2${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
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
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[], scope: string) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator(scope).innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

const who = (base: number, phone: boolean) => base + (phone ? 4 : 0);

test("Free: three peers and the company's own row, three years of profit and loss, the latest quarter, each lock naming Basic", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/IN/TATASTEEL", "Tata Steel", who(0, phone));
  const peers = page.locator("#co-peers");
  await peers.scrollIntoViewIfNeeded();
  const table = peers.getByRole("table", { name: "TATASTEEL and its peers" });
  await expect(table).toBeVisible({ timeout: 20_000 });
  await expect(table.locator("tbody tr")).toHaveCount(4);                       // its own row and three peers
  await expect(table.locator("tbody tr").first()).toHaveClass(/ct-own/);
  await expect(table.locator("tbody tr").first()).toContainText("Tata Steel");
  await expect(table.locator("tfoot")).toContainText("Median of 3 peers");
  await expect(peers.getByText(/The other 3 peers and sorting the table are on the Basic plan/)).toBeVisible();
  await expect(table.getByRole("button", { name: /P\/E/ })).toHaveCount(0);      // no sorting on Free
  await expect(peers.getByLabel("Sort by")).toHaveCount(0);
  await expect(peers.getByRole("button", { name: "Download CSV" })).toHaveCount(0);
  // a peer opens its own page
  await expect(table.locator("tbody tr").nth(1).getByRole("link")).toHaveAttribute("href", /^\/research\/IN\/[A-Z]+$/);
  await sane(page, errors, "#co-peers");

  const st = page.locator("#co-statements");
  await st.scrollIntoViewIfNeeded();
  const pl = st.getByRole("table", { name: /Profit and loss/ });
  await expect(pl).toBeVisible({ timeout: 20_000 });
  await expect(pl.locator("thead th")).toHaveCount(4);                           // the row names and three years
  await expect(st.getByRole("radio", { name: "Balance sheet" })).toHaveCount(0);
  await expect(st.getByText(/years of profit and loss, the balance sheet, cash flow, ratios and the last \d+ quarters/)).toBeVisible();
  await sane(page, errors, "#co-statements");

  const sh = page.locator("#co-holding-history");
  await sh.scrollIntoViewIfNeeded();
  const holding = sh.getByRole("table", { name: "TATASTEEL shareholding by quarter" });
  await expect(holding).toBeVisible({ timeout: 20_000 });
  await expect(holding.locator("tbody tr")).toHaveCount(1);
  await expect(sh.getByRole("img")).toHaveCount(0);
  await expect(sh.getByText(/quarters and the chart of who owns it are on the Basic plan/)).toBeVisible();
  await expect(sh.getByText(/pledged isn't in the stored filings/)).toBeVisible();
  await sane(page, errors, "#co-holding-history");
  if (SHOTS) await peers.screenshot({ path: `${SHOTS}/company-peers-free-${info.project.name}.png` });
});

test("Basic: every peer and sorting, every statement and the quarters, twelve quarters of shareholding with the chart", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/IN/TATASTEEL", "Tata Steel", who(8, phone));
  const peers = page.locator("#co-peers");
  await peers.scrollIntoViewIfNeeded();
  const table = peers.getByRole("table", { name: "TATASTEEL and its peers" });
  // (updated on purpose, LIVE8B-012: on a phone the company and its five nearest come first, then "Show more")
  if (phone) {
    await expect(table.locator("tbody tr")).toHaveCount(6, { timeout: 20_000 });
    await peers.getByRole("button", { name: "Show 1 more" }).click();
  }
  await expect(table.locator("tbody tr")).toHaveCount(7, { timeout: 20_000 });
  await expect(peers.getByText(/on the Basic plan/)).toHaveCount(0);
  await expect(peers.getByText("Downloading the peers as CSV is on the Pro plan.")).toBeVisible();
  // sort by P/E, highest first, then lowest (a header on a desktop, the card's "Sort by" on a phone): the company's own row stays on top
  const pe = async () => (await table.locator("tbody tr").locator("td").filter({ hasText: /×$/ }).allInnerTexts()).slice(1).map((t) => parseFloat(t.replace(/[^\d.]/g, "")));
  if (phone) {
    await peers.getByLabel("Sort by").selectOption("pe");
    let got = await pe();
    expect(got).toEqual([...got].sort((a, b) => b - a));
    await peers.getByRole("button", { name: "High to low" }).click();
    got = await pe();
    expect(got).toEqual([...got].sort((a, b) => a - b));
  } else {
    const sortPe = table.getByRole("button", { name: /^P\/E/ });
    await sortPe.click();
    await expect(table.locator("thead th").filter({ hasText: "P/E" })).toHaveAttribute("aria-sort", "descending");
    await sortPe.click();
    await expect(table.locator("thead th").filter({ hasText: "P/E" })).toHaveAttribute("aria-sort", "ascending");
    const got = await pe();
    expect(got).toEqual([...got].sort((a, b) => a - b));
  }
  await expect(table.locator("tbody tr").first()).toHaveClass(/ct-own/);
  await sane(page, errors, "#co-peers");

  const st = page.locator("#co-statements");
  await st.scrollIntoViewIfNeeded();
  await expect(st.getByRole("table", { name: /Profit and loss/ })).toBeVisible({ timeout: 20_000 });
  for (const name of ["Balance sheet", "Cash flow", "Ratios", "Quarters"]) {
    await st.getByRole("button", { name, exact: true }).or(st.getByRole("radio", { name, exact: true })).first().click();
    await expect(st.getByRole("table", { name: new RegExp(name) })).toBeVisible();
    // the fundamentals page holds fewer years of cash flow than of profit and loss: "–" there, with its note
    if (name === "Cash flow") {
      await expect(st.getByRole("table", { name: /Cash flow/ })).toContainText("–");
      await expect(st.getByText(/the stored filings have no figure for that period/)).toBeVisible();
    }
  }
  await sane(page, errors, "#co-statements");

  const sh = page.locator("#co-holding-history");
  await sh.scrollIntoViewIfNeeded();
  await expect(sh.getByRole("img", { name: /Who owns it, quarter by quarter/ })).toBeVisible({ timeout: 20_000 });
  expect(await sh.getByRole("table", { name: "TATASTEEL shareholding by quarter" }).locator("tbody tr").count()).toBeGreaterThan(1);
  await expect(sh.getByText(/on the Basic plan/)).toHaveCount(0);
  await sane(page, errors, "#co-holding-history");
  if (SHOTS) {
    await peers.screenshot({ path: `${SHOTS}/company-peers-basic-${info.project.name}.png` });
    await st.screenshot({ path: `${SHOTS}/company-statements-basic-${info.project.name}.png` });
    await sh.screenshot({ path: `${SHOTS}/company-holding-basic-${info.project.name}.png` });
  }
});

test("Pro: the peers download as CSV and the statements as Excel", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/IN/TATASTEEL", "Tata Steel", who(16, phone));
  const peers = page.locator("#co-peers");
  await peers.scrollIntoViewIfNeeded();
  // (updated on purpose, LIVE8B-012: a phone shows the company and its five nearest first)
  await expect(peers.getByRole("table", { name: "TATASTEEL and its peers" }).locator("tbody tr")).toHaveCount(phone ? 6 : 7, { timeout: 20_000 });
  const csv = page.waitForEvent("download");
  await peers.getByRole("button", { name: "Download CSV" }).click();
  expect((await csv).suggestedFilename()).toBe("stratlab-TATASTEEL-peers.csv");
  const st = page.locator("#co-statements");
  await st.scrollIntoViewIfNeeded();
  await expect(st.getByRole("table", { name: /Profit and loss/ })).toBeVisible({ timeout: 20_000 });
  const xlsx = page.waitForEvent("download");
  await st.getByRole("button", { name: "Excel" }).click();
  expect((await xlsx).suggestedFilename()).toMatch(/^stratlab-TATASTEEL-statements-(consolidated|standalone)\.xlsx$/);
  await sane(page, errors, "#co-statements");
});

test("a US company: its SEC statements, and a note in place of a shareholding pattern", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/US/AAPL", "Apple", who(9, phone));
  const st = page.locator("#co-statements");
  await st.scrollIntoViewIfNeeded();
  await expect(st.getByRole("table", { name: /Profit and loss/ })).toBeVisible({ timeout: 30_000 });
  await expect(st.getByText(/figures in \$ million/)).toBeVisible();
  const sh = page.locator("#co-holding-history");
  await sh.scrollIntoViewIfNeeded();
  await expect(sh.getByTestId("holding-note")).toContainText("don't file a quarterly shareholding pattern");
  await sane(page, errors, "#co-holding-history");
});

test("the deep dive has the same three cards", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/IN/RELIANCE/deep", "business, capex and growth", who(10, phone));
  for (const id of ["#dd-peers", "#dd-statements", "#dd-holding-history"]) {
    const card = page.locator(id);
    await card.scrollIntoViewIfNeeded();
    await expect(card.getByRole("table").first()).toBeVisible({ timeout: 30_000 });
  }
  await sane(page, errors, "#dd-statements");
});

test("LIVE8B-003: a statements table wider than its card opens on the latest years with the row names in view", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/IN/TATASTEEL", "Tata Steel", who(11, phone));
  const st = page.locator("#co-statements");
  await st.scrollIntoViewIfNeeded();
  const pl = st.getByRole("table", { name: /Profit and loss/ });
  await expect(pl).toBeVisible({ timeout: 20_000 });
  const wrap = st.locator(".k-tbl-wrap").first();
  // the card narrower than the years (a 12-year table in a 1,004 px card at 1440): squeeze the box, then scroll it to the latest year
  await wrap.evaluate((b) => { (b as HTMLElement).style.maxWidth = "360px"; b.scrollLeft = b.scrollWidth; });
  expect(await wrap.evaluate((b) => b.scrollLeft)).toBeGreaterThan(0);
  const box = await wrap.boundingBox();
  for (const cell of [pl.locator("tbody th[scope=row]").first(), pl.locator("thead th").first()]) {
    const r = await cell.boundingBox();
    expect(r && box && r.x >= box.x - 1, "the row names stay in view while the years scroll").toBeTruthy();
  }
  await expect(pl.locator("tbody th[scope=row]").first()).toHaveCSS("position", "sticky");
  await sane(page, errors, "#co-statements");
});
