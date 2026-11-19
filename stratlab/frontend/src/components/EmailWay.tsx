import { useNavigate } from "react-router-dom";
import { emailSignInOn, emailSignInPath, startEmailSignIn } from "../lib/signin";

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
    <a className={`btn outline${small ? " sm" : ""} email-way${className ? ` ${className}` : ""}`} href={emailSignInPath(next)} data-testid="email-way"
      onClick={(e) => { e.preventDefault(); startEmailSignIn(next, (u) => navigate(u)); }}>
      <Mail />{label}
    </a>
  );
}
