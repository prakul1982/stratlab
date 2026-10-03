import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";

type Check = { name: string; area: string; state: "pass" | "warn" | "fail"; detail: string; seconds: number | null };
type Result = { at: string; counts: Record<"pass" | "warn" | "fail", number>; checks: Check[]; auto?: boolean };
type Day = { at: string; auto: boolean; pass: number; warn: number; fail: number; failed: string[] };
const BADGE = { pass: ["Pass", "pass"], warn: ["Check", "warn"], fail: ["Fail", "fail"] } as const;

/** Every feature once on live data, with what came back compared to what it should be. */
export function PlatformPanel() {
  const { fail } = useApp();
  const [r, setR] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Day[]>([]);
  useEffect(() => {
    api<{ last: Result | null; history: Day[] }>("/admin/platform/last").then((x) => { if (x.last) setR(x.last); setHistory(x.history); }).catch(() => {});
  }, []);
  const go = async () => {
    setBusy(true);
    try { setR(await api<Result>("/admin/platform/check", { method: "POST" })); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const order = { fail: 0, warn: 1, pass: 2 };
  return (
    <section className="card stack" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Check every feature</h2>
        <button className="btn sm" disabled={busy} onClick={go}>{busy ? "Checking… (about a minute)" : "Run checks"}</button>
      </div>
      <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Runs each part of StratLab once on this server with live data: prices in every market and how fresh they are, a two-year
        backtest per market, the NIFTY 50 and US scans, sector rotation, the NIFTY option chain, exchange filings, company pages, news, the database and the
        holiday calendar. No AI is used. It also runs by itself every day at 4:50 PM IST: anything that fails is tried again two minutes later, and
        if it still fails it is emailed to you (and sent to your phone or Telegram if set in Account). Run it by hand after a deploy.</p>
      {history.length > 1 && <p className="tiny muted" style={{ margin: 0 }}>Last {history.length} runs: {history.map((h) => (h.fail ? "✗" : "✓")).join(" ")}
        {history.some((h) => h.fail) ? ` · last failure ${ago(history.filter((h) => h.fail).slice(-1)[0].at)}` : " · no failures"}</p>}
      {r && (
        <>
          <p className="small" style={{ margin: 0 }}>{r.auto ? "Automatic check, " : ""}{ago(r.at)} · <b>{r.counts.pass} pass</b> · {r.counts.warn} to check · <span className={r.counts.fail ? "neg" : ""}>{r.counts.fail} fail</span></p>
          <div className="stack" style={{ gap: 6 }}>
            {[...r.checks].sort((a, b) => order[a.state] - order[b.state] || a.area.localeCompare(b.area)).map((c) => (
              <div key={c.name} className="row small" style={{ gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                <span className={`badge ${BADGE[c.state][1]}`}>{BADGE[c.state][0]}</span>
                <b>{c.name}</b>
                <span className="muted">{c.detail}{c.seconds != null ? ` (${c.seconds}s)` : ""}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
