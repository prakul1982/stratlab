import { useRef } from "react";
import { scrollBehavior } from "../../lib/motion";

/** The way back from "Show more" (owner, 7 Nov: "whenever i click show more why there is no option to show less"): it goes back to the
 * first rows and brings the top of the section (its card) back into view, so the reader is not left far down an emptied page. Put it
 * beside every "Show N more" / "Show all N" once more than the first rows are shown. */
export function ShowLess({ onLess, label = "Show less", className = "btn quiet sm" }: { onLess: () => void; label?: string; className?: string }) {
  const me = useRef<HTMLButtonElement>(null);
  const less = () => {
    const at = me.current?.closest<HTMLElement>(".k-card, [data-section], section") ?? me.current?.parentElement ?? null;
    onLess();
    window.requestAnimationFrame(() => {
      if (!at || !at.isConnected) return;
      // only when its top has gone up past the screen: a short list already in view stays still
      if (at.getBoundingClientRect().top < 0) at.scrollIntoView({ block: "start", behavior: scrollBehavior() });
    });
  };
  return <button ref={me} type="button" className={className} data-show-less="" onClick={less}>{label}</button>;
}
