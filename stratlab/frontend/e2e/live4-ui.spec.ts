import { test, expect, type Page } from "@playwright/test";
import { open, sane, sessionAs } from "./pages-kit";

// LIVE4 (final live review, 6 Nov 2026): the presentation fixes, measured in the browser on desktop (1440) and phone (Pixel 7).
const pro = sessionAs("pro-token", "u-pro", "pro@example.com");

/** Whether two boxes overlap by more than a pixel each way. */
const overlaps = (a: { x: number; y: number; width: number; height: number }, b: typeof a) =>
  Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x) > 1 && Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y) > 1;

async function rowBoxes(page: Page) {
  return page.getByTestId("results-day").first().locator("tbody tr").evaluateAll((trs) => trs.map((tr) => {
    const b = tr.getBoundingClientRect();
    const link = tr.querySelector("th a")!.getBoundingClientRect(), tag = tr.querySelector("th .res-sym > .k-note:not(.res-name)")?.getBoundingClientRect();
    const cells = [...tr.querySelectorAll("td")].filter((td) => getComputedStyle(td).display !== "none").map((td) => td.getBoundingClientRect());
    return { h: b.height, right: b.right, link: { x: link.x, y: link.y, width: link.width, height: link.height, sw: (tr.querySelector("th a") as HTMLElement).scrollWidth },
      tag: tag ? { x: tag.x, y: tag.y, width: tag.width, height: tag.height } : null, cellRight: Math.max(0, ...cells.map((c) => c.right)) };
  }));
}

test("LIVE4-010: a results day is two short lines a company on a phone, one line of headers on a desktop, and no name runs under its tag", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called", pro);
  const day = page.getByTestId("results-day").first();
  await expect(day.locator("tbody tr").first()).toBeVisible({ timeout: 30_000 });
  await expect(day.getByText(/^±\d+\.\d%$/).first()).toBeVisible({ timeout: 30_000 });
  const rows = await rowBoxes(page);
  expect(rows.length).toBeGreaterThan(2);
  for (const r of rows) {
    // the symbol keeps its whole width and its F&O tag sits after it, never over it
    expect(r.link.sw, "the symbol fits its link").toBeLessThanOrEqual(Math.ceil(r.link.width) + 1);
    if (r.tag) expect(overlaps(r.link, r.tag), "the symbol and its tag overlap").toBe(false);
  }
  if (phone) {
    // two lines: the symbol with the price and the day's move, then the usual move (and what the options imply)
    for (const r of rows) {
      expect(r.h, "a company's row on a phone").toBeLessThan(r.tag ? 92 : 72);
      expect(r.cellRight, "a figure past the row's edge").toBeLessThanOrEqual(r.right + 1);
    }
    await expect(day.locator("tbody tr").first().locator("td.k-brief")).toHaveCount(2);
    // no row ends in a label over a dash
    const dashes = await day.locator("tbody td").evaluateAll((tds) => tds.filter((td) => getComputedStyle(td).display !== "none" && /^\s*[–-]\s*$/.test(td.textContent ?? "")).length);
    expect(dashes).toBe(0);
    // the day's CSV button is on the day's heading line
    const head = await day.locator(".k-eyebrow").boundingBox(), csv = await day.getByRole("button", { name: /Download CSV/ }).boundingBox();
    expect(Math.abs(head!.y + head!.height / 2 - (csv!.y + csv!.height / 2))).toBeLessThan(16);
  } else {
    // every header on one line: no header taller than the shortest by more than a few pixels
    const wrapped = await day.locator("thead th").evaluateAll((ths) => ths.filter((th) => {
      const walk = document.createTreeWalker(th, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        if (!n.textContent?.trim()) continue;
        const r = document.createRange(); r.selectNodeContents(n);
        if (new Set([...r.getClientRects()].filter((x) => x.width > 1).map((x) => Math.round(x.top))).size > 1) return true;
      }
      return false;
    }).map((th) => th.textContent));
    expect(wrapped, "headers that wrapped").toEqual([]);
  }
  await sane(page, errors);
});
