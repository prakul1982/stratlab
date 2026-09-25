export type RefType =
  | "price" | "num" | "sma" | "ema" | "rsi" | "macd" | "macd_signal" | "macd_hist"
  | "bb_upper" | "bb_mid" | "bb_lower" | "vwap" | "supertrend"
  | "adx" | "stoch_k" | "atr_pct" | "dc_upper" | "dc_lower" | "volume" | "vol_sma"
  | "open" | "high" | "low" | "body" | "upper_wick" | "lower_wick" | "range" | "atr"
  | "prev_close" | "day_open" | "day_high" | "day_low" | "day_chg";
export type Op = "xa" | "xb" | "gt" | "lt";
export type Tf = "1d" | "1h" | "15m" | "5m";
export type HigherTf = "15m" | "1h" | "1d";

export interface Ref { t: RefType; p?: number | null; m?: number | null; v?: number | null; ago?: number | null; k?: number | null; tf?: HigherTf | null }
export interface Cond { l: Ref; op: Op; r: Ref; w?: number | null }
export interface Risk {
  capital: number; riskPct: number; maxAlloc: number; sl: number; tgt: number; brokerage: number; slippage: number;
  trail?: number; maxBars?: number;
  stopType?: "pct" | "points" | "atr" | "swing"; tgtType?: "pct" | "points" | "r";
  sizing?: "risk" | "capital"; perTrade?: number; leverage?: number;
}
export interface Session { start: string; end: string; squareoff: string; maxTradesDay: number; cooldown: number; dailyLossPct: number }
export interface Strategy {
  name: string; tf: Tf; text: string; entry: Cond[]; exit: Cond[]; entryJoin: "all" | "any" | "score"; risk: Risk;
  side?: "long" | "short" | "both"; minScore?: number; shortEntry?: Cond[]; shortExit?: Cond[];
  session?: Session; product?: "auto" | "delivery" | "intraday";
}

export interface Instrument {
  id: string; token?: number | string | null; symbol: string; name?: string; exchange?: string; type?: string;
  market?: string; currency?: string; step?: number; lot?: number; fno?: boolean; expiry?: string | null;
  strike?: number | null; tz?: string;
}

export interface Market {
  id: string; name: string; venues: string; currency: string | null; symbol: string; tz: string;
  hours: { open: string | null; close: string | null; days: string } | null; what: string; costs: string;
  provider: string | null; brokerage: number; status: "live" | "offline" | "soon"; max_days: Record<Tf, number> | null;
}

export type VerdictKind = "edge" | "mixed" | "luck" | "not_enough" | "no_edge";
export type CheckStatus = "pass" | "warn" | "fail" | "skip";

export interface Check {
  id: "unseen" | "nearby" | "shuffle" | "sample"; title: string; status: CheckStatus; detail: string;
  data: any;
}
export interface Verdict {
  verdict: VerdictKind; headline: string; summary: string; passed: number; total: number; checks: Check[];
  suggestions: { action: string; text: string }[];
}
export interface Stats {
  ret: number; pnl: number; cagr: number; mdd: number; sharpe: number; n: number; win: number;
  pf: number | null; avg: number; buy_hold_ret: number;
}
export interface Costs {
  gross_pnl: number; total: number; items: { label: string; amount: number }[]; net_pnl: number;
  tax: { amount: number | null; note: string }; kept: number;
}
export interface Trade {
  entry_t: string; exit_t: string | null; entry: number; exit: number; qty: number; pnl: number;
  costs?: number; ret: number; why: string; side?: "long" | "short"; symbol?: string;
}
export interface GroupMember { id?: string; symbol: string }
export interface Group { id: string; name: string; market: string; maxOpen: number; members: GroupMember[] }
export interface GroupResult {
  name: string; max_open: number; most_open: number; skipped: string[];
  members: { symbol: string; id: string; trades: number; pnl: number; win: number | null; buy_hold: number | null }[];
}
export interface Experiment {
  v: number; label: string; created_at: string; strategy: Strategy; instrument: Instrument; days: number; tf: Tf;
  candles: number; range: { from: string; to: string }; stats: Stats; costs: Costs; verdict: Verdict;
  series: { t: string[]; close: number[]; equity: (number | null)[]; buy_hold: (number | null)[];
    overlays: Record<string, (number | null)[]>; split: number | null };
  trades: Trade[];
  basket?: Basket;
  group?: GroupResult;
  walkforward?: WalkForward;
  public?: string;          // the token of its public link, when one is on
}
export interface WFWindow {
  train_from: string; train_to: string; test_from: string; test_to: string;
  chosen: { label: string; value: number; yours: number }[]; train_ret: number; test_ret: number; fixed_ret: number; trades: number;
}
export interface WalkForward {
  status: "pass" | "warn" | "fail" | "skip"; headline: string; detail: string; windows: WFWindow[];
  wf_ret?: number; fixed_ret?: number; buy_hold_ret?: number; profitable?: number; total?: number; trades?: number;
  efficiency?: number | null; settings_used?: number; tuned?: string[]; grid_size?: number; from?: string; to?: string;
  series?: { t: string[]; wf: number[]; fixed: number[] };
}
export interface BasketRow { id: string; symbol: string; name?: string | null; ret?: number; buy_hold?: number; n?: number; win?: number; mdd?: number; error?: string }
export interface Basket {
  status: "pass" | "warn" | "fail"; headline: string; market: string; days: number; tested: number; profitable: number;
  beat_buy_hold: number; median_ret: number | null; rows: BasketRow[];
}
export interface NotebookSummary { experiments: number; last_verdict: VerdictKind | null; last_label: string | null }
export interface NotebookItem {
  id: string; name: string; question: string | null; instrument: Instrument | { id: string } | null;
  summary: NotebookSummary | null; updated_at: string; tf?: Tf | null; pinned?: boolean;
}
export interface Notebook extends NotebookItem {
  kind: "notebook"; notes: string; strategy: Strategy; instrument: Instrument | null; experiments: Experiment[];
  group?: Group | null;
}

export interface PlanInfo {
  name: string; price: number; backtests_per_month: number | null; ai_builds_per_month: number | null;
  live_limit: number; live_trial_hours: number | null; pro_features: boolean;
}
export interface Me {
  id: string; email: string | null; plan: "free" | "basic" | "pro"; plan_info: PlanInfo;
  billing: { subscribed_plan: string | null; status: string | null; renews_or_ends: string | null; cancel_at_period_end: boolean };
  usage: { backtests_used: number; backtests_limit: number | null; ai_used: number; ai_limit: number | null };
  trial: { started: boolean; active: boolean; ends_at: string | null; available: boolean } | null;
  live_running: number; live_limit: number;
  alerts: { enabled: boolean; telegram_chat_id: string | null; email: string | null };
  data_online: boolean; billing_enabled?: boolean; is_admin?: boolean;
}

export interface LiveEvent { t: string; side: "buy" | "sell"; px: number; qty: number; why: string; pnl?: number }
export interface LiveOrder { side: "buy" | "sell"; qty: number; price: number; reason: string | null; pnl: number | null; ts: string }
export interface LiveSnapshot {
  id: string; name: string; status: "running" | "stopped" | "paused"; stop_reason?: string | null;
  instrument: Instrument; strategy: Strategy; started_at: string; stopped_at?: string | null;
  last_price?: number | null; last_tick_at?: string | null; feed_connected?: boolean;
  bars: { t: string; o: number; h: number; l: number; c: number }[]; forming?: { t: string; c: number } | null;
  overlays: Record<string, (number | null)[]>; events: LiveEvent[]; equity_curve: { t: string; eq: number }[];
  account: { capital: number; equity: number; cash: number; qty: number; entry?: number | null; stop?: number | null;
    target?: number | null; unrealised: number; realised: number; trades: number; wins: number };
  orders: LiveOrder[];
}
export interface LiveRow {
  id: string; name: string; instrument: Instrument; status: "running" | "stopped" | "paused";
  started_at: string; stopped_at: string | null; stop_reason: string | null;
}

// ---------- options ----------
export interface OptLeg { side: "sell" | "buy"; opt: "CE" | "PE"; offset: number; lots: number }
export interface OptionStrategy {
  name: string; structure: string; exchange: "NFO" | "BFO" | "MCX"; underlying: string; expiry: string;
  offsetUnit: "strikes" | "points"; legs: OptLeg[];
  timing: { entry: string; lastEntry: string; squareoff: string; maxEntries: number; cooldown: number };
  risk: { stopType: "none" | "amount" | "credit_pct"; stop: number; tgtType: "none" | "amount" | "credit_pct"; tgt: number;
    trailAfter: number; trailBy: number; legStopPct: number; dailyLoss: number };
  recenter: { enabled: boolean; every: number; threshold: number; roll: "shorts" | "all" };
  sizing: { mode: "lots" | "margin"; lots: number; capital: number; safety: number };
  costs: { brokerage: number; slippageTicks: number; freeze: number };
  notes: string;
}
export interface Underlying { exchange: "NFO" | "BFO" | "MCX"; name: string; lot: number; expiries: string[]; venue: string; popular: boolean; freeze: number; index: boolean }
export interface OptQuote { ltp: number | null; bid: number | null; ask: number | null; oi?: number | null; volume?: number | null; ts?: string | null }
export interface OptChain { expiry: string | null; expiries?: string[]; lot?: number; spot: number | null; atm?: number; step?: number;
  rows: { strike: number; ce: OptQuote | null; pe: OptQuote | null }[]; freeze?: number }
export interface OptPreview {
  spot: number; atm: number; step: number; expiry: string; lot: number; freeze: number; units: number;
  margin_one: number | null; margin: number | null; strikes: number[];
  legs: { side: "sell" | "buy"; opt: "CE" | "PE"; lots: number; strike: number | null; sym: string | null; quote: OptQuote | null; fill: number | null }[];
}
export interface OptLegLive { sym: string; opt: "CE" | "PE"; side: "sell" | "buy"; strike: number; qty: number; entry: number; mark: number; open: boolean; pnl: number }
export interface OptTrade { opened: string; closed: string; why: string; pnl: number; gross: number; costs: number; credit: number; rolls: number;
  units: number; orders: number; best: number; worst: number; expiry: string; legs: { sym: string; side: string; qty: number; entry: number; exit: number | null }[] }
export interface OptionSnapshot {
  id: string; name: string; kind: "options"; status: "running" | "stopped" | "paused"; stop_reason?: string | null;
  instrument: { symbol: string; exchange: string; underlying: string }; strategy: OptionStrategy; started_at: string; stopped_at?: string | null;
  spot: number | null; last_tick_at?: string | null; fresh: boolean; feed_connected?: boolean; expiry?: string | null; lot?: number | null; note: string;
  legs: OptLegLive[];
  position: { opened: string; center: number; spot_in: number; credit: number; mtm: number; costs: number; net: number; best: number; worst: number;
    rolls: number; units: number; orders: number; expiry: string } | null;
  events: { t: string; side: "buy" | "sell"; qty: number; px: number; why: string; sym: string; pnl?: number; slices?: number }[];
  trades: OptTrade[]; equity_curve: { t: string; eq: number }[];
  account: { capital: number; equity: number; cash: number; realised: number; today: number; halted: boolean; entries_today: number;
    trades: number; wins: number; unrealised: number };
}
