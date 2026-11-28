/* The rarely needed half of lib/analyticsGate (conv101, T1 and T2), loaded only when the address asks for it (?internal=, ?from=) or at a
 * sign-up, so the landing page's download stays inside its budget (review-r5). */
import { markInternal } from "./analyticsGate";

/** ?internal=1 (or 0) in the address: set or clear the mark, and say so on the page for a few seconds. Returns what it did. */
export function readInternalSwitch(search: string = typeof location === "undefined" ? "" : location.search): "on" | "off" | null {
  const v = new URLSearchParams(search).get("internal");
  if (v !== "1" && v !== "0") return null;
  markInternal(v === "1");
  if (typeof document !== "undefined" && document.body) {
    const note = document.createElement("div");
    note.setAttribute("role", "status");
    note.setAttribute("data-internal-note", v);
    note.textContent = v === "1" ? "This device is now left out of StratLab's analytics." : "This device is counted in StratLab's analytics again.";
    note.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:9999;background:#1D1B17;color:#F5F1E8;padding:10px 16px;border-radius:10px;font:14px/1.4 system-ui,sans-serif;max-width:calc(100vw - 32px)";
    document.body.appendChild(note);
    window.setTimeout(() => note.remove(), 6000);
  }
  return v === "1" ? "on" : "off";
}

/** Where the visit came from, carried into the sign-up: ?from=stock|theme|blog|… on a link from a page the server draws, kept 30 days. */
const FROM_KEY = "stratlab.from";
const FROM = /^[a-z][a-z0-9_-]{0,23}$/;
export function rememberFrom(search: string = typeof location === "undefined" ? "" : location.search): void {
  const v = new URLSearchParams(search).get("from");
  if (!v || !FROM.test(v)) return;
  try { localStorage.setItem(FROM_KEY, JSON.stringify({ v, at: Date.now() })); } catch { /* storage off */ }
}
export function signupFrom(): string | null {
  try {
    const j = JSON.parse(localStorage.getItem(FROM_KEY) || "null");
    return j && typeof j.v === "string" && FROM.test(j.v) && Date.now() - j.at < 30 * 86_400_000 ? j.v : null;
  } catch { return null; }
}
