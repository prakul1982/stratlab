import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Your SIP and fund behaviour, on the Mutual funds page: your XIRR beside each fund's NAV return, the gap in rupees,
// the SIP record and a redemption after a fall from the high, on desktop and phone. The statement is synthetic
// (made-up investor and funds) and so is the NAV history (tests/fake_mf_history.py: a high of 24 in June 2024, the
// redemption at 20 in August). Each project signs in as its own fake Basic user.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const MF = new URL("../../backend/tests/fixtures/mf/", import.meta.url).pathname;
const ADVICE = /\b(buy|sell|accumulate|avoid|you should|we suggest|recommend|don't stop|keep investing)\b/i;
const PROVIDERS = /kite|zerodha|yahoo|screener\.in|finnhub|amfi|cams|kfintech api/i;

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, path: string, ready: string, n: number) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, sessionFor(n));
  await page.goto(path);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(path);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(400);
  return errors;
}

async function sane(page: Page, errors: string[], text: string) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(ADVICE);
  expect(text).not.toMatch(PROVIDERS);
}

async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true]")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

test("fund behaviour: your return against the fund's, the SIP record and a redemption after a fall", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = phone ? 283 : 280;                     // Basic users of the fake database, one per project
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.delete(`${API}/money/mutual-funds`, { headers: auth })).ok()).toBeTruthy();
  const raw = readFileSync(MF + "synthetic_cas.pdf").toString("base64");
  expect((await request.post(`${API}/money/mutual-funds/import`, { headers: auth, data: { filename: "cas.pdf", data: raw, password: "ABCDE1234F", mode: "replace" } })).ok()).toBeTruthy();

  const errors = await open(page, "/money/mutual-funds", "Your mutual funds, in one place", n);
  // MF-1: the totals in one card, each fund's own return, SIP record and falls folded under its row
  const card = page.getByRole("region", { name: "Costs and how you invested" });
  await expect(card.getByText("Gap in rupees, all funds")).toBeVisible({ timeout: 30_000 });
  const flexi = page.getByRole("list", { name: "Schemes" }).getByRole("listitem").filter({ hasText: "Example Flexi Cap Fund - Direct Plan - Growth" });
  await expect(flexi).toHaveCount(1);
  await flexi.locator("summary").click();
  const how = flexi.getByRole("region", { name: /^How you invested/ });
  // TABLE-SWEEP (owner, 29 Oct): the scheme's story is a table of facts (it was sentences)
  const facts = how.getByRole("table", { name: /^How you invested in Example Flexi Cap Fund/ });
  const span = facts.getByRole("row", { name: /^Compared over/ });
  await expect(span).toContainText("10 Jan 2018 to today");
  await expect(span).toContainText("NAV 10 to 25");          // beside the dates on a desktop, under the words on a phone

  // the SIP record: one instalment in Feb 2019, long since stopped
  const sip = facts.getByRole("row", { name: /^SIP record/ });
  await expect(sip).toContainText("1 month paid, 0 missed");
  await expect(sip).toContainText("Feb 2019 to Feb 2019");
  await expect(sip).toContainText("no instalment after Feb 2019");

  // sold at 20 with the high at 24: a 16.7% fall; the 300 units are ₹7,500 today against ₹6,000 received (a row of its own table now)
  const fall = how.getByRole("table", { name: /^Redemptions after a fall, Example Flexi Cap Fund/ }).getByRole("row", { name: /15 Aug 2024/ });
  await expect(fall).toContainText("16.7%");
  await expect(fall).toContainText("high 24 on 3 Jun 2024");
  await expect(fall).toContainText("₹6,000");
  await expect(fall).toContainText("₹7,500");
  await card.getByText("How this is worked out").click();
  await expect(card.getByText(/hindsight arithmetic/).first()).toBeVisible();

  if (process.env.E2E_SHOTS) {
    await page.screenshot({ path: `${process.env.E2E_SHOTS}/fund-behaviour-${info.project.name}.png`, fullPage: true });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.screenshot({ path: `${process.env.E2E_SHOTS}/fund-behaviour-${info.project.name}-dark.png`, fullPage: true });
    await page.emulateMedia({ colorScheme: "light" });
  }
  await expect(card.getByText(/not a suggestion to start, stop or change a SIP/)).toBeVisible();
  await sane(page, errors, await card.innerText());
  if (phone) await touchable(page);
});
