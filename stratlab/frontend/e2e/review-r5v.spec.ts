import { expect, test, type Page } from "@playwright/test";

// Round 5, the visitor review's public company pages, opened on the site's own address (the local copy forwards /stocks to
// the API as the site's host does): the site's header and footer and its fonts, one price rule (the last close, dated),
// market caps in words, the newest years in view on a phone, and /stocks, funds, share classes and a trailing slash.

async function visit(page: Page, where: string) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.goto(where);
  return errors;
}

test("a public company page wears the site's header, footer and type, and dates its price as a close", async ({ page }, info) => {
  const errors = await visit(page, "/stocks/in/RELIANCE");
  await expect(page.locator("h1")).toContainText("Reliance Industries");
  const header = page.locator("header.nav");
  await expect(header.getByRole("link", { name: "StratLab home" })).toBeVisible();
  await expect(header.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", /\/research\/IN\/RELIANCE$/);
  const foot = page.locator("footer.site");
  for (const name of ["Terms of service", "Privacy policy", "Cancellation and refunds", "Contact us"]) await expect(foot.getByRole("link", { name })).toBeVisible();
  // one price rule: the last close with its date, never "Last price"
  await expect(page.getByText(/^As of \d{1,2} \w{3} \d{4} close\./)).toBeVisible();
  await expect(page.locator(".stat", { hasText: /Last close, \d{1,2} \w{3} \d{4}/ })).toHaveCount(1);
  await expect(page.locator("main")).not.toContainText("Last price");
  await expect(page.locator(".stat", { hasText: "Market cap" }).locator("b")).toHaveText(/^₹[\d.,]+ (lakh crore|crore)$/);
  await expect(page.locator(".stat", { hasText: "EBITDA margin" })).toHaveCount(1);
  await expect(page.locator("main")).not.toContainText("Operating margin");
  // the site's own fonts, from the site's own address
  const font = await page.request.get("/fonts/fraunces-latin-400-normal.woff2");
  expect(font.status()).toBe(200);
  expect((await font.body()).subarray(0, 4).toString()).toBe("wOF2");
  expect(await page.evaluate(async () => (await document.fonts.load('16px "Fraunces"')).length + (await document.fonts.load('15px "IBM Plex Sans"')).length)).toBe(2);
  expect(await page.evaluate(() => getComputedStyle(document.querySelector("h1")!).fontFamily)).toMatch(/Fraunces/);
  // the newest year is in view on a phone, with a cue that earlier years are to the left
  // (scrolled to vertically only: scrolling the cell itself into view would also scroll the table sideways)
  await page.evaluate(() => window.scrollTo(0, document.querySelector(".tbl")!.getBoundingClientRect().top + window.scrollY - 100));
  const [box, tbl] = [await page.locator(".tbl th").last().boundingBox(), await page.locator(".tbl").boundingBox()];
  expect(box!.x, "the newest year starts inside the table's view").toBeGreaterThanOrEqual(tbl!.x - 1);
  expect(box!.x + box!.width, "the newest year ends inside the table's view").toBeLessThanOrEqual(tbl!.x + tbl!.width + 1);
  await expect(page.locator(".scroll-cue")).toBeVisible({ visible: info.project.name === "phone" });
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
  expect(errors).toEqual([]);
});

test("/stocks finds a company, funds say what they are, and every company has one address", async ({ page }) => {
  const errors = await visit(page, "/stocks");
  await expect(page.getByRole("heading", { level: 1, name: "Company pages" })).toBeVisible();
  await page.getByLabel("Company name or symbol").fill("reliance");
  await page.getByRole("button", { name: "Find" }).click();
  await page.getByRole("link", { name: /RELIANCE/ }).first().click();
  await expect(page).toHaveURL(/\/stocks\/in\/RELIANCE$/);

  const fund = await page.request.get("/stocks/us/SPY");
  expect(fund.status()).toBe(404);
  expect(await fund.text()).toContain("SPY is an exchange-traded fund (ETF)");
  for (const [from, to] of [["/stocks/in/RELIANCE/", "/stocks/in/RELIANCE"], ["/stocks/us/BRK.B", "/stocks/us/BRK-B"]]) {
    const r = await page.request.get(from, { maxRedirects: 0 });
    expect(r.status(), from).toBe(301);
    expect(r.headers()["location"], from).toBe(to);
  }
  expect(errors).toEqual([]);
});
