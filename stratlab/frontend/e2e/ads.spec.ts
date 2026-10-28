import { expect, test, type Page } from "@playwright/test";

// ADS-1: ads (and the Meta Pixel and Microsoft Clarity) are ready to switch on and change nothing until they are. With ads off (the shipped state) a Free account sees a StratLab
// card under a company's AI read, Basic and Pro see nothing, and no public page has a slot. With a fake ads-on config (the settings the
// owner will set, and a stand-in for Google's script that draws a grey box) the question comes first, "Allow ads" loads the script
// and one ad, "No thanks" loads nothing and is remembered, and the plans, pages and answers that must never see an ad don't.
const session = (token: string, id: string, email: string) => ({ access_token: token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r", user: { id, aud: "authenticated", email, role: "authenticated", app_metadata: {}, user_metadata: {} } });
const WHO = { free: session("free-token", "u-free", "free@example.com"), basic: session("basic-token", "u-basic", "basic@example.com"), pro: session("pro-token", "u-pro", "pro@example.com") };

const READ = { summary: "Runs refineries, a telecom network and retail stores.", valuation_note: "P/E 24 against 20-28 over five years.",
  facts: [{ id: "growth", label: "Growth", items: [{ label: "Sales, 3 years", text: "11.6% a year" }] }],
  bull: ["Jio has 470 million users."], bear: ["Refining margins move with crude."], segments: [], position: "", watch: [], ideas: [], generated_at: Date.now() / 1000 };

/** Google's script, stood in for: it draws a grey 250px box into the next unfilled slot, as a filled ad would. */
const FAKE_ADS = `(function(){var q=window.adsbygoogle||[];function fill(){var i=document.querySelector("ins.adsbygoogle:not([data-adsbygoogle-status])");if(!i)return;
i.setAttribute("data-adsbygoogle-status","done");i.setAttribute("data-ad-status","filled");var d=document.createElement("div");d.setAttribute("data-fake-ad","");
d.style.cssText="height:250px;background:#bbb;color:#111;display:flex;align-items:center;justify-content:center";d.textContent="Test ad";i.appendChild(d)}
window.adsbygoogle={push:fill};q.forEach(fill)})();`;
const ON = { ADS_ENABLED: "true", ADSENSE_CLIENT: "ca-pub-1234567890123456", ADSENSE_SLOT_PUBLIC: "1111111111", ADSENSE_SLOT_AI: "2222222222" };

type Setup = { who?: keyof typeof WHO; ads?: boolean; choice?: "yes" | "no"; extra?: Record<string, string>; adsOnly?: boolean };

/** Opens a page. Everything off the machine is answered with nothing, and every request to Google is counted. */
async function open(page: Page, path: string, ready: string | RegExp, o: Setup = {}) {
  const errors: string[] = [], google: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => { if (/googlesyndication|doubleclick|adtrafficquality|adservice\.google|facebook\.|clarity\.ms/.test(r.url())) google.push(r.url()); });
  await page.route(/connect\.facebook\.net|clarity\.ms/, (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.route("**/research/company/IN/RELIANCE/ai*", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(READ) }));
  await page.route("https://pagead2.googlesyndication.com/**", (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: FAKE_ADS }));
  if (o.ads || o.extra) {
    await page.route(/\/config\.js(\?|$)/, async (r) => {
      const real = await (await r.fetch()).text();
      await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify({ ...(o.ads ? ON : {}), ...o.extra })});\n` });
    });
  }
  await page.addInitScript(([s, choice, adsOnly]) => {
    if (s) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
    // the saved answer is there on the first load only, so a test can take it back and reload
    // (adsOnly: the yes a page the server draws saves, which answers the question about Google ads alone)
    if (choice && !sessionStorage.getItem("seeded")) { localStorage.setItem("stratlab.ads", JSON.stringify({ c: choice, at: Date.now(), ...(adsOnly ? { s: "ads" } : {}) })); sessionStorage.setItem("seeded", "1"); }
  }, [o.who ? WHO[o.who] : null, o.choice ?? null, !!o.adsOnly] as const);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 2500 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return { errors, google };
}

const company = (page: Page, who: keyof typeof WHO, o: Setup = {}) => open(page, "/research/IN/RELIANCE", "Runs refineries", { who, ...o });
const noSideways = async (page: Page) => {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
};

// ---------- ads off: the shipped state ----------
test("ads off: a Free account sees one StratLab card under the AI read; Basic and Pro see nothing; nothing from Google is asked for", async ({ page }) => {
  const { errors, google } = await company(page, "free");
  const card = page.getByTestId("ad-house");
  await expect(card).toHaveCount(1);
  await card.scrollIntoViewIfNeeded();
  await expect(card).toBeVisible();
  expect(["Basic has more AI builds and deep dives", "Test your idea with the four luck checks", "Read today's market brief"]).toContain(await card.locator("b").innerText());
  await expect(card.locator(".ad-label")).toHaveText("From StratLab");
  await expect(card.getByRole("link")).toHaveCount(1);
  await expect(page.getByTestId("ad-slot")).toHaveCount(0);
  await expect(page.getByTestId("ad-consent")).toHaveCount(0);
  await expect(page.getByText("Advertisement")).toHaveCount(0);
  // under the written read, in the same column
  const read = await page.locator(".ai-read .k-card, .ai-read > div").first().boundingBox(), c = await card.boundingBox();
  expect(c!.y).toBeGreaterThan(read!.y);
  await noSideways(page);
  expect(google, "no request to an ad host").toEqual([]);
  expect(errors).toEqual([]);
});

for (const who of ["basic", "pro"] as const) {
  test(`ads off: ${who} sees no card and no slot under the AI read`, async ({ page }) => {
    const { google } = await company(page, who);
    await expect(page.locator(".ai-read")).toBeVisible();
    await page.waitForTimeout(500);
    await expect(page.locator(".ad")).toHaveCount(0);
    expect(google).toEqual([]);
  });
}

test("ads off: the landing page and the library have no slot, and no empty gap where one would be", async ({ page }) => {
  const { google } = await open(page, "/library", "StratLab's own strategies");
  await expect(page.locator(".lib-card").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".ad")).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await page.waitForTimeout(500);
  await expect(page.locator(".ad")).toHaveCount(0);
  expect(google).toEqual([]);
});

// ---------- ads on (a fake config) ----------
test("ads on: Free is asked first, Allow loads the script and one labelled ad that holds its height", async ({ page }) => {
  const { errors, google } = await company(page, "free", { ads: true });
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible();
  await expect(ask).toContainText("Google ads");
  await expect(ask).toHaveAttribute("role", "dialog");
  await expect(page.getByTestId("ad-house"), "until the answer, a StratLab card holds the place").toHaveCount(1);
  await expect(page.getByTestId("ad-slot")).toHaveCount(0);
  expect(google, "nothing is asked of Google before Allow").toEqual([]);
  await expect(ask.getByRole("button")).toHaveCount(2);
  await ask.getByRole("button", { name: "Allow" }).click();
  await expect(ask).toHaveCount(0);
  const slot = page.getByTestId("ad-slot");
  await slot.scrollIntoViewIfNeeded();
  await expect(slot).toBeVisible();
  await expect(slot.locator(".ad-label")).toHaveText("Advertisement");
  await expect(slot.locator("[data-fake-ad]")).toBeVisible();
  expect(google.length).toBe(1);
  expect(google[0]).toContain("/pagead/js/adsbygoogle.js?client=ca-pub-1234567890123456");
  await expect(slot.locator("ins.adsbygoogle")).toHaveAttribute("data-ad-slot", "2222222222");
  // the box held its height from the start: the ad fits inside it, and the page below did not move when it arrived
  const box = await slot.locator(".ad-box").boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(280);
  // not styled like StratLab's cards: no fill and no frame of its own
  const css = await slot.evaluate((e) => { const s = getComputedStyle(e); return { bg: s.backgroundColor, radius: s.borderRadius, left: s.borderLeftWidth }; });
  expect(css.bg).toBe("rgba(0, 0, 0, 0)");
  expect(css.left).toBe("0px");
  // clear of the buttons above it: nothing clickable within 24px
  const above = await page.evaluate(() => { const s = document.querySelector('[data-testid="ad-slot"]')!.getBoundingClientRect().top;
    return Math.min(...Array.from(document.querySelectorAll(".ai-read button, .ai-read a")).map((b) => s - b.getBoundingClientRect().bottom).filter((d) => d > -1)); });
  expect(above).toBeGreaterThanOrEqual(24);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("stratlab.ads")!).c)).toBe("yes");
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("ads on: No thanks loads nothing, leaves a StratLab card, and is remembered", async ({ page }) => {
  const { google } = await company(page, "free", { ads: true });
  await page.getByTestId("consent").getByRole("button", { name: "No thanks" }).click();
  await expect(page.getByTestId("ad-house")).toBeVisible();
  await expect(page.getByTestId("ad-slot")).toHaveCount(0);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("stratlab.ads")!).c)).toBe("no");
  await page.reload();
  await expect(page.locator(".ai-read")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ad-house")).toBeVisible();
  await expect(page.getByTestId("consent")).toHaveCount(0);
  expect(google).toEqual([]);
});

test("ads on: a saved Allow shows the ad without asking again", async ({ page }) => {
  await company(page, "free", { ads: true, choice: "yes" });
  await expect(page.getByTestId("consent")).toHaveCount(0);
  await page.getByTestId("ad-slot").scrollIntoViewIfNeeded();
  await expect(page.locator("[data-fake-ad]")).toHaveCount(1);
});

for (const who of ["basic", "pro"] as const) {
  test(`ads on: ${who} never sees a slot, a question or a card, even after allowing ads`, async ({ page }) => {
    const { google } = await company(page, who, { ads: true, choice: "yes" });
    await expect(page.locator(".ai-read")).toBeVisible();
    await page.waitForTimeout(800);
    await expect(page.locator(".ad, [data-fake-ad]")).toHaveCount(0);
    expect(google).toEqual([]);
  });
}

test("ads on: a Free account's money pages never have one", async ({ page }) => {
  const { google } = await open(page, "/holdings", /holdings/i, { who: "free", ads: true, choice: "yes" });
  await page.waitForTimeout(800);
  await expect(page.locator(".ad, [data-fake-ad]")).toHaveCount(0);
  await page.goto("/money");
  await page.waitForTimeout(800);
  await expect(page.locator(".ad, [data-fake-ad]")).toHaveCount(0);
  expect(google).toEqual([]);
});

test("ads on: the public library asks a visitor first; No thanks leaves no gap and is remembered", async ({ page }) => {
  const { google } = await open(page, "/library", "StratLab's own strategies", { ads: true });
  await expect(page.locator(".lib-card").first()).toBeVisible({ timeout: 30_000 });
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible();
  await expect(page.locator(".ad"), "no slot before the visitor says yes").toHaveCount(0);
  expect(google).toEqual([]);
  await ask.getByRole("button", { name: "No thanks" }).click();
  await expect(page.locator(".ad")).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".lib-card").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  await expect(page.locator(".ad")).toHaveCount(0);
  expect(google).toEqual([]);
});

test("ads on: the public library shows one ad after Allow in the banner, below the strategies", async ({ page }) => {
  const { errors } = await open(page, "/library", "StratLab's own strategies", { ads: true, choice: "yes" });
  await expect(page.locator(".lib-card").first()).toBeVisible({ timeout: 30_000 });
  const slot = page.getByTestId("ad-slot");
  await slot.scrollIntoViewIfNeeded();
  await expect(slot.locator("[data-fake-ad]")).toBeVisible();
  await expect(slot.locator("ins.adsbygoogle")).toHaveAttribute("data-ad-slot", "1111111111");
  await expect(page.locator(".ad")).toHaveCount(1);
  // (VR7-004: on a phone the cards past the first twelve are in the page but hidden until "Show more": the last one drawn)
  const last = await page.locator(".lib-card:visible").last().boundingBox(), s = await slot.boundingBox();
  expect(s!.y).toBeGreaterThan(last!.y + last!.height);
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("ads on: the landing page has one slot, in the lower sections and not the first screen", async ({ page }) => {
  const { google } = await open(page, "/", "Test it, research it, track it", { ads: true });
  await expect(page.getByTestId("consent")).toHaveCount(1);
  expect(google, "nothing is asked of Google until Allow").toEqual([]);
  await page.getByTestId("consent").getByRole("button", { name: "Allow" }).click();
  const slot = page.locator(".ad");
  await expect(slot).toHaveCount(1);
  const y = await slot.evaluate((e) => e.getBoundingClientRect().top + window.scrollY);
  expect(y).toBeGreaterThan((page.viewportSize()?.height ?? 800) * 2);
});

test("ads on: signed in with a saved sign-in, the public pages have no slot of their own", async ({ page }) => {
  await open(page, "/library", /strategy library|StratLab's own strategies/i, { who: "pro", ads: true, choice: "yes" });
  await page.waitForTimeout(800);
  await expect(page.locator(".ad, [data-fake-ad]")).toHaveCount(0);
});

// ---------- the Meta Pixel and Microsoft Clarity ----------
const TRACK = { META_PIXEL_ID: "1234567890", CLARITY_PROJECT_ID: "abc123def4" };
const pixelCalls = (page: Page) => page.evaluate(() => ((window as unknown as { fbq?: { queue: unknown[][] } }).fbq?.queue ?? []).map((a) => Array.from(a)));
const clarityCalls = (page: Page) => page.evaluate(() => ((window as unknown as { clarity?: { q?: unknown[][] } }).clarity?.q ?? []).map((a) => Array.from(a)));

test("trackers: nothing loads or is asked of Meta or Microsoft before Allow; No thanks keeps it that way", async ({ page }) => {
  const { google } = await open(page, "/library", "StratLab's own strategies", { extra: TRACK });
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible();
  await expect(ask).toContainText("Analytics");
  await expect(ask).toContainText("Meta's ad measurement and Microsoft Clarity");
  await expect(ask).toContainText("all text hidden");
  await page.waitForTimeout(600);
  expect(google, "no request before the answer").toEqual([]);
  expect(await pixelCalls(page)).toEqual([]);
  await ask.getByRole("button", { name: "No thanks" }).click();
  await page.waitForTimeout(600);
  expect(google).toEqual([]);
  await page.reload();
  await page.waitForTimeout(800);
  await expect(page.getByTestId("consent")).toHaveCount(0);
  expect(google).toEqual([]);
});

test("trackers: Allow loads the pixel (PageView) and Clarity (masked), and the private pages stop them", async ({ page }) => {
  const { google, errors } = await open(page, "/mine", /./, { who: "free", extra: TRACK });
  await expect(page.getByTestId("consent")).toBeVisible({ timeout: 30_000 });
  expect(google).toEqual([]);
  await page.getByTestId("consent").getByRole("button", { name: "Allow" }).click();
  await expect.poll(() => google.some((u) => /connect\.facebook\.net\/en_US\/fbevents\.js/.test(u))).toBe(true);
  expect(google.some((u) => u.includes("www.clarity.ms/tag/abc123def4"))).toBe(true);
  expect(await pixelCalls(page)).toEqual([["set", "autoConfig", false, "1234567890"], ["init", "1234567890"], ["track", "PageView"]]);
  await expect(page.locator("#root")).toHaveAttribute("data-clarity-mask", "True");
  // a client-side move to another page counts once; a private page counts nothing and stops Clarity
  await page.evaluate(() => { history.pushState({}, "", "/research"); dispatchEvent(new PopStateEvent("popstate")); });
  await expect.poll(async () => (await pixelCalls(page)).filter((c) => c[1] === "PageView" || c[0] === "track").length).toBe(2);
  const before = (await pixelCalls(page)).length;
  await page.evaluate(() => { history.pushState({}, "", "/holdings"); dispatchEvent(new PopStateEvent("popstate")); });
  await expect.poll(async () => (await clarityCalls(page)).some((c) => c[0] === "stop")).toBe(true);
  expect((await pixelCalls(page)).length, "no event from a private page").toBe(before);
  await page.evaluate(() => { history.pushState({}, "", "/money"); dispatchEvent(new PopStateEvent("popstate")); });
  await page.waitForTimeout(500);
  expect((await pixelCalls(page)).length).toBe(before);
  expect(errors).toEqual([]);
});

test("trackers: a private page is never asked, and with a saved yes nothing loads there", async ({ page }) => {
  const { google } = await open(page, "/holdings", /holdings/i, { who: "free", extra: TRACK, choice: "yes" });
  await page.waitForTimeout(1000);
  await expect(page.getByTestId("consent")).toHaveCount(0);
  expect(google, "nothing from Meta or Microsoft on holdings").toEqual([]);
  await page.goto("/account");
  await page.waitForTimeout(800);
  await expect(page.getByTestId("consent")).toHaveCount(0);
  expect(google).toEqual([]);
});

test("trackers: Do Not Track keeps the pixel and Clarity off even after Allow", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, "doNotTrack", { get: () => "1" }));
  const { google } = await open(page, "/library", "StratLab's own strategies", { extra: TRACK, choice: "yes" });
  await page.waitForTimeout(800);
  expect(google).toEqual([]);
});

test("privacy: the page names the trackers and the answer can be changed", async ({ page }) => {
  await open(page, "/privacy", "Privacy policy", { extra: TRACK, choice: "yes" });
  await expect(page.getByText("Meta Pixel").first()).toBeVisible();
  await expect(page.getByText("Microsoft Clarity").first()).toBeVisible();
  const c = page.getByTestId("ad-choice");
  await expect(c).toContainText("allowed");
  await c.getByRole("button", { name: "Change my choice" }).click();
  await page.waitForLoadState("load");
  await expect(page.getByTestId("consent")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ad-choice")).toContainText("not asked yet");
});

// ---------- the pages the server draws: public/ads.js ----------
const SERVER_PAGE = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Server page</title><style>.ad-box{min-height:280px}</style></head><body><main><h1>A company</h1>
<p>Facts.</p><section class="ad" data-ads data-client="ca-pub-1234567890123456" data-slot="1111111111" data-name="company" aria-label="Advertisement">
<p class="ad-label">Advertisement</p><div class="ad-box"></div></section></main><script src="/ads.js" defer></script></body></html>`;

async function serverPage(page: Page, choice?: "yes" | "no") {
  const google: string[] = [];
  page.on("request", (r) => { if (/googlesyndication/.test(r.url())) google.push(r.url()); });
  await page.route("https://pagead2.googlesyndication.com/**", (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: FAKE_ADS }));
  await page.route("**/__server-page", (r) => r.fulfill({ status: 200, contentType: "text/html", body: SERVER_PAGE }));
  if (choice) await page.addInitScript((c) => localStorage.setItem("stratlab.ads", JSON.stringify({ c, at: Date.now() })), choice);
  await page.goto("/__server-page");
  return google;
}

test("a server-drawn page: asks first, Allow loads one ad, and the answer is shared with the app", async ({ page }) => {
  const google = await serverPage(page);
  await expect(page.locator(".ad-ask")).toBeVisible();
  await expect(page.locator(".ad-label")).toHaveText("Ads on StratLab");
  expect(google).toEqual([]);
  // (VR4-015) the question does not sit in a box held at 280px for an ad that is not coming yet
  expect((await page.locator(".ad-box").boundingBox())!.height).toBeLessThan(200);
  await page.getByRole("button", { name: "Allow ads" }).click();
  await expect(page.locator(".ad-box")).toHaveCSS("min-height", "280px");
  await expect(page.locator("[data-fake-ad]")).toBeVisible();
  await expect(page.locator(".ad-label")).toHaveText("Advertisement");
  expect(google.length).toBe(1);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("stratlab.ads")!).c)).toBe("yes");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("stratlab.ads")!).s), "the yes says it was about Google ads alone").toBe("ads");
});

test("a server-drawn page: No thanks removes the box and loads nothing; a saved answer is not asked again", async ({ page }) => {
  const google = await serverPage(page);
  await page.getByRole("button", { name: "No thanks" }).click();
  await expect(page.locator(".ad")).toHaveCount(0);
  await page.reload();
  await page.waitForTimeout(500);
  await expect(page.locator(".ad")).toHaveCount(0);
  expect(google).toEqual([]);
});

test("a server-drawn page: an answer the app saved (yes) shows the ad at once", async ({ page }) => {
  const google = await serverPage(page, "yes");
  await expect(page.locator("[data-fake-ad]")).toBeVisible();
  await expect(page.locator(".ad-ask")).toHaveCount(0);
  expect(google.length).toBe(1);
});

test("trackers: a yes given for Google ads alone starts neither tracker; the app asks about them, and No thanks keeps the ads allowed", async ({ page }) => {
  const { google } = await open(page, "/library", "StratLab's own strategies", { extra: TRACK, choice: "yes", adsOnly: true });
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible();
  await expect(ask).toContainText("Analytics");
  await expect(ask).toContainText("Meta's ad measurement and Microsoft Clarity");
  await expect(ask).not.toContainText("Google");
  await page.waitForTimeout(800);
  expect(google, "the yes about ads is not a yes to these").toEqual([]);
  expect(await pixelCalls(page)).toEqual([]);
  await ask.getByRole("button", { name: "No thanks" }).click();
  await expect(page.getByTestId("consent")).toHaveCount(0);
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("stratlab.ads")!));
  expect(saved).toMatchObject({ c: "yes", s: "ads", t: "no" });
  await page.reload();
  await page.waitForTimeout(800);
  await expect(page.getByTestId("consent")).toHaveCount(0);
  expect(google).toEqual([]);
});

test("trackers: Allow on that question starts them, and the Privacy page says what the answer covers", async ({ page }) => {
  const { google } = await open(page, "/library", "StratLab's own strategies", { extra: TRACK, choice: "yes", adsOnly: true });
  await page.getByTestId("consent").getByRole("button", { name: "Allow" }).click();
  await expect.poll(() => google.some((u) => /connect\.facebook\.net\/en_US\/fbevents\.js/.test(u))).toBe(true);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("stratlab.ads")!).s)).toBeUndefined();
  await page.goto("/privacy");
  await expect(page.getByText("the question is about Google ads only").first()).toBeVisible();
});
