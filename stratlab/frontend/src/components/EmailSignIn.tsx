import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { emailSignInOn, sendEmailCode, verifyEmailCode } from "../lib/signin";
import { codeDigits, emailLooksRight, emailSignInProblem } from "../lib/signinError";

/** Seconds before another email can be asked for: the sign-in service allows one a minute for an address, so the button waits too. */
export const RESEND_WAIT = 60;

/* Sign-in by email, under Continue with Google (owner, 16 Nov). The sign-in service emails a one-time code with a link: the code is
 * typed here (it works whichever app opens the email, on a phone too), or the link is opened on this device. The same address is the
 * same account as with Google (the service links them by address), and a new address makes a new account. Drawn only while
 * /config.js switches email sign-in on (EMAIL_SIGNIN), so nothing shows before the sign-in service's email provider is set up. */
export function EmailSignIn({ next, signup = false }: { next?: string | null; signup?: boolean }) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  // R61: opened from an "or sign in with email" link (/login#email), the address box is ready to type in
  const box = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (location.hash !== "#email" || !box.current) return;
    box.current.focus({ preventScroll: true });
    box.current.scrollIntoView({ block: "center" });
  }, []);
  useEffect(() => {
    if (wait <= 0) return;
    const t = window.setTimeout(() => setWait((w) => w - 1), 1000);
    return () => window.clearTimeout(t);
  }, [wait]);
  if (!emailSignInOn()) return null;

  const send = async (to: string) => {
    if (busy || wait > 0) return;
    if (!emailLooksRight(to)) { setError("That email address doesn't look right. Check it and try again."); return; }
    setBusy(true); setError(null);
    try {
      const { error: e } = await sendEmailCode(to.trim(), next);
      if (e) { setError(emailSignInProblem(e, "send")); return; }
      setSentTo(to.trim()); setCode(""); setWait(RESEND_WAIT);
    } catch (e) { setError(emailSignInProblem(e, "send")); }
    finally { setBusy(false); }
  };
  const onSend = (e: FormEvent) => { e.preventDefault(); void send(email); };
  const onVerify = async (e: FormEvent) => {
    e.preventDefault();
    const digits = codeDigits(code);
    if (!sentTo || busy) return;
    if (digits.length < 6) { setError("Type the code from the email: it is 6 or more digits."); return; }
    setBusy(true); setError(null);
    try {
      const { error: err } = await verifyEmailCode(sentTo, digits);
      if (err) { setError(emailSignInProblem(err, "verify")); setBusy(false); return; }
      // signed in: the app opens from the start, and then the page kept for after sign-in (lib/returnTo)
      location.assign("/");
    } catch (err) { setError(emailSignInProblem(err, "verify")); setBusy(false); }
  };

  return (
    <div className="email-signin" data-testid="email-signin">
      <p className="email-signin-or" aria-hidden="true"><span>or</span></p>
      {!sentTo ? (
        <form className="email-signin-form" onSubmit={onSend} noValidate>
          <label htmlFor={`${id}-email`} className="email-signin-label">{signup ? "Sign up" : "Sign in"} with email</label>
          <div className="email-signin-row">
            <input ref={box} id={`${id}-email`} className="k-input" type="email" name="email" autoComplete="email" inputMode="email" placeholder="you@example.com"
              value={email} onChange={(e) => setEmail(e.target.value)} aria-describedby={`${id}-help`} aria-invalid={!!error || undefined} />
            <button type="submit" className="btn outline" disabled={busy || wait > 0}>{busy ? "Sending…" : wait > 0 ? `Email me a code (${wait}s)` : "Email me a code"}</button>
          </div>
          <span id={`${id}-help`} className="small muted">We email a one-time code and link. No password.</span>
        </form>
      ) : (
        <form className="email-signin-form" onSubmit={onVerify} noValidate>
          <p className="small" role="status" data-testid="email-sent">We sent a sign-in code to <b>{sentTo}</b>. Type it here, or open the link in the email on this device. Check spam if it isn't there in a minute.</p>
          <label htmlFor={`${id}-code`} className="email-signin-label">Sign-in code</label>
          <div className="email-signin-row">
            <input id={`${id}-code`} className="k-input email-signin-code" type="text" name="code" autoComplete="one-time-code" inputMode="numeric"
              pattern="[0-9]*" maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} aria-invalid={!!error || undefined} />
            <button type="submit" className="btn" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          </div>
          <div className="email-signin-row">
            <button type="button" className="btn quiet sm" disabled={busy || wait > 0} onClick={() => void send(sentTo)}>{wait > 0 ? `Send again in ${wait}s` : "Send a new code"}</button>
            <button type="button" className="btn quiet sm" disabled={busy} onClick={() => { setSentTo(null); setError(null); setCode(""); }}>Use another email</button>
          </div>
        </form>
      )}
      {error && <p className="banner" role="alert" data-testid="email-error">{error}</p>}
    </div>
  );
}
