import { expect, test, type Page } from "@playwright/test";

// The AI assistant page (/assistant): make a key (shown once, with the setup steps filled in), use it against the MCP endpoint,
// see the call in the log, revoke it and see the endpoint refuse it, on desktop and phone (dark mode on the phone).
// Each project signs in as its own fake Pro user.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const ADVICE = /\b(buy|sell|hold|accumulate|avoid|cheap|expensive|overpriced|underpriced|overvalued|undervalued|recommend\w*)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|amfi|nseindia/i;
const SHOTS = process.env.E2E_SHOTS;

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, n: number) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto("/assistant");
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto("/assistant");
  const card = page.locator("main");
  await expect(card.getByRole("heading", { level: 1, name: "AI assistant" })).toBeVisible({ timeout: 30_000 });
  await expect(card.getByLabel("Name of the assistant")).toBeVisible({ timeout: 30_000 });
  return { errors, card };
}

const mcp = (page: Page, token: string, method: string, params: object = {}) => page.request.post(`${API}/mcp`, {
  headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "application/json, text/event-stream",
    "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method, ...(method === "tools/call" ? { "Mcp-Name": (params as { name: string }).name } : {}) },
  data: { jsonrpc: "2.0", id: 1, method, params: { ...params, _meta: { "io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {} } } },
});

test("AI assistant: make a key, use it, see the log, revoke it", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  if (phone) await page.emulateMedia({ colorScheme: "dark" });
  const { errors, card } = await open(page, phone ? 296 : 293);
  await expect(card).toContainText("No key can place a real order");
  await expect(card).toContainText("Facts only, not advice");

  await card.getByLabel("Name of the assistant").fill("Claude test");
  await card.getByRole("checkbox").check();
  await card.getByRole("button", { name: "Make a key" }).click();
  const fresh = card.locator(".k-callout");
  const shown = fresh.getByLabel("Key", { exact: true });
  await expect(shown).toContainText(/^slm_[A-Za-z0-9_-]{40,}$/);
  const token = (await shown.innerText()).trim();
  await expect(card).toContainText("can't show it again");
  // the setup steps carry the endpoint and the new key
  await expect(fresh.getByLabel("Command")).toContainText(`--header "Authorization: Bearer ${token}"`);
  await expect(fresh.getByLabel("Command")).toContainText("/mcp");
  await expect(card.getByText("Claude test").first()).toBeVisible();
  await expect(card.getByText("Paper orders", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/assistant$/);

  // nothing on the card reads as advice or names a data source; nothing scrolls sideways, even with the code blocks open
  const text = await card.innerText();
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  if (phone) {     // dark mode: the code blocks keep a dark panel with light text
    const [bg, fg] = await card.locator("pre").first().evaluate((el) => [getComputedStyle(el).backgroundColor, getComputedStyle(el).color]);
    const lum = (c: string) => { const [r, g, b] = (c.match(/\d+/g) ?? ["0", "0", "0"]).map(Number); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    expect(lum(bg)).toBeLessThan(lum(fg));
  }

  if (SHOTS) await card.screenshot({ path: `${SHOTS}/assistant-new-key-${info.project.name}.png` });
  // the key works against the endpoint, and the call shows in the log
  const list = await mcp(page, token, "tools/list");
  expect(list.status()).toBe(200);
  expect((await list.json()).result.tools.map((t: { name: string }) => t.name)).toContain("place_paper_order");
  const r = await mcp(page, token, "tools/call", { name: "get_watchlist", arguments: {} });
  expect((await r.json()).result.isError).toBe(false);
  await card.getByRole("button", { name: "Done" }).click();
  await page.reload();
  await expect(card.getByText("get_watchlist").first()).toBeVisible({ timeout: 30_000 });
  await expect(card).not.toContainText(token);                 // never shown again

  // revoke: the endpoint refuses the key at once, and it folds under Revoked keys
  await card.getByRole("button", { name: "Revoke" }).first().click();
  const ask = page.getByRole("dialog", { name: /^Revoke "Claude test"\?$/ });
  await expect(ask).toContainText("stops reaching StratLab at once");
  await ask.getByRole("button", { name: "Revoke key" }).click();
  await expect(card.getByText(/Revoked keys/)).toBeVisible();
  expect((await mcp(page, token, "tools/list")).status()).toBe(401);
  if (SHOTS) await card.screenshot({ path: `${SHOTS}/assistant-${info.project.name}.png` });
  expect(errors, "uncaught errors in the page").toEqual([]);
});
