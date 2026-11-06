import { test } from "@playwright/test";
import { open, sessionAs } from "./pages-kit";
const pro = sessionAs("pro-token", "u-pro", "pro@example.com");
const admin = sessionAs("admin-token", "u-admin", "admin@example.com");
const OUT = "/tmp/claude-0/-home-user-stratlab/336f6e68-98b8-5cb9-ae6f-089a8eabd8fc/scratchpad/r14-shots";
const PAGES: [string, string, string, typeof pro | null][] = [
  ["results", "/research/results?region=IN&scope=all", "Board meetings companies have called", pro],
  ["pulse", "/research/pulse", "How the market", pro],
  ["rotation", "/research/rotation", "Sector rotation", pro],
  ["networth", "/money/net-worth", "Where you stand", admin],
  ["accounts", "/settings#accounts", "Brokers", pro],
  ["invest", "/invest", "Market breadth", pro],
];
for (const [w, scheme] of [[1440, "dark"], [1440, "light"], [390, "dark"], [390, "light"], [1280, "dark"]] as const) {
  test(`shots ${w} ${scheme}`, async ({ page }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width: w, height: w < 500 ? 844 : 900 });
    await page.emulateMedia({ colorScheme: scheme });
    for (const [name, path, ready, who] of PAGES) {
      if (w === 1280 && name !== "results") continue;
      await open(page, path, ready, who!);
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `${OUT}/${name}-${w}-${scheme}.png`, fullPage: true });
      await page.unrouteAll({ behavior: "ignoreErrors" });
    }
    if (w === 390) {
      const p = await page.context().newPage();
      await p.setViewportSize({ width: 390, height: 844 });
      await p.goto("/"); await p.waitForTimeout(3000);
      await p.screenshot({ path: `${OUT}/landing-390-${scheme}.png`, fullPage: true });
      await p.goto("/plans"); await p.waitForTimeout(3000);
      await p.screenshot({ path: `${OUT}/plans-390-${scheme}.png`, fullPage: false });
      await p.close();
    }
  });
}
