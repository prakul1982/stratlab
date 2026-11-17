/* Google sends a refused or failed sign-in back to the site with `?error=…` or `#error=…` (and an error_description) in
 * the address. This turns that into one plain sentence for the landing page to show, or null when the address carries no
 * such problem. No imports: unit/signin-error.test.mjs reads it as it is. */

/** A sign-in that came back but couldn't be completed (lib/signin.ts signInUnfinished: a one-time code the service wouldn't
 * trade, a spent emailed link). The address no longer carries anything by then, so this is the sentence (LIVE3-009). */
export const UNFINISHED_SIGNIN = "That sign-in didn't finish, so you're not signed in. This happens when sign-in starts in one browser or app and ends in another, or the link was used already. Choose Continue with Google to try again.";

export function signInProblem(search: string, hash: string, unfinished = false): string | null {
  const p = new URLSearchParams(`${search.replace(/^\?/, "")}&${hash.replace(/^#/, "")}`);
  const code = (p.get("error") || p.get("error_code") || "").toLowerCase();
  const text = (p.get("error_description") || "").replace(/\s+/g, " ").trim().slice(0, 160);
  if (!code && !text) return unfinished ? UNFINISHED_SIGNIN : null;
  if (code === "access_denied" || /access.denied|cancel/i.test(text))
    return "You're not signed in: Google sign-in was cancelled or wasn't allowed. Choose Continue with Google to try again.";
  if (/exchange external code|server_error|temporarily_unavailable/i.test(`${code} ${text}`))
    return "Google sign-in couldn't finish on our side. Try again in a moment, and write to us from the Contact page if it keeps happening.";
  return text ? `Sign-in didn't finish: ${text.replace(/[.\s]*$/, "")}. Choose Continue with Google to try again.` : "Sign-in didn't finish. Choose Continue with Google to try again.";
}

/** A plain sentence for what the sign-in service said about an email sign-in (sending the code, or the code typed in). */
export function emailSignInProblem(err: unknown, step: "send" | "verify"): string {
  const e = (err ?? {}) as { status?: number; code?: string; message?: string };
  const code = String(e.code ?? "").toLowerCase(), msg = String(e.message ?? "");
  const after = msg.match(/after (\d+) seconds?/i);
  if (after) return `For security, a new email can be sent in ${after[1]} seconds. Check your inbox and spam folder for the last one meanwhile.`;
  if (e.status === 429 || /rate.?limit/.test(code) || /rate limit/i.test(msg))
    return "Too many sign-in emails were asked for just now. Wait a few minutes, then try again, or use Continue with Google.";
  if (step === "verify" && (/otp_expired|invalid|expired/.test(code) || /expired|invalid/i.test(msg)))
    return "That code didn't work: it may be mistyped, used already or more than an hour old. Check it, or send a new one.";
  if (/email_address_invalid|validation_failed/.test(code) || /invalid.*email|email.*invalid/i.test(msg)) return "That email address doesn't look right. Check it and try again.";
  if (/provider_disabled|otp_disabled|signup_disabled/.test(code) || /disabled|not allowed/i.test(msg))
    return "Email sign-in isn't available right now. Use Continue with Google.";
  if (!e.status && /fetch|network|load failed/i.test(msg)) return "Can't reach the sign-in service. Check your connection and try again.";
  return step === "send" ? "Couldn't send the sign-in email. Try again in a moment, or use Continue with Google." : "Couldn't sign you in with that code. Try again, or send a new one.";
}

/** A typed address worth sending to: one @, a dot in the domain, no spaces. */
export const emailLooksRight = (v: string): boolean => /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()) && v.trim().length <= 254;

/** The code as typed, digits only (a pasted "123 456" or "123-456" works). */
export const codeDigits = (v: string): string => v.replace(/\D/g, "").slice(0, 10);
