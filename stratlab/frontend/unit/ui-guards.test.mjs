import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

// Guards that keep the interface on the kit: no page or component outside the kit's own files and the charts draws
// with an inline style, asks with the browser's confirm(), or uses the old ".card" / ".seg" class names.
// Kit internals and charts are the places where a number really does decide a position (a bar's width, a tooltip's
// place), so they are the only files left out.
const SRC = new URL("../src", import.meta.url).pathname;
const SKIP_DIRS = ["components/kit", "components/chart"];
const SKIP_FILES = ["components/Charts.tsx", "components/StrikeChart.tsx", "components/Rotation.tsx", "pages/DevKit.tsx"];

function files(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...files(p));
    else if (/\.tsx$/.test(name)) out.push(p);
  }
  return out;
}
const pages = [...files(join(SRC, "pages")), ...files(join(SRC, "components"))]
  .map((p) => relative(SRC, p))
  .filter((p) => !SKIP_DIRS.some((d) => p.startsWith(d + "/")) && !SKIP_FILES.includes(p));

/** The class names written in a file's className attributes (also the ones picked inside ${...} of a template). */
function classTokens(src) {
  const tokens = [];
  const words = (text) => { for (const t of String(text).split(/\s+/)) if (t) tokens.push(t); };
  const quoted = (code) => { for (const x of code.matchAll(/"([^"]*)"|'([^']*)'|`([^`]*)`/g)) words(x[1] ?? x[2] ?? x[3]); };
  const re = /className=(?:"([^"]*)"|\{`([^`]*)`\}|\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\})/g;
  for (const m of src.matchAll(re)) {
    if (m[1] != null) words(m[1]);
    else if (m[2] != null) { words(m[2].replace(/\$\{[^}]*\}/g, " ")); for (const x of m[2].matchAll(/\$\{([^}]*)\}/g)) quoted(x[1]); }
    else quoted(m[3] ?? "");
  }
  return tokens;
}

test("the guard looks at the pages and components", () => {
  assert.ok(pages.length > 60, `only ${pages.length} files found`);
  assert.ok(pages.includes("pages/PlansPage.tsx") && pages.includes("components/Shell.tsx"));
});

test("no inline style={{...}} in a page or a component", () => {
  const bad = pages.filter((p) => /style=\{\{/.test(readFileSync(join(SRC, p), "utf8")));
  assert.deepEqual(bad, [], "use a kit class or add one to styles.css: " + bad.join(", "));
});

test("no native confirm(): ask in the page with ConfirmDialog", () => {
  const bad = pages.filter((p) => /(^|[^\w.$])(window\.)?confirm\(\s*[^)\s]/m.test(readFileSync(join(SRC, p), "utf8")));
  assert.deepEqual(bad, [], bad.join(", "));
});

test("no browser time box (it shows 02:45 PM in some locales): use TimeInput, 24-hour with its zone", () => {
  const bad = pages.filter((p) => /\btype=(?:"time"|\{\s*["']time["']\s*\})/.test(readFileSync(join(SRC, p), "utf8")));
  assert.deepEqual(bad, [], bad.join(", "));
});

test('no old ".card" or ".seg" class names: use Card and Seg from the kit', () => {
  const bad = pages.filter((p) => classTokens(readFileSync(join(SRC, p), "utf8")).some((t) => t === "card" || t === "seg"));
  assert.deepEqual(bad, [], bad.join(", "));
});

test("the class-name reader sees what it should", () => {
  assert.deepEqual(classTokens('<div className="card stack a">'), ["card", "stack", "a"]);
  assert.deepEqual(classTokens("<div className={`seg x${y ? \" on\" : \"\"}`}>"), ["seg", "x", "on"]);
  assert.deepEqual(classTokens('<div className={a ? "card" : "b"}>'), ["card", "b"]);
  assert.deepEqual(classTokens('<div className="k-card lp-card seg-row">'), ["k-card", "lp-card", "seg-row"]);
});
