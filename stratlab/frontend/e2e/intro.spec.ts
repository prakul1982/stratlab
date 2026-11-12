import { expect, test, type Page } from "@playwright/test";
import { session, sessionAs } from "./pages-kit";
import { TOURS, TOUR_IDS, type TourId } from "../src/lib/intro";

// Release 42, lane i1 (owner, 12 Nov: "the intro we have on the website itself is also trash, it only shows like 5 steps to get in or
// smth, fix that too"): a tour per space, each step on its real page pointing at its real control. These walk every tour on a laptop
// and a phone, take one back up from "Take the tour", follow the welcome into the picked space's tour, offer the other spaces once,
// and say a locked part's plan.

const FREE = sessionAs("free-token", "u-free", "free@example.com");

/** Signed in, the old tour flag set (so nothing starts by itself), the account's onboarding writes kept off the shared fake account. */
async function signIn(page: Page, path: string, who: typeof session = session, o: { fresh?: boolean } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const url = new URL(r.request().url());
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") return r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
    if (url.pathname === "/me/onboarding" && r.request().method() === "PUT") return r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
    return r.fallback();
  });
  if (o.fresh) {
    // read as an account never asked the welcome question, until it answers (the fake account is shared with other tests)
    let answered = false;
    page.on("request", (q) => { if (q.method() === "PUT" && /\/me\/prefs$/.test(q.url())) answered = true; });
    await page.route(/\/me$/, async (r) => {
      const res = await r.fetch();
      const j = await res.json();
      if (!answered) { j.prefs = {}; j.onboarding = {}; j.established = false; }
      await r.fulfill({ response: res, json: j });
    });
  }
  await page.addInitScript(([s, fresh]) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    if (!fresh) localStorage.setItem("stratlab.tour.v1", "1");
  }, [who, !!o.fresh] as const);
  await page.goto(path);
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

const openTour = (page: Page, tour?: TourId) => page.evaluate((t) => window.dispatchEvent(new CustomEvent("stratlab:tour", { detail: { tour: t } })), tour);
const note = (page: Page) => page.locator(".k-coach[data-placed] .k-coach-note");
const box = (page: Page, sel: string) => page.locator(sel).first().evaluate((e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });

test("every tour, step by step: its page opens, the ring is on a real thing on screen, the note clear of it, back where it began", async ({ page }, info) => {
  test.setTimeout(300_000);
  const phone = info.project.name === "phone";
  const errors = await signIn(page, "/mine");
  const vh = page.viewportSize()!.height, vw = page.viewportSize()!.width;
  for (const id of TOUR_IDS) {
    const tour = TOURS[id];
    await openTour(page, id);
    const dlg = page.getByRole("dialog", { name: `Tour: ${tour.name}` });
    for (const [i, step] of tour.steps.entries()) {
      await expect(dlg.getByRole("heading", { name: step.title })).toBeVisible({ timeout: 30_000 });
      await expect(note(page)).toBeVisible();
      await expect(dlg).toContainText(`${tour.name} · ${i + 1} of ${tour.steps.length}`);
      // its own page (a company step: any company's)
      const here = step.here ?? (step.go ? new RegExp(`^${step.go.replace(/[/]/g, "\\/")}(\\?|$)`) : null);
      if (here) await expect.poll(() => new URL(page.url()).pathname + new URL(page.url()).search, `${step.id}: its page`).toMatch(here);
      // the menu is open for a step in it on a phone, shut otherwise
      if (phone) await expect(page.locator("aside.sidebar.open"), `${step.id}: the phone's menu`).toHaveCount(step.menu ? 1 : 0);
      await page.waitForTimeout(450);           // the ring's glide, the page settling
      const ring = page.locator(".k-coach-ring");
      await expect(ring, `${step.id}: the ring is on something`).not.toHaveAttribute("data-off", /./);
      const r = await box(page, ".k-coach-ring"), n = await box(page, ".k-coach-note");
      expect(r.w > 8 && r.h > 8 && r.y >= -6 && r.y + 8 < vh && r.x >= -6 && r.x + r.w <= vw + 6, `${step.id}: the ring ${JSON.stringify(r)} is on screen`).toBe(true);
      expect(n.y >= 0 && n.y + n.h <= vh + 1 && n.x >= 0 && n.x + n.w <= vw + 1, `${step.id}: the note ${JSON.stringify(n)} fits the window`).toBe(true);
      // the note never covers the middle of what it points at
      const cx = r.x + r.w / 2, cy = r.y + Math.min(r.h, 40) / 2;
      expect(cx > n.x && cx < n.x + n.w && cy > n.y && cy < n.y + n.h, `${step.id}: the note ${JSON.stringify(n)} covers the ring ${JSON.stringify(r)}`).toBe(false);
      // a screen reader hears the step
      await expect(page.locator(".k-coach [aria-live=polite]")).toContainText(step.title);
      await dlg.getByRole("button", { name: i === tour.steps.length - 1 ? "Done" : "Next" }).click();
    }
    await expect(dlg).toHaveCount(0);
    await expect(page, `${id}: back where it began`).toHaveURL(/\/mine$/);
  }
  // nothing on the page wider than the window afterwards, and no errors
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(vw + 1);
  expect(errors).toEqual([]);
});

test("the keyboard: arrows move, Tab stays in the note, Esc stops and the list offers to resume there", async ({ page }) => {
  const errors = await signIn(page, "/mine");
  // "Take the tour" in the Account menu opens the list, the space showing first
  const phone = page.viewportSize()!.width <= 900;
  if (phone) await page.getByRole("button", { name: "Open menu" }).click();
  await page.locator(".sidebar .acct-btn").click();
  await page.getByRole("menuitem", { name: "Take the tour" }).click();
  const list = page.getByRole("dialog", { name: "Take a tour" });
  await expect(list).toBeVisible({ timeout: 15_000 });
  const first = list.getByRole("button", { name: /^Getting around/ });
  await expect(first).toBeFocused();
  await expect(first).toContainText("here now");
  for (const t of ["Trade", "Invest", "Money"]) await expect(list.getByRole("button", { name: new RegExp(`^${t}`) })).toContainText(/\d steps/);
  await list.getByRole("button", { name: /^Invest/ }).click();
  const dlg = page.getByRole("dialog", { name: "Tour: Invest" });
  await expect(dlg).toContainText("1 of 5", { timeout: 30_000 });
  await expect(dlg.getByRole("button", { name: "Next" })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(dlg).toContainText("2 of 5", { timeout: 30_000 });
  await expect(page).toHaveURL(/\/research\/(IN|US)\/[^/]+$/);
  await page.keyboard.press("ArrowLeft");
  await expect(dlg).toContainText("1 of 5", { timeout: 30_000 });
  await page.keyboard.press("ArrowRight");
  await expect(dlg).toContainText("2 of 5", { timeout: 30_000 });
  await page.keyboard.press("ArrowRight");
  await expect(dlg).toContainText("3 of 5", { timeout: 30_000 });
  await expect(page).toHaveURL(/\/research\/themes$/);
  for (let k = 0; k < 8; k++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest(".k-coach-note")), "Tab stays in the note").toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dlg).toHaveCount(0);
  await expect(page).toHaveURL(/\/mine$/);
  // the list picks it up again
  await openTour(page);
  const again = page.getByRole("dialog", { name: "Take a tour" });
  await expect(again, "the list shows at once (it points at nothing, so it waits for nothing)").toBeVisible({ timeout: 2500 });
  const invest = again.getByRole("button", { name: /^Invest/ });
  await expect(invest).toContainText("Resume at step 3 of 5");
  await invest.click();
  await expect(dlg).toContainText("3 of 5", { timeout: 30_000 });
  await expect(dlg.getByRole("heading", { name: "Themes, company by company" })).toBeVisible();
  // "Open one" on the first step opens a company and moves on
  await dlg.getByRole("button", { name: "Back" }).click();
  await dlg.getByRole("button", { name: "Back" }).click();
  await expect(dlg).toContainText("1 of 5", { timeout: 30_000 });
  await dlg.getByRole("button", { name: "Open one" }).click();
  await expect(dlg).toContainText("2 of 5", { timeout: 30_000 });
  await expect(page).toHaveURL(/\/research\/(IN|US)\/[^/]+$/);
  await dlg.getByRole("button", { name: "Skip tour" }).click();
  await expect(dlg).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("the welcome starts the picked space's tour; the other spaces are offered once, the first time they are entered", async ({ page }) => {
  test.setTimeout(180_000);
  const errors = await signIn(page, "/mine", FREE, { fresh: true });
  const welcome = page.getByRole("dialog").filter({ hasText: "What brings you here?" });
  await expect(welcome).toBeVisible({ timeout: 30_000 });
  await expect(welcome).toContainText("Then a short look around the one you pick");
  await welcome.getByRole("button", { name: /^Invest/ }).click();
  const dlg = page.getByRole("dialog", { name: "Tour: Invest" });
  await expect(dlg).toContainText("Look up any company", { timeout: 30_000 });
  await expect(page).toHaveURL(/\/research$/);
  // on Free, the company step says its monthly limits
  await dlg.getByRole("button", { name: "Next" }).click();
  await expect(dlg).toContainText("On Free: 2 deep dives", { timeout: 30_000 });
  await page.keyboard.press("Escape");
  await expect(dlg).toHaveCount(0);
  await expect(page).toHaveURL(/\/invest$/);                 // back to the home the answer opened
  await expect(page.locator(".intro-offer"), "Invest's tour was stopped: not offered again by itself").toHaveCount(0);
  // Money: offered once; Not now is kept
  await page.goto("/money");
  const offer = page.locator(".intro-offer");
  await expect(offer).toContainText("New to Money?", { timeout: 15_000 });
  await expect(page.getByRole("dialog")).toHaveCount(0);          // not a dialog: it takes no focus
  const before = await page.locator("main h1").boundingBox();
  await offer.getByRole("button", { name: "Not now" }).click();
  await expect(offer).toHaveCount(0);
  expect(await page.locator("main h1").boundingBox(), "nothing on the page moved").toEqual(before);
  await page.reload();
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2000);
  await expect(offer).toHaveCount(0);
  // Trade: Show me starts it
  await page.goto("/trade");
  await expect(offer).toContainText("New to Trade?", { timeout: 15_000 });
  await offer.getByRole("button", { name: "Show me" }).click();
  const trade = page.getByRole("dialog", { name: "Tour: Trade" });
  await expect(trade).toContainText("Describe an idea", { timeout: 30_000 });
  // a locked part says its plan, in facts
  for (let i = 0; i < 3; i++) await trade.getByRole("button", { name: "Next" }).click();
  await expect(trade).toContainText("Options paper trading at set times: on the Basic plan.", { timeout: 30_000 });
  // a reload mid-tour comes back on the same step
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Tour: Trade" })).toContainText("4 of 5", { timeout: 30_000 });
  expect(errors).toEqual([]);
});

test("on Pro nothing is said to be on another plan", async ({ page }) => {
  const errors = await signIn(page, "/mine");
  await openTour(page, "trade");
  const dlg = page.getByRole("dialog", { name: "Tour: Trade" });
  for (let i = 0; i < 3; i++) { await expect(dlg).toContainText(`${i + 1} of 5`, { timeout: 30_000 }); await dlg.getByRole("button", { name: "Next" }).click(); }
  await expect(dlg).toContainText("Options, priced before you start", { timeout: 30_000 });
  await expect(dlg.locator(".intro-plan")).toHaveCount(0);
  expect(errors).toEqual([]);
});
