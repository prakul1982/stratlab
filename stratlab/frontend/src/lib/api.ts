import { createClient } from "@supabase/supabase-js";

declare global {
  interface Window {
    STRATLAB_CONFIG?: { API_BASE: string; SUPABASE_URL: string; SUPABASE_ANON_KEY: string };
    Razorpay?: any;
  }
}

export const CFG = window.STRATLAB_CONFIG ?? { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" };
export const supabase = createClient(CFG.SUPABASE_URL || "http://localhost", CFG.SUPABASE_ANON_KEY || "missing");

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
      (Array.isArray(d) ? "Some settings are out of range. Check the numbers and try again." : "") ||
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
