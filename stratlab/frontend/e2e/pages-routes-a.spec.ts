import { test } from "@playwright/test";
import { open, sane, touchable, PAGES } from "./pages-kit";

// Every main page, signed in as the owner, on desktop and phone (the first half of the list in pages-kit.ts): no crash,
// nothing wider than the screen, no broken numbers.

for (const [path, ready] of PAGES.slice(0, 20)) {
  test(`page ${path}`, async ({ page }, info) => {
    await sane(page, await open(page, path, ready));
    if (info.project.name === "phone") await touchable(page);
  });
}
