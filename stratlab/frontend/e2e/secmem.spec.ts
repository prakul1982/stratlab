import { expect, test, type Page } from "@playwright/test";

// SECMEM 1b/1c (Wed 4 Nov): sign-in never puts a session token in the address, and no Meta or Microsoft request goes out
// before the visitor answers the analytics question. Google sign-in is the PKCE flow: the round trip comes back with a
// one-time code in the query, which is traded (with the verifier this browser kept) for the session, and the code is then
// taken out of the address. The emailed one-time links Admin sends carry a hashed token the app trades the same way.
// Each test signs in as its own account (secmem-0..), desktop and phone apart.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SB = "https://demo.supabase.co/auth/v1";
const who = (n: number, phone: boolean) => { const i = n + (phone ? 1 : 0); return { token: `secmem-${i}`, id: `u-secmem-${i}`, email: `secmem${i}@example.com` }; };
const sessionFor = (u: ReturnType<typeof who>) => ({ access_token: u.token, token_type: "bearer", expires_in: 86400,
  expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated", app_metadata: { provider: "google" }, user_metadata: {} } });
const saved = (page: Page) => page.evaluate(() => localStorage.getItem("sb-demo-auth-token"));

async function offline(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(() => localStorage.setItem("stratlab.tour.v1", "1"));
  return errors;
}

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

test("Google sign-in is PKCE: no token in the address, the code is traded and dropped; a reload stays in; Sign out ends it", async ({ page, request }, info) => {
  const u = who(0, info.project.name === "phone");
  await request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer ${u.token}` }, data: { level: "some", focus: "both" } });
  const errors = await offline(page);
  let authorize: URL | null = null;
  const traded: Record<string, string>[] = [];
  await page.route(`${SB}/authorize**`, (r) => { authorize = new URL(r.request().url()); return r.fulfill({ status: 200, body: "signing in", contentType: "text/plain" }); });
  await page.route(`${SB}/token?grant_type=pkce`, (r) => { traded.push(r.request().postDataJSON()); return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sessionFor(u)) }); });
  let loggedOut = 0;
  await page.route(`${SB}/logout**`, (r) => { loggedOut++; return r.fulfill({ status: 204, body: "" }); });

  await page.goto("/account");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Sign in to see/, { timeout: 30_000 });
  await page.getByRole("button", { name: "Continue with Google" }).click();
  await expect.poll(() => authorize?.href ?? "").toContain("provider=google");
  const asked = authorize!;
  expect(asked.searchParams.get("code_challenge"), "a PKCE challenge goes with the sign-in").toMatch(/^[\w-]{43,128}$/);
  expect(asked.searchParams.get("code_challenge_method")).toMatch(/^s256$/i);
  // Google comes back to the address Supabase was given, with a one-time code in the query (nothing after a #)
  const back = new URL(asked.searchParams.get("redirect_to")!);
  expect(back.pathname).toBe("/");
  back.searchParams.set("code", "one-time-code");
  await page.goto(back.pathname + back.search);
  await expect(page).toHaveURL(/\/account$/, { timeout: 30_000 });              // the page asked for, with no code and no #
  expect(page.url()).not.toMatch(/code=|#|access_token/);
  expect(traded).toHaveLength(1);
  expect(traded[0].auth_code).toBe("one-time-code");
  expect(traded[0].code_verifier, "the verifier this browser kept").toMatch(/^[\w~.-]{43,128}$/);
  expect(JSON.parse((await saved(page))!).access_token).toBe(u.token);
  const main = page.locator("main");
  await expect(main.getByRole("button", { name: "Sign out", exact: true })).toBeVisible({ timeout: 30_000 });

  await page.reload();
  await expect(main.getByRole("button", { name: "Sign out", exact: true })).toBeVisible({ timeout: 30_000 });
  expect(traded, "a reload doesn't sign in again").toHaveLength(1);
  await main.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect.poll(() => saved(page)).toBeNull();
  expect(loggedOut).toBe(1);
  expect(errors).toEqual([]);
});

test("an emailed one-time link: its hashed token is traded for the session and taken out of the address; a spent one leaves you signed out", async ({ page, request }, info) => {
  const u = who(2, info.project.name === "phone");
  await request.put(`${API}/me/prefs`, { headers: { Authorization: `Bearer ${u.token}` }, data: { level: "some", focus: "both" } });
  const errors = await offline(page);
  const verified: Record<string, string>[] = [];
  let spent = false;
  await page.route(`${SB}/verify**`, (r) => {
    verified.push(r.request().postDataJSON());
    return spent ? r.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ code: 403, error_code: "otp_expired", msg: "Email link is invalid or has expired" }) })
      : r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sessionFor(u)) });
  });
  await page.goto("/?token_hash=0123456789abcdef0123456789abcdef&type=magiclink");
  await expect.poll(() => saved(page), { timeout: 30_000 }).not.toBeNull();
  expect(verified).toHaveLength(1);
  expect(verified[0]).toMatchObject({ token_hash: "0123456789abcdef0123456789abcdef", type: "magiclink" });
  expect(page.url()).not.toMatch(/token_hash|type=|#/);
  await page.goto("/account");
  await expect(page.locator("main").getByRole("button", { name: "Sign out", exact: true })).toBeVisible({ timeout: 30_000 });

  // the same link again in a fresh browser: the service refuses it, the address is cleaned, and nobody is signed in
  spent = true;
  await page.evaluate(() => localStorage.removeItem("sb-demo-auth-token"));
  await page.goto("/?token_hash=0123456789abcdef0123456789abcdef&type=magiclink");
  await expect.poll(() => verified.length, { timeout: 30_000 }).toBe(2);
  await expect.poll(() => page.url()).not.toMatch(/token_hash/);
  expect(await saved(page)).toBeNull();
  await expect(page.getByRole("alert").filter({ hasText: "That sign-in didn't finish" })).toBeVisible({ timeout: 30_000 });     // said, not silent (LIVE3-009)
  expect(errors).toEqual([]);
});

// LIVE3-009: a sign-in that comes back with a code that can't be traded (started in another browser or app, so this one kept no
// verifier; or the service refuses it) drops the code from the address and says so in words with Continue with Google, on an
// app address and on the landing page alike, never a silent sign-in wall with ?code= left in the address.
test("a sign-in code that can't be traded: the address is cleaned and the page says it didn't finish, with a retry", async ({ page }) => {
  const errors = await offline(page);
  const traded: string[] = [];
  await page.route(`${SB}/token?grant_type=pkce`, (r) => { traded.push(r.request().url()); return r.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: "invalid_grant", error_description: "invalid flow state, no valid flow state found" }) }); });
  // no verifier in this browser: the case of a sign-in begun elsewhere
  await page.goto("/mine?code=0b1d2c3e-bogus");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("That sign-in didn't finish", { timeout: 30_000 });
  await expect(page.locator("main")).toContainText("Choose Continue with Google to try again");
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/mine");
  expect(page.url()).not.toMatch(/code=/);
  // a verifier kept but the service refuses the code: the landing page says it in its alert line
  await page.evaluate(() => { sessionStorage.clear(); localStorage.setItem("sb-demo-auth-token-code-verifier", JSON.stringify("v".repeat(56))); });
  await page.goto("/?code=0b1d2c3e-refused");
  await expect(page.getByRole("alert").filter({ hasText: "That sign-in didn't finish" })).toBeVisible({ timeout: 30_000 });
  expect(traded.length).toBeGreaterThan(0);
  expect(page.url()).not.toMatch(/code=/);
  expect(errors).toEqual([]);
});

// 1c: a first visit, before any answer, sends nothing to Meta or Microsoft and holds no script of theirs; No thanks keeps it
// so across a move and a reload; Allow (another first visit) loads both.
const TRACK = { META_PIXEL_ID: "1234567890", CLARITY_PROJECT_ID: "abc123def4" };
async function visitor(page: Page) {
  const asked: string[] = [];
  page.on("request", (r) => { if (/facebook\.(net|com)|clarity\.ms/.test(r.url())) asked.push(r.url()); });
  await offline(page);
  await page.route(/connect\.facebook\.net|clarity\.ms/, (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
  await page.route(/\/config\.js(\?|$)/, async (r) => {
    const real = await (await r.fetch()).text();
    await r.fulfill({ status: 200, contentType: "text/javascript", body: `${real}\nObject.assign(window.STRATLAB_CONFIG, ${JSON.stringify(TRACK)});\n` });
  });
  return asked;
}
const theirScripts = (page: Page) => page.locator('script[src*="facebook"], script[src*="clarity.ms"]').count();

test("consent: a first visit sends nothing to Meta or Microsoft before the answer, and No thanks keeps it that way", async ({ page }) => {
  const asked = await visitor(page);
  await page.goto("/");
  const ask = page.getByTestId("consent");
  await expect(ask).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(800);
  expect(asked, "no request before the answer").toEqual([]);
  expect(await theirScripts(page)).toBe(0);
  await ask.getByRole("button", { name: "No thanks" }).click();
  await page.goto("/library");
  await page.reload();
  await page.waitForTimeout(800);
  await expect(page.getByTestId("consent")).toHaveCount(0);
  expect(asked, "never after No thanks").toEqual([]);
  expect(await theirScripts(page)).toBe(0);
});

test("consent: Allow on a first visit loads the pixel and Clarity", async ({ page }) => {
  const asked = await visitor(page);
  await page.goto("/");
  await expect(page.getByTestId("consent")).toBeVisible({ timeout: 30_000 });
  expect(asked).toEqual([]);
  await page.getByTestId("consent").getByRole("button", { name: "Allow" }).click();
  await expect.poll(() => asked.some((x) => /connect\.facebook\.net\/en_US\/fbevents\.js/.test(x))).toBe(true);
  await expect.poll(() => asked.some((x) => x.includes("www.clarity.ms/tag/abc123def4"))).toBe(true);
});
