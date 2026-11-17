import { expect, test } from "@playwright/test";
import { open } from "./a11y-kit";

// LIVE10B (17 Nov 2026): the live end-to-end review of Release 60. What only a browser shows.

/** Every visible form control on the page with no accessible label: no <label> tied to it, no aria-label, no aria-labelledby. */
const unlabelled = (page: import("@playwright/test").Page) => page.evaluate(() => Array.from(document.querySelectorAll("main input:not([type=hidden]), main select, main textarea"))
  .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; })
  .filter((e) => !((e as HTMLInputElement).labels?.length || e.getAttribute("aria-label") || e.getAttribute("aria-labelledby")))
  .map((e) => `${e.tagName.toLowerCase()} ${(e as HTMLInputElement).type ?? ""} ${(e as HTMLInputElement).value ?? ""}`));

test("LIVE10B-018/022/038: the options builder's More settings, the scan view and the notification ticks are all labelled", async ({ page }) => {
  await open(page, "/options");
  await page.locator("summary", { hasText: "More settings" }).first().click();
  await expect(page.getByLabel("Entries a day")).toBeVisible({ timeout: 30_000 });
  expect(await unlabelled(page)).toEqual([]);
  await open(page, "/research/scan");
  await expect(page.getByLabel("Group to scan")).toBeVisible({ timeout: 30_000 });
  expect(await unlabelled(page)).toEqual([]);
  await open(page, "/settings#notifications");
  await expect(page.getByText("A short report after each market closes")).toBeVisible({ timeout: 30_000 });
  expect(await unlabelled(page)).toEqual([]);
});
