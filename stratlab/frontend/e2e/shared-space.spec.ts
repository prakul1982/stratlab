// A page in more than one space's menu opens inside the space it was opened from (owner, 4 Nov: "whenever we click on something in
// Calendar (Trade sidebar → All dates / Results / Corporate actions) it redirects to Invest — keep the main space there only").
// Every shared page (from the menu map), from every space that lists it, by the page's own tabs (the breadcrumb's menu on a
// phone): the space switcher, the breadcrumb and the address keep that space, through a reload and the back button.
import { expect, test, type Page } from "@playwright/test";
import { NAV } from "../src/lib/nav";
import { SPACE_IDS, spaceOf } from "../src/lib/spaces";

const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/me/prefs", (r) => (r.request().method() === "PUT" ? r.fulfill({ json: { prefs: {} } }) : r.fallback()));     // nobody's saved space changes
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

// (updated on purpose, NAV3, CX-1: "a 7-link Calendar group repeats in Trade, Invest and Money"; owner OK 16 Nov to merge menu entries):
// the Calendar is one entry of one menu. The owner's 4 Nov rule ("keep the main space there only") now holds by construction: a Calendar tab
// opens in one place, whichever page it was clicked from, and an old link carrying ?space= (bookmarks, emails) still opens its page.
const CALENDAR = NAV.invest.groups.find((g) => g.id === "calendar")!;

for (const space of SPACE_IDS) {
  test(`the Calendar clicked from a ${space} page is the one Calendar: its tabs keep their trail, through a reload, back and an old ?space= link`, async ({ page }, info) => {
    test.setTimeout(240_000);
    const phone = info.project.name === "phone";
    const errors = await open(page, NAV[space].home);
    const side = page.locator("aside.sidebar");
    const crumb = page.getByRole("navigation", { name: "Breadcrumb" });
    if (phone) await page.getByRole("button", { name: "Open menu" }).click();
    // one Calendar link in the whole menu, and no space switch
    await expect(side.getByRole("link", { name: "Calendar", exact: true })).toHaveCount(1);
    await expect(side.getByRole("group", { name: "Space" })).toHaveCount(0);
    // on a phone the one menu is longer than the drawer: the link is scrolled to first, and the menu's "More below" line can move it as the
    // scroll ends, so the tap is tried again until it lands
    const cal = side.getByRole("link", { name: "Calendar", exact: true });
    await expect(async () => {
      if (phone && !(await page.locator("aside.sidebar.open").count())) await page.getByRole("button", { name: "Open menu" }).click();
      await cal.scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      await cal.click({ timeout: 3000 });
      await expect(page).toHaveURL(/\/calendar$/, { timeout: 3000 });
    }).toPass({ timeout: 30_000 });
    for (const p of CALENDAR.pages) {
      if (phone) {
        await crumb.locator(".k-crumb-btn").click();
        await page.getByRole("menuitem", { name: p.label, exact: true }).click();
      } else await page.getByTestId("hub-tabs").getByRole("link", { name: p.tab ?? p.label, exact: true }).click();
      await expect(page, p.to).toHaveURL(new RegExp(`${p.to.replace(/[/]/g, "\\/")}$`), { timeout: 30_000 });
      const own = NAV[spaceOf(p.to) ?? "invest"].label;
      await expect(crumb, p.to).toHaveText(new RegExp(`^${own}\\s*›\\s*Calendar`), { timeout: 30_000 });
    }
    await page.reload();
    await expect(crumb).toHaveText(/Calendar/, { timeout: 30_000 });
    await page.goBack();
    await expect(crumb).toHaveText(/Calendar/, { timeout: 30_000 });
    // an old shared link with ?space= opens the page it names
    await page.goto(`/research/results?space=${space}`);
    await expect(crumb).toHaveText(/^Invest\s*›\s*Calendar/, { timeout: 30_000 });
    expect(errors).toEqual([]);
  });
}
