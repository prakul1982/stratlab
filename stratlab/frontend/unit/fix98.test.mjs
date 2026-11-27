import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// fix98: unit checks of the sign-in timing fix the browser spec (e2e/site80.spec.ts, "a plan card's email button…") proves on the page.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("fix98: a plan card's email button waits for the form's code itself, showing it is busy, with a generous ceiling", () => {
  const way = read("src/components/EmailWay.tsx");
  const ms = Number(/export const EMAIL_FORM_WAIT_MS = (\d+);/.exec(way)?.[1]);
  assert.ok(ms >= 10000, `a slow phone's download fits in the wait (${ms} ms; 1500 let /login open without its form)`);
  assert.match(way, /aria-busy=\{busy \|\| undefined\}/);
  assert.match(way, /if \(going\.current\) return;/);             // pressed again while waiting: the page opens once
  // the address and the page change in the same task: no frame at /login still showing the page before (the flake's other half)
  assert.match(way, /import \{ flushSync \} from "react-dom";/);
  assert.match(way, /\(u\) => flushSync\(\(\) => navigate\(u\)\)/);
  assert.match(read("src/styles.css"), /\.email-way\[aria-busy="true"\] \{ cursor: progress; background: var\(--line\); \}/);
});

test("fix98: the sign-in page opened for its email form waits for the form as a whole page, never drawn without it", () => {
  const login = read("src/pages/Login.tsx");
  assert.match(login, /if \(login && location\.hash === "#email" && emailSignInOn\(\) && !emailFormNow\(\)\) use\(emailFormSettled\(\)\);/);
  // before the form is used, so a frame that draws the page draws the form
  assert.ok(login.indexOf("use(emailFormSettled())") < login.indexOf("const EmailNow = emailFormNow()?.EmailSignIn;"));
  const src = read("src/lib/emailForm.ts");
  assert.match(src, /loadEmailForm\(\)\.then\(\(\) => undefined, \(\) => undefined\)/);     // never rejects: a failed download draws the page
});
