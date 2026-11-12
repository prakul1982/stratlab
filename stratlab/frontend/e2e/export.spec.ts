import { expect, test, type Download, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { open, sessionAs } from "./pages-kit";

// EXPORT (owner, 4 Nov: "you forgot to put an export PDF or slides option in themes; also check wherever we can give this option of
// exporting the data and provide it"). Every page whose main content is a table offers "Download CSV" (one button, lib/csv.ts, saved
// through lib/share.ts download()); the theme dive offers Slides (PDF), Slides (PowerPoint) and a CSV of every company. Each test signs in
// as its own fake account per project (export-N in tests/fake_db.py), desktop and phone.

const as = (n: number, phone: boolean) => { const i = n * 2 + (phone ? 1 : 0); return sessionAs(`export-${i}`, `u-export-${i}`, `export${i}@example.com`); };
const THEME = "/research/themes?region=IN&q=" + encodeURIComponent("India steel and mining");

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

/** A minimal CSV reader for the files the app writes (quoted cells, "" for a quote, CRLF lines). */
function parse(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; }
    else if (ch === '"') q = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\r") continue;
    else if (ch === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

/** The file a CSV button saved: named stratlab-…-<day>.csv, UTF-8 with a byte-order mark, a header and rows, no column left blank in every
 * row, numbers written plainly (never "1,234" inside a cell that is a number). */
async function checkCsv(file: Download, where: string) {
  expect(file.suggestedFilename(), where).toMatch(/^stratlab-[a-z0-9-]+-\d{4}-\d{2}-\d{2}\.csv$/);
  const raw = await readFile((await file.path())!, "utf8");
  expect(raw.charCodeAt(0), `${where}: byte-order mark`).toBe(0xfeff);
  const rows = parse(raw.slice(1));
  expect(rows.length, `${where}: a header and at least one row`).toBeGreaterThan(1);
  const [head, ...body] = rows;
  expect(head.every((h) => h.trim().length > 0), `${where}: every column named (${head.join(" | ")})`).toBe(true);
  for (const r of body) expect(r.length, `${where}: a row as wide as the header`).toBe(head.length);
  // every row named, and most columns filled (a figure the fake world doesn't hold, a capex line, can be blank throughout; a column the file
  // failed to read from the table would make many)
  for (const r of body) expect(r[0], `${where}: a row with no name`).not.toBe("");
  const blank = head.filter((_, c) => body.every((r) => r[c] === ""));
  expect(blank.length, `${where}: columns with nothing in any row: ${blank.join(", ")}`).toBeLessThanOrEqual(Math.floor(head.length / 2));
  for (const r of body) for (const c of r) expect(c, `${where}: undefined/NaN in the file`).not.toMatch(/^(undefined|NaN|null|\[object Object\])$/);
  return { head, body };
}

async function clickAll(page: Page, where: string) {
  const buttons = page.locator("main [data-csv]").filter({ visible: true });
  const n = await buttons.count();
  for (let i = 0; i < n; i++) {
    const b = buttons.nth(i);
    await b.scrollIntoViewIfNeeded();
    const [file] = await Promise.all([page.waitForEvent("download"), b.click()]);
    await checkCsv(file, `${where} #${i + 1} (${await b.getAttribute("data-csv")})`);
  }
  return n;
}

test("R21: a theme's first deck shows the loading bar while the AI map is written, then saves the file", async ({ page }, info) => {
  test.setTimeout(240_000);
  const phone = info.project.name === "phone";
  const errors = await open(page, THEME, "The whole chain in one table", as(0, phone));
  let asked = 0;
  await page.route("**/research/theme-dive/deck?**", async (route) => {
    asked += 1;
    if (asked === 1) {
      await route.fulfill({ status: 202, contentType: "application/json",
        body: JSON.stringify({ preparing: true, retry_after: 3, message: "Preparing the deck: the AI map is being written." }) });
    } else {
      await route.continue();
    }
  });
  const box = page.getByTestId("theme-downloads");
  const done = page.waitForEvent("download", { timeout: 60_000 });
  await box.getByRole("button", { name: "Slides (PDF)" }).click();
  await expect(box.getByRole("status").filter({ hasText: "Preparing the deck: the AI map is being written" }).first()).toBeAttached({ timeout: 5_000 });
  const pdf = await done;
  expect((await readFile((await pdf.path())!)).subarray(0, 5).toString()).toBe("%PDF-");
  expect(asked).toBe(2);
  await expect(box.getByRole("status")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("themes: Slides (PDF), Slides (PowerPoint) and the companies' CSV each save a file", async ({ page }, info) => {
  test.setTimeout(240_000);
  const phone = info.project.name === "phone";
  const errors = await open(page, THEME, "The whole chain in one table", as(0, phone));
  const box = page.getByTestId("theme-downloads");
  await expect(box).toBeVisible();
  const [pdf] = await Promise.all([page.waitForEvent("download"), box.getByRole("button", { name: "Slides (PDF)" }).click()]);
  // a name people can read in their Downloads (owner, 5 Nov): StratLab - <theme> theme (<market>) - <day>
  expect(pdf.suggestedFilename()).toMatch(/^StratLab - India steel and mining theme \(India\) - \d{1,2} [A-Z][a-z]{2} \d{4}\.pdf$/i);
  expect((await readFile((await pdf.path())!)).subarray(0, 5).toString()).toBe("%PDF-");
  const [deck] = await Promise.all([page.waitForEvent("download"), box.getByRole("button", { name: "Slides (PowerPoint)" }).click()]);
  expect(deck.suggestedFilename()).toMatch(/^StratLab - India steel and mining theme \(India\) - \d{1,2} [A-Z][a-z]{2} \d{4}\.pptx$/i);
  expect((await readFile((await deck.path())!)).subarray(0, 2).toString()).toBe("PK");
  const [csv] = await Promise.all([page.waitForEvent("download"), box.getByRole("button", { name: /^CSV/ }).click()]);
  const { head, body } = await checkCsv(csv, "theme companies");
  expect(head).toEqual(["Company", "Symbol", "Layer", "Industry", "Market value (₹ crore)", "Revenue (₹ crore)", "EBITDA margin (%)", "Net margin (%)", "ROCE (%)",
    "Year of the figures", "In the theme by", "What it does, in its own words"]);
  // a company per row, its market value a plain number
  const cap = head.indexOf("Market value (₹ crore)");
  expect(body.some((r) => /^\d+(\.\d+)?$/.test(r[cap]))).toBe(true);
  expect(new Set(body.map((r) => r[head.indexOf("In the theme by")]))).toContain("Official industry");
  // the layer tables' own CSVs are not repeated: one Download group for the theme
  expect(errors).toEqual([]);
});

// (updated on purpose, FREE-TIER: Free has no slide decks of its own now; a Free account's deck button is locked, says where decks are and
// sits beside the sample deck, instead of a first deck and a stopped second one)
test("a Free account's theme deck button is locked and says decks are on Basic", async ({ page }, info) => {
  test.setTimeout(180_000);
  const i = 20 + (info.project.name === "phone" ? 1 : 0);
  const who = sessionAs(`export-${i}`, `u-export-${i}`, `export${i}@example.com`);
  const errors = await open(page, THEME, "The whole chain in one table", who);
  const box = page.getByTestId("theme-downloads");
  const lock = box.getByTestId("deck-locked");
  await expect(lock).toHaveText("🔒 Slides: on Basic", { timeout: 30_000 });
  await expect(lock).toHaveAttribute("href", "/plans");
  await expect(lock).toHaveAttribute("title", "Slide decks are on Basic: 5 a month. The sample deck on the Plans page shows what one holds.");
  await expect(box.getByRole("button", { name: "Slides (PDF)" })).toHaveCount(0);
  await expect(box.getByRole("button", { name: /^CSV/ })).toBeVisible();          // the companies' CSV stays on every plan
  expect(errors).toEqual([]);
});

// Every page whose main content is a table, as the fake world fills it: each has at least one "Download CSV", and every one saves a good file.
// (The results calendar and the trend scans are left to unit/export.test.mjs's sweep: the fake world has no results this week by the real
// clock, and a scan runs only when asked.)
const PAGES: [string, string][] = [
  ["/research/screens", "companies match"], ["/invest/breadth", "Breadth"], ["/invest/ipos", "IPO"], ["/invest/ipos/in-bonfig", "Bonfig"],
  ["/trade/positioning", "Positioning"], ["/trade/positioning/stocks", "Stock futures"], ["/research/corporate-actions?scope=all", "Corporate actions"],
["/trade/events", "Index changes"], ["/invest/etf-gaps", "ETF"], ["/invest/flows", "FII"],
  ["/invest/stock-lending", "Lending"], ["/trade/closing-auction", "auction"], ["/research/rotation", "rotation"],
  ["/research/pulse", "Sector"], ["/research/IN/RELIANCE/deep", "business, capex and growth"], ["/research/compare?region=IN&a=TCS&b=INFY", "side by side"],
  ["/research/filings?view=all", "Red flags across companies"],
];

for (const [path, ready] of PAGES) {
  test(`CSV on ${path}`, async ({ page }, info) => {
    test.setTimeout(120_000);
    const phone = info.project.name === "phone";
    const errors = await open(page, path, ready, as(1, phone));
    await page.waitForTimeout(1500);                       // the later cards (their tables) load after the first screen
    const n = await clickAll(page, path);
    expect(n, `${path}: a Download CSV button`).toBeGreaterThan(0);
    expect(errors).toEqual([]);
  });
}
