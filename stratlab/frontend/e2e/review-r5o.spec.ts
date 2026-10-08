import { expect, test, type Page } from "@playwright/test";
import { blankStrategy, defaultExit, INDICATORS, INDICATOR_GROUPS, parseStrategyText, withDefaultExit } from "../src/lib/rules";

// Round 5, the owner's review (R5O-…). The first tests need no browser.
const pure = (info: { project: { name: string } }) => test.skip(info.project.name !== "desktop", "no browser needed: once is enough");
const ema = (p: number) => ({ t: "ema" as const, p });

test("no target the person didn't ask for (R5O-010)", ({}, info) => {
  pure(info);
  expect(blankStrategy().risk.tgt).toBe(0);
  const p = parseStrategyText("Buy when 20 EMA crosses above 50 EMA. Stop loss 2%");
  const s = { ...blankStrategy(), entry: p.entry, exit: p.exit, risk: { ...blankStrategy().risk, ...p.risk } };
  expect(s.risk.sl).toBe(2);
  expect(s.risk.tgt).toBe(0);
});

test("the sell rule shown as the default is the one the notebook runs (R5O-010)", ({}, info) => {
  pure(info);
  const s = { ...blankStrategy(), entry: [{ l: ema(20), op: "xa" as const, r: ema(50) }] };
  expect(defaultExit(s)).toEqual([{ l: ema(20), op: "xb", r: ema(50) }]);
  expect(withDefaultExit(s, ["sl"]).exit).toEqual([{ l: ema(20), op: "xb", r: ema(50) }]);
  expect(withDefaultExit(s, ["exit"]).exit).toEqual([]);                       // the idea said how to sell: left alone
  const rsi = { ...blankStrategy(), entry: [{ l: { t: "rsi" as const, p: 14 }, op: "xb" as const, r: { t: "num" as const, v: 30 } }] };
  expect(withDefaultExit(rsi, []).exit).toEqual([{ l: { t: "rsi", p: 14 }, op: "xa", r: { t: "num", v: 55 } }]);
  const level = { ...blankStrategy(), entry: [{ l: { t: "price" as const }, op: "gt" as const, r: { t: "num" as const, v: 100 } }] };
  expect(withDefaultExit(level, []).exit).toEqual([]);                          // nothing follows: the page says no sell rule is set
});

test("the rule picker is grouped, in plain words (R5O-040)", ({}, info) => {
  pure(info);
  const stage = INDICATORS.find((i) => i.t === "stage")!;
  expect(stage.name).toBe("Stage (1–4)");
  expect(stage.friendly).toMatch(/1 basing, 2 rising, 3 topping, 4 falling/);
  expect(INDICATORS.map((i) => i.name).join(" ")).not.toMatch(/Weinstein|Donchian/);
  for (const i of INDICATORS) expect(INDICATOR_GROUPS.map(([g]) => g)).toContain(i.group);
  for (const [g] of INDICATOR_GROUPS) expect(INDICATORS.filter((i) => i.group === g).length).toBeLessThanOrEqual(8);
});

// ---------- in the browser, against the fake world ----------
function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function signedIn(page: Page, n: number) {
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => {
    localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    localStorage.setItem("stratlab.tour.v1", "1");
  }, sessionFor(n));
}

/** An empty account is asked "What brings you here?" first: answer it, then go on. */
async function dismissWelcome(page: Page) {
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  if (await welcome.waitFor({ timeout: 4000 }).then(() => true).catch(() => false)) {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
  }
}

test("a failed /me shows Retry, and Retry brings the account back (R5O-002)", async ({ page }, info) => {
  await signedIn(page, info.project.name === "phone" ? 140 : 131);
  let down = true;
  await page.route(/\/me(\?|$)/, (r) => (down
    ? r.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "database_unavailable", message: "StratLab's database isn't answering right now (ref ABC123)." } }) })
    : r.fallback()));
  await page.goto("/settings");
  const banner = page.getByRole("alert").filter({ hasText: "couldn't load your account" });
  await expect(banner).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Checking access")).toHaveCount(0);
  down = false;
  await banner.getByRole("button", { name: "Retry" }).click();
  await expect(banner).toHaveCount(0, { timeout: 15_000 });
});

test("library cards say the return beside buy and hold, in facts (R5O-014)", async ({ page }, info) => {
  await signedIn(page, info.project.name === "phone" ? 143 : 134);
  await page.goto("/library");
  await dismissWelcome(page);
  const cards = page.locator(".k-cards > section");
  await expect(cards.first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("lib-hold").first()).toContainText(/after costs against .* for buying and holding/);
  await expect(page.locator(".k-cards")).not.toContainText("Likely a real edge");
});

test("Help has its own title (R5O-032)", async ({ page }, info) => {
  await signedIn(page, info.project.name === "phone" ? 146 : 137);
  await page.goto("/help");
  await dismissWelcome(page);
  await expect(page).toHaveTitle("Help · StratLab", { timeout: 30_000 });
});
