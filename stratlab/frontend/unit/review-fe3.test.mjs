// Frontend review (notebooks, experiments, new notebook, library): state that belongs to one notebook starts fresh with
// the next, a late library answer can't replace a newer one, a build can't start twice, the library says exits are "or".
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("a notebook's page is keyed by its id, so a typed run label and test period don't carry to the next notebook", () => {
  const src = read("src/pages/NotebookPage.tsx");
  assert.match(src, /export function NotebookPage\(\) \{\s*const \{ id \} = useParams\(\);\s*return <NotebookView key=\{id\} \/>;/);
});

test("a run that finishes after you've left the notebook doesn't take you back to it", () => {
  const src = read("src/pages/NotebookPage.tsx");
  assert.match(src, /if \(mounted\.current\) nav\(`\/n\/\$\{nb\.id\}\/e\/\$\{out\.experiment\.v\}`\);\s*else notify\(/);
});

test("the library search ignores an answer for a search that has since changed", () => {
  const src = read("src/pages/LibraryPage.tsx");
  assert.match(src, /let live = true;/);
  assert.match(src, /\.then\(\(r\) => \{ if \(!live\) return;/);
  assert.match(src, /\.catch\(\(e\) => \{ if \(!live\) return;/);
  assert.match(src, /return \(\) => \{ live = false; window\.clearTimeout\(t\); \};/);
});

test("Ctrl+Enter in the idea box while a build runs doesn't start a second build", () => {
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /const build = async \(idea = text\) => \{\s*if \(building\.current\) return;/);
  assert.match(src, /building\.current = false;\s*setBusy\(false\);/);
});

test("a group that can't be attached to a new notebook doesn't leave the made notebook unopened", () => {
  const src = read("src/pages/Home.tsx");
  assert.match(src, /try \{ await api\(`\/notebooks\/\$\{nb\.id\}`, \{ method: "PUT", body: \{ group: b\.group \} \}\); \}\s*catch \{ notify\(/);
});

test("the library's rules read exits as 'or' (any one closes the trade) and a swing stop in candles", () => {
  const src = read("src/components/LibraryBits.tsx");
  assert.match(src, /label === "Sell when" \|\| label === "Cover when" \|\| s\.entryJoin === "any" \? " or " : " and "/);
  assert.match(src, /stopType === "swing" \? " candles \(swing\)"/);
});
