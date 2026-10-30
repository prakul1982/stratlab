import { expect, type APIRequestContext, type Page } from "@playwright/test";

// The helpers a11y.spec.ts and a11y-axe.spec.ts share (split so the axe passes, six of the file's ten minutes, run on a shard of
// their own: Playwright shards by file).

export const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

export async function open(page: Page, path: string, { tour = true, as = false } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript(([s, seen, own]) => {
    if (!own) localStorage.setItem("sb-demo-auth-token", JSON.stringify(s));
    if (seen) localStorage.setItem("stratlab.tour.v1", "1"); else localStorage.removeItem("stratlab.tour.v1");
  }, [session, tour, as] as const);
  await page.goto(path);
  await page.getByText("What brings you here?").waitFor({ timeout: 4000 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.locator("main")).toBeVisible();
  return errors;
}

/** What has focus, and whether it is inside `sel`. */
export const focusIn = (page: Page, sel: string) => page.evaluate((s) => !!document.activeElement?.closest(s), sel);

/** Tab `n` times (Shift+Tab for the second half) and say whether focus ever left `sel`. */
export async function staysIn(page: Page, sel: string, n = 24) {
  for (let i = 0; i < n; i++) {
    await page.keyboard.press(i < n / 2 ? "Tab" : "Shift+Tab");
    if (!(await focusIn(page, sel))) return false;
  }
  return true;
}

export const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
export const admin = { Authorization: "Bearer admin-token" };
export const PAGES = ["/mine", "/trade", "/invest", "/money", "/holdings", "/money/net-worth", "/research/IN/RELIANCE", "/research/screens", "/library",
  "/notebooks", "/options", "/paper", "/trade/positioning", "/alerts", "/settings", "/new", "/admin/emails", "/invest/ipos", "/money/mutual-funds",
  "/tax-report", "/money/us-tax", "/account"];
/** A notebook with one finished experiment, made for this run (the pages of a notebook and of an experiment); the caller deletes it. */
export async function ownNotebook(request: APIRequestContext, name: string) {
  const ema = { name: "Axe check", tf: "1d", entry: [{ l: { t: "ema", p: 10 }, op: "xa", r: { t: "ema", p: 30 } }],
    exit: [{ l: { t: "ema", p: 10 }, op: "xb", r: { t: "ema", p: 30 } }], risk: { capital: 10000, riskPct: 2, sl: 4, tgt: 0, brokerage: 0, slippage: 0.05 } };
  const nb = await (await request.post(`${API}/notebooks`, { headers: admin, data: { name, question: "q", strategy: ema, instrument: "CRYPTO:BTC-USD" } })).json();
  await request.post(`${API}/notebooks/${nb.id}/experiments`, { headers: admin, data: { days: 800 } });
  return nb.id as string;
}
// serious and critical fail; so do two moderate ones that make a screen reader's list of landmarks and headings useless (A11Y-2: a name used twice, a skipped level)
export const ALSO = ["landmark-unique", "heading-order"];
export const serious = (r: { violations: { id: string; impact?: string | null; help: string; nodes: { target: unknown[] }[] }[] }, where: string) =>
  r.violations.filter((x) => x.impact === "serious" || x.impact === "critical" || ALSO.includes(x.id)).map((v) => `${where} ${v.id}: ${v.help} (${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(", ")})`);

// ---- A11Y-1: what axe can't see ----------------------------------------------------------------------------------------------------------------

export const viewFor = (name: string) => (name === "phone" ? { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true } : { viewport: { width: 1440, height: 900 } });

export const MY_ADS = { ADS_ENABLED: "true", ADSENSE_CLIENT: "ca-pub-1234567890123456", ADSENSE_SLOT_PUBLIC: "1111111111", ADSENSE_SLOT_AI: "2222222222" };
export const FREE = { access_token: "free-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
  user: { id: "u-free", aud: "authenticated", email: "free@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
