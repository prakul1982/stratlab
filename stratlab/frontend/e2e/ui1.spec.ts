import { expect, test } from "@playwright/test";
import { open, sane } from "./pages-kit";

// Lane ui1, the owner's UI sweep (18 Nov). Item 6 ("fix ui dude", the Themes page): one line under the title; the market switch, the box
// and "Map it" on one row (the switch above them on a phone); the shared library as equal chips with short names, at most two rows, then
// "All N themes"; the ideas folded under "More ideas".
const LONG = ["Utilities (Indian power, gas and water-linked infrastructure)", "Automotive", "Banking and lenders", "Cement", "Defence and aerospace manufacturing",
  "Railways capex", "Renewables and solar", "EV and battery supply chain", "Digital payments", "Specialty chemicals", "Pharmaceuticals (generic drug makers and APIs)",
  "Steel and mining", "Telecom", "Consumer staples", "Hospitals", "Real estate", "Capital goods", "Shipbuilding", "Data centres", "Insurance", "Brokers", "Textiles",
  "Hotels", "Ports", "Agrochemicals", "Paints", "Electronics manufacturing (EMS and components)", "Water", "Sugar and ethanol", "FMCG"];

test("item 6: the Themes box is one row, the library two rows of equal short chips, the ideas folded (owner, 18 Nov)", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await page.route("**/research/theme-library/suggest**", (r) => r.fulfill({ json: { items: LONG.map((name) => ({ name, q: name.toLowerCase(), region: "IN", at: "2026-11-10T09:00:00Z", day: "2026-11-10", members: 40, searched: 3 })) } }));
  const errors = await open(page, "/research/themes?region=IN", "Map it");
  // one line under the title on a laptop (two at most on a phone)
  const lede = page.locator(".k-page-head .k-lede");
  const lines = await lede.evaluate((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)));
  expect(lines).toBeLessThanOrEqual(phone ? 2 : 1);
  // the box and Map it share a row, centred on each other; on a laptop the market switch is on that row too
  const box = await page.getByRole("textbox", { name: "Theme" }).boundingBox();
  const btn = await page.getByRole("button", { name: "Map it" }).boundingBox();
  const seg = await page.locator(".theme-map .k-seg").boundingBox();
  expect(Math.abs((box!.y + box!.height / 2) - (btn!.y + btn!.height / 2))).toBeLessThanOrEqual(1);
  expect(btn!.x).toBeGreaterThan(box!.x + box!.width - 1);
  if (!phone) expect(Math.abs((seg!.y + seg!.height / 2) - (box!.y + box!.height / 2))).toBeLessThanOrEqual(1);
  // Ready to open: equal chips with short names, two rows, the last cell "All 30 themes"
  const grid = page.getByTestId("theme-already");
  await expect(grid).toContainText("Ready to open:");
  const chips = grid.locator(".theme-ready > button");
  await expect(chips.first()).toHaveText("Utilities");
  await expect(chips.first()).toHaveAttribute("title", /^Utilities \(Indian power, gas and water-linked infrastructure\) · updated 10 Nov$/);
  await expect(chips.last()).toHaveText("All 30 themes");
  const boxes = await chips.evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return { y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height) }; }));
  expect(new Set(boxes.map((b) => b.y)).size, "two rows").toBe(2);
  expect(new Set(boxes.map((b) => b.w)).size, "equal widths").toBe(1);
  expect(new Set(boxes.map((b) => b.h)).size, "equal heights").toBe(1);
  // the ideas are folded under the library
  const ideas = page.getByTestId("theme-ideas");
  await expect(ideas.locator("summary")).toHaveText("More ideas");
  await expect(ideas.getByRole("button", { name: "India defence" })).toBeHidden();
  await chips.last().click();
  await expect(grid.locator(".theme-ready > button")).toHaveCount(30);
  await grid.getByRole("button", { name: "Fewer themes" }).click();
  await expect(grid.locator(".theme-ready > button").last()).toHaveText("All 30 themes");
  await sane(page, errors);
});
