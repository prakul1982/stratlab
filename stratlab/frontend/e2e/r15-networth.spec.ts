import { expect, test } from "@playwright/test";
import { open, sane } from "./pages-kit";

// R15 #3 (owner, 7 Nov: "it was fine before"): "Where you stand" is a full-width table in its card again, not a half-width block.
test("Net worth: the Where you stand totals span the card", async ({ page }, info) => {
  const errors = await open(page, "/money/net-worth", "Where you stand");
  const card = page.getByRole("region", { name: "Totals" });
  const table = card.getByRole("table", { name: "Where you stand" });
  await expect(table).toBeVisible();
  const [c, t] = [await card.boundingBox(), await table.boundingBox()];
  expect(t!.width, "the totals table fills its card").toBeGreaterThan(c!.width * 0.85);
  if (info.project.name === "desktop") {
    const align = await table.locator("td").first().evaluate((el) => getComputedStyle(el).textAlign);
    expect(align).toMatch(/right|end/);
  }
  await sane(page, errors);
});
