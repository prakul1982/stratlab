// The owner's "View as Free / Basic / Pro": what is stored on this device, the header every request carries, the banner's
// words, and that the control and the banner are wired into the app.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const v = await import("../src/lib/viewAs.ts");

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const memoryStore = () => {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, x) => void m.set(k, String(x)), removeItem: (k) => void m.delete(k), m };
};
const brokenStore = () => ({ getItem() { throw new Error("storage off"); }, setItem() { throw new Error("storage off"); }, removeItem() { throw new Error("storage off"); } });

test("only free, basic and pro are plans to view as; anything else is off", () => {
  assert.equal(v.parseViewAs("free"), "free");
  assert.equal(v.parseViewAs(" Basic "), "basic");
  assert.equal(v.parseViewAs("PRO"), "pro");
  for (const bad of ["", "off", "admin", "enterprise", null, undefined, 3, {}]) assert.equal(v.parseViewAs(bad), null, String(bad));
});

test("the control reads View as: Free / Basic / Pro / Off, and Off means none", () => {
  assert.deepEqual(v.VIEW_AS_CHOICES.map((c) => c.label), ["Free", "Basic", "Pro", "Off"]);
  assert.equal(v.choiceToPlan("off"), null);
  assert.equal(v.choiceToPlan("basic"), "basic");
  assert.equal(v.choiceToPlan("nonsense"), null);
  assert.equal(v.planToChoice(null), "off");
  assert.equal(v.planToChoice(undefined), "off");
  assert.equal(v.planToChoice("pro"), "pro");
});

test("the choice persists until it is turned off", () => {
  const s = memoryStore();
  assert.equal(v.readViewAs(s), null);
  v.writeViewAs("free", s);
  assert.equal(s.m.get(v.VIEW_AS_KEY), "free");
  assert.equal(v.readViewAs(s), "free");                  // a reload reads it back
  v.writeViewAs("pro", s);
  assert.equal(v.readViewAs(s), "pro");
  v.writeViewAs(null, s);
  assert.equal(s.m.has(v.VIEW_AS_KEY), false);
  assert.equal(v.readViewAs(s), null);
});

test("a hand-edited or old stored value is off, never a made-up plan", () => {
  const s = memoryStore();
  s.setItem(v.VIEW_AS_KEY, "superuser");
  assert.equal(v.readViewAs(s), null);
  assert.deepEqual(v.viewAsHeaders(s), {});
});

test("every request carries X-View-As while it is on, and nothing when it is off", () => {
  const s = memoryStore();
  assert.deepEqual(v.viewAsHeaders(s), {});
  v.writeViewAs("basic", s);
  assert.deepEqual(v.viewAsHeaders(s), { "X-View-As": "basic" });
  v.writeViewAs(null, s);
  assert.deepEqual(v.viewAsHeaders(s), {});
  assert.match(src("lib/api.ts"), /viewAsHeaders\(\)/, "api() sends it");
});

test("with storage off it still works until the page closes, and nothing throws", () => {
  const s = brokenStore();
  assert.doesNotThrow(() => v.writeViewAs("free", s));
  assert.equal(v.readViewAs(s), "free");
  assert.deepEqual(v.viewAsHeaders(s), { "X-View-As": "free" });
  v.writeViewAs(null, s);
  assert.equal(v.readViewAs(s), null);
});

test("the banner says which plan, that the real plan is unchanged, and offers Turn off", () => {
  assert.equal(v.viewAsBanner("free"), "Viewing as Free. Your real plan is unchanged.");
  assert.equal(v.viewAsBanner("basic"), "Viewing as Basic. Your real plan is unchanged.");
  assert.equal(v.viewAsBanner("pro"), "Viewing as Pro. Your real plan is unchanged.");
  const banner = src("components/ViewAs.tsx");
  assert.match(banner, /label: "Turn off"/);
  assert.match(banner, /setViewAs\(null\)/);
});

test("the banner is on every page, and the control is in the user menu and in Admin", () => {
  assert.match(src("main.tsx"), /<ViewAsBanner \/>/, "mounted inside the app shell, above every page");
  assert.match(src("pages/admin/OverviewSection.tsx"), /<ViewAsCard \/>/, "Admin");
  const menu = src("components/SideMenus.tsx");
  assert.match(menu, /me\?\.is_admin && \(\s*<div className="acct-viewas"/, "the user menu shows it to the owner only");
  assert.match(menu, /VIEW_AS_CHOICES\.map/);
});

test("only the server's word shows it: the banner and menu read me.view_as, and a non-owner's stale choice is dropped", () => {
  const app = src("lib/app.tsx");
  assert.match(app, /viewAs: me\?\.is_admin \? me\.view_as \?\? null : null/);
  assert.match(app, /me && !me\.is_admin && readViewAs\(\)\) writeViewAs\(null\)/);
  assert.match(app, /"\/admin\/view-as"/, "checked with the server before it is kept");
});

test("the new files follow the kit: no inline style, no confirm()", () => {
  for (const p of ["components/ViewAs.tsx", "components/SideMenus.tsx", "pages/admin/OverviewSection.tsx"]) {
    const t = src(p);
    assert.doesNotMatch(t, /style=\{\{/, p);
    assert.doesNotMatch(t, /(^|[^\w.$])(window\.)?confirm\(\s*[^)\s]/m, p);
  }
});
