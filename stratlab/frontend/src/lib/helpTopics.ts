import { HELP } from "./help";

/** The (i) explanations people ask about by name, with the words they use, so a question in search ("what is a
 * walk-forward test?", "how is the drawdown worked out?") finds the explanation already written for it. */
export interface HelpTopic { key: keyof typeof HELP; title: string; words: string; text: string }

const TOPICS: [keyof typeof HELP, string, string][] = [
  ["walkforward", "Walk-forward test", "walk forward walkforward out of sample retune re-tune optimise optimize"],
  ["unseen", "The unseen-data check", "unseen out of sample 70 30 split tuned overfit overfitting"],
  ["nearby", "The nearby-settings check", "nearby settings parameters lengths robust overfit curve fit"],
  ["shuffle", "The reshuffle check", "shuffle reshuffle monte carlo order drawdown"],
  ["sample", "Enough trades", "sample size number of trades enough few"],
  ["verdict", "The verdict", "verdict edge luck real result"],
  ["strength", "Checks passed", "strength checks passed honesty"],
  ["basket", "Does it work on similar stocks?", "similar stocks instruments peers basket robustness"],
  ["sharpe", "Sharpe ratio", "sharpe ratio risk adjusted return volatility"],
  ["profitFactor", "Profit factor", "profit factor winners losers"],
  ["worstFall", "Worst fall (maximum drawdown)", "drawdown max maximum dd worst fall peak trough"],
  ["winRate", "Win rate", "win rate winning percentage hit rate accuracy"],
  ["buyHold", "Buy and hold", "buy and hold benchmark holding"],
  ["totalReturn", "Total return", "total return profit loss"],
  ["avgTrade", "Average trade", "average trade per trade expectancy"],
  ["keep", "Profit after costs", "costs charges brokerage stt stamp duty gst fees tax after costs"],
  ["stop", "Stop loss", "stop loss sl stoploss"],
  ["target", "Target", "target take profit tp"],
  ["trail", "Trailing stop", "trailing trail stop"],
  ["stopUnits", "Stops in percent, points or ATR", "stop units percent points atr average true range"],
  ["risk", "Risk per trade and position size", "risk position size sizing quantity how many shares"],
  ["short", "Selling short", "short selling shorting sell first"],
  ["candles", "Candles and timeframes", "candle candles candlestick timeframe interval daily hourly"],
  ["crosses", "Crosses above or is above?", "crosses cross above crossover is above"],
  ["maxBars", "Closing after a number of candles", "max bars candles time exit time stop"],
  ["session", "Intraday session rules", "intraday session square off entry window"],
  ["period", "How far back to test", "period history years how long back"],
  ["capital", "Starting capital", "capital starting money"],
  ["equity", "The equity curve", "equity curve account value"],
  ["paper", "Paper trading", "paper trading fake money simulate forward test live"],
  ["group", "Testing a whole group", "group basket portfolio many stocks one pot"],
  ["csv", "Your own prices (CSV)", "csv upload prices spreadsheet own data"],
  ["notebook", "Notebooks", "notebook notebooks"],
  ["experimentsQuota", "Experiments in your plan", "experiments allowance quota monthly limit"],
  ["optVix", "The India VIX filter", "vix india vix volatility filter"],
  ["optStrikeRule", "How strikes are picked", "strike strikes delta atm at the money premium pick"],
  ["optFreeze", "Freeze limit", "freeze limit quantity slices"],
  ["optBacktest", "Backtesting options", "options backtest history expired strikes"],
  ["research52", "52-week range", "52 week range high low"],
  ["researchMargins", "Margins", "margin margins gross operating net"],
  ["researchHolding", "Shareholding", "shareholding promoters fii dii holding"],
  ["researchEarnings", "Earnings against estimates", "earnings eps estimates beat miss"],
];

export const HELP_TOPICS: HelpTopic[] = TOPICS.map(([key, title, words]) => ({ key, title, words, text: HELP[key] }));

const STOP = new Set(["what", "whats", "is", "are", "a", "an", "the", "how", "does", "do", "did", "i", "my", "me", "to", "of",
  "in", "on", "for", "and", "or", "it", "its", "why", "which", "when", "where", "can", "should", "you", "your", "was", "be",
  "with", "about", "explain", "mean", "means", "meaning", "this", "that", "there", "work", "works", "tell", "s"]);

/** The words of a search that carry meaning: lower case, punctuation gone ("walk-forward?" → walk, forward), without
 * the words every question has ("what", "is", "the") unless nothing else is left. */
export function searchWords(q: string): string[] {
  const words = q.toLowerCase().replace(/(\w)-(\w)/g, "$1 $2").split(/\s+/)
    .map((w) => w.replace(/^[^\w&/+]+|[^\w&/+]+$/g, "").replace(/['’]s$/, "")).filter((w) => w.length > 1);
  const kept = words.filter((w) => !STOP.has(w));
  return kept.length ? kept : words;
}

/** Explanations for a search, best first: every word it names should be in the topic's title or words. */
export function matchHelp(q: string, limit = 3): HelpTopic[] {
  const words = searchWords(q);
  if (!words.length) return [];
  const phrase = words.join(" ");
  return HELP_TOPICS.map((t) => {
    const title = t.title.toLowerCase().replace(/-/g, " ");
    const hay = ` ${title} ${t.words} `;
    const hits = words.filter((w) => hay.includes(` ${w}`));
    let s = hits.reduce((n, w) => n + (title.includes(w) ? 3 : 1), 0);
    if (words.length > 1 && hay.includes(phrase)) s += 4;
    return [hits.length / words.length >= 0.5 ? s : 0, t] as const;
  }).filter(([s]) => s > 0).sort((a, b) => b[0] - a[0]).slice(0, limit).map(([, t]) => t);
}
