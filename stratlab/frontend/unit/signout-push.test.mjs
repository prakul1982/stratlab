// Signing out takes this browser's notification subscription off the account first, and never waits on it for long.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

function browser({ unsubscribe }) {
  const sub = { toJSON: () => ({ endpoint: "https://fcm.googleapis.com/fcm/send/x" }), unsubscribe };
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: {
    serviceWorker: { getRegistration: async () => ({ pushManager: { getSubscription: async () => sub } }) } } });
  globalThis.window = { PushManager: {}, Notification: {} };
  globalThis.Notification = {};
}

test("leaving push drops this browser's subscription and never throws or waits long", async () => {
  const { leavePush } = await import("../src/lib/pwa.ts");
  let gone = 0;
  browser({ unsubscribe: async () => { gone += 1; return true; } });
  await leavePush();
  assert.equal(gone, 1);                                                    // the browser's own subscription is removed
  browser({ unsubscribe: async () => { throw new Error("browser says no"); } });
  await leavePush();                                                         // a failure does not stop the sign-out
  browser({ unsubscribe: () => new Promise(() => {}) });                    // a call that never answers
  const t = Date.now();
  await leavePush(50);
  assert.ok(Date.now() - t < 1000);
});

test("every sign-out calls leavePush before supabase.auth.signOut", () => {
  // "Sign out" (the menu, the Account page, the server's 401) goes through signOutHere, which calls leavePush first and signs
  // out this device only; the one direct call left is "Sign out everywhere" (global), which calls leavePush itself
  const here = { "src/components/SideMenus.tsx": 0, "src/pages/AccountPage.tsx": 1, "src/lib/app.tsx": 0 };
  for (const [file, n] of Object.entries(here)) {
    const src = read(file);
    const calls = [...src.matchAll(/supabase\.auth\.signOut\(/g)];
    assert.equal(calls.length, n, file);
    for (const m of calls) {
      assert.match(src.slice(Math.max(0, m.index - 80), m.index), /leavePush\(\)/, file);
      assert.match(src.slice(m.index, m.index + 60), /signOut\(\{ scope: "global" \}\)/, file);
    }
  }
  assert.match(read("src/lib/signout.ts"), /await leavePush\(\);[\s\S]*auth\.signOut\(\{ scope: "local" \}\)/);
});
