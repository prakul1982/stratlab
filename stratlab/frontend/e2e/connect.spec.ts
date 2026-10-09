import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Settings -> Connected accounts: the statement inbox (address, filter steps, statement password, last received, upload by
// hand), Zerodha (closed to users until Zerodha approves the app; open to the owner), US stocks through Interactive Brokers,
// and the EPF / NPS / AIS uploads. Statements here are made-up files in e2e/fixtures. Each run signs in as its own new user.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SHOTS = process.env.E2E_SHOTS;
const HERE = path.dirname(fileURLToPath(import.meta.url));
const NSDL = path.join(HERE, "fixtures", "synthetic-nsdl-statement.pdf");
const EPF = path.join(HERE, "fixtures", "synthetic-epf-passbook.pdf");
const PROVIDERS = /kite|yahoo|screener\.in|finnhub|amfi|nseindia/i;      // Zerodha, CAMS and NSDL are named where the user must recognise them
const base = { token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r" };
const who = (n: number, phone: boolean) => { const i = n + (phone ? 3 : 0); return { token: `load-${i}`, id: `u-load-${i}`, email: `load${i}@example.com` }; };
type Who = ReturnType<typeof who>;
const auth = (u: Who) => ({ Authorization: `Bearer ${u.token}` });

async function signIn(page: Page, request: APIRequestContext, u: Who, path: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("dialog", (d) => { errors.push(`a browser dialog opened: ${d.message()}`); void d.dismiss(); });
  await request.put(`${API}/me/prefs`, { headers: auth(u), data: { level: "some", focus: "both" } });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  const session = { ...base, access_token: u.token, user: { id: u.id, aud: "authenticated", email: u.email, role: "authenticated",
    app_metadata: { provider: "google" }, user_metadata: { full_name: "Asha Rao" } } };
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  return errors;
}

async function sane(page: Page, errors: string[], phone: boolean) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, PROVIDERS]) expect(text).not.toMatch(bad);
  if (!phone) return;
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main a, main select, main input:not([type=checkbox])")).filter((el) => {
    const b = el.getBoundingClientRect();
    return b.width && b.height && !el.closest("p, li, .info-btn, .k-label-row, .k-linkcard, [aria-hidden=true]") && !el.matches(".info-btn") && getComputedStyle(el).display !== "inline" && b.height < 32;
  }).map((el) => `${el.tagName} "${(el.textContent || "").trim().slice(0, 30)}"`));
  expect(small, "controls too small to tap").toEqual([]);
}

const shot = async (page: Page, name: string, phone: boolean, dark: boolean) => {
  if (!SHOTS) return;
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${SHOTS}/${name}-${phone ? "400" : "1300"}-${dark ? "dark" : "light"}.png`, fullPage: true });
};

test("statement inbox: an address, the filter steps, a password, and a statement read from an upload", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const u = who(291, phone);
  const errors = await signIn(page, request, u, "/settings#accounts");
  const main = page.locator("main");
  const inbox = main.locator("#inbox");
  await expect(inbox.getByRole("heading", { name: "Statement inbox" })).toBeVisible({ timeout: 30_000 });
  await expect(inbox.getByRole("button", { name: "Set up my inbox" })).toBeVisible();
  await shot(page, "connected-inbox-before", phone, !phone);

  await inbox.getByRole("button", { name: "Set up my inbox" }).click();
  const address = inbox.getByTestId("inbox-address");
  await expect(address).toHaveText(/^u-[a-z2-7]{20}@in\.example\.test$/);
  await expect(inbox.getByRole("button", { name: "Copy" })).toBeVisible();
  await expect(inbox.getByTestId("inbox-last")).toContainText("Nothing yet");

  await inbox.getByText("Set up the filter, once").click();
  await expect(inbox.getByTestId("inbox-steps")).toContainText("Forwarding and POP/IMAP");
  await expect(inbox.getByTestId("inbox-steps")).toContainText("Outlook");

  // a password is kept, and shown only as "saved"
  await inbox.getByLabel("Your statement password", { exact: true }).fill("ABCDE1234F");
  await inbox.getByRole("button", { name: "Set your statement password" }).click();
  await expect(inbox.getByText("Password saved", { exact: true })).toBeVisible();
  await expect(inbox).not.toContainText("ABCDE1234F");
  const raw = await (await request.get(`${API}/connect`, { headers: auth(u) })).text();
  expect(raw).not.toContain("ABCDE1234F");

  // the manual upload reads the same way as an email
  await inbox.getByLabel("Statement PDF").setInputFiles(NSDL);
  await expect(inbox.getByTestId("inbox-last")).toContainText("Read and saved", { timeout: 30_000 });
  const held = await (await request.get(`${API}/holdings`, { headers: auth(u) })).json();
  expect(held.rows.map((r: { symbol: string }) => r.symbol).sort()).toEqual(["INFY", "ITC"]);

  await sane(page, errors, phone);
  await shot(page, "connected-inbox", phone, !phone);

  // turning it off deletes the address and the password
  await inbox.getByRole("button", { name: "Turn off the inbox" }).click();
  await page.getByRole("button", { name: "Turn it off" }).click();
  await expect(inbox.getByRole("button", { name: "Set up my inbox" })).toBeVisible();
  const after = await (await request.get(`${API}/connect`, { headers: auth(u) })).json();
  expect(after.inbox).toMatchObject({ address: null, has_password: false });
});

test("US stocks: a bad token says why, a good one reads positions, disconnecting deletes it; Zerodha is not open yet", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  const u = who(295, phone);
  const errors = await signIn(page, request, u, "/settings#accounts");
  const main = page.locator("main");
  await expect(main.locator("#zerodha")).toContainText("Not open yet", { timeout: 30_000 });
  await expect(main.locator("#zerodha").getByRole("button", { name: "Connect Zerodha" })).toHaveCount(0);

  const card = main.locator("#ibkr");
  await card.getByLabel("Flex token").fill("bad-token-0000000000");
  await card.getByLabel("Query id").fill("123456");
  await card.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByText("doesn't recognise that token")).toBeVisible({ timeout: 30_000 });
  await card.getByLabel("Flex token").fill("good-token-1234567890");
  await card.getByRole("button", { name: "Connect" }).click();
  await expect(card.getByTestId("ibkr-line")).toContainText("US positions", { timeout: 30_000 });
  await expect(card.getByText("Connected", { exact: true })).toBeVisible();
  const view = await (await request.get(`${API}/connect`, { headers: auth(u) })).text();
  expect(view).not.toContain("good-token-1234567890");
  await sane(page, errors, phone);
  await shot(page, "connected-ibkr", phone, !phone);

  await card.getByRole("button", { name: "Disconnect" }).click();
  await page.getByRole("button", { name: "Disconnect" }).last().click();
  await expect(card.getByLabel("Flex token")).toBeVisible();
  expect((await (await request.get(`${API}/connect`, { headers: auth(u) })).json()).ibkr.connected).toBe(false);
});

test("Zerodha is open to the owner: log in, read holdings, refresh; and an EPF passbook is read, checked and saved", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  if (!phone) await page.emulateMedia({ colorScheme: "dark" });
  // an admin account (the server lets load293 and load296 in as admins): Zerodha is open to the owner before approval
  const OWNER = who(293, phone);
  const a = await (await request.get(`${API}/connect/kite/login`, { headers: auth(OWNER) })).json();
  const state = decodeURIComponent(a.url.split("redirect_params=")[1]).split("state=")[1];
  const back = await request.get(`${API}/connect/kite/callback`, { params: { request_token: "t", status: "success", state }, maxRedirects: 0 });
  expect(back.status()).toBe(303);
  expect(back.headers()["location"]).toContain("kite=ok");
  const errors = await signIn(page, request, OWNER, "/settings#accounts");
  const main = page.locator("main");
  const z = main.locator("#zerodha");
  await expect(z.getByTestId("kite-line")).toHaveText(/^Connected · last read today \d\d:\d\d IST/, { timeout: 30_000 });
  await z.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByText("Read 1 holdings.")).toBeVisible();
  await sane(page, errors, phone);
  await shot(page, "connected-zerodha", phone, !phone);
  await z.getByRole("button", { name: "Disconnect" }).click();
  await expect(z.getByRole("button", { name: "Connect Zerodha" })).toBeVisible();

  // EPF: the figures found are shown to be checked, nothing is saved until then
  const docs = main.locator("#docs");
  await docs.getByLabel("EPF passbook file").setInputFiles(EPF);
  await expect(docs.getByLabel(/^Your EPF balance/)).toHaveValue("270000", { timeout: 30_000 });
  expect((await (await request.get(`${API}/money/networth`, { headers: auth(OWNER) })).json()).assets?.some?.((x: { kind: string }) => x.kind === "epf") ?? false).toBe(false);
  await shot(page, "connected-docs", phone, !phone);
  await docs.getByRole("button", { name: "Save these figures" }).click();
  await expect(docs.getByTestId("doc-epf")).toContainText("Saved as of", { timeout: 30_000 });
  await sane(page, errors, phone);
});
