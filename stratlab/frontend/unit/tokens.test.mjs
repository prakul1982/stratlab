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

// Text colours against the surfaces they sit on, in both themes (WCAG AA, 4.5:1 for text).
const lum = (hex) => { const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const tokens = (block) => Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*(#[0-9A-Fa-f]{6})\b/g)].map((m) => [m[1], m[2]]));
const themes = { light: tokens(css.match(/:root \{\s*--paper[^}]*\}/)[0]), dark: tokens(css.match(/:root\[data-theme="dark"\] \{([^}]*)\}/)[1]) };
for (const [name, t] of Object.entries(themes)) {
  test(`text colours read on paper, cards and chips in the ${name} theme`, () => {
    for (const fg of ["--ink", "--ink-2", "--muted", "--blue", "--blue-ink", "--orange-ink", "--up", "--down"]) {
      for (const bg of ["--paper", "--card", "--paper-2"]) {
        const r = ratio(t[fg], t[bg]);
        assert.ok(r >= 4.5, `${fg} on ${bg} (${name}) is ${r.toFixed(2)}:1, needs 4.5:1`);
      }
    }
    for (const [fg, bg] of [["--up", "--up-soft"], ["--down", "--down-soft"], ["--blue-ink", "--blue-soft"], ["--orange-ink", "--orange-soft"], ["--on-ink", "--ink"], ["--on-blue", "--blue"]]) {
      const r = ratio(t[fg], t[bg]);
      assert.ok(r >= 4.5, `${fg} on ${bg} (${name}) is ${r.toFixed(2)}:1, needs 4.5:1`);
    }
  });
}
