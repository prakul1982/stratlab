/* The Markets button on the public pages (MW-1), and nothing else of Market Watch: the policy pages and the landing page are held to
 * a download size (R5V-020), so the button is drawn from here and the launcher (the panel's place, its saved size, the loading of the
 * board) comes with the first press, or at once when the panel was left open on this device. */
import { lazy, Suspense, useCallback, useState, type ComponentType } from "react";
import { importWithRetry } from "../../lib/lazyRetry";
import { useConsentLift } from "../../lib/consentLift";
import { LAYOUT_KEY, isSheet } from "../../lib/watchKey";
import { Markets } from "../Icons";
import "./launcher.css";

const load = () => import("./Launcher").then((m) => ({ default: m.MarketsLauncher }));
const Full = lazy(() => importWithRetry(load)) as unknown as ComponentType<{ mode: "app" | "public"; userId?: string; button: "public"; autoOpen?: boolean }>;

/** Left open on a wide screen last time (a sheet is never open at load: the launcher says why). Storage may be blocked: then not open. */
function leftOpen(key: string): boolean {
  try { return !isSheet(window.innerWidth) && JSON.parse(localStorage.getItem(key) ?? "null")?.open === true; } catch { return false; }
}

export function PublicMarkets({ userId }: { userId?: string }) {
  const mode = userId ? "app" : "public";
  const [full, setFull] = useState<"no" | "left" | "pressed">(() => (leftOpen(`${LAYOUT_KEY}.${userId ?? "visitor"}`) ? "left" : "no"));
  useConsentLift(full === "no");
  const ahead = useCallback(() => void load().catch(() => undefined), []);
  if (full !== "no") return <Suspense fallback={null}><Full mode={mode} userId={userId} button="public" autoOpen={full === "pressed"} /></Suspense>;
  return (
    <button type="button" className="mw-launch public" aria-label="Open Market Watch" aria-expanded={false} data-testid="markets-launch"
      onClick={() => setFull("pressed")} onPointerEnter={ahead} onFocus={ahead}>
      <Markets size={18} /><span>Markets</span>
    </button>
  );
}
