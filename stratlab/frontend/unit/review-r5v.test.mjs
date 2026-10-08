// Round 5, the visitor review's data-trust items on the frontend side: the landing's made-up sample cards, the one
// margin label, the public company pages' fonts at fixed addresses, and one address per page (no trailing slash).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { PUBLIC_FONTS, fontSource } from "../scripts/publicFonts.mjs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("the landing's sample cards name no real company and show no quote 'today' (R5V-002, R5V-003)", () => {
  const login = read("src/pages/Login.tsx");
  const samples = login.slice(login.indexOf("function SpaceArt"), login.indexOf("/* small illustrations for the four checks */"));
  assert.ok(samples.length > 500, "found the sample cards");
  for (const bad of [/RELIANCE/, /NVIDIA/, /\bNVDA\b/, /NASDAQ/, /\bNSE\b/, /BTC/, /\btoday\b/, /18 Oct/, /symbol=/])
    assert.doesNotMatch(samples, bad, `${bad} in the landing's sample cards`);
  // every card carries the readable label, not the old 12px grey line
  assert.equal((samples.match(/className="lp-illus"/g) || []).length, 4);
  assert.match(login, /const ILLUSTRATION = "Illustration: made-up figures"/);
  assert.doesNotMatch(samples, /tiny muted">Sample figures/);
  const css = read("src/styles.css");
  assert.match(css, /\.lp-illus \{[^}]*font: 600 var\(--t-label\)/);
});

test("the margin from operating profit before depreciation is called EBITDA margin wherever it shows (R5V-004)", () => {
  assert.match(read("src/pages/Screens.tsx"), /\{ id: "opm", label: "EBITDA margin"/);
  assert.match(read("src/pages/DeepDive.tsx"), /n\.bank \? "Financing margin" : "EBITDA margin"/);
  const research = read("src/components/Research.tsx");
  // a bank's quarters say "Financing margin" (R7O-001); every other company's, "EBITDA margin"
  assert.match(research, /\{ name: bank \? "Financing margin" : "EBITDA margin", cells: q\.opm/);
  assert.match(research, /"EBITDA margin": "Operating profit before depreciation/);
  assert.doesNotMatch(research, /"OPM": "Operating profit margin/);
  // the company card's price line says what the price is
  assert.match(read("src/components/companyCard.ts"), /`Last close, \$\{d\.as_of\}`/);
});

test("the public company pages' fonts are built to fixed addresses, and every one the page asks for exists (R5V-023)", () => {
  const page = readFileSync(new URL("../../backend/app/stock_pages.py", import.meta.url), "utf8");
  const asked = [...page.matchAll(/url\(\/fonts\/([^)]+)\)/g)].map((m) => m[1]).sort();
  assert.deepEqual(asked, PUBLIC_FONTS.map(([f]) => f).sort());
  for (const [file, pkg] of PUBLIC_FONTS) assert.ok(existsSync(fontSource(file, pkg)), `${pkg}/files/${file}`);
  assert.match(read("vite.config.ts"), /plugins: \[react\(\), publicFonts\(\)/);
});

test("one address per page: a trailing slash redirects, and the fonts are cached (R5V-013, R5V-023)", () => {
  const vercel = JSON.parse(read("vercel.json"));
  assert.equal(vercel.trailingSlash, false);
  const fonts = vercel.headers.find((h) => h.source === "/fonts/(.*)");
  assert.ok(fonts && /max-age=\d+/.test(fonts.headers.find((x) => x.key === "Cache-Control").value));
});
