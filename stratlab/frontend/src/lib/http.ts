/* The smallest piece of talking to the server: the error type and a read that needs no account. Pages that anyone can
 * open (the landing page's prices, the policies, a shared verdict, the public library) use `publicGet`, so they don't
 * download the sign-in library just to ask a public question. */
import { CFG } from "./config";

export class ApiError extends Error {
  status = 0;
  code?: string;
  /** For a 422: each field the server turned down, with what's wrong in plain words and its limit (lib/validate). */
  fields?: Record<string, string>;
}

/** The server's answer to a public address, no sign-in. A failure is an `ApiError` with the server's own words. */
export async function publicGet<T = any>(path: string, signal?: AbortSignal): Promise<T> {
  if (!CFG.API_BASE) {
    const e = new ApiError("The StratLab server isn't connected yet (API_BASE in config.js).");
    e.code = "no_backend";
    throw e;
  }
  let r: Response;
  try {
    r = await fetch(CFG.API_BASE + path, { headers: { Accept: "application/json" }, signal });
  } catch (x) {
    if ((x as Error)?.name === "AbortError") throw x;
    const e = new ApiError("Can't reach the StratLab server. Check your connection and try again.");
    e.code = "network";
    throw e;
  }
  let payload: any = null;
  try { payload = await r.json(); } catch { /* empty body */ }
  if (!r.ok) {
    const d = payload?.detail;
    const e = new ApiError((d && (d.message || (typeof d === "string" ? d : ""))) || `Something went wrong (${r.status}). Try again.`);
    e.status = r.status;
    e.code = d?.code;
    throw e;
  }
  return payload as T;
}
