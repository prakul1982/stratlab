import { AuthClient } from "@supabase/auth-js";

declare global {
  interface Window {
    STRATLAB_CONFIG?: { API_BASE: string; SUPABASE_URL: string; SUPABASE_ANON_KEY: string; SENTRY_DSN?: string;
      BUSINESS_NAME?: string; CONTACT_EMAIL?: string; BUSINESS_ADDRESS?: string };
    Razorpay?: any;
  }
}

export const CFG: NonNullable<Window["STRATLAB_CONFIG"]> = window.STRATLAB_CONFIG ?? { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" };

// Error alerts: only when a Sentry DSN is in config.js, and the SDK is only downloaded then.
if (CFG.SENTRY_DSN) {
  import("@sentry/browser").then((S) => S.init({ dsn: CFG.SENTRY_DSN, environment: location.hostname,
    // nothing personal: no user fields, cookies, headers, bodies or query strings
    dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false },
    ignoreErrors: ["ResizeObserver loop", "AbortError", "Failed to fetch", "Load failed", "NetworkError"] })).catch(() => {});
}
// Only sign-in is used, so the standalone auth client is loaded rather than the whole Supabase client (database,
// storage, realtime): the same settings the full client would use, down to the storage key, so saved logins carry over.
const sbBase = new URL((CFG.SUPABASE_URL || "http://localhost").replace(/\/?$/, "/"));
const sbKey = CFG.SUPABASE_ANON_KEY || "missing";
/** Where the saved login lives in localStorage. */
export const SESSION_KEY = `sb-${sbBase.hostname.split(".")[0]}-auth-token`;
export const supabase = {
  auth: new AuthClient({
    url: new URL("auth/v1", sbBase).href,
    headers: { Authorization: `Bearer ${sbKey}`, apikey: sbKey },
    storageKey: SESSION_KEY,
    autoRefreshToken: true, persistSession: true, detectSessionInUrl: true, flowType: "implicit",
  }),
};

export class ApiError extends Error {
  status = 0;
  code?: string;
}

type Opts = { method?: string; body?: unknown; raw?: boolean };

let onUnauthorized: () => void = () => {};
let onOffline: () => void = () => {};
export function setApiHandlers(h: { unauthorized: () => void; offline: () => void }) {
  onUnauthorized = h.unauthorized;
  onOffline = h.offline;
}

export async function api<T = any>(path: string, { method = "GET", body, raw = false }: Opts = {}): Promise<T> {
  if (!CFG.API_BASE) {
    const e = new ApiError("The StratLab server isn't connected yet (API_BASE in config.js).");
    e.code = "no_backend";
    throw e;
  }
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  let r: Response;
  try {
    r = await fetch(CFG.API_BASE + path, {
      method,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    const e = new ApiError("Can't reach the StratLab server. Check your connection and try again.");
    e.code = "network";
    throw e;
  }
  if (raw && r.ok) return r as unknown as T;
  let payload: any = null;
  try {
    payload = await r.json();
  } catch {
    /* empty body */
  }
  if (!r.ok) {
    const d = payload?.detail;
    const msg = (d && (d.message || (typeof d === "string" ? d : ""))) ||
      (Array.isArray(d) ? invalidMessage(d) : "") ||
      `Something went wrong (${r.status}). Try again.`;
    const e = new ApiError(msg);
    e.status = r.status;
    e.code = d?.code;
    if (r.status === 401) onUnauthorized();
    if (d?.code === "data_offline") onOffline();
    throw e;
  }
  return payload as T;
}

const FIELD_HELP: Record<string, string> = {
  alert_email: "That email address doesn't look right.",
  telegram_chat_id: "The Telegram chat ID is a number, like 123456789 (from @userinfobot).",
  endpoint: "This browser's notification service isn't supported.",
};

/** A readable message for FastAPI's list of invalid fields. */
function invalidMessage(items: { loc?: (string | number)[] }[]): string {
  for (const it of items) {
    const field = [...(it.loc ?? [])].reverse().find((x) => typeof x === "string" && FIELD_HELP[x as string]);
    if (field) return FIELD_HELP[field as string];
  }
  return "Some settings are out of range. Check the numbers and try again.";
}

export async function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return;
  await new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load the payment window. Check your connection."));
    document.head.appendChild(s);
  });
}
