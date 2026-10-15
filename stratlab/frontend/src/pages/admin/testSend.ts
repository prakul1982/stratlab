/** Admin → Email previews → "Send me a test": the line that stays under the button after each press (R23-009: the
 * 4.5 s toast was the only answer, and a press that repeated the last toast's words looked like no answer at all). The
 * time makes each press's line its own. */

const two = (n: number) => String(n).padStart(2, "0");

export function clock(at: Date): string {
  return `${two(at.getHours())}:${two(at.getMinutes())}:${two(at.getSeconds())}`;
}

export function sentLine(subject: string, to: string, at: Date): string {
  return `"${subject}" sent to ${to} at ${clock(at)}. Check your inbox (and spam).`;
}

export function sendErrorLine(e: unknown, at: Date): string {
  const msg = (e as { message?: unknown } | null)?.message;
  const why = typeof msg === "string" && msg.trim() ? msg.trim().replace(/\.?$/, ".") : "The test email couldn't be sent. Try again.";
  return `Not sent (${clock(at)}): ${why}`;
}
