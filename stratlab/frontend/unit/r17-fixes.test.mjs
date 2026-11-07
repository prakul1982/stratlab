// Release 17 fixes (7 Nov): insider trades from BSE marked as such; the visitor router's page moves are not transitions (one click on
// the signed-out landing), paid for by landing bytes; the cards that drew their own h2 use the kit's heading, so the section frame applies.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R17-002: insider trades read from BSE's list say so, in the table and under it", () => {
  const d = read("src/components/Deals.tsx");
  assert.match(d, /insider_from\?: "BSE" \| null;/);
  assert.match(d, /\{d\.exchange === "BSE" \? "BSE disclosure" : "Disclosure"\} ↗/);
  assert.match(d, /rep\.insider_from === "BSE" && <p className="k-note" data-testid="deals-from-bse">Insider trades here are from BSE's disclosures: NSE's list didn't answer just now\.<\/p>/);
});

test("R17-003: the visitor's router, like the app's, does not run page moves as transitions", () => {
  assert.match(read("src/visitor/visitorMain.tsx"), /<BrowserRouter useTransitions=\{false\}>/);
  assert.match(read("src/main.tsx"), /<BrowserRouter useTransitions=\{false\}>/);
});

test("R17-003: words two pages share are written once in the landing page's download, and each page still has them", async () => {
  const src = read("src/content/seo.ts");
  assert.equal((src.match(/StratLab has three plans: Free, Basic and Pro/g) ?? []).length, 1);
  assert.equal((src.match(/How to reach StratLab for help, billing and refunds/g) ?? []).length, 1);
  const { PAGES } = await import("../src/content/seo.ts");
  const by = (p) => PAGES.find((x) => x.path === p);
  for (const p of ["/pricing", "/plans"]) {
    assert.equal(by(p).summary.length, 2, p);
    assert.match(by(p).summary[0], /^StratLab has three plans: Free, Basic and Pro\./);
    assert.match(by(p).summary[1], /You can cancel any time from Account\.$/);
  }
  assert.equal(by("/contact").description, by("/contact").summary[0]);
  assert.match(by("/contact").description, /^How to reach StratLab for help, billing and refunds, or a privacy request/);
});

test("R17-004: no section card draws its own h2: the deep dive's document cards and the Features page's cards use the kit's heading", () => {
  const head = read("src/components/kit/Card.tsx");
  assert.match(head, /sub != null \? <div className="k-stack k-card-headtext">\{heading\}<span className="k-small k-muted">\{sub\}<\/span><\/div> : heading/);
  const dd = read("src/pages/DeepDive.tsx");
  assert.match(dd, /<CardHead title="From the company's own documents" sub=\{/);
  assert.match(dd, /<CardHead title="Management report card" sub=\{/);
  const nav = read("src/pages/NavPages.tsx");
  assert.match(nav, /<CardHead title=\{<Link to="\/mine">\{MINE_NAME\}<\/Link>\} \/>/);
  assert.match(nav, /<CardHead title=\{<Link to=\{s\.home\}>\{s\.label\}<\/Link>\} \/>/);
  // the read buttons in the header row take a line of their own on a phone rather than wrap their words (UI-lint R4)
  assert.match(read("src/styles.css"), /\.dd-ask \{ flex-wrap: wrap; \}\n\.dd-ask > \.btn \{ white-space: nowrap; max-width: 100%; \}/);
  for (const f of ["src/pages/DeepDive.tsx", "src/pages/NavPages.tsx"]) {
    const s = read(f);
    // a raw card title right inside a Card (the page-link tiles of a group page keep theirs: a grid of links, not sections)
    assert.doesNotMatch(s.replace(/<Card testId="group-card">\s*<div className="nav-card">\s*<h2/, ""), /<Card[^>]*>\s*(<div[^>]*>\s*){0,2}<h2 className="k-card-title"/, f);
  }
});
