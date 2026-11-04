// Help & feedback (owner, 4 Nov): the form's choices and limit are the server's own, the browser is sent in a few words (never the
// whole user-agent string), the labelled button is in the menu's top and the phone's top bar, on Help and in the public footer,
// and Admin has the inbox with new reports counted in "Needs your attention".
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { FEEDBACK_TYPES, FEEDBACK_MAX, browserLine } = await import("../src/lib/feedback.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const server = readFileSync(new URL("../../backend/app/feedback.py", import.meta.url), "utf8");

test("the three types and the length limit are the server's own", () => {
  for (const [value, label] of FEEDBACK_TYPES) assert.ok(server.includes(`"${value}": "${label}"`), value);
  assert.deepEqual(FEEDBACK_TYPES.map(([v]) => v), ["broken", "not_working", "idea"]);
  assert.match(server, new RegExp(`MAX_TEXT = ${FEEDBACK_MAX}\\b`));
});

test("the browser goes as a few words: name, major version and system, whatever the browser", () => {
  const cases = [
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.58 Mobile Safari/537.36", "Chrome 130 on Android"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", "Safari 17 on iOS"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/129.0.6668.69 Mobile/15E148 Safari/604.1", "Chrome 129 on iOS"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.56", "Edge 130 on Windows"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:131.0) Gecko/20100101 Firefox/131.0", "Firefox 131 on macOS"],
    ["Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36", "Samsung Internet 26 on Android"],
    ["Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0", "Opera 115 on Linux"],
    ["curl/8.4.0", "A browser on another system"],
  ];
  for (const [ua, want] of cases) {
    const got = browserLine(ua);
    assert.equal(got, want, ua);
    assert.ok(got.length <= 120 && !/Mozilla|AppleWebKit|KHTML|Gecko\//.test(got), "no raw user-agent parts");
  }
});

test("the labelled Feedback button: the menu's top, the phone's top bar, Help, the public footer; one dialog at the root", () => {
  const shell = read("src/components/Shell.tsx");
  const top = shell.indexOf('<div className="side-top">'), groups = shell.indexOf('className="side-groups"');
  const side = shell.indexOf('<FeedbackButton className="btn quiet sm side-feedback" />');
  assert.ok(top > 0 && side > top && side < groups, "in the menu's top, above the menu's entries (not the footer)");
  const bar = shell.indexOf('<header className="topbar">');
  assert.ok(shell.indexOf('<FeedbackButton className="btn quiet sm top-feedback" />') > bar, "in the phone's top bar");
  assert.match(read("src/components/Feedback.tsx"), />Feedback<\/button>/);
  assert.match(read("src/main.tsx"), /<FeedbackHost \/>/);
  assert.match(read("src/components/Feedback.tsx"), /if \(location\.hash === "#feedback"\) setOpen\(true\);/);      // a link opens it too
  assert.match(read("e2e/ui-lint-world.ts"), /"\/admin\/feedback", "\/admin\/emails", "\/help#feedback"\]/);           // the inbox and the dialog are laid out by the checker
  assert.match(read("src/components/LegalLinks.tsx"), /onClick=\{openFeedback\}>Feedback<\/button>/);
  assert.match(read("src/pages/AppGates.tsx"), /onClick=\{openFeedback\}>Report a problem or an idea<\/button>/);
  assert.match(read("src/pages/Login.tsx"), /onClick=\{openFeedback\}>Report a problem or an idea<\/button>/);
  // sent with the words: the path (no query), version, browser line, screen; nothing else from the page
  const dlg = read("src/components/Feedback.tsx");
  assert.match(dlg, /path: loc\.pathname, version: \(APP_BUILD\.sha \?\? ""\)\.slice\(0, 12\), browser: browserLine\(navigator\.userAgent\), screen: `\$\{innerWidth\}×\$\{innerHeight\}`/);
  assert.doesNotMatch(dlg, /localStorage|access_token|document\.cookie|loc\.search/);
});

test("Admin has the Feedback inbox, and new reports are in Needs your attention", () => {
  assert.match(read("src/pages/admin/AdminContext.tsx"), /\{ path: "feedback", label: "Feedback"/);
  assert.match(read("src/pages/AdminPage.tsx"), /<Route path="feedback" element=\{<FeedbackSection \/>\} \/>/);
  assert.match(read("src/pages/admin/attention.ts"), /if \(sv\.feedback_new\) out\.push\(\{ text: `\$\{plural\(sv\.feedback_new, "new feedback report"\)\} from users\.`, to: "\/admin\/feedback"/);
  const inbox = read("src/pages/admin/FeedbackSection.tsx");
  for (const h of ["When", "Type", "What they wrote", "Page", "Plan", "Reply wanted", "Status"]) assert.ok(inbox.includes(`header: "${h}"`), h);
});
