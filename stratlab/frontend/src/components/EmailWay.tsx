import { useNavigate } from "react-router-dom";
import { emailSignInOn, emailSignInPath, startEmailSignIn } from "../lib/signin";
import { emailFormWithin, loadEmailForm } from "../lib/emailForm";

/** The longest a press waits for the sign-in page's email form before opening the page anyway (LIVE17B-002). */
export const EMAIL_FORM_WAIT_MS = 1500;
const warm = () => { loadEmailForm().catch(() => undefined); };

/* R61 (owner, on Release 60: "there is no option to sign in with email on the homepage"): the email way in beside a visitor's Continue with
 * Google button, opening the sign-in page with its email form ready (components/EmailSignIn.tsx). Drawn only while /config.js switches email
 * sign-in on (EMAIL_SIGNIN), and drawn at once (the switch is read before the page draws), so nothing moves when it appears.
 * R64 (owner, on Release 63: "tf is this button make it proper"): a real outlined button with a mail mark, the Google button's size, beside
 * it, never a grey "or sign in with email" text line under it. `small` matches a small Google button (the rule template's). */
const Mail = () => (
  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
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
    <a className={`btn outline${small ? " sm" : ""} email-way${className ? ` ${className}` : ""}`} href={emailSignInPath(next)} data-testid="email-way"
      onPointerEnter={warm} onFocus={warm} onTouchStart={warm}
      onClick={(e) => { e.preventDefault(); void emailFormWithin(EMAIL_FORM_WAIT_MS).then(() => startEmailSignIn(next, (u) => navigate(u))); }}>
      <Mail />{label}
    </a>
  );
}
