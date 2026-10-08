/* "View as": the site owner can see the app as a Free, Basic or Pro user would, without changing their own plan. The choice
 * is kept on this device and sent with every request in the X-View-As header; the server honours it for the owner only
 * (auth.current_profile), so the same plan locks, upgrade prompts and limits show on the live site. Plain functions with no
 * React or network in them, so the words and the storage can be tested alone. */

export type ViewAs = "free" | "basic" | "pro";
export type ViewAsChoice = ViewAs | "off";

export const VIEW_AS_KEY = "stratlab.viewas.v1";
export const VIEW_AS_HEADER = "X-View-As";

export const VIEW_AS_NAME: Record<ViewAs, string> = { free: "Free", basic: "Basic", pro: "Pro" };
/** The choices in the order they are shown: "View as: Free / Basic / Pro / Off". */
export const VIEW_AS_CHOICES: { value: ViewAsChoice; label: string }[] = [
  { value: "free", label: "Free" }, { value: "basic", label: "Basic" }, { value: "pro", label: "Pro" }, { value: "off", label: "Off" },
];

/** A stored or typed value as a plan to view as, or null (off) for anything else. */
export function parseViewAs(v: unknown): ViewAs | null {
  const s = typeof v === "string" ? v.trim().toLowerCase() : "";
  return s === "free" || s === "basic" || s === "pro" ? s : null;
}

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
let memory: ViewAs | null = null;        // when storage is off (a private window) the choice lives until the page closes

function store(): Store | null {
  try { return globalThis.localStorage ?? null; } catch { return null; }
}

/** The choice kept on this device: null when it is off. */
export function readViewAs(s: Store | null = store()): ViewAs | null {
  try {
    const raw = s?.getItem(VIEW_AS_KEY);
    if (raw != null) return parseViewAs(raw);
  } catch { /* storage off */ }
  return memory;
}

/** Keep the choice (null turns it off). */
export function writeViewAs(v: ViewAs | null, s: Store | null = store()): void {
  memory = v;
  try {
    if (v) s?.setItem(VIEW_AS_KEY, v);
    else s?.removeItem(VIEW_AS_KEY);
  } catch { /* storage off */ }
}

/** The header to send with a request: nothing while it is off. */
export function viewAsHeaders(s: Store | null = store()): Record<string, string> {
  const v = readViewAs(s);
  return v ? { [VIEW_AS_HEADER]: v } : {};
}

/** The banner's sentence, shown on every page while it is on. The "Turn off" button follows it. */
export function viewAsBanner(plan: ViewAs): string {
  return `Viewing as ${VIEW_AS_NAME[plan]}. Your real plan is unchanged.`;
}

/** What a choice sets: a plan, or null for Off. */
export function choiceToPlan(c: string): ViewAs | null {
  return c === "off" ? null : parseViewAs(c);
}

/** The choice to mark in the control for the plan being viewed (Off when none). */
export function planToChoice(plan: ViewAs | null | undefined): ViewAsChoice {
  return plan ?? "off";
}
