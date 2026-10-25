import { expect, test, type Page } from "@playwright/test";

// IPOs (Invest → IPOs): India's and the US's issues in the fake world (tests/fake_ipo.py seed: the real exchange pages' terms and bids
// and two real offer documents' facts, dated around today). The lists and their tabs per market, an open issue's bids, an issue's
// page with the facts read from its offer document and its summary, the alert setting, and what a Free account sees locked.
// Each project signs in as its own Basic (and its own Free) account.
const API = process.env.E2E_API ?? "http://127.0.0.1:8765";
const SHOTS = process.env.IPO_SHOTS ?? "/tmp/claude-0/-home-user-stratlab/336f6e68-98b8-5cb9-ae6f-089a8eabd8fc/scratchpad/feat-ipos";

function sessionFor(n: number) {
  return { access_token: `load-${n}`, token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400, refresh_token: "r",
    user: { id: `u-load-${n}`, aud: "authenticated", email: `load${n}@example.com`, role: "authenticated", app_metadata: {}, user_metadata: {} } };
}

async function open(page: Page, where: string, ready: string, who: ReturnType<typeof sessionFor>) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, who);
  await page.goto(where);
  const welcome = page.getByRole("dialog", { name: "What brings you here?" });
  const answered = await welcome.waitFor({ timeout: 4000 }).then(async () => {
    await welcome.getByRole("button", { name: /^All of it/ }).click();
    await expect(welcome).toHaveCount(0);
    return true;
  }).catch(() => false);
  if (answered) await page.goto(where);
  await expect(page.getByText(ready, { exact: false }).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  return errors;
}

async function sane(page: Page, errors: string[]) {
  expect(errors, "uncaught errors in the page").toEqual([]);
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  const text = await page.locator("main").innerText();
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\[object Object\]/, /\bInfinity\b/, /nseindia|yahoo|finnhub|screener\.in|kite connect|nasdaq\.com|edgar/i]) expect(text, `"${bad}" on the page`).not.toMatch(bad);
  expect(text).not.toMatch(/\b(you should|buy|sell|accumulate|avoid|grey market|gmp)\b/i);
}

async function touchable(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("main button, main select, main a, main [role=button], main input:not([type=range]):not([type=checkbox]):not([type=radio])"))
    .filter((el) => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || el.closest("p, li, td, th, dd, .info-btn, .chip-x, .search-box, .nb-name, [aria-hidden=true], .k-sub-line")) return false;
      if (el.matches(".info-btn, .chip-x") || getComputedStyle(el).display === "inline") return false;
      return b.height < 32;
    }).map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || (el as HTMLInputElement).placeholder || "").trim().slice(0, 30)}" ${Math.round(el.getBoundingClientRect().height)}px`));
  expect(small, "controls too small to tap").toEqual([]);
}

const basic = (phone: boolean) => (phone ? 106 : 103);        // Basic accounts in the fake world
const free = (phone: boolean) => (phone ? 123 : 105);         // Free accounts

test("IPO lists: every stage in India, the US without an Open tab, the open issue's bids, and the alert setting", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const n = basic(phone);
  const auth = { Authorization: `Bearer load-${n}` };
  expect((await request.put(`${API}/invest/ipos/alerts`, { headers: auth, data: { on: false, events: ["open", "close", "allotment", "listing"], markets: ["IN"], sme: false } })).ok()).toBeTruthy();

  const errors = await open(page, "/invest/ipos", "Open 1", sessionFor(n));
  await expect(page.getByRole("heading", { name: "IPOs", level: 1 })).toBeVisible();
  const stage = page.getByRole("radiogroup", { name: "Stage" });
  await expect(stage.getByRole("radio")).toHaveCount(4);
  await expect(stage.getByRole("radio", { name: /^Open 1$/ })).toBeChecked();             // the open tab first when an issue is open
  await expect(page.getByTestId("ipo-tab-line")).toContainText("Bidding on the last day ends at 5 PM IST");
  const open1 = page.locator("tr[data-ipo=in-bonfig], [data-ipo=in-bonfig]").filter({ visible: true }).first();
  await expect(open1).toContainText("Bonfiglioli Transmissions Limited");
  await expect(open1).toContainText("₹558 to ₹586");
  await expect(open1).toContainText("25 shares");
  await expect(open1).toContainText("₹14,650");                                             // the lot at the top of the band
  await expect(open1).toContainText("46.06 times");                                         // the bids so far, both exchanges together
  await expect(page.locator(".k-badge.live").filter({ hasText: "Live" }).first()).toBeVisible();
  if (phone) await touchable(page);

  await stage.getByRole("radio", { name: /^Upcoming/ }).click();
  const mk = page.locator("[data-ipo=in-mksons]").filter({ visible: true }).first();
  await expect(mk).toContainText("₹153 to ₹162");
  await expect(mk).toContainText("91 shares");
  await expect(mk).toContainText("(expected)");                                              // listing by SEBI's timetable, said so
  await expect(page.locator("[data-ipo=in-bse-4907]").filter({ visible: true }).first()).toContainText("SME platform");
  await page.getByTestId("ipo-filed").locator("summary").click();
  await expect(page.getByTestId("ipo-filed").getByText("Hunger Pangs Limited").first()).toBeVisible();
  await expect(page.getByTestId("ipo-filed")).toContainText("DRHP");

  // a Social Stock Exchange fund raise is not an IPO: in its own fold with the exchange's note off its name, never in the Closed tab
  await page.getByTestId("ipo-social").locator("summary").click();
  await expect(page.getByTestId("ipo-social").getByText("Rays of Belief Limited").first()).toBeVisible();
  await expect(page.getByTestId("ipo-social")).not.toContainText("FPSE");
  await page.getByTestId("ipo-withdrawn").locator("summary").click();
  await expect(page.getByTestId("ipo-withdrawn").locator("[data-ipo=in-zenith]").filter({ visible: true }).first()).toContainText("Withdrawn");
  await expect(page.getByTestId("ipo-withdrawn").locator("[data-ipo=in-orbit]").filter({ visible: true }).first()).toContainText("Postponed");

  await stage.getByRole("radio", { name: /^Closed/ }).click();
  const core = page.locator("[data-ipo=in-bse-4902]").filter({ visible: true }).first();
  await expect(core).toContainText("Core4 Engineers Limited");
  await expect(core).toContainText("SME platform");

  await stage.getByRole("radio", { name: /^(Recently listed|Listed)/ }).click();
  const tonbo = page.locator("[data-ipo=in-tonbo]").filter({ visible: true }).first();
  await expect(tonbo).toContainText("₹700");                                                 // the issue price
  await expect(tonbo).toContainText("₹1,160");                                               // the listing price
  await expect(tonbo).toContainText(/\+65\.7%/);
  await expect(tonbo).toContainText(/\+62\.1%/);
  await expect(page.locator("[data-ipo=in-zetwerk]").filter({ visible: true }).first()).toContainText(/(−|-)8\.4%/);
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/ipos-india-${info.project.name}.png`, fullPage: true });

  // the US: no Open tab, what is expected, priced and listed
  await page.getByRole("radiogroup", { name: "Market" }).getByRole("radio", { name: "US" }).click();
  await expect(stage.getByRole("radio")).toHaveCount(3);
  await expect(stage.getByRole("radio", { name: /^Open/ })).toHaveCount(0);
  await expect(page.getByTestId("ipo-us-note")).toContainText("no public bidding window");
  await expect(page.locator("[data-ipo=us-1100000-1]").filter({ visible: true }).first()).toContainText("$14.00 to $16.00");      // the first tab with issues
  await stage.getByRole("radio", { name: /^(Recently listed|Listed)/ }).click();
  await expect(page.locator("[data-ipo=us-1273626-119431]").filter({ visible: true }).first()).toContainText("$19.50");
  await stage.getByRole("radio", { name: /^Priced/ }).click();
  await expect(page.locator("[data-ipo=us-1403574-119467]").filter({ visible: true }).first()).toContainText("City Therapeutics");
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/ipos-us-${info.project.name}.png`, fullPage: true });

  // alerts: Basic can turn them on; the choice is kept
  await page.getByRole("radiogroup", { name: "Market" }).getByRole("radio", { name: "India" }).click();
  const alerts = page.getByTestId("ipo-alerts");
  const on = alerts.getByRole("checkbox", { name: /Message me when an IPO/ });
  await expect(on).not.toBeChecked();
  const saved = page.waitForResponse((r) => r.url().endsWith("/invest/ipos/alerts") && r.request().method() === "PUT");
  await on.click();
  expect((await saved).ok()).toBeTruthy();
  await expect(on).toBeChecked();
  const chip = alerts.getByRole("group", { name: "Which events" }).getByRole("button", { name: "Allotment" });
  await expect(chip).toHaveAttribute("aria-pressed", "true");
  const saved2 = page.waitForResponse((r) => r.url().endsWith("/invest/ipos/alerts") && r.request().method() === "PUT");
  await chip.click();
  expect((await saved2).ok()).toBeTruthy();
  await expect(chip).toHaveAttribute("aria-pressed", "false");
  const back = await (await request.get(`${API}/invest/ipos/alerts`, { headers: auth })).json();
  expect(back).toMatchObject({ on: true, events: ["open", "close", "listing"], markets: ["IN"], allowed: true });
  await sane(page, errors);
});

test("An IPO's page: terms, bids, the offer document's facts and its summary (Basic), documents", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors = await open(page, "/invest/ipos/in-bonfig", "Bids received", sessionFor(basic(phone)));
  await expect(page.getByRole("heading", { name: "Bonfiglioli Transmissions Limited", level: 1 })).toBeVisible();
  await expect(page.getByText("Open for bidding").first()).toBeVisible();
  const terms = page.getByTestId("ipo-terms");
  await expect(terms).toContainText("₹558 to ₹586");
  await expect(terms).toContainText("25 shares");
  await expect(terms).toContainText("minimum ₹14,650");
  await expect(terms).toContainText("4,32,39,042 shares");                                        // the offer for sale, in Indian grouping
  await expect(terms).toContainText("Industrial Products");
  await expect(page.getByTestId("ipo-dates")).toContainText("5 PM IST");
  const bids = page.getByTestId("ipo-bids");
  await expect(bids).toContainText("Qualified institutional buyers");
  await expect(bids).toContainText("Non-institutional, bids over ₹10 lakh");
  await expect(bids).toContainText("Retail individual investors");
  await expect(bids).toContainText("46.06 times");
  await expect(bids.locator(".k-badge.live")).toBeVisible();

  const facts = page.getByTestId("ipo-facts");
  await expect(facts.getByTestId("ipo-promoters")).toContainText("Sonia Bonfiglioli, Luciano Bonfiglioli");
  await expect(facts.getByTestId("ipo-selling")).toContainText("Bonfiglioli S.p.A. (promoter)");
  await expect(facts.getByTestId("ipo-objects")).toContainText("The objects of the Offer are to");
  await expect(facts.getByTestId("ipo-objects")).toContainText("Page 111 of the PDF");
  await expect(facts).toContainText("Dec 2025");
  await expect(facts).toContainText("Revenue from operations");
  await expect(facts).toContainText("₹2,014 cr");                                                // 2,013.53 crore
  await expect(facts).toContainText("Page 72 of the PDF");

  const sum = page.getByTestId("ipo-summary");
  await expect(sum.getByTestId("ipo-sum-promoters")).toContainText("The promoters are Sonia Bonfiglioli");
  await sum.getByTestId("ipo-sum-promoters").locator("summary").click();
  await expect(sum.getByTestId("ipo-sum-promoters")).toContainText("OUR PROMOTERS: SONIA BONFIGLIOLI");      // the words of the document under each statement
  await expect(sum.getByTestId("ipo-sum-objects")).toContainText("carry out the offer for sale");

  const docs = page.getByTestId("ipo-docs");
  const sebi = docs.getByRole("link", { name: /Red herring prospectus \(RHP\)/ }).first();
  await expect(sebi).toHaveAttribute("href", /^https:\/\/(www\.sebi\.gov\.in|nsearchives\.nseindia\.com)\//);
  await expect(docs).toContainText("SEBI");
  await sane(page, errors);
  if (phone) await touchable(page);
  await page.screenshot({ path: `${SHOTS}/ipo-detail-india-${info.project.name}.png`, fullPage: true });

  // a US listing: the facts from the prospectus and how it has traded since
  await page.goto("/invest/ipos/us-1273626-119431");
  await expect(page.getByRole("heading", { name: "Iambic Therapeutics, Inc.", level: 1 })).toBeVisible();
  const since = page.getByTestId("ipo-listing");
  await expect(since).toContainText("$16.00");
  await expect(since).toContainText("$19.50");
  await expect(since).toContainText(/\+21\.9%/);
  await expect(since.getByRole("link", { name: /company page/ })).toHaveAttribute("href", "/research/US/IAM");
  await expect(page.getByTestId("ipo-proceeds")).toContainText("We estimate that the net proceeds");
  await expect(page.getByTestId("ipo-facts")).toContainText("9,375,000");
  await expect(page.getByTestId("ipo-docs").getByRole("link", { name: /Final prospectus \(424B4\)/ })).toHaveAttribute("href", /^https:\/\/www\.sec\.gov\//);
  await expect(page.getByTestId("ipo-summary")).toContainText("isn't written yet");                    // written by the job, or on request
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/ipo-detail-us-${info.project.name}.png`, fullPage: true });
});

test("A Free account sees the lists and the facts, and the summary and the alerts locked on the Basic plan", async ({ page, request }, info) => {
  const phone = info.project.name === "phone";
  const who = sessionFor(free(phone));
  const errors = await open(page, "/invest/ipos", "Open 1", who);
  const alerts = page.getByTestId("ipo-alerts");
  await expect(alerts.locator(".plan-note")).toContainText("IPO alerts are on the Basic plan");
  await expect(page.locator(".plan-note")).toHaveCount(1);                                                                    // one lock note on the page: the card's own
  await expect(page.locator(".page-lock")).toHaveCount(0);
  await expect(alerts.getByRole("checkbox", { name: /Message me/ })).toHaveCount(0);
  await expect(page.locator("[data-ipo=in-bonfig]").filter({ visible: true }).first()).toContainText("46.06 times");        // the bids are free
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/ipos-free-${info.project.name}.png`, fullPage: true });

  expect((await request.put(`${API}/invest/ipos/alerts`, { headers: { Authorization: `Bearer load-${free(phone)}` }, data: { on: true, events: ["open"], markets: ["IN"], sme: false } })).status()).toBe(402);

  await page.goto("/invest/ipos/in-bonfig");
  await expect(page.getByTestId("ipo-facts").getByTestId("ipo-promoters")).toContainText("Sonia Bonfiglioli");               // facts and bids stay free
  await expect(page.getByTestId("ipo-bids")).toContainText("46.06 times");
  const sum = page.getByTestId("ipo-summary");
  await expect(sum).toContainText("The summary of the offer document is on the Basic plan");
  await expect(page.getByTestId("locked-preview")).toContainText("The risk factors the document puts first");
  await expect(sum.getByTestId("ipo-sum-promoters")).toHaveCount(0);
  await expect(page.locator(".page-lock")).toHaveCount(0);                                                                    // one lock note on the page, not two
  await sane(page, errors);
  await page.screenshot({ path: `${SHOTS}/ipo-detail-free-${info.project.name}.png`, fullPage: true });
});
