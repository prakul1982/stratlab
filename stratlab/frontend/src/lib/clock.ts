import { useEffect, useState } from "react";

/** The start of the current minute, moving on at each minute's turn. Every "opens in …" on the page counts from this one
 * moment, so the sidebar and Home say the same thing (R48-010: "1d 4h" beside "1d 5h", worked out at different times). */
export function useMinute(): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 60000) * 60000);
  useEffect(() => {
    let t = 0;
    const next = () => {
      t = window.setTimeout(() => { setNow(Math.floor(Date.now() / 60000) * 60000); next(); }, 60000 - (Date.now() % 60000) + 50);
    };
    next();
    return () => window.clearTimeout(t);
  }, []);
  return now;
}
