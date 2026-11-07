// R19 (7 Nov 2026): reads kept once for everyone, "Last updated" and Refresh in one shared component, the refreshes left beside it,
// Settings' "Your usage" table and Admin → Library.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R19: what's left, when it starts again and how much is used, in plain words", async () => {
  const { refreshesLeft, resetsWord, usedWord } = await import("../src/lib/usageText.ts");
  const usage = { plan: "Free", rows: [{ key: "refresh", label: "Refreshes", used: 1, limit: 3, left: 2, resets: "day" }] };
  assert.equal(refreshesLeft(usage), 2);
  assert.equal(refreshesLeft(null), null);
  assert.equal(refreshesLeft({ plan: "Pro", rows: [{ key: "refresh", label: "", used: 4, limit: null, left: null, resets: "day" }] }), null);
  assert.equal(resetsWord({ resets: "day" }), "Midnight India time");
  assert.equal(resetsWord({ resets: "month" }, new Date("2026-11-07T10:00:00Z")), "1 Dec");
  assert.equal(resetsWord({ resets: "month" }, new Date("2026-12-31T20:00:00Z")), "1 Feb");      // already 1 Jan in India
  assert.equal(resetsWord({ resets: null }), "When you remove one");
  assert.equal(usedWord({ used: 2, limit: 5 }), "2 of 5");
  assert.equal(usedWord({ used: 2, limit: null }), "2 (no limit)");
  assert.equal(usedWord({ used: null, limit: 5 }), "–");
});

test("R19: sizes and saved work for Admin → Library", async () => {
  const { bytesText, hoursText } = await import("../src/lib/usageText.ts");
  assert.equal(bytesText(800), "800 B");
  assert.equal(bytesText(14_540), "14.2 KB");
  assert.equal(bytesText(3_250_000), "3.1 MB");
  assert.equal(bytesText(null), "–");
  assert.equal(hoursText(40), "40 s");
  assert.equal(hoursText(720), "12 min");
  assert.equal(hoursText(12_600), "3.5 h");
});

test("R19: every stored shared read shows the one stamp and note, never its own 'Written' line", () => {
  for (const f of ["src/components/Research.tsx", "src/pages/Research.tsx", "src/pages/ThemesPage.tsx"]) {
    const src = read(f);
    assert.match(src, /<StoredStamp /, f);
    assert.match(src, /<StoredNote /, f);
    assert.doesNotMatch(src, /Written \{/, f);
  }
  const stamp = read("src/components/StoredStamp.tsx");
  assert.match(stamp, /Last updated \{writtenAt/);
  assert.match(stamp, /left today/);
  assert.match(stamp, /disabled=\{busy \|\| none\}/);                  // none left: the button is off, with the reason beside it
  assert.match(stamp, /No refreshes left today, back at midnight IST/);
  assert.match(stamp, /<Working label=/);                              // the kit's bar while a Refresh is out
  assert.doesNotMatch(stamp, /\.message/);                             // never a raw error
});

test("R19: Settings has 'Your usage' and Admin has a Library tab, both on the shared pieces", () => {
  const settings = read("src/pages/SettingsPage.tsx");
  assert.match(settings, /value: "usage", label: "Your usage"/);
  assert.match(settings, /<UsageTable \/>/);
  assert.match(read("src/pages/admin/AdminContext.tsx"), /path: "library", label: "Library"/);
  const lib = read("src/pages/admin/LibrarySection.tsx");
  assert.match(lib, /\/admin\/stored/);
  assert.match(lib, /Refresh now/);
  assert.match(lib, /ConfirmDialog/);
  assert.match(lib, /<DataTable /);
});

test("R19: the landing chunk gains nothing (the new pieces are imported only by signed-in pages)", () => {
  for (const f of ["src/components/Icons.tsx", "src/lib/share.ts"]) assert.doesNotMatch(read(f), /StoredStamp|usage/i, f);
});
