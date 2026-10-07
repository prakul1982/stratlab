import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { ALL_PAGES } from "../src/lib/nav";

// Every page of the menu, opened as the site owner against the fake world: nothing may log a console error, reject a
// promise nobody handles, or get a 500 from the server, and every link drawn on it must open a page (not the home page
// the catch-all route falls back to).
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };

const main = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const patterns = [...main.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((r) => r !== "*")
  .map((r) => new RegExp("^" + r.replace(/\/\*/g, "(/.*)?").replace(/:[A-Za-z]+/g, "[^/]+") + "/?$"));
const OUTSIDE = ["/terms", "/privacy", "/refunds", "/contact"];
const opens = (p: string) => OUTSIDE.includes(p) || patterns.some((r) => r.test(p));

const EXTRA = ["/", "/mine", "/features", "/plans", "/account", "/settings", "/research/IN/RELIANCE", "/research/US/AAPL", "/research/IN/RELIANCE/deep",
  "/old-page-that-never-existed"];
const PATHS = [...new Set([...ALL_PAGES.map((l) => l.page.to), ...EXTRA])];

async function visit(page: Page, path: string) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`uncaught: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) problems.push(`console: ${m.text().slice(0, 200)}`); });
  page.on("response", (r) => { if (r.status() >= 500) problems.push(`${r.status()} ${new URL(r.url()).pathname}`); });
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  await page.goto(path);
  const ask = page.getByText("What brings you here?");
  await ask.waitFor({ timeout: 3000 }).then(() => page.getByRole("dialog").getByRole("button", { name: /All of it/ }).first().click()).catch(() => undefined);
  await expect(page.locator("main")).toBeVisible({ timeout: 30_000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(500);
  return problems;
}

for (const path of PATHS) {
  test(`${path}: no console errors, no 500s, no dead links`, async ({ page }) => {
    const problems = await visit(page, path);
    const hrefs = await page.evaluate(() => [...new Set(Array.from(document.querySelectorAll("a[href^='/']")).map((a) => (a as HTMLAnchorElement).getAttribute("href") || ""))]);
    const dead = hrefs.map((h) => h.split(/[?#]/)[0]).filter((h) => h && h !== "/" && !/^\/(api|assets|v|c|stocks|sitemaps?)(\/|$)/.test(h) && !opens(h));
    expect(problems, "errors while the page loaded").toEqual([]);
    expect(dead, "links that open no page").toEqual([]);
  });
}
