import { useEffect, useState } from "react";

/** A placeholder that cycles through concrete examples. A real example teaches what to type better than "Search…",
 * and a changing one shows the range without a wall of text. Slow enough to read; stops when the page is hidden. */
export function useRotating(items: string[], ms = 3800): string {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (items.length < 2) return;
    const t = window.setInterval(() => { if (!document.hidden) setI((x) => (x + 1) % items.length); }, ms);
    return () => window.clearInterval(t);
  }, [items.length, ms]);
  return items[i % Math.max(1, items.length)] ?? "";
}

/** Examples for the "ask or do anything" box, the ones matching what the user came for first. */
export function askExamples(focus: string | null): string[] {
  const invest = ["Deep dive Apollo Hospitals", "Which sectors are leading right now?", "Red flags in my watchlist",
    "Stage 2 stocks in NIFTY 50", "Compare TCS and Infosys"];
  const trade = ["Test: buy NIFTY when RSI drops below 30", "Paper trade a 20/50 EMA cross on Bitcoin",
    "Short straddle on BANKNIFTY", "What is a walk-forward test?", "Momentum ideas for bank stocks"];
  const mix = (a: string[], b: string[]) => a.flatMap((x, k) => [x, b[k]]).filter(Boolean);
  return focus === "invest" ? mix(invest, trade.slice(0, 2)) : focus === "trade" ? mix(trade, invest.slice(0, 2)) : mix(invest, trade);
}
