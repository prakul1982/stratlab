import { useEffect, useState } from "react";
import { onCount, callsInFlight } from "../lib/inflight";

/** A thin moving bar along the top of the screen while the app waits on the server (owner, 5 Nov: "put loading bar everywhere, it creates
 * confusion whether something is working or not"). Every call to the server counts (lib/api, lib/inflight); the bar shows once a wait
 * passes SHOW_AFTER_MS, so a quick answer or a background refresh doesn't flicker it, and it finishes across the screen when the last
 * call is back. */
export const SHOW_AFTER_MS = 350;

export function TopProgress() {
  const [state, setState] = useState<"off" | "on" | "done">("off");
  useEffect(() => {
    let show: number | undefined, hide: number | undefined;
    const on = (n: number) => {
      if (n > 0) {
        window.clearTimeout(hide);
        if (show === undefined) show = window.setTimeout(() => setState("on"), SHOW_AFTER_MS);
      } else {
        window.clearTimeout(show); show = undefined;
        setState((s) => (s === "on" ? "done" : "off"));
        hide = window.setTimeout(() => setState("off"), 450);
      }
    };
    on(callsInFlight());
    const stop = onCount(on);
    return () => { stop(); window.clearTimeout(show); window.clearTimeout(hide); };
  }, []);
  if (state === "off") return null;
  return <div className={`top-progress${state === "done" ? " done" : ""}`} role="progressbar" aria-label="Loading" aria-busy={state === "on"}><span /></div>;
}
