import { expect, test } from "@playwright/test";
import { HOLDINGS_FILES, MF, open, sane } from "./pages-kit";

const API = process.env.E2E_API ?? "http://127.0.0.1:8765";

// R15 (owner's screenshots of 7 Nov): page fixes. Each test names its item.

test("R15 #1: More in Money starts open, and still folds", async ({ page }) => {
  const errors = await open(page, "/money", "More in Money");
  const more = page.getByTestId("more-tools");
  const btn = more.getByRole("button", { name: /^More in Money/ });
  await expect(btn).toHaveAttribute("aria-expanded", "true");
  await expect(more.getByRole("table").first()).toBeVisible();
  await btn.click();
  await expect(btn).toHaveAttribute("aria-expanded", "false");
  await expect(more.getByRole("table").first()).toBeHidden();
  await sane(page, errors);
});

test("R15 #7: US stocks tax's Each sale in rupees shows the first 10 sales, then Show more", async ({ page }) => {
  // 13 sales in the year (the fake world has none): the page's own reply with rows put in
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/money/us-tax", async (r) => {
    const res = await r.fetch();
    const d = await res.json();
    const rate = { rate: 88.35, on: "2025-09-30", fallback: false };
    d.trades = [{ id: "t1", d: "2025-09-10", side: "B", sym: "SYM1", qty: 2, price: 500 }];
    if (Array.isArray(d.years) && d.years[0]) {
      d.fy = d.years[0].fy;
      d.years[0].rows = Array.from({ length: 13 }, (_, i) => ({ symbol: `SYM${i + 1}`, bought: "2025-09-10", sold: "2025-10-13", qty: 2, cost_usd: 1000, sale_usd: 1010,
        rate_buy: rate, rate_sell: rate, cost: 88350, indexed_cost: null, sale: 89234, gain: 884, term: "ST", rate: null, bucket: "slab" }));
      d.years[0].count = 13;
    }
    d.locked = false;
    await r.fulfill({ response: res, json: d });
  });
  const errors = await open(page, "/money/us-tax", "Each sale in rupees");
  const sales = page.getByRole("table", { name: "US sales in rupees" });
  await expect(sales.getByRole("row").filter({ hasText: /SYM\d+/ })).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 13.")).toBeVisible();
  await page.getByRole("button", { name: "Show 3 more" }).click();
  await expect(sales.getByRole("row").filter({ hasText: /SYM\d+/ })).toHaveCount(13);
  await sane(page, errors);
});

test("R15 #3: Where you stand is the headline figure beside a small own / owe / net worth table; History opens the snapshots", async ({ page }, info) => {
  const errors = await open(page, "/money/net-worth", "Where you stand");
  const card = page.getByRole("region", { name: "Totals" });
  const head = card.getByTestId("nw-headline");
  await expect(head.getByTestId("nw-figure")).toHaveText(/^₹[\d,]+$/);
  const table = card.getByRole("table", { name: "Where you stand" });
  for (const r of ["What you own", "What you owe", "Net worth"]) await expect(table.getByRole("row").filter({ hasText: r })).toHaveCount(1);
  if (info.project.name === "desktop") {
    // balanced edge to edge: the figure on the left half, the table on the right
    const [c, f, t] = [await card.boundingBox(), await head.getByTestId("nw-figure").boundingBox(), await table.boundingBox()];
    expect(f!.x).toBeLessThan(c!.x + c!.width / 2);
    expect(t!.x).toBeGreaterThan(c!.x + c!.width / 2 - 40);
    expect(t!.x + t!.width).toBeGreaterThan(c!.x + c!.width - 60);
  }
  // no "History: N snapshots" line at the card's foot: the header's History button opens them
  await expect(card.locator("summary", { hasText: /^History:/ })).toHaveCount(0);
  const btn = card.getByRole("button", { name: /^History · \d+ snapshots?$/ });
  await expect(card.getByTestId("nw-snapshots")).toHaveCount(0);
  await btn.click();
  await expect(card.getByTestId("nw-snapshots").getByRole("table", { name: "The history's snapshots" })).toBeVisible();
  await btn.click();
  await expect(card.getByTestId("nw-snapshots")).toHaveCount(0);
  await sane(page, errors);
});

test("R15 #12: the breadth table is in the kit's colours on the Invest home and the Breadth page", async ({ page }) => {
  let errors = await open(page, "/invest", "Market breadth");
  const card = page.getByTestId("breadth-card");
  const rose = card.getByRole("row").filter({ hasText: "Rose / fell" }).first();
  await expect(rose.locator(".k-up").first()).toBeVisible({ timeout: 30_000 });
  await expect(rose.locator(".k-down").first()).toBeVisible();
  const hl = card.getByRole("row").filter({ hasText: "52-week highs / lows" }).first();
  await expect(hl.locator(".k-up, .k-down").first()).toBeVisible();
  const p50 = card.getByRole("row").filter({ hasText: "Above 50-day average" }).first();
  const share = p50.locator("td .k-up, td .k-down").first();
  await expect(share).toBeVisible();
  const v = parseFloat((await share.innerText()).replace(/[^\d.]/g, ""));
  await expect(share).toHaveClass(v > 50 ? /k-up/ : /k-down/);
  await sane(page, errors);
  errors = await open(page, "/invest/breadth", "Above 50-day average");
  const row = page.getByRole("row").filter({ hasText: "Above 50-day average" }).first();
  await expect(row.locator(".k-up, .k-down").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("row").filter({ hasText: "Rose / fell" }).first().locator(".k-up").first()).toBeVisible();
  await sane(page, errors);
});

test("R15 #15: the deep dive has no Holders and deals card", async ({ page }) => {
  const errors = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
  await expect(page.getByRole("heading", { name: "Growth and margins" }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Holders and deals" })).toHaveCount(0);
  await sane(page, errors);
});

test("R15 #16, #17: Market today's mood: the headlines read sits under the mood; FII/DII and Volatility are coloured text, one height", async ({ page }, info) => {
  // five days of flows (the fake world has one), so the two tables pair up side by side as on the live site
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/research/pulse/mood", async (r) => {
    const res = await r.fetch();
    const d = await res.json();
    if (d.flows?.rows?.length) {
      const one = d.flows.rows[0];
      d.flows.rows = ["2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27", one.day].map((day, i) => ({ ...one, day, fii: one.fii + i * 311, dii: one.dii - i * 207 }));
    }
    await r.fulfill({ response: res, json: d });
  });
  const errors = await open(page, "/research/pulse", "FII and DII, cash market");
  // #17: "What the headlines say" right after the mood card, before the tables
  const order = await page.locator("main h2").allInnerTexts();
  const said = order.findIndex((t) => t.startsWith("What the headlines say"));
  const flows = order.findIndex((t) => t.startsWith("FII and DII"));
  expect(said, order.join(" | ")).toBeGreaterThan(-1);
  expect(said).toBeLessThan(flows);
  expect(said).toBeLessThan(order.findIndex((t) => t.startsWith("Volatility")));
  // #16: no pills, coloured figures, a bold total, and the two cards one height side by side
  for (const id of ["pulse-flows", "pulse-risk"]) {
    await expect(page.getByTestId(id).locator(".k-delta")).toHaveCount(0);
    await expect(page.getByTestId(id).locator("td .k-up, td .k-down").first()).toBeVisible();
  }
  const total = page.getByTestId("pulse-flows").locator("tfoot td").first();
  expect(Number(await total.evaluate((el) => getComputedStyle(el).fontWeight))).toBeGreaterThanOrEqual(600);
  if (info.project.name === "desktop") {
    const [a, b] = [await page.getByTestId("pulse-flows").boundingBox(), await page.getByTestId("pulse-risk").boundingBox()];
    expect(Math.abs(a!.y - b!.y)).toBeLessThan(2);
    expect(Math.abs(a!.height - b!.height)).toBeLessThan(2);
  }
  await sane(page, errors);
});

test("R15 #11: Results' Implied column only on days with an F&O stock; a non-F&O row says Not F&O; F&O rows fill in", async ({ page }, info) => {
  const errors = await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called");
  await expect(page.getByTestId("results-count")).toHaveText("20 companies", { timeout: 30_000 });
  await expect(page.getByText("Reading the option prices")).toHaveCount(0, { timeout: 20_000 });
  const tables = page.getByRole("table", { name: /^Results on/ });
  const n = await tables.count();
  let withFo = 0, without = 0;
  for (let i = 0; i < n; i++) {
    const t = tables.nth(i);
    const fo = await t.getByText("F&O", { exact: true }).count();
    const implied = info.project.name === "desktop" ? t.getByRole("columnheader").filter({ hasText: "Implied" }) : t.getByText(/^(Implied|Not F&O)/);
    if (fo > 0) {
      withFo++;
      if (info.project.name === "desktop") await expect(implied).toHaveCount(1);
      await expect(t.getByText(/^±\d+\.\d%$/).first()).toBeVisible();
      const plain = await t.getByRole("row").count() - 1 - fo;
      if (plain > 0 && info.project.name === "desktop") await expect(t.getByText("Not F&O").first()).toBeVisible();
    } else {
      without++;
      await expect(implied, "no Implied column on a day with no F&O stock").toHaveCount(0);
    }
  }
  expect(withFo, "the world has a day with F&O stocks").toBeGreaterThan(0);
  expect(without, "...and a day without").toBeGreaterThan(0);
  await sane(page, errors);
});

test("R15 #13: Find a company's search spans its card, the chips under it", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a phone's box is the card's width anyway");
  const errors = await open(page, "/research", "Find a company");
  const card = page.locator("section.k-card").filter({ has: page.getByRole("heading", { name: "Find a company" }) });
  const [c, box] = [await card.boundingBox(), await card.getByRole("combobox").or(card.locator("input")).first().boundingBox()];
  expect(box!.width).toBeGreaterThan(c!.width * 0.85);
  await sane(page, errors);
});

test("R15 #4: Holdings' import is one row, the upload and a chip a connected broker; a chip reads it now with the loading bar; Add or Start again once a file is picked", async ({ page }, info) => {
  // two brokers connected (the fake world's owner has none): the page's own reply with them put in
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/holdings", async (r) => {
    if (r.request().method() !== "GET") return r.fallback();
    const res = await r.fetch();
    const d = await res.json();
    d.zerodha = { live: true, count: 13, read_at: "2026-10-27T22:00:00+05:30" };
    d.brokers = [{ key: "upstox", name: "Upstox", live: true, count: 3, read_at: "2026-10-28T10:55:00+05:30" }, { key: "dhan", name: "Dhan", live: false, count: 2, read_at: "2026-10-28T01:00:00+05:30" }];
    await r.fulfill({ response: res, json: d });
  });
  let release: () => void = () => undefined;
  const held = new Promise<void>((ok) => { release = ok; });
  await page.route((u) => u.href.startsWith(API) && u.pathname === "/connect/upstox/refresh", async (r) => { await held; await r.fulfill({ json: { count: 3 } }); });
  const errors = await open(page, "/holdings", "Import from your broker");
  const card = page.locator("section.k-card").filter({ has: page.getByRole("heading", { name: "Import from your broker" }) });
  const upload = card.locator("label.k-upload");
  const up = card.getByTestId("upstox-refresh");
  await expect(up).toContainText("Upstox");
  await expect(card.getByTestId("zerodha-refresh")).toContainText("Zerodha");
  await expect(card.getByTestId("dhan-refresh")).toContainText("Dhan");
  if (info.project.name === "desktop") {
    const [a, b] = [await upload.boundingBox(), await up.boundingBox()];
    expect(Math.abs((a!.y + a!.height / 2) - (b!.y + b!.height / 2)), "the chips sit on the upload button's row").toBeLessThan(6);
  }
  // no Add / Start again before a file is picked
  await expect(card.getByRole("radio", { name: "Add to my holdings" })).toHaveCount(0);
  // a tap on a chip reads that broker, its loading bar in the chip meanwhile
  await up.getByRole("button", { name: "Read from Upstox now" }).click();
  await expect(up.getByTestId("cell-working")).toBeVisible();
  release();
  await expect(page.getByText("Read 3 holdings from Upstox.")).toBeVisible({ timeout: 15_000 });
  await expect(up.getByTestId("cell-working")).toHaveCount(0);
  // a file picked: its name with Add (chosen) or Start again, Read and Cancel
  await card.getByLabel("Holdings file").setInputFiles(HOLDINGS_FILES + "upstox_holdings.csv");
  const pending = card.getByTestId("holdings-pending");
  await expect(pending).toContainText("upstox_holdings.csv");
  await expect(pending.getByRole("radio", { name: "Add to my holdings" })).toBeChecked();
  await pending.getByRole("button", { name: "Cancel" }).click();
  await expect(card.getByRole("radio", { name: "Add to my holdings" })).toHaveCount(0);
  await sane(page, errors);
});

test("R15 #6: Mutual funds' upload is one row (pick, read, the files so far); the file's choices come once it is picked", async ({ page }, info) => {
  const errors = await open(page, "/money/mutual-funds", "Upload your statement");
  const form = page.getByRole("form", { name: "Upload your statement" });
  const pick = form.locator("label.k-upload");
  const read = form.getByRole("button", { name: "Read my funds" });
  await expect(read).toBeDisabled();
  if (info.project.name === "desktop") {
    const [a, b] = [await pick.boundingBox(), await read.boundingBox()];
    expect(Math.abs(a!.y - b!.y), "pick and read on one row").toBeLessThan(6);
  }
  await expect(page.getByRole("radio", { name: "Add to my funds" })).toHaveCount(0);
  await expect(page.getByText("Pick your statement first.")).toHaveCount(0);       // the hint is the button's title now
  await form.getByLabel("CAS PDF or CSV file").setInputFiles(MF + "synthetic_cas.pdf");
  await expect(form.getByTestId("mf-picked")).toContainText("synthetic_cas.pdf");
  await expect(form.getByLabel("PDF password")).toBeVisible();
  await expect(read).toBeEnabled();
  await sane(page, errors);
});
