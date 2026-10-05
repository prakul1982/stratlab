import { api } from "./api";
import type { Region } from "./research";
import { track } from "./analytics";

/** Stock alerts the user sets: a price level, a day's move, a moving average, RSI, Stage, a 52-week high or low, and
 * (Indian stocks) an insider trade or a bulk or block deal disclosed to the exchange, or a stock entering or leaving
 * an exchange surveillance list. */
export type AlertKind = "price" | "move" | "ma" | "rsi" | "stage" | "high52" | "low52" | "insider" | "deal" | "surveillance" | "etfgap" | "bizupdate";
export type AlertOp = "above" | "below" | "up" | "down" | "either" | null;

export interface StockAlert {
  id: string; region: Region; symbol: string; kind: AlertKind; op: AlertOp; value: number | null; period: number | null;
  repeat: boolean; note: string | null; status: "active" | "triggered"; created_at: string; triggered_at: string | null;
  fired: number; last_text: string | null; text: string;
}
export interface AlertsPage {
  active: StockAlert[]; triggered: StockAlert[]; limit: number; count: number; channels: string[];
  email: string | null; email_confirmed: boolean;
}
export interface AlertBody {
  region: Region; symbol: string; kind: AlertKind; op: AlertOp; value: number | null; period: number | null; repeat: boolean; note: string | null;
}

/** The choices in the form: each is one kind with its direction. */
export const CONDITIONS: { key: string; label: string; kind: AlertKind; op: AlertOp; india?: boolean }[] = [
  { key: "price_above", label: "Price crosses above", kind: "price", op: "above" },
  { key: "price_below", label: "Price crosses below", kind: "price", op: "below" },
  { key: "move_up", label: "Rises in a day by", kind: "move", op: "up" },
  { key: "move_down", label: "Falls in a day by", kind: "move", op: "down" },
  { key: "move_either", label: "Moves either way in a day by", kind: "move", op: "either" },
  { key: "ma_above", label: "Price crosses above its moving average", kind: "ma", op: "above" },
  { key: "ma_below", label: "Price crosses below its moving average", kind: "ma", op: "below" },
  { key: "rsi_above", label: "14-day RSI crosses above", kind: "rsi", op: "above" },
  { key: "rsi_below", label: "14-day RSI crosses below", kind: "rsi", op: "below" },
  { key: "stage", label: "Stage changes", kind: "stage", op: null },
  { key: "high52", label: "Makes a new 52-week high", kind: "high52", op: null },
  { key: "low52", label: "Makes a new 52-week low", kind: "low52", op: null },
  { key: "insider", label: "A promoter or insider trade is disclosed", kind: "insider", op: null, india: true },
  { key: "deal", label: "A bulk or block deal is reported", kind: "deal", op: null, india: true },
  { key: "surveillance", label: "Enters or leaves an exchange surveillance list", kind: "surveillance", op: null, india: true },
  // an Indian ETF's price against its NAV (Basic and up)
  { key: "etfgap_above", label: "ETF trades above its NAV by", kind: "etfgap", op: "above", india: true },
  { key: "etfgap_below", label: "ETF trades below its NAV by", kind: "etfgap", op: "below", india: true },
  { key: "etfgap_either", label: "ETF trades away from its NAV, either way, by", kind: "etfgap", op: "either", india: true },
  // a new monthly or quarterly business update filed (Basic and up)
  { key: "bizupdate", label: "Files a monthly or quarterly business update", kind: "bizupdate", op: null, india: true },
];
/** Alerts on exchange disclosures and surveillance lists, checked against the exchange's daily lists rather than the
 * live price. */
export const EVENT_KINDS: AlertKind[] = ["insider", "deal", "surveillance", "bizupdate"];
export const MA_PERIODS = [20, 50, 100, 150, 200];

export const conditionKey = (a: { kind: AlertKind; op: AlertOp }) =>
  CONDITIONS.find((c) => c.kind === a.kind && (c.op === a.op || c.op === null))?.key ?? "price_above";

export const CHANNEL_NAME: Record<string, string> = { push: "phone", telegram: "Telegram", email: "email" };

export const alertsApi = {
  list: () => api<AlertsPage>("/alerts"),
  create: (b: AlertBody) => api<AlertsPage & { alert: StockAlert; note: string | null }>("/alerts", { method: "POST", body: b })
    .then((r) => { track("alert created", { region: b.region, kind: b.kind }); return r; }),
  update: (id: string, b: AlertBody) => api<AlertsPage & { alert: StockAlert; note: string | null }>(`/alerts/${id}`, { method: "PUT", body: b }),
  remove: (id: string) => api<AlertsPage>(`/alerts/${id}`, { method: "DELETE" }),
  clearTriggered: () => api<AlertsPage>("/alerts", { method: "DELETE" }),
};
