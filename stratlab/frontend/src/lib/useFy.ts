import { useSearchParams } from "react-router-dom";
import { askedFy } from "./fy";

/** The year a link asked this page to open on (`?fy=2025`), if any. It is this page's alone: a year asked for or picked here
 * no longer opens the other Money pages on it (RC2B-002). */
export function useAskedFy(): number | null {
  const [sp] = useSearchParams();
  return askedFy(sp.get("fy"));
}
