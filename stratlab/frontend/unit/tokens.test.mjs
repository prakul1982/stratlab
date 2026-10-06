import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// The dark colours are written twice in styles.css (explicit dark, and "follow the system"); they must stay identical.
const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const decls = (block) => block.split(";").map((d) => d.trim().replace(/\s+/g, " ")).filter(Boolean).sort();

test("the two dark-mode token blocks are identical", () => {
  const a = css.match(/:root\[data-theme="dark"\] \{([^}]*)\}/);
  const b = css.match(/:root:not\(\[data-theme\]\) \{([^}]*)\}/);
  assert.ok(a && b, "both dark blocks exist");
  assert.deepEqual(decls(b[1]), decls(a[1]));
});

test("up and down colours exist in both themes, and --red-ink is an alias of --down", () => {
  for (const t of ["--up", "--up-soft", "--down", "--down-soft"]) assert.equal(css.split(`${t}:`).length - 1, 3, `${t} is defined for light, dark and system dark`);
  assert.match(css, /--red-ink: var\(--down\)/);
});
