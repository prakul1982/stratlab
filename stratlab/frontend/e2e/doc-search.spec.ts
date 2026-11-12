import { expect, test, type Page } from "@playwright/test";
import { open, sessionAs } from "./pages-kit";

// Search inside filings and call transcripts (lane b1), on desktop and phone, dark and light, against the fake world's made-up documents
// (tests/visual_server.py doc_search_world): the extracts with the match marked and a link to the filed copy at its page, the plan's
// limits (Free: the first 3 results, by company only; Basic: every result and filter; Pro: every year and the CSV), the empty and
// no-results states, and the ways in: the palette's "Search filings for …" and a company page's "Search its documents".
// Each test signs in as its own account (tests/fake_db.py b1-N: Free, Basic and Pro in turn).
const ADVICE = /\b(buy|sell|accumulate|avoid|cheap|expensive|undervalued|overvalued|recommend)\b/i;
const SHOTS = process.env.E2E_SHOTS;

function who(info: { project: { name: string } }, n: number) {
  const i = n + (info.project.name === "phone" ? 9 : 0);
  return sessionAs(`b1-${i}`, `u-b1-${i}`, `b1${i}@example.com`);
}

async function checks(page: Page, errors: string[]) {
  expect(errors).toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(await page.locator("main").first().innerText()).not.toMatch(ADVICE);
}

async function shots(page: Page, name: string, project: string) {
  if (!SHOTS) return;
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${SHOTS}/${name}-${project}-${scheme}.png`, fullPage: true });
  }
  await page.emulateMedia({ colorScheme: "light" });
}

test("Pro: a search shows extracts with the match marked, linked to the filed copy, and downloads the CSV", async ({ page }, info) => {
  const errors = await open(page, "/research/search?q=order%20book", "mention “order book”", who(info, 2));
  const hits = page.getByRole("list", { name: "Results for order book" }).getByRole("listitem");
  await expect(hits.first()).toBeVisible();
  expect(await hits.count()).toBeGreaterThanOrEqual(4);                         // every year: last year's RELIANCE transcript too
  await expect(page.getByText("Filed since")).toHaveCount(0);
  const rel = hits.filter({ hasText: "Transcript of the earnings call for Q2 FY27" }).filter({ hasText: "Reliance Industries Ltd" });
  await expect(rel.locator("mark").first()).toHaveText(/order/i);
  const link = rel.getByRole("link", { name: /Open at page 3/ });
  await expect(link).toHaveAttribute("href", /^https:\/\/nsearchives\.nseindia\.com\/.+\.pdf#page=3$/);
  await expect(link).toHaveAttribute("target", "_blank");
  // a document's markup is drawn as text
  const infy = hits.filter({ hasText: "Infosys Ltd" });
  await expect(infy.getByText("<script>alert('x')</script>", { exact: false })).toBeVisible();
  expect(await page.locator(".ds-extract script").count()).toBe(0);
  await expect(hits.filter({ hasText: "HDFC Bank Ltd" }).getByText("Read from a scan", { exact: true })).toBeVisible();
  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await csv).suggestedFilename()).toMatch(/^stratlab-filings-order-book\.csv$/);
  await checks(page, errors);
  await shots(page, "doc-search-pro", info.project.name);
});

test("Free: the first 3 results of the last year, by company only, with the lock saying Basic", async ({ page }, info) => {
  const errors = await open(page, "/research/search?q=order%20book&sector=Energy", "mention “order book”", who(info, 0));
  const hits = page.getByRole("list", { name: "Results for order book" }).getByRole("listitem");
  await expect(hits).toHaveCount(3);
  await expect(page.getByText(/Free shows the first 3 of the \d+ documents found/)).toBeVisible();
  await expect(page.getByText("Searched without the sector filter", { exact: false })).toBeVisible();
  await expect(page.getByRole("group", { name: "Sector" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download CSV" })).toHaveCount(0);
  await expect(page.getByText(/Filed since/)).toBeVisible();
  await checks(page, errors);
  await shots(page, "doc-search-free", info.project.name);
});

test("Basic: every filter, the empty start and a search with no results", async ({ page }, info) => {
  const errors = await open(page, "/research/search", "Search inside the filed documents", who(info, 1));
  await shots(page, "doc-search-empty", info.project.name);
  await page.getByRole("button", { name: "capacity utilisation" }).click();
  await expect(page.getByText(/mention “capacity utilisation”/)).toBeVisible();
  await expect(page.getByRole("group", { name: "Kind of document" })).toBeVisible();
  await page.getByRole("group", { name: "Kind of document" }).getByRole("button", { name: "Investor presentation" }).click();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/kind=presentation/);
  const hits = page.getByRole("list", { name: "Results for capacity utilisation" }).getByRole("listitem");
  await expect(hits).toHaveCount(1);
  await expect(hits.first()).toContainText("Investor presentation");
  await page.getByLabel("Words or a phrase").fill("zebra crossing permits");
  await page.getByLabel("Words or a phrase").press("Enter");
  await expect(page.getByText("No document mentions “zebra crossing permits”")).toBeVisible();
  await checks(page, errors);
  await shots(page, "doc-search-none", info.project.name);
});

test("the ways in: a company page's link and the palette's \"Search filings for …\"", async ({ page }, info) => {
  const errors = await open(page, "/research/IN/RELIANCE", "Reliance", who(info, 5));
  const link = page.locator("#filings").getByTestId("doc-search-link");
  await link.scrollIntoViewIfNeeded();
  await link.click();
  await expect(page).toHaveURL(/\/research\/search\?symbols=RELIANCE$/);
  await expect(page.getByRole("button", { name: "Remove RELIANCE" })).toBeVisible();
  await page.getByLabel("Words or a phrase").fill("capex");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const hits = page.getByRole("list", { name: "Results for capex" }).getByRole("listitem");
  await expect(hits.first()).toContainText("Reliance Industries Ltd");
  await page.keyboard.press("Control+k");
  const box = page.getByRole("textbox", { name: "Search or ask anything" });
  await box.fill("order book");
  await page.getByRole("option", { name: /Search filings for “order book”/ }).click();
  await expect(page).toHaveURL(/\/research\/search\?q=order(%20|\+)book$/);
  await expect(page.getByText("mention “order book”")).toBeVisible();
  await checks(page, errors);
});
