import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// site85 (Release 85): unit checks of the fixes the browser specs (e2e/site85.spec.ts) prove on the pages.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE21B-001: a saved sign-in on an app page starts in the app's frame, never the landing's header and heading", () => {
  const boot = read("public/boot.js"), html = read("index.html"), entry = read("src/lib/entry.ts");
  // only a saved sign-in, and not on the pages anyone sees the same way: boot.js's list is lib/entry.ts's
  const forAll = boot.match(/var FOR_ALL = (\[.*\]);/)[1];
  assert.equal(forAll, entry.match(/export const PUBLIC_FOR_ALL = (\[.*\]);/)[1]);
  assert.match(boot, /if \(document\.documentElement\.hasAttribute\("data-saved"\) && !FOR_ALL\.some\(/);
  // the landing's frame is taken out as it is parsed, and hidden until then
  assert.match(boot, /new MutationObserver\(appFrame\)/);
  assert.match(html, /html\[data-app-boot\] #root > \.boot-head, html\[data-app-boot\] \[data-boot-head\], html\[data-app-boot\] \[data-boot\] \{ display: none; \}/);
  // the start-up guard's slow and failed notices still see the frame as "the app has not drawn yet"
  assert.equal((boot.match(/\[data-boot-shell\]/g) || []).length, 4);
  // the HTML frame and the app's own first frame (components/BootFrame.tsx) are the same: top bar with four held button places, the menu's
  // panel with the logo, the page column
  const frame = read("src/components/BootFrame.tsx");
  const classes = (s) => [...s.matchAll(/class(?:Name)?=\\?"([^"\\]+)\\?"/g)].map((m) => m[1]).filter((c) => !/^logo/.test(c));
  const seg = boot.match(/shell\.className = "([^"]+)";[\s\S]*?var box = ('[^']*');[\s\S]*?shell\.innerHTML = ([\s\S]*?);\n/);
  const fromBoot = [seg[1], ...classes(new Function("box", `return ${seg[3]};`)(new Function(`return ${seg[2]};`)()))];
  const fromApp = classes(frame.slice(frame.indexOf("return (")));
  assert.deepEqual(fromBoot.slice(0, fromApp.length), fromApp);
  assert.deepEqual(fromApp, ["shell boot-shell", "topbar", "icon-btn", "brand", "row tight", "icon-btn", "icon-btn", "icon-btn", "sidebar", "side-top", "side-brand", "brand", "main", "page"]);
  // and the app draws it while the sign-in is read and the data status asked
  const main = read("src/main.tsx");
  assert.equal((main.match(/return <><BootFrame><h1 className="sr-only">Opening StratLab<\/h1><Opening label="Opening StratLab" \/><\/BootFrame><Tracking \/><\/>;/g) || []).length, 2);
});
