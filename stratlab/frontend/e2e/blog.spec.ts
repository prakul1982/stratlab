import { expect, test, type Page } from "@playwright/test";

// The public blog (BLOG-1): a Blog link in the public header and footers (and the signed-in app's Account and Plans footers) that opens
// the API's real HTML pages, a list of posts and a post with its tables, and Admin → Data and jobs → Blog, where a post is hidden (it
// answers 404 on the site) and published again. The fake world has the last three trading days' Market Briefs of each market as posts
// and the research posts built from its own library samples, IPO tracker and index history (tests/visual_server.py).
const session = { access_token: "admin-token", token_type: "bearer", expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
  refresh_token: "r", user: { id: "u-admin", aud: "authenticated", email: "owner@example.com", role: "authenticated", app_metadata: {}, user_metadata: {} } };
const SHOTS = process.env.E2E_SHOTS;

async function signedIn(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? r.fallback() : r.fulfill({ status: 200, body: "{}", contentType: "application/json" });
  });
  await page.addInitScript((s) => { localStorage.setItem("sb-demo-auth-token", JSON.stringify(s)); localStorage.setItem("stratlab.tour.v1", "1"); }, session);
  return errors;
}

async function noSideways(page: Page) {
  const { scroll, width } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(width + 1);
}

async function shot(page: Page, name: string, info: { project: { name: string } }) {
  if (!SHOTS) return;
  const phone = info.project.name === "phone";
  await page.emulateMedia({ colorScheme: phone ? "light" : "dark" });
  await page.waitForTimeout(250);
  await page.screenshot({ path: `${SHOTS}/${name}-${phone ? "400-light" : "1300-dark"}.png`, fullPage: true });
}

test("blog: the public header, menu and footer carry a Blog link, and it opens the blog", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  await page.goto("/library");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
  if (phone) {
    await page.locator("details.pub-menu summary").click();
    await expect(page.getByRole("navigation", { name: "Site (menu)" }).getByRole("link", { name: "Blog" })).toHaveAttribute("href", "/blog");
  } else {
    await expect(page.getByRole("navigation", { name: "Site", exact: true }).getByRole("link", { name: "Blog" })).toHaveAttribute("href", "/blog");
  }
  const foot = page.getByRole("navigation", { name: "Explore" }).getByRole("link", { name: "Blog" });
  await expect(foot).toHaveAttribute("href", "/blog");
  await foot.click();
  await expect(page).toHaveURL(/\/blog$/);
  await expect(page.getByRole("heading", { level: 1, name: "StratLab blog" })).toBeVisible();
  await noSideways(page);
});

test("blog: the landing page's header and footer, and the signed-in Account and Plans footers, link to it", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".lp-foot").getByRole("link", { name: "Blog" })).toHaveAttribute("href", "/blog", { timeout: 30_000 });
  await expect(page.locator('nav[aria-label="Sections"] a[href="/blog"], nav[aria-label="Sections (menu)"] a[href="/blog"]').first()).toHaveAttribute("href", "/blog");
  // the hero says nothing about it: one more link in the header, not a new button over the fold
  await expect(page.locator(".lp-hero a[href='/blog'], main a[href='/blog']")).toHaveCount(0);
});

test("blog: Account and Plans footers link to the blog when signed in", async ({ page }) => {
  const errors = await signedIn(page);
  for (const path of ["/account", "/plans"]) {
    await page.goto(path);
    await expect(page.locator(".legal-links").getByRole("link", { name: "Blog" })).toHaveAttribute("href", "/blog", { timeout: 30_000 });
  }
  expect(errors).toEqual([]);
});

test("blog: the list shows the briefs and the research as cards, and a post is a readable page with its tables", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/blog");
  await expect(page.getByRole("heading", { level: 1, name: "StratLab blog" })).toBeVisible({ timeout: 30_000 });
  const cards = page.locator("ul.posts a.post");
  expect(await cards.count()).toBeGreaterThanOrEqual(6);
  await expect(page.getByRole("navigation", { name: "Blog sections" }).getByRole("link")).toHaveText(["All posts", "Market briefs", "Research"]);
  await expect(page.getByText("Facts, not advice").first()).toBeVisible();
  await noSideways(page);
  await shot(page, "blog-list", info);
  await page.getByRole("navigation", { name: "Blog sections" }).getByRole("link", { name: "Market briefs" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Market briefs" })).toBeVisible();
  expect(await page.locator("ul.posts a.post").count()).toBeGreaterThanOrEqual(4);      // three days of each market (a day with no figure yet is not listed)
  await page.locator("ul.posts a.post", { hasText: "India market brief" }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("India market brief");
  await expect(page.getByRole("heading", { level: 2, name: "Index closes" })).toBeVisible();
  // O5: the index closes are one table: the index, its close, its change on the day and its distance from the 52-week high
  const idx = page.locator("article .btbl table").first();
  await expect(idx).toContainText("NIFTY 50");
  await expect(idx.locator("thead th").nth(2)).toContainText("Day");
  await expect(page.locator("article ul.kpis li")).toHaveCount(0);
  await expect(page.getByText("Facts, not advice.").first()).toBeVisible();
  await expect(page.locator("article").getByRole("link", { name: "Company pages" })).toHaveAttribute("href", "/stocks");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /^https:\/\/stratlab\.studio\/blog\/india-market-brief-\d{4}-\d{2}-\d{2}$/);
  expect(await page.locator('script[type="application/ld+json"]').count()).toBe(1);
  await noSideways(page);
  await shot(page, "blog-post", info);
  expect(errors).toEqual([]);
  // a research post: its tables stay inside their box on a phone
  await page.goto("/blog/research");
  const research = page.locator("ul.posts a.post");
  expect(await research.count()).toBeGreaterThanOrEqual(1);
  await research.first().click();
  await expect(page.locator(".btbl").first()).toBeVisible();
  await noSideways(page);
  await shot(page, "blog-research", info);
});

test("blog: the feed, the sitemap and robots are served at the site's own addresses", async ({ page }) => {
  const feed = await page.request.get("/blog/feed.xml");
  expect(feed.status()).toBe(200);
  expect(feed.headers()["content-type"]).toContain("application/atom+xml");
  expect(await feed.text()).toContain("<entry>");
  const map = await page.request.get("/sitemaps/blog.xml");
  expect(map.status()).toBe(200);
  expect(await map.text()).toContain("/blog/india-market-brief-");
  expect((await page.request.get("/blog/no-such-post-at-all")).status()).toBe(404);
  const robots = await (await page.request.get("/robots.txt")).text();
  expect(robots).toContain("Allow: /blog");
});

test("admin: the Blog panel lists the posts, hides one (404 on the site) and publishes it again, and writes the research posts", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const title = phone ? "US market brief" : "India market brief";      // each run takes its own post, so the two don't hide the same one
  const errors = await signedIn(page);
  await page.goto("/admin/data");
  await expect(page.getByRole("heading", { level: 2, name: "Blog", exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/\d+ posts?: \d+ on the site/)).toBeVisible();
  await expect(page.getByTestId("blog-run")).toContainText("Research last written");
  const table = page.getByRole("table", { name: "Blog posts" });
  const row = table.getByRole("row").filter({ hasText: title }).first();
  const href = await row.getByRole("link").first().getAttribute("href");
  expect(href).toMatch(/^\/blog\/(india|us)-market-brief-\d{4}-\d{2}-\d{2}$/);
  expect((await page.request.get(href!)).status()).toBe(200);
  await shot(page, "admin-blog", info);
  await row.getByRole("button", { name: "Hide" }).click();
  await expect(row).toContainText("Hidden");
  expect((await page.request.get(href!)).status()).toBe(404);
  expect(await (await page.request.get("/blog/feed.xml")).text()).not.toContain(href!);
  await row.getByRole("button", { name: "Publish" }).click();
  await expect(row).toContainText("Published");
  expect((await page.request.get(href!)).status()).toBe(200);
  await noSideways(page);
  expect(errors).toEqual([]);
});

test("admin: the Blog panel's buttons add the stored briefs and write the research posts", async ({ page }) => {
  await signedIn(page);
  await page.goto("/admin/data");
  await expect(page.getByRole("button", { name: "Write the research posts" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Add posts for stored briefs" }).click();
  await expect(page.getByText("Every stored brief already has its post.").or(page.getByText(/Added \d+ market brief posts?\./)).first()).toBeVisible();
  await page.getByRole("button", { name: "Write the research posts" }).click();
  await expect(page.getByTestId("blog-run")).toContainText("Research last written", { timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Write the research posts" })).toBeEnabled({ timeout: 90_000 });
});

test("PUB-2: a post has one content width, headline numbers as tiles, tables that line up, and its method folded", async ({ page }, info) => {
  const phone = info.project.name === "phone";
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/blog/classic-strategies-ten-markets-after-costs");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Classic strategies");
  // the byline's facts are one quiet line, not a box
  const facts = page.locator("p.facts");
  await expect(facts).toContainText("Facts, not advice");
  expect(await facts.evaluate((e) => ({ lines: Math.round(e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight)), bg: getComputedStyle(e).backgroundColor, border: getComputedStyle(e).borderLeftWidth }))).toMatchObject({ bg: "rgba(0, 0, 0, 0)", border: "0px" });
  if (!phone) expect(await facts.evaluate((e) => e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight))).toBeLessThan(1.5);
  // one width: the text, the tiles, the chart and the tables share their left and right edges
  const edges = await page.evaluate(() => Array.from(document.querySelectorAll("article > p:not(.blog-eyebrow):not(.byline):not(.facts), article > ul.kpis, article > figure.hbars, article > .btbl, article > details"))
    .map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right)]; }));
  expect(edges.length).toBeGreaterThan(8);
  expect(new Set(edges.map((x) => x[0])).size, "left edges").toBe(1);
  expect(new Set(edges.map((x) => x[1])).size, "right edges").toBe(1);
  // the headline numbers are a row of tiles, with one small chart under them
  const tiles = page.locator("ul.kpis li");
  expect(await tiles.count()).toBe(4);
  await expect(tiles.first()).toContainText(/\d+ of \d+/);
  expect(await tiles.evaluateAll((e) => new Set(e.map((x) => Math.round(x.getBoundingClientRect().height))).size)).toBe(1);        // tiles of one height
  expect(await page.locator("figure.hbars li").count()).toBeGreaterThanOrEqual(10);                                                // a bar for each market
  // the method is folded (its text is in the page); a table's names don't wrap, its numbers sit right, its text left
  await expect(page.locator("details[data-method]").first()).not.toHaveAttribute("open", "");
  expect(await page.locator("details[data-method]").first().textContent()).toContain("slippage");
  // (VR7-002: on a phone each market is a fold, closed: the first is opened to measure its table)
  if (phone) await page.locator("details.mk").first().evaluate((e) => { (e as HTMLDetailsElement).open = true; });
  const t = page.locator(".btbl.fx").filter({ hasText: "Rule set" }).first();
  expect(await t.locator("thead th").evaluateAll((e) => e.every((x) => x.getBoundingClientRect().height < 40))).toBe(true);        // no header wraps
  expect(await t.locator("tbody th[scope=row]").evaluateAll((e) => e.every((x) => (() => { const a = x.querySelector("a")!, cs = getComputedStyle(a); return a.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom) < 30; })() && x.scrollWidth <= x.clientWidth + 1))).toBe(true);   // no name wraps or is cut
  expect(await t.locator("td").evaluateAll((e) => e.every((x) => x.scrollWidth <= x.clientWidth + 1))).toBe(true);                       // no figure or check is cut
  // (on a phone a table of five columns or more is a card per row, VR5-007: its figures are laid out left, each under its column's name)
  if (!phone) expect(await t.locator("tbody tr").first().locator("td").evaluateAll((e) => e.map((x) => getComputedStyle(x).textAlign))).toEqual(["right", "right", "right", "right", "left"]);
  await noSideways(page);
  expect(errors).toEqual([]);
});
