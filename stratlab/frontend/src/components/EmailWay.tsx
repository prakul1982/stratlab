import { flushSync } from "react-dom";
import { useNavigate } from "react-router-dom";
import { emailSignInOn, emailSignInPath, startEmailSignIn } from "../lib/signin";
import { emailFormWithin, loadEmailForm } from "../lib/emailForm";

/** The longest a press waits for the sign-in page's email form before opening the page anyway (LIVE17B-002). fix98: 1.5 s let a slow
 * phone open /login before the form's code was here, a frame without the form (CI's site80 on a phone); the press now waits for the code
 * itself, the button showing it is busy, and only a download stuck this long opens the page, which then waits for the form as a whole
 * page (pages/Login.tsx), never drawn with an empty band. */
export const EMAIL_FORM_WAIT_MS = 15000;
const warm = () => { loadEmailForm().catch(() => undefined); };

/* R61 (owner, on Release 60: "there is no option to sign in with email on the homepage"): the email way in beside a visitor's Continue with
 * Google button, opening the sign-in page with its email form ready (components/EmailSignIn.tsx). Drawn only while /config.js switches email
 * sign-in on (EMAIL_SIGNIN), and drawn at once (the switch is read before the page draws), so nothing moves when it appears.
 * R64 (owner, on Release 63: "tf is this button make it proper"): a real outlined button with a mail mark, the Google button's size, beside
 * it, never a grey "or sign in with email" text line under it. `small` matches a small Google button (the rule template's). */
// fix98: its size and stroke are set in styles.css (.email-way > svg), so the landing page's code stays inside its budget (review-r5 R5V-020)
const Mail = () => (
  <svg aria-hidden="true" viewBox="0 0 24 24">
    <rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3.5 6.5 8.5 6.5 8.5-6.5" />
  </svg>
);

/** `label`: the button's words when they name what it starts (LIVE12B-024: a plan card's "Sign in with email to get Basic", beside its Google
 * button's "Continue with Google to get Basic", not a bare sign-in). */
export function EmailWay({ next, className, small = false, label = "Sign in with email" }: { next?: string | null; className?: string; small?: boolean; label?: string }) {
  const navigate = useNavigate();
  if (!emailSignInOn()) return null;
  // LIVE16B-001: a plan card's choice goes along (/login?plan=basic#email), and the sign-in page opens in place, not by loading the site again
  return (
    // LIVE17B-002: the sign-in page's email form is asked for as the pointer or focus reaches the button, and the page opens once it is here
    // (at most EMAIL_FORM_WAIT_MS), so it is drawn with the form in place, never an empty band where the form goes
    // fix98: pressed, it shows it is busy (aria-busy, the pressed look) until the form's code is here, then opens the page
    <a className={`btn outline${small ? " sm" : ""} email-way${className ? ` ${className}` : ""}`} href={emailSignInPath(next)} data-testid="email-way"
      onPointerEnter={warm} onFocus={warm} onTouchStart={warm}
      // fix98: the address and the sign-in page change in one go (flushSync): a navigation from a promise is rendered in a later task, and a
      // slow phone painted a frame at /login still showing /plans, without the form (CI's site80 on a phone)
      onClick={(e) => { e.preventDefault(); void emailFormWithin(EMAIL_FORM_WAIT_MS).then(() => startEmailSignIn(next, (u) => flushSync(() => navigate(u)))); }}>
      <Mail />{label}
    </a>
  );
}
