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

// the menu map's shared entries and their pages: today the Calendar, in every space
const SHARED = (() => {
  const seen = new Map<string, Set<string>>();
  for (const sp of SPACE_IDS) for (const g of NAV[sp].groups) for (const p of g.pages) seen.set(p.to, (seen.get(p.to) ?? new Set()).add(sp));
  return SPACE_IDS.map((sp) => ({ space: sp, groups: NAV[sp].groups.filter((g) => g.pages.some((p) => (seen.get(p.to)?.size ?? 0) > 1)) }));
})();

for (const { space, groups } of SHARED) {
  test(`a shared page clicked from ${space}'s menu stays in ${space}: switcher, breadcrumb, address, reload and back`, async ({ page }, info) => {
    test.setTimeout(240_000);
    const phone = info.project.name === "phone";
    const label = NAV[space].label;
    const errors = await open(page, NAV[space].home);
    const side = page.locator("aside.sidebar");
    const crumb = page.getByRole("navigation", { name: "Breadcrumb" });
    const inSpace = async (what: string) => {
      await expect(crumb, what).toHaveText(new RegExp(`^${label}\\s*›`), { timeout: 30_000 });
      if (phone) await page.getByRole("button", { name: "Open menu" }).click();
      await expect(side.getByRole("group", { name: "Space" }).getByRole("button", { name: label }), what).toHaveAttribute("aria-pressed", "true");
      if (phone) await page.keyboard.press("Escape");
    };
    for (const g of groups) {
      if (phone) await page.getByRole("button", { name: "Open menu" }).click();
      await side.getByRole("link", { name: g.label, exact: true }).click();
      await inSpace(`${g.label} from ${space}`);
      for (const p of g.pages) {
        if (phone) {
          await crumb.locator(".k-crumb-btn").click();
          await page.getByRole("menuitem", { name: p.label, exact: true }).click();
        // (updated on purpose, R43: a tab may show a shorter name, NavPage.tab, so the row of tabs stays on one line at 1280)
        } else await page.getByTestId("hub-tabs").getByRole("link", { name: p.tab ?? p.label, exact: true }).click();
        const own = spaceOf(p.to);
        // the address names the space when it isn't the page's own, so a bookmark or a shared link keeps it
        await expect(page, p.to).toHaveURL(new RegExp(`${p.to.replace(/[/]/g, "\\/")}${own === space ? "(\\?(?!.*space=).*)?" : "\\?(.*&)?space=" + space}$`), { timeout: 30_000 });
        await inSpace(`${p.to} from ${space}`);
      }
      // a reload keeps it, and so does going back a page
      await page.reload();
      await inSpace(`reload of ${page.url()}`);
      await page.goBack();
      await inSpace("back");
    }
    expect(errors).toEqual([]);
  });
}
