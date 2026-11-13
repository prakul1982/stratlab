import { expect, test, type Locator, type Page } from "@playwright/test";
import { open, sessionAs } from "./pages-kit";

// Bet 3 MVP (public, shareable research): a deep dive and a finished theme are shared as links; the link opens a dated public teaser
// at /r/<token> (no account needed, kept out of search, a clear way into the app); Account lists the links and turns one off, after
// which it answers "not available". The public theme pages and the embeds are server pages the site forwards to the API.
// Each test signs in as its own Pro account (tests/fake_db.py b3-*), on desktop and phone.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SHOTS = process.env.E2E_SHOTS;
const THEME = "India steel and mining";
const PROVIDERS = /kite|yahoo|screener\.in|finnhub|nseindia/i;

function who(info: { project: { name: string } }, slot: number) {
  const i = (info.project.name === "phone" ? 6 : 0) + slot;
  return { token: `b3-${i}`, session: sessionAs(`b3-${i}`, `u-b3-${i}`, `b3${i}@example.com`) };
}

async function shots(page: Page, name: string, phone: boolean, part?: Locator) {
  if (!SHOTS) return;
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.waitForTimeout(200);
    const file = `${SHOTS}/b3-${name}-${phone ? "390" : "1440"}-${scheme}.png`;
    await (part ? part.screenshot({ path: file }) : page.screenshot({ path: file, fullPage: true }));
  }
  await page.emulateMedia({ colorScheme: "light" });
}

async function noSideScroll(page: Page) {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
}

/** Press Share link and read the token the server gave (the copy itself goes to the clipboard or the share sheet). */
async function share(page: Page, path: RegExp): Promise<string> {
  const made = page.waitForResponse((r) => path.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await page.getByTestId("share-research").first().click();
  const res = await made;
  expect(res.status()).toBe(200);
  return ((await res.json()) as { token: string }).token;
}

test("a deep dive's share link opens a dated public teaser, and Account turns it off", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const me = who(info, 0);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => undefined);
  const errors = await open(page, "/research/IN/RELIANCE/deep", "business, capex and growth", me.session);
  await expect(page.getByTestId("share-research")).toHaveText(/Share link/);
  const token = await share(page, /^\/research\/share\/deep\/IN\/RELIANCE$/);
  expect(token).toMatch(/^[A-Za-z0-9_-]{24}$/);
  expect(errors).toEqual([]);

  // the link, as anyone opens it: the API's own page through the site
  const res = await page.goto(`/r/${token}`);
  expect(res?.status()).toBe(200);
  expect(res?.headers()["x-robots-tag"]).toBe("noindex, follow");
  await expect(page.locator("h1")).toHaveText(/Reliance/);
  await expect(page.locator("[data-shared]")).toContainText("Shared from StratLab");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex,follow");
  const cta = page.locator("[data-cta]").getByRole("link", { name: "See the full research on StratLab" });
  await expect(cta).toHaveAttribute("href", /\/research\/IN\/RELIANCE\/deep$/);
  expect(await page.locator("main").innerText()).not.toMatch(PROVIDERS);
  await noSideScroll(page);
  await shots(page, "share-deep", phone);

  // Account: the link is listed, and turning it off takes the page down
  await page.goto("/account");
  const card = page.locator("#shares");
  await expect(card.getByRole("heading", { name: "Shared research links" })).toBeVisible({ timeout: 30_000 });
  await expect(card.getByTestId("share-count")).toHaveText(/share links? made this month \(no limit on your plan\)/);
  await expect(card.getByRole("link", { name: /Reliance/ }).first()).toBeVisible();
  await card.scrollIntoViewIfNeeded();
  await shots(page, "account-shares", phone, card);
  await card.getByRole("button", { name: /Turn off the link to Reliance/ }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Turn off" }).click();
  await expect(card.getByText("Off", { exact: true }).first()).toBeVisible();
  const gone = await page.request.get(`${API}/r/${token}`);
  expect(gone.status()).toBe(404);
  expect(gone.headers()["x-robots-tag"]).toBe("noindex");
});

test("a finished theme is shared as a teaser of its layers, and its public pages and embed are reachable", async ({ page }, info) => {
  test.setTimeout(180_000);
  const phone = info.project.name === "phone";
  const me = who(info, 1);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => undefined);
  await open(page, `/research/themes?region=IN&q=${encodeURIComponent(THEME)}`, "The whole chain in one table", me.session);
  // the button shows once the map and its checks are finished (only then is the theme kept in the library)
  await expect(page.getByTestId("share-research")).toBeVisible({ timeout: 120_000 });
  const token = await share(page, /^\/research\/share\/theme$/);
  const res = await page.goto(`/r/${token}`);
  expect(res?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Layers of the theme" })).toBeVisible();
  await expect(page.locator("[data-cta]").getByRole("link", { name: "See the full research on StratLab" })).toHaveAttribute("href", /\/research\/themes\?q=/);
  await noSideScroll(page);
  await shots(page, "share-theme", phone);

  // the theme's public page, from the link's own button
  const pageLink = page.locator("[data-cta] a.btn.ghost");
  const href = (await pageLink.getAttribute("href")) ?? "";
  const path = new URL(href).pathname;
  expect(path).toMatch(/^\/themes\/in\/[a-z0-9-]+$/);
  const themePage = await page.goto(path);
  expect(themePage?.status()).toBe(200);
  await expect(page.locator("[data-layer]").first()).toBeVisible();
  // (updated on purpose, R44/AS1: a link from a public page into the app says so, "(needs sign-in)", and carries rel="nofollow")
  await expect(page.locator("[data-cta]").getByRole("link", { name: /^Open the .+ theme \(needs sign-in\)$/ })).toBeVisible();
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/median/i);
  expect(text).not.toMatch(PROVIDERS);
  await noSideScroll(page);
  await shots(page, "theme-page", phone);
  const dir = await page.goto("/themes/in");
  expect(dir?.status()).toBe(200);
  await expect(page.locator(`a[href="${path}"]`)).toBeVisible();
  await shots(page, "themes-directory", phone);

  // the embeds: framable charts with their source and date
  for (const [url, name] of [[`/embed/theme${path.slice("/themes".length)}`, "embed-theme"], ["/embed/price/in/RELIANCE", "embed-price"]] as const) {
    const r = await page.goto(url);
    expect(r?.status(), url).toBe(200);
    expect(r?.headers()["x-frame-options"], url).toBeUndefined();
    expect(r?.headers()["content-security-policy"], url).toMatch(/frame-ancestors \*/);
    await expect(page.locator("svg[role=img]")).toBeVisible();
    await expect(page.getByText(/^Source: .+ As of /)).toBeVisible();
    await shots(page, name, phone);
  }
});
