import { expect, test } from "@playwright/test";
import { sessionAs, open, sane, touchable, seeUnfolded, barsAroundZero, API, settle, answerLevel, watchSharing, sharedLink } from "./pages-kit";

// The company pages, the deep dive, the public company pages, fact cards, screens, deals, surveillance flags and corporate
// actions, drawn against the fake world.

test("results calendar: every company's dates, and the company page links to it", async ({ page }, info) => {
  await sane(page, await open(page, "/research/results?region=IN&scope=all", "Board meetings companies have called"));
  // results days earlier this week sit folded in their week
  await seeUnfolded(page, page.getByRole("link", { name: "RELIANCE" }).first());
  await expect(page.getByText("Financial Results").first()).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await expect(page.getByRole("link", { name: "RELIANCE" }).first()).toHaveAttribute("href", "/research/IN/RELIANCE");
  await page.goto("/research/IN/RELIANCE");
  await expect(page.getByRole("link", { name: /^Results on / })).toBeVisible({ timeout: 30_000 });
});

test("losses hang below the zero line, with exact labels (company page)", async ({ page }) => {
  const errors = await open(page, "/research/IN/ORIONPOLY", "Sales and profit, by year");
  await barsAroundZero(page);
  // Orion Polymers, the demo world's made-up loss case, at its own scale: a ₹1,250 crore loss in FY22 (tests/fake_fundamentals.py)
  await expect(page.getByText("−1,250").first()).toBeVisible();      // the real minus, never a hyphen
  await expect(page.getByText("loss years in between, so no yearly rate").first()).toBeVisible();
  await sane(page, errors);
});

test("losses hang below the zero line (deep dive)", async ({ page }) => {
  const errors = await open(page, "/research/IN/ORIONPOLY/deep", "Growth and margins");
  await barsAroundZero(page);
  await expect(page.getByText("A loss year in the period, so no yearly rate").first()).toBeVisible();
  await sane(page, errors);
});

test("the company AI read shows plain numbers, never 0-100 scores", async ({ page }) => {
  // an old stored read can still carry scores: the page must draw the fact rows and none of the scores
  const read = {
    summary: "Runs refineries, a telecom network and retail stores.", valuation_note: "P/E 24 against 20-28 over five years.",
    scores: { moat: 92, growth: 94, momentum: 81, health: 38 }, composite: 77,
    facts: [
      { id: "growth", label: "Growth", items: [{ label: "Sales, 3 years", text: "11.6% a year" }, { label: "Net profit, 5 years", text: "15.3% a year" }] },
      { id: "price", label: "Price trend", items: [{ label: "Price vs 200-day average", text: "1.5% below" }, { label: "Stage (150-day average)", text: "Stage 3 (topping)" }] },
      { id: "debt", label: "Debt and cash", items: [{ label: "Debt to equity", text: "0.44" }, { label: "Interest cover", text: "6.1x" }] },
      { id: "margins", label: "Margins and returns", items: [{ label: "Operating margin, 5 years", text: "17% → 16% → 18% (Mar 2023 to Mar 2025)" }, { label: "ROCE", text: "9.7%" }] },
    ],
    bull: ["Jio has 470 million users."], bear: ["Refining margins move with crude."], segments: [], position: "", watch: [], ideas: [],
    generated_at: Date.now() / 1000,
  };
  await page.route("**/research/company/IN/RELIANCE/ai*", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(read) }));
  const errors = await open(page, "/research/IN/RELIANCE", "The numbers");
  const ai = page.locator(".ai-read");
  for (const t of ["Growth", "Price trend", "Debt and cash", "Margins and returns", "11.6% a year", "1.5% below", "6.1x", "ROCE"])
    await expect(ai.getByText(t, { exact: false }).first()).toBeVisible();
  const text = await ai.innerText();
  expect(text).not.toMatch(/\b(moat|momentum|health|score)\b/i);
  for (const n of ["92", "94", "81", "38", "77"]) expect(text).not.toMatch(new RegExp(`(^|\\s)${n}(\\s|$)`));
  expect(await ai.locator(".score-track").count()).toBe(0);
  // deals: "Bought" and "Sold" in one neutral style, words only
  const sides = page.locator(".deals-table .badge");
  const looks = new Set(await sides.evaluateAll((els) => els.map((e) => `${getComputedStyle(e).backgroundColor}|${getComputedStyle(e).color}`)));
  expect(looks.size).toBeLessThanOrEqual(1);
  await sane(page, errors);
});

test("a US deep dive is in dollars, from the SEC's filings", async ({ page }) => {
  const errors = await open(page, "/research/US/AAPL/deep", "Growth and margins");
  await expect(page.getByText("$ billion").first()).toBeVisible();          // a company this size reads in billions
  expect(await page.locator("main").innerText()).not.toMatch(/\d{3},\d{3} million/);
  await expect(page.getByText("Read the annual report and releases")).toBeVisible();
  await expect(page.getByText("Check past releases")).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/₹|crore/);
  await sane(page, errors);
});

// Public company pages are plain HTML from the API (the site's host forwards /stocks/* there), for search engines.
for (const [path, name, symbol] of [["/stocks/in/RELIANCE", "Reliance Industries", "RELIANCE"], ["/stocks/us/AAPL", "Apple Inc.", "AAPL"]]) {
  test(`public company page ${path}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(API + path);
    await expect(page.locator("h1")).toContainText(name);
    await expect(page.getByRole("link", { name: `Test a strategy on ${symbol}` })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open the full deep dive" })).toBeVisible();
    await expect(page.getByText(/As of \d+ \w+ \d{4}/).first()).toBeVisible();
    expect(errors).toEqual([]);
    const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
    expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
    expect(await page.locator("main").innerText()).not.toMatch(/\bNaN\b|\bundefined\b|\bnull\b|Infinity/);
    if (info.project.name === "phone") await touchable(page);
  });
}

test("a company page's test link opens a new test on that company", async ({ page }) => {
  const errors = await open(page, "/new?market=IN&symbol=RELIANCE", "testing a strategy on RELIANCE");
  await sane(page, errors);
});

for (const [path, ready] of [["/research/IN/RELIANCE", "Reliance"], ["/research/US/AAPL/deep", "Growth and margins"]]) {
  test(`share a company's fact card from ${path}`, async ({ page, request }, info) => {
    const phone = info.project.name === "phone";
    await watchSharing(page);
    const errors = await open(page, path, ready);
    await answerLevel(page);
    // a company page keeps Share under More (R1-042); the deep dive shows it as a button
    const more = path.endsWith("/deep") ? null : page.locator("main").getByRole("button", { name: "More", exact: true }).first();
    if (more) await more.click();
    const button = more ? page.getByRole("menuitem", { name: "Share", exact: true }) : page.getByRole("button", { name: "Share", exact: true });
    await expect(button).toBeVisible();
    if (phone) await touchable(page);
    await button.click();
    const link = await sharedLink(page, phone);
    const token = link.match(/\/c\/([A-Za-z0-9_-]+)$/)?.[1];
    expect(token, `a card link: ${link}`).toBeTruthy();
    // the public link previews as the card the browser drew, and opens the company's public page
    const preview = await (await request.get(`${API}/c/${token}`)).text();
    expect(preview).toContain('property="og:image"');
    expect(preview).toContain(`/c/${token}.png`);
    expect(preview).toMatch(/\/stocks\/(in\/RELIANCE|us\/AAPL)\?ref=[A-Za-z0-9_-]{12}/);
    expect(preview).toContain("Facts, not advice");
    expect(preview).not.toMatch(/kite|zerodha|yahoo|screener|finnhub/i);
    const png = await request.get(`${API}/c/${token}.png`);
    expect(png.status()).toBe(200);
    expect((await png.body()).subarray(0, 4).toString("latin1")).toBe("\x89PNG");
    await sane(page, errors);
  });
}

test("screens: filter by plain facts, sort by a column, save one; no provider names", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const tag = `e2e screen ${info.project.name} ${Date.now()}`;          // both projects share the fake database
  const errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Prices as of \d+ \w+ \d{4}/)).toBeVisible();              // read today, like the rest of the app
  const table = page.locator(".screens-table");
  await expect(table.locator("tbody tr").first()).toContainText("Reliance Industries Ltd");   // the largest market value first (R5O-012), the listed name
  if (phone) await page.getByRole("button", { name: /Show filters/ }).click();
  await page.getByRole("button", { name: "Energy", exact: true }).click();
  await expect(page.getByText(/3 of 20 companies match/)).toBeVisible();                 // RELIANCE, ONGC, COALINDIA
  await page.getByRole("button", { name: "What is Debt to equity?" }).click();
  await expect(page.getByRole("note")).toContainText("Borrowings divided by shareholders' equity");
  await page.getByLabel("P/E (price to earnings): at most").fill("abc");
  await expect(page.getByText("Enter a plain number, like 15 or -10.")).toBeVisible();
  await page.getByLabel("P/E (price to earnings): at most").fill("1");
  await expect(page.getByText("No company meets every condition.", { exact: false })).toBeVisible();
  await page.getByLabel("P/E (price to earnings): at most").fill("");
  await expect(page.getByText(/3 of 20 companies match/)).toBeVisible();
  if (phone) await page.getByLabel("Sort by").selectOption({ label: "P/E" });             // a phone's cards have no header row: the Sort by box does it
  else { await page.getByTestId("cols-screens").click(); await table.getByRole("button", { name: "P/E" }).click(); }     // the extra columns are one click away
  await expect(table.locator("th[aria-sort=ascending]")).toContainText("P/E");
  await page.getByRole("button", { name: /Low to high/ }).click();
  await expect(table.locator("th[aria-sort=descending]")).toContainText("P/E");
  if (phone) await touchable(page);
  await page.getByLabel("Name").fill(tag);
  await page.getByLabel("Weekly email of new matches").check();
  await page.getByRole("button", { name: "Save screen" }).click();
  const saved = page.getByRole("button", { name: `${tag} · weekly` });
  await expect(saved).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible();
  await saved.click();                                                                  // a saved screen opens its conditions
  await expect(page.getByText(/3 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: `Delete ${tag}` }).click();
  // asks first (R62-011)
  await page.getByRole("dialog", { name: `Delete “${tag}”?` }).getByRole("button", { name: "Delete this screen" }).click();
  await expect(page.getByRole("button", { name: `${tag} · weekly` })).toHaveCount(0);
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub/i);
  expect(text).not.toMatch(/\b(buy|sell|undervalued|best stocks?|score)\b/i);
  await sane(page, errors);
});

test("as-of lines: the company page, deep dive and holdings say how fresh their numbers are", async ({ page }) => {
  let errors = await open(page, "/research/IN/RELIANCE", "Reliance");
  await expect(page.getByText(/Prices as of \d+ \w+ \d{4}, \d\d:\d\d/).first()).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
  await expect(page.getByText(/Reported numbers as of \d+ \w+ \d{4}/).first()).toBeVisible();
  await sane(page, errors);
  errors = await open(page, "/holdings", "By sector");
  await expect(page.getByText(/Prices as of \d+ \w+ \d{4}/).first()).toBeVisible();
  await sane(page, errors);
});

test("deals and insider trades: a dated table on the company page and the deep dive, facts only", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  let errors = await open(page, "/research/IN/RELIANCE", "Deals and insider trades");
  const panel = page.locator("#deals");
  const table = panel.locator(".deals-table");
  await expect(table).toContainText("Mukesh Shah Family Trust", { timeout: 30_000 });
  await expect(table).toContainText("Promoter");
  await expect(table).toContainText("25,000");
  await expect(table).toContainText("₹7.3 cr");
  await expect(panel).toContainText("1 person bought 25,000 shares");
  await expect(table.getByRole("link", { name: /Disclosure/ }).first()).toHaveAttribute("href", /^https:\/\//);
  await panel.getByRole("radio", { name: "Bulk and block deals" }).click();
  await expect(table).toContainText("Index Fund One");
  await expect(table).not.toContainText("Mukesh Shah Family Trust");
  const text = await panel.innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub|nseindia/i);      // "Screener" alone is a menu entry
  expect(text).not.toMatch(/\b(signal|smart money|buy|sell|accumulate|avoid)\b/i);
  if (phone) await touchable(page);
  await sane(page, errors);

  errors = await open(page, "/research/IN/RELIANCE/deep", "Growth and margins");
  await expect(page.getByText("Promoter and insider buying and selling, 6 months").first()).toBeVisible({ timeout: 30_000 });
  // the deals are the company page's own table, linked from the deep dive rather than shown twice (DD-054)
  await expect(page.getByTestId("deep-holders-deals").getByRole("link", { name: "deals and insider trades" })).toHaveAttribute("href", "/research/IN/RELIANCE#deals");
  if (phone) await touchable(page);
  await sane(page, errors);
});

test("screens: promoter or insider bought in the last N days", async ({ page }, info) => {
  const errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  if (info.project.name === "phone") await page.getByRole("button", { name: /Show filters/ }).click();
  const group = page.getByRole("radiogroup", { name: "Promoter or insider bought" });
  await group.getByRole("radio", { name: "Yes" }).click();
  await expect(page.getByText(/5 of 20 companies match/)).toBeVisible();
  await expect(page.getByTestId("screens-insider-note")).toHaveCount(0);                 // the stored dates cover 90 days
  await page.getByLabel("Promoter or insider bought: in the last").selectOption("365");
  await expect(page.getByText(/10 of 20 companies match/)).toBeVisible();
  // the demo's stored purchases reach back 120 days (RC3M-009): a year is said to be wider than that, and "No" shows nobody
  await expect(page.getByTestId("screens-insider-note")).toContainText("are stored only from");
  await group.getByRole("radio", { name: "No" }).click();
  await expect(page.getByText(/0 of 20 companies match/)).toBeVisible();
  await expect(page.getByTestId("screens-insider-note")).toContainText("no company can be shown as having had none");
  await page.getByLabel("Promoter or insider bought: in the last").selectOption("90");
  await expect(page.getByText(/15 of 20 companies match/)).toBeVisible();
  await expect(page.getByTestId("screens-insider-note")).toHaveCount(0);
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "What is Promoter or insider bought?" }).click();
  await expect(page.getByRole("note")).toContainText("insider-trading disclosures");
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/kite|zerodha|yahoo|screener\.in|finnhub/i);
  expect(text).not.toMatch(/\b(buy|sell|signal|score)\b/i);
  await sane(page, errors);
});

test("surveillance flags: badges with what each measure is on the company page, holdings and screens; facts only", async ({ page, request }, info) => {
  // the fake exchange: RELIANCE on long-term ASM Stage II, TATASTEEL short-term ASM Stage I, ITC GSM Stage II and T2T, INFY in the F&O ban
  let errors = await open(page, "/research/IN/RELIANCE", "Sales and profit, by year");
  await answerLevel(page);
  const flags = page.locator("[data-surveillance=RELIANCE]").first();
  await expect(flags.getByText("LT-ASM 2")).toBeVisible({ timeout: 30_000 });
  await flags.getByRole("button", { name: "What RELIANCE's exchange surveillance flags mean" }).click();
  const note = page.getByRole("note");
  await expect(note).toContainText("Stage 2: 100% margin");
  await expect(note).toContainText("List as of");
  const said = await note.innerText();
  expect(said).not.toMatch(/\b(buy|sell|avoid|risky|danger|warning)\b/i);
  expect(said).not.toMatch(/nseindia|kite|zerodha|yahoo|screener|finnhub/i);
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  errors = await open(page, "/holdings", "By sector");
  const table = page.getByRole("table", { name: "Positions" });
  await expect(table.locator("[data-surveillance=RELIANCE]").getByText("LT-ASM 2")).toBeVisible({ timeout: 30_000 });
  await sane(page, errors);

  errors = await open(page, "/research/screens?region=IN", "Filter companies by plain facts");
  await answerLevel(page);
  await expect(page.getByText(/20 of 20 companies match/)).toBeVisible({ timeout: 30_000 });
  if (info.project.name === "phone") await page.getByRole("button", { name: /Show filters/ }).click();
  await page.getByRole("radiogroup", { name: "Exchange surveillance" }).getByRole("radio", { name: "On a list" }).click();
  await expect(page.getByText(/4 of 20 companies match/)).toBeVisible();
  await page.getByRole("button", { name: "ASM (long or short term)", exact: true }).click();
  await expect(page.getByText(/2 of 20 companies match/)).toBeVisible();
  const rows = page.locator(".screens-table");
  await expect(rows.getByText("ST-ASM 1")).toBeVisible();
  await page.getByRole("radiogroup", { name: "Exchange surveillance" }).getByRole("radio", { name: "On none" }).click();
  await expect(page.getByText(/18 of 20 companies match/)).toBeVisible();
  if (info.project.name === "phone") await touchable(page);
  await sane(page, errors);

  const pub = await (await request.get(`${API}/stocks/in/RELIANCE`)).text();
  expect(pub).toContain("Exchange surveillance");
  expect(pub).toContain("LT-ASM 2");
});

test("corporate actions: the calendar, a company's actions, and a bonus applied (and undone) in My Holdings", async ({ page, request }, info) => {
  // each project signs in as its own user, so the two runs don't adjust the same holdings at once
  const [token, id, email] = info.project.name === "phone" ? ["basic-token", "u-basic", "basic@example.com"] : ["pro-token", "u-pro", "pro@example.com"];
  const csv = Buffer.from("Symbol,Quantity,Average price\nTCS,12,3520\nRELIANCE,50,2400\n").toString("base64");
  expect((await request.post(`${API}/holdings/import`, { headers: { Authorization: `Bearer ${token}` },
    data: { filename: "holdings.csv", data: csv, mode: "replace" } })).ok()).toBeTruthy();
  const who = sessionAs(token, id, email);

  let errors = await open(page, "/research/corporate-actions?region=IN&scope=all", "Dividends, bonuses and splits", who);
  await settle(page);
  // ex-dates gone by sit under "Last two weeks", folded below the ones coming up
  const past = page.locator("details.earlier", { hasText: "Last two weeks" });
  if (await past.count()) await expect(past).not.toHaveAttribute("open", "");
  await seeUnfolded(page, page.getByRole("link", { name: "TCS" }).first());
  // each action is a row of a table (RES-1): the kind, its figure in its own column, and what the figure does not say under the kind
  await expect(page.getByRole("row", { name: /TCS.*Bonus 1:1/ }).first()).toContainText("1 new share for every 1 held");
  await expect(page.getByRole("row", { name: /TCS.*Interim dividend/ }).first()).toContainText("₹11");
  await expect(page.getByText("Annual General Meeting")).toHaveCount(0);           // a meeting isn't an action
  if (info.project.name === "phone") await page.getByRole("button", { name: /^Filters/ }).click();       // the filters sit behind a button on a phone
  await page.getByRole("combobox", { name: "Kind of action" }).selectOption("bonus");
  await expect(page.getByText(/Dividend - Rs|₹5.50 a share/)).toHaveCount(0);
  await seeUnfolded(page, page.getByText("1 new share for every 1 held").first());
  await page.getByRole("radio", { name: "My stocks" }).click();
  await seeUnfolded(page, page.getByText("1 new share for every 1 held").first());      // TCS is in the holdings
  await sane(page, errors);
  if (info.project.name === "phone") await touchable(page);
  expect(await page.locator("main").innerText()).not.toMatch(/yahoo|finnhub|kite|screener/i);

  await page.goto("/research/IN/TCS");
  const panel = page.locator("#corporate-actions");
  // the fake exchange's dates are relative to India's day, so a run that crosses midnight IST reads the list again and
  // carries the dividend under two ex-dates (CI at 00:10 IST, 24 Oct): one is enough, as in the calendar above
  // (a table: Ex-date | Type | Amount a share | Record date, one row for each)
  const actions = panel.getByRole("table", { name: /Corporate actions/ });
  await expect(actions.getByRole("columnheader")).toHaveText(["Ex-date", "Type", "Amount a share", "Record date"], { timeout: 30_000 });
  await expect(actions.getByRole("row").filter({ hasText: "Interim dividend" }).first().getByRole("cell", { name: "₹11", exact: true })).toBeVisible();
  await expect(actions.getByRole("row").filter({ hasText: "Final dividend" }).getByRole("cell", { name: /^₹30/ })).toBeVisible();      // (its mark for the note "in today's shares" is beside it)
  await expect(panel.getByText(/Dividends with an ex-date in the last 12 months/)).toBeVisible();

  errors = await open(page, "/holdings", "By sector", who);
  await settle(page);
  const notice = page.getByText(/TCS had a 1:1 bonus on .*: your quantity is now 24, average price ₹1,760/);
  await expect(notice).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Dividends" })).toBeVisible();
  // TCS can have two dividends ahead in the window (around midnight IST the seeded dates shift a day): one or more rows is the point
  await expect(page.getByRole("table", { name: "Dividends ahead" })).toContainText("TCS");
  if (info.project.name === "phone") await touchable(page);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("TCS: quantity 24, average price ₹1,760.00.")).toBeVisible();
  const positions = page.getByRole("table", { name: "Positions" });
  await expect(positions.getByRole("row").filter({ hasText: "TCS" }).getByRole("cell", { name: /^24 ₹1,760\.00 → / })).toBeVisible();   // the one "Qty · avg → last" cell
  await expect(notice).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("TCS is back to 12 shares.")).toBeVisible();
  await expect(notice).toBeVisible();
  await sane(page, errors);
});
