import { expect, test, type Page } from "@playwright/test";

// MO-4: the notebook is one centred column with floating Lab notes, and Positioning leaves no dead space beside a short card.
// Signed in as the site owner, tour seen.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const admin = { Authorization: "Bearer admin-token" };
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const EMA = { name: "Trend follower", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
  exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };

async function open(page: Page, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  return errors;
}

test("MO-4a: the notebook is centred like every page, and the Lab notes float, open, save, close and remember", async ({ page, request }, info) => {
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name: `Notes ${info.project.name}`, question: "Does the cross work?", strategy: EMA, instrument: "CRYPTO:BTC-USD" } })).json();
  const errors = await open(page, `/n/${nb.id}`);
  await expect(page.getByRole("heading", { name: `Notes ${info.project.name}` })).toBeVisible({ timeout: 30_000 });
  const phone = (page.viewportSize()?.width ?? 1440) <= 640;

  // one column: the notebook's cards run the page's full width, the same as another page's; nothing sits beside them
  const main = await page.locator(".page").boundingBox();
  const card = await page.locator(".k-card").first().boundingBox();
  expect(Math.abs(card!.x - main!.x), "the notebook starts at the page's left edge").toBeLessThan(2);
  expect(Math.abs((card!.x + card!.width) - (main!.x + main!.width)), "and runs to its right edge: no column beside it").toBeLessThan(2);

  // the button: fixed at the bottom-right, no dot yet, the panel closed
  const btn = page.getByTestId("lab-notes-btn");
  await expect(btn).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("region", { name: "Lab notes" })).toBeHidden();
  const vp = page.viewportSize()!;
  const b = await btn.boundingBox();
  // at the right: on a laptop an edge handle on the window's right edge, in the margin beside the page (LIVE1A-001: the bottom tab lay over cards), within a finger of the screen's on a phone
  if (phone) {
    expect(b!.x + b!.width, "at the right").toBeGreaterThan(vp.width - 40);
    expect(b!.y + b!.height, "at the bottom").toBeGreaterThan(vp.height - 40);
    expect(b!.height, "a finger-sized target").toBeGreaterThanOrEqual(44);
  } else {
    expect(b!.x + b!.width, "on the window's right edge").toBeGreaterThan(vp.width - 2);
    expect(b!.x, "in the margin, clear of the page").toBeGreaterThanOrEqual(main!.x + main!.width - 1);
    expect(b!.width, "a finger-sized target").toBeGreaterThanOrEqual(40);
  }
  await expect(btn.locator(".ln-dot")).toHaveCount(0);

  // open: the notes get the focus, the panel is a labelled region, the placeholder and the tip are there
  await btn.click();
  await expect(btn).toHaveAttribute("aria-expanded", "true");
  const panel = page.getByRole("region", { name: "Lab notes" });
  await expect(panel).toBeVisible();
  const box = page.getByPlaceholder("What did you notice? What do you want to try next?");
  await expect(box).toBeFocused();
  await expect(panel.getByRole("button", { name: "About lab notes" })).toBeVisible();
  const pb = await panel.boundingBox();
  if (phone) expect(pb!.width, "a bottom sheet across the screen").toBeGreaterThan(vp.width - 2);
  else expect(pb!.width, "a card of about 380px").toBeLessThan(400);
  expect(pb!.y + pb!.height, "inside the screen").toBeLessThanOrEqual(vp.height + 1);
  expect(pb!.x + pb!.width, "inside the screen").toBeLessThanOrEqual(vp.width + 1);

  // it autosaves, and a dot shows on the button once there are notes
  await box.fill("Volume looks too strict; try 120%.");
  await expect.poll(async () => (await (await request.get(`${API}/notebooks/${nb.id}`, { headers: admin })).json()).notes, { timeout: 10_000 }).toBe("Volume looks too strict; try 120%.");
  await expect(btn.locator(".ln-dot")).toHaveCount(1);
  await expect(btn).toContainText("this notebook has notes");

  // Escape closes it and puts the focus back on the button; an open (i) tip takes the first Escape
  await panel.getByRole("button", { name: "About lab notes" }).click();
  await expect(panel.getByRole("note")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel.getByRole("note")).toHaveCount(0);
  await expect(panel).toBeVisible();
  await box.focus();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(btn).toBeFocused();
  await expect(btn).toHaveAttribute("aria-expanded", "false");

  // the close button does the same, and the choice is remembered on this device
  await btn.click();
  await expect(box).toBeFocused();
  await panel.getByRole("button", { name: "Close lab notes" }).click();
  await expect(btn).toBeFocused();
  await btn.click();
  await expect(panel).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Lab notes" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder("What did you notice?")).toHaveValue("Volume looks too strict; try 120%.");
  await expect(page.getByPlaceholder("What did you notice?"), "reopened from storage without grabbing the focus").not.toBeFocused();
  expect(errors, "uncaught errors in the page").toEqual([]);
});

test("MO-4b: Positioning's cash and put-call cards are one under the other, with no empty half-row", async ({ page }) => {
  const errors = await open(page, "/trade/positioning");
  const cash = page.getByRole("region", { name: "FII and DII cash market" });
  const pcr = page.getByRole("region", { name: "Put-call ratio by index" });
  await expect(cash).toBeVisible({ timeout: 30_000 });
  await expect(pcr).toBeVisible();
  const a = (await cash.boundingBox())!, c = (await pcr.boundingBox())!;
  expect(c.y, "the PCR card sits under the cash card").toBeGreaterThan(a.y + a.height - 1);
  expect(Math.abs(a.x - c.x), "in the same column").toBeLessThan(2);
  expect(Math.abs(a.width - c.width), "as wide").toBeLessThan(2);
  expect(c.y - (a.y + a.height), "one gap between them, no dead space").toBeLessThan(48);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("MO-4b: two cards in a row end level (Market events: the week and the reminders)", async ({ page }) => {
  await open(page, "/trade/events");
  const week = page.getByRole("region", { name: "The next seven days" });
  await expect(week).toBeVisible({ timeout: 30_000 });
  const rem = page.getByRole("region", { name: /Reminders/ });
  const a = (await week.boundingBox())!, c = (await rem.boundingBox())!;
  // each keeps its own height (VR1-082: stretched, the week card ended 130px of nothing short of its list); side by side they start level
  if (Math.abs(a.y - c.y) < 4) expect(Math.abs(a.y - c.y), "side by side: level at the top").toBeLessThan(2);
  else expect(c.y).toBeGreaterThan(a.y + a.height - 1);     // stacked on a phone
});
