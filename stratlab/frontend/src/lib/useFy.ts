import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { askedFy, rememberFy } from "./fy";

/** The year a link asked this page to open on (`?fy=2025`), if any. A year asked for is the year now being looked at, so
 * it carries to the other Money pages like one picked by hand. */
export function useAskedFy(): number | null {
  const [sp] = useSearchParams();
  const asked = askedFy(sp.get("fy"));
  useEffect(() => { if (asked != null) rememberFy(asked); }, [asked]);
  return asked;
}
