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

/** Public reads started before the page's code arrived (entry.tsx), each taken once by the page that asks for it. */
const early = new Map<string, Promise<unknown>>();

/** Start a public read now, while the page's code is still downloading (R8V-013: /library showed "Opening StratLab…"
 * for about 3 s, its one question to the server asked only after some forty files). The page's own `publicGet` for the
 * same address then takes this answer instead of asking again. */
export function prefetchPublic(path: string): void {
  if (!CFG.API_BASE || early.has(path)) return;
  const got = readPublic(path);
  got.catch(() => undefined);             // a failure is the page's to report, when it asks
  early.set(path, got);
}

/** The server's answer to a public address, no sign-in. A failure is an `ApiError` with the server's own words. */
export async function publicGet<T = any>(path: string, signal?: AbortSignal): Promise<T> {
  const ahead = early.get(path);
  if (ahead) {
    early.delete(path);                    // once: asking again (a retry, a later visit) reads afresh
    return ahead as Promise<T>;
  }
  return readPublic<T>(path, signal);
}

async function readPublic<T = any>(path: string, signal?: AbortSignal): Promise<T> {
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
