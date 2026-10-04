import { readFileSync } from "node:fs";
import { expect, test, type Page, type Request } from "@playwright/test";
import { cleanProps, maskPath, track } from "../src/lib/analytics";

// Usage analytics (PostHog): completely off without a key, nothing personal when on, and the CSP lets in only its host.
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const HOST = "https://us.i.posthog.com";

/** Open a page signed in, optionally with a PostHog key in config.js; returns every request the page made. */
async function open(page: Page, path: string, ready: string, key = "") {
  const requests: Request[] = [];
  page.on("request", (r) => requests.push(r));
  if (key) {
    await page.route("**/config.js", (r) => r.fulfill({ contentType: "application/javascript",
      body: `window.STRATLAB_CONFIG = {API_BASE:"${process.env.E2E_API}",SUPABASE_URL:"https://demo.supabase.co",SUPABASE_ANON_KEY:"demo",POSTHOG_KEY:"${key}"};` }));
  }
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 4000 }).then(() => page.getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.getByText(ready, { exact: false }).first()).toBeVisible({ timeout: 30_000 });
  return requests;
}

const toPostHog = (rs: Request[]) => rs.filter((r) => /posthog/i.test(r.url()));
/** The events in everything sent to PostHog so far. */
const events = (rs: Request[]) => toPostHog(rs).filter((r) => r.method() === "POST").flatMap((r) => {
  try { const b = JSON.parse(r.postData() || "null"); return Array.isArray(b) ? b : b?.batch ?? (b ? [b] : []); } catch { return []; }
}) as { event: string; properties: Record<string, unknown> }[];

test.describe("analytics wrapper", () => {
  test("only plain words and counts get through, never anything personal", () => {
    const clean = cleanProps({ region: "IN", plan: "pro", count: 3, email: "a@b.com", name: "Asha", symbol: "RELIANCE",
      amount: 125000, price: 2450.5, qty: 10, holdings: "RELIANCE,TCS", source: "someone@example.com", rows: -1, filters: 2.5, kind: "x".repeat(40) });
    expect(clean).toEqual({ region: "IN", plan: "pro", count: 3 });
    expect(cleanProps(undefined)).toEqual({});
    expect(cleanProps({ region: { nested: 1 } as unknown as string })).toEqual({});
  });

  test("addresses lose ids, tokens, queries and anything with an @", () => {
    expect(maskPath("/research/IN/RELIANCE/deep")).toBe("/research/IN/RELIANCE/deep");     // symbols are public
    expect(maskPath("/research/IN/M&M")).toBe("/research/IN/M&M");
    expect(maskPath("/n/3f2b9c1e-8a7d-4e21-9c55-0b1a2c3d4e5f/e/2")).toBe("/n/:id/e/2");
    expect(maskPath("/paper/a1b2c3d4e5f6a7b8")).toBe("/paper/:id");
    expect(maskPath("/verdict/AbC123xyz_secret")).toBe("/verdict/:token");
    expect(maskPath("/account?email=me@x.com#newsletters")).toBe("/account");
    expect(maskPath("/x/me@example.com")).toBe("/x/:hidden");
  });

  test("track never throws, even with no browser, no key or odd input", () => {
    expect(() => track("backtest run", { region: "IN" })).not.toThrow();
    expect(() => track("", null)).not.toThrow();
    expect(() => track("x", { region: undefined, count: NaN })).not.toThrow();
  });

  test("the CSP lets in the PostHog host for sending, and nothing else from it", () => {
    const vercel = JSON.parse(readFileSync(new URL("../vercel.json", import.meta.url), "utf8"));
    const csp: string = vercel.headers[0].headers.find((h: { key: string }) => h.key === "Content-Security-Policy").value;
    const netlify = readFileSync(new URL("../netlify.toml", import.meta.url), "utf8").match(/Content-Security-Policy = "([^"]+)"/)![1];
    for (const policy of [csp, netlify]) {
      const dirs = Object.fromEntries(policy.split(";").map((d) => d.trim().split(/\s+/)).map(([k, ...v]) => [k, v]));
      expect(dirs["connect-src"]).toContain(HOST);
      for (const d of ["script-src", "img-src", "frame-src", "worker-src", "default-src"]) expect(dirs[d].join(" "), d).not.toMatch(/posthog/);
      expect(policy.match(/posthog[^ ;]*/g)).toEqual(["posthog.com"]);       // one host, no wildcard
    }
    expect(csp).toBe(netlify);
  });
});

test.describe("analytics in the app", () => {
  test("with no key nothing loads and nothing is sent", async ({ page }) => {
    const rs = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
    await page.goto("/admin");
    await expect(page.getByText("Needs your attention")).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(2500);
    expect(toPostHog(rs).map((r) => r.url())).toEqual([]);
    expect(rs.filter((r) => /module\.slim|posthog/i.test(r.url())).map((r) => r.url()), "the analytics code was downloaded").toEqual([]);
    await expect(page.getByTestId("posthog-dashboard")).toHaveCount(0);
  });

  test("Do Not Track keeps it off even with a key", async ({ page }) => {
    await page.addInitScript(() => Object.defineProperty(Navigator.prototype, "doNotTrack", { get: () => "1" }));
    const rs = await open(page, "/research", "Companies", "phc_test");
    await page.waitForTimeout(3500);
    expect(rs.filter((r) => /module\.slim|posthog/i.test(r.url())).map((r) => r.url())).toEqual([]);
  });

  test("with a key: pageviews and funnel events by user id, with nothing personal", async ({ page }) => {
    // PostHog drops events from automated browsers: look like a person's browser for this test
    await page.addInitScript(() => {
      Object.defineProperty(Navigator.prototype, "webdriver", { get: () => false });
      Object.defineProperty(Navigator.prototype, "userAgentData", { get: () => undefined });
      Object.defineProperty(Navigator.prototype, "userAgent", { get: () => "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36" });
    });
    const rs = await open(page, "/research", "Companies", "phc_test");
    await page.goto("/research/IN/RELIANCE/deep?email=owner%40example.com&ref=owner@example.com");     // a query never goes out
    await expect(page.getByText("Growth and margins").first()).toBeVisible({ timeout: 30_000 });
    await expect.poll(() => events(rs).map((e) => e.event), { timeout: 20_000 }).toEqual(expect.arrayContaining(["$pageview", "deep dive opened"]));
    expect(toPostHog(rs).every((r) => r.url().startsWith(HOST + "/")), "only the PostHog host is called").toBe(true);
    const all = events(rs);
    const deep = all.find((e) => e.event === "deep dive opened")!;
    expect(deep.properties.region).toBe("IN");
    expect(all.find((e) => e.event === "$pageview" && String(e.properties.$current_url).endsWith("/research/IN/RELIANCE/deep"))).toBeTruthy();
    expect(all.some((e) => e.properties.distinct_id === "u-admin"), "identified by the internal user id").toBe(true);
    const sent = toPostHog(rs).map((r) => r.postData() || "").join("\n");
    for (const personal of ["owner@example.com", "owner%40example.com", "email="]) expect(sent).not.toContain(personal);
    expect(sent).not.toMatch(/\$snapshot|\$autocapture|\$rageclick/);
    // the owner's way in, on Admin → Overview
    await page.goto("/admin");
    await expect(page.getByTestId("posthog-dashboard")).toHaveAttribute("href", "https://us.posthog.com");
  });
});
