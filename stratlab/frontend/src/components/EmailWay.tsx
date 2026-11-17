import { emailSignInOn, EMAIL_SIGNIN_PATH, startEmailSignIn } from "../lib/signin";

/* R61 (owner, on Release 60: "there is no option to sign in with email on the homepage"): a small "or sign in with email" beside a
 * visitor's Continue with Google button, opening the sign-in page with its email form ready (components/EmailSignIn.tsx). Drawn only
 * while /config.js switches email sign-in on (EMAIL_SIGNIN), and drawn at once (the switch is read before the page draws), so nothing
 * moves when it appears. Small and kept out of the sign-in library's download: it is a link. */
export function EmailWay({ next, className }: { next?: string | null; className?: string }) {
  if (!emailSignInOn()) return null;
  return (
    <span className={`small email-way${className ? ` ${className}` : ""}`} data-testid="email-way">
      or <a className="link" href={EMAIL_SIGNIN_PATH} onClick={(e) => { e.preventDefault(); startEmailSignIn(next); }}>sign in with email</a>
    </span>
  );
}
