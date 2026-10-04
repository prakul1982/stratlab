import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { money, moneyShort, signClass } from "../../lib/format";
import { track } from "../../lib/analytics";
import { AsOf, Empty, Info, Loading, Modal, STATUS_NAME } from "../../components/ui";
import { DrawdownBand, LineChart } from "../../components/Charts";
import { Pencil, Plus, Trash, Upload } from "../../components/Icons";
import type { CheckStatus, VerdictKind } from "../../lib/types";

/* The real-trade journal (Trade space): import a tradebook or tax P&L, see every round trip with its charges, keep a
 * note on each, and see the stats and the backtest verdict's honesty checks run on the real trades. Facts about past
 * trades only. */

type Note = { tag?: string; notes?: string; links?: string[]; emotions?: string[]; mistakes?: string[]; stop?: number; target?: number; side?: "long" | "short" };
type Trade = {
  id: string; symbol: string; u: string; segment: string; segment_label: string; side: "long" | "short" | null; entry_t: string; exit_t: string;
  qty: number; entry: number; exit: number; gross: number; charges: number; net: number; r: number | null; hold_s: number | null; hold_days: number;
  fills: number; src: "tradebook" | "pnl" | "manual"; expired: boolean; charges_from: string; note: Note;
};
type Row = { key: string; label?: string; n: number; win_rate: number; net: number; avg: number; gross: number; charges: number };
type Check = { id: string; title: string; status: CheckStatus; detail: string; data: any };
type Summary = {
  n: number; wins: number; losses: number; win_rate: number | null; avg_win: number | null; avg_loss: number | null; expectancy: number | null;
  profit_factor: number | null; gross: number; charges: number; net: number; charges_pct: number | null; max_dd: number; max_dd_pct: number | null;
  best: number | null; worst: number | null; avg_hold_days: number | null; first: string | null; last: string | null;
  streaks: { longest_win: number; longest_loss: number; current: { kind: "win" | "loss" | null; n: number } }; equity: { t: string; v: number }[];
};
type Open = { symbol: string; side: string; qty: number; since: string; avg: number; realised: number };
type Journal = {
  as_of: string; updated_at: string | null; full: boolean; limit: number | null; count: number; total: number; beyond_limit: number; removed: number;
  trades: Trade[]; open: Open[]; unmatched: Open[]; overlap: number; summary: Summary;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number; checks: Check[] } | null;
  breakdowns: Record<string, Row[]> | null;
  r: { n: number; of: number; avg: number | null; buckets: { label: string; n: number }[]; planned_rr: number | null; planned_n: number; hit_target: number } | null;
  files: { name: string; broker: string; trades: number; at: string }[];
  settings: { capital: number | null; brokerage_delivery: number; brokerage_other: number };
  links: Record<string, string>; paper: { id: string; name: string; status: string; symbol?: string }[]; tags: string[];
  emotions: string[]; mistakes: string[]; segments: Record<string, string>; assumptions: string; plan_name: string;
};
type Imported = { added: number; duplicates: number; over: number; problems: { line: number; text: string; reason: string }[]; problem_count: number;
  skipped: { name: string; reason: string }[]; broker: string; journal: Journal };
type Compared = { tag: string; session: { id: string; name: string }; note: string;
  real: Record<string, number | null>; paper: Record<string, number | null> };

const inr = (v: number | null | undefined, dp = 0) => money(v, "INR", dp);
const signed = (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : ""}${inr(v)}`);
const day = (iso: string) => new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
const when = (iso: string) => (iso.length > 10 ? `${day(iso)} ${iso.slice(11, 16)}` : day(iso));
const qtyText = (q: number) => q.toLocaleString("en-IN", { maximumFractionDigits: 4 });
const MAX_MB = 20;

function holdText(t: Trade) {
  if (t.hold_s != null) {
    const m = t.hold_s / 60;
    if (m < 60) return `${Math.max(1, Math.round(m))} min`;
    if (t.hold_days === 0) return `${(m / 60).toFixed(1)} h`;
  }
  return t.hold_days === 0 ? "Same day" : `${t.hold_days} day${t.hold_days === 1 ? "" : "s"}`;
}

const VIEWS: [string, string][] = [["weekday", "Day of week"], ["hour", "Time of day"], ["tag", "Setup"], ["instrument", "Instrument"], ["hold", "Holding time"],
  ["segment", "Segment"], ["side", "Long or short"], ["mistake", "Mistakes"], ["emotion", "Feelings"]];

export function JournalPage() {
  const { notify, fail } = useApp();
  const [j, setJ] = useState<Journal | null>(null);
  const [result, setResult] = useState<Imported | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Trade | null>(null);
  const [adding, setAdding] = useState(false);
  const [setup, setSetup] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"add" | "replace">("add");

  const load = useCallback(() => api<Journal>("/trade/journal").then(setJ).catch(fail), [fail]);
  useEffect(() => { load(); }, [load]);

  const pick = async (files: FileList | null) => {
    const list = Array.from(files ?? []).filter((f) => {
      if (f.size <= MAX_MB * 1024 * 1024) return true;
      notify(`${f.name} is larger than ${MAX_MB} MB. Split it by year (or quarter) and upload each one.`);
      return false;
    });
    if (!list.length) { if (file.current) file.current.value = ""; return; }
    setBusy(true);
    try {
      let last: Imported | null = null, added = 0, dup = 0;
      for (const [i, f] of list.entries()) {
        const q = new URLSearchParams({ filename: f.name.slice(0, 200), mode: i === 0 ? mode : "add" });
        last = await api<Imported>(`/trade/journal/import?${q}`, { method: "POST", file: f });
        added += last.added; dup += last.duplicates;
        track("journal file imported", { rows: last.added, zip: /\.zip$/i.test(f.name) });
      }
      if (last) { setResult({ ...last, added, duplicates: dup }); setJ(last.journal); setMode("add"); }
    } catch (e) { fail(e); } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  };

  const fromTax = async () => {
    setBusy(true);
    try {
      const r = await api<Imported>("/trade/journal/import-tax", { method: "POST" });
      setJ(r.journal); setResult(null);
      notify(r.added ? `${r.added} trade line${r.added === 1 ? "" : "s"} brought in from the tax report.` : "Those trades are already in your journal.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const remove = () => {
    if (!confirm("Delete my journal? Every imported and added trade, your notes and settings are removed from StratLab. Your broker account isn't touched.")) return;
    api("/trade/journal", { method: "DELETE" }).then(() => { setResult(null); return load(); })
      .then(() => notify("Your journal is deleted.")).catch(fail);
  };

  if (!j) return <Loading label="Opening your journal" />;
  const s = j.summary;
  const has = j.total > 0;

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Trade journal</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Your real trades, judged honestly</h1>
        <p className="page-sub">Your broker's tradebook, equity and F&amp;O, as round trips after charges, with your notes and the same checks a backtest's verdict uses. Facts about past trades; only you can see them.</p>
      </div>

      <section className="card stack" style={{ gap: 14 }} aria-labelledby="j-import">
        <div className="spread" style={{ flexWrap: "wrap" }}>
          <h2 id="j-import" className="h2">Bring in your trades</h2>
          <div className="row wrap" style={{ gap: 8 }}>
            <button className="btn quiet sm" onClick={() => setSetup(true)}>Capital and brokerage</button>
            <button className="btn quiet sm" onClick={() => setAdding(true)}><Plus size={16} />Add a trade by hand</button>
          </div>
        </div>
        <p className="small muted" style={{ margin: 0 }}>Upload the tradebook (every purchase and sale) from Zerodha Console, Groww, Upstox, Angel One, ICICI Direct or HDFC Securities, or the tax P&amp;L ZIP or its "Tradewise Exits" files (F&amp;O, commodity and currency included). Any CSV works with the columns Date, Symbol, Type (B or S), Quantity and Price. Trades already in the journal are skipped.</p>
        <div className="row wrap" style={{ gap: 10 }}>
          <label className="btn" style={{ cursor: busy ? "wait" : "pointer" }}>
            <Upload size={17} />{busy ? "Reading…" : "Upload files"}
            <input ref={file} type="file" multiple hidden disabled={busy} accept=".csv,.txt,.tsv,.xlsx,.xls,.zip" aria-label="Tradebook or tax P&L files" onChange={(e) => pick(e.target.files)} />
          </label>
          {has && (
            <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <span>Files</span>
              <select value={mode} onChange={(e) => setMode(e.target.value as "add" | "replace")} aria-label="Add to or replace the imported trades">
                <option value="add">Add to my trades</option><option value="replace">Replace imported trades</option>
              </select>
            </label>
          )}
          <button className="btn outline" disabled={busy} onClick={fromTax}>Use my tax report's trades</button>
        </div>
        {result && (
          <div className="stack" style={{ gap: 6 }} role="status">
            <p className="small" style={{ margin: 0 }}><b>{result.added.toLocaleString()} trade line{result.added === 1 ? "" : "s"} added</b>{result.duplicates > 0 && `, ${result.duplicates.toLocaleString()} already in the journal (skipped)`}{result.broker !== "CSV" ? ` from a ${result.broker} file` : ""}.</p>
            {result.problem_count > 0 && (
              <details className="small"><summary>{result.problem_count} line{result.problem_count === 1 ? "" : "s"} couldn't be read</summary>
                <ul>{result.problems.slice(0, 30).map((p, i) => <li key={i}>Line {p.line} · {p.text}: {p.reason}</li>)}</ul>
              </details>
            )}
            {result.skipped.length > 0 && (
              <details className="small"><summary>{result.skipped.length} file{result.skipped.length === 1 ? "" : "s"} left out</summary>
                <ul>{result.skipped.map((p, i) => <li key={i}>{p.name}: {p.reason}</li>)}</ul>
              </details>
            )}
          </div>
        )}
      </section>

      {!has ? (
        <Empty title="No trades yet">
          <p className="muted">Upload a tradebook or tax P&amp;L above, or add a trade by hand. Once trades close, the stats and the checks appear here.</p>
        </Empty>
      ) : (
        <>
          {j.beyond_limit > 0 && (
            <div className="banner">
              <span>Your plan keeps the last {j.limit} trades, so {j.beyond_limit.toLocaleString()} older one{j.beyond_limit === 1 ? " isn't" : "s aren't"} counted. {j.plan_name} counts every trade.</span>
              <Link to="/plans" className="btn sm">See plans</Link>
            </div>
          )}
          {j.verdict ? <VerdictView v={j.verdict} /> : <Locked plan={j.plan_name} what="The honesty checks on your real trades (enough trades, luck or edge, bad-luck drawdown, charges)" />}
          <Stats s={s} />
          <section className="card stack" style={{ gap: 12 }} aria-labelledby="j-curve">
            <h2 id="j-curve" className="h2">Running P&amp;L after charges</h2>
            <LineChart lines={[{ values: s.equity.map((p) => p.v), color: "var(--blue)", label: "P&L after charges", width: 2 }]}
              labels={s.equity.map((p) => when(p.t))} axisLabels={s.equity.map((p) => day(p.t))} format={(v) => inr(v)} axisFormat={(v) => moneyShort(v, "INR")}
              baseline={0} ariaLabel={`Running P&L after charges over ${s.n} trades, ending at ${inr(s.net)}`} />
            <p className="tiny muted" style={{ margin: 0 }}>Each point is a trade's exit, adding up from ₹0. {s.first && s.last ? `${day(s.first)} to ${day(s.last)}.` : ""}</p>
          </section>
          {j.breakdowns ? <Breakdowns b={j.breakdowns} r={j.r} /> : <Locked plan={j.plan_name} what="Breakdowns by day, time of day, setup, instrument and holding time, and R-multiples" />}
          {j.full && <PaperVsReal j={j} />}
          <Trades j={j} onEdit={setEditing} />
          {(j.open.length > 0 || j.unmatched.length > 0) && <OpenList j={j} />}
        </>
      )}

      <section className="stack" style={{ gap: 8 }}>
        <p className="tiny muted" style={{ margin: 0 }}>{j.assumptions} Facts about past trades, not advice.</p>
        <AsOf parts={[["Worked out", j.as_of], ["Trades saved", j.updated_at]]} />
        <div className="row wrap" style={{ gap: 10 }}>
          {j.removed > 0 && <button className="btn quiet sm" onClick={() => api<Journal>("/trade/journal/restore", { method: "POST" }).then(setJ).catch(fail)}>Show {j.removed} removed trade{j.removed === 1 ? "" : "s"} again</button>}
          <button className="btn quiet sm danger" onClick={remove}><Trash size={16} />Delete my journal</button>
        </div>
      </section>

      {editing && <NoteEditor j={j} t={editing} onClose={() => setEditing(null)} onSaved={(x) => { setJ(x); setEditing(null); }} />}
      {adding && <AddTrade onClose={() => setAdding(false)} onSaved={(x) => { setJ(x); setAdding(false); notify("Trade added."); }} />}
      {setup && <Settings j={j} onClose={() => setSetup(false)} onSaved={(x) => { setJ(x); setSetup(false); notify("Saved. Charges and drawdowns are worked out again."); }} />}
    </div>
  );
}

function Locked({ plan, what }: { plan: string; what: string }) {
  return (
    <section className="card dashed stack" style={{ gap: 8 }}>
      <p className="small" style={{ margin: 0 }}><b>{what}</b> are on the {plan} plan. The trade list, your notes and the basic stats below are for everyone.</p>
      <Link to="/plans" className="btn sm" style={{ alignSelf: "flex-start" }}>See plans</Link>
    </section>
  );
}

function Figure({ label, children, tone, help }: { label: string; children: React.ReactNode; tone?: string; help?: string }) {
  return <div className="stat"><span className="tiny muted">{label}{help && <Info>{help}</Info>}</span><b className={`num ${tone ?? ""}`}>{children}</b></div>;
}

function Stats({ s }: { s: Summary }) {
  const st = s.streaks;
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="j-stats">
      <h2 id="j-stats" className="h2">{s.n} closed trade{s.n === 1 ? "" : "s"}</h2>
      <div className="stat-row" aria-label="Stats">
        <Figure label="P&L after charges" tone={signClass(s.net)}>{signed(s.net)}</Figure>
        <Figure label="Win rate">{s.win_rate == null ? "–" : `${s.win_rate}%`} <span className="small muted">{s.wins}W · {s.losses}L</span></Figure>
        <Figure label="Average win" tone="pos">{inr(s.avg_win)}</Figure>
        <Figure label="Average loss" tone="neg">{inr(s.avg_loss)}</Figure>
        <Figure label="Expectancy" tone={signClass(s.expectancy)} help="The average result per trade after charges: the total P&L divided by the number of trades.">{signed(s.expectancy)}</Figure>
        <Figure label="Profit factor" help="Money made on winning trades divided by money lost on losing ones. Above 1 means the wins added up to more than the losses.">{s.profit_factor ?? (s.wins ? "No losses" : "–")}</Figure>
        <Figure label="Deepest fall" tone="neg" help="The biggest drop of the running P&L from a high, after charges. As a % of your capital plus the P&L at that high, when you've entered your capital.">{inr(-s.max_dd)}{s.max_dd_pct != null && <span className="small"> ({s.max_dd_pct}%)</span>}</Figure>
        <Figure label="Longest streaks">{st.longest_win}W · {st.longest_loss}L <span className="small muted">{st.current.kind ? `now ${st.current.n} ${st.current.kind === "win" ? "win" : "loss"}${st.current.n === 1 ? "" : st.current.kind === "win" ? "s" : "es"}` : ""}</span></Figure>
        <Figure label="Charges" help="STT/CTT, exchange and SEBI fees, stamp duty, GST and brokerage, as a share of the P&L before charges.">{inr(s.charges)}{s.charges_pct != null && <span className="small muted"> · {s.charges_pct}% of gross</span>}</Figure>
      </div>
      {s.gross <= 0 && s.n > 0 && <p className="small muted" style={{ margin: 0 }}>Before charges the trades came to {signed(s.gross)}; charges of {inr(s.charges)} were on top of that.</p>}
    </section>
  );
}

const CHECK_HELP: Record<string, string> = {
  sample: "Under 15 trades, luck dominates; 30 or more is a fair sample. The same rule as a backtest's verdict.",
  luck: "Your trades' results are kept, but each win or loss is given a random sign 1,000 times. If random signs often make as much as you did, the result could be luck. It also checks the later half of your trades made money too.",
  shuffle: "The order of your trades is reshuffled 1,000 times. The worst falls show how deep a drawdown the same trades could have had with worse luck.",
  costs: "Would the result survive charges twice as high: a costlier broker, more slippage, or a busier market?",
};

function VerdictView({ v }: { v: NonNullable<Journal["verdict"]> }) {
  return (
    <>
      <section className="row" style={{ gap: 32, alignItems: "flex-end", paddingBottom: 22, borderBottom: "1px solid var(--line-2)", flexWrap: "wrap" }} aria-label="Verdict on your real trades">
        <div className="stack" style={{ gap: 10, flex: "1 1 480px", minWidth: 0 }}>
          <span className="eyebrow">Verdict on your real trades</span>
          <h2 className={`verdict-head ${v.verdict}`} style={{ fontSize: "clamp(44px, 7vw, 84px)" }}>{v.headline}</h2>
          <p className="serif" style={{ fontSize: 20, lineHeight: 1.4, color: "var(--ink-2)", maxWidth: 820, margin: 0 }}>{v.summary}</p>
        </div>
        <div className="card stack" style={{ gap: 8, width: 230, flex: "none", padding: 18 }}>
          <span className="small muted" style={{ fontWeight: 600 }}>Strength of evidence</span>
          <div className="dots" aria-label={`${v.passed} of ${v.total} checks passed`}>
            {Array.from({ length: v.total }, (_, k) => <span key={k} className={k < v.passed ? "on" : ""} />)}
          </div>
          <span className="mono">{v.passed} of {v.total} checks passed</span>
        </div>
      </section>
      <section className="grid4">{v.checks.map((c) => <CheckCard key={c.id} c={c} />)}</section>
    </>
  );
}

/** Two bars in rupees, each side of a zero line: the earlier and later halves of the trades. */
function Halves({ a, b, an, bn }: { a: number; b: number; an: number; bn: number }) {
  const max = Math.max(Math.abs(a), Math.abs(b), 1);
  const bar = (v: number, label: string) => (
    <div className="stack" style={{ gap: 4 }} title={`${label}: ${signed(v)}`}>
      <span className="small muted">{label}</span>
      <div className="row" style={{ gap: 8 }}>
        <span style={{ height: 12, width: `${Math.max(4, (Math.abs(v) / max) * 140)}px`, borderRadius: 4, background: v >= 0 ? "var(--blue)" : "var(--orange)" }} />
        <span className={`mono small ${signClass(v)}`}>{signed(v)}</span>
      </div>
    </div>
  );
  return <div className="stack" style={{ gap: 8 }}>{bar(a, `Earlier ${an} trades`)}{bar(b, `Later ${bn} trades`)}</div>;
}

function CheckCard({ c }: { c: Check }) {
  const d = c.data;
  return (
    <div className="card stack" style={{ gap: 12, padding: 20 }} data-check={c.id}>
      <div className="spread" style={{ alignItems: "flex-start" }}><h3 className="h3 row" style={{ gap: 0 }}>{c.title}<Info>{CHECK_HELP[c.id]}</Info></h3><span className={`badge ${c.status}`}>{STATUS_NAME[c.status]}</span></div>
      {c.id === "sample" && d && <div className="serif" style={{ fontSize: 56, lineHeight: 1, letterSpacing: "-0.03em" }}>{d.trades}</div>}
      {c.id === "luck" && d && <Halves a={d.earlier} b={d.later} an={d.earlier_n} bn={d.later_n} />}
      {c.id === "shuffle" && d && d.unit === "pct" && <DrawdownBand yours={d.yours} p95={d.p95} worst={d.worst} />}
      {c.id === "shuffle" && d && d.unit === "rupees" && <p className="mono small" style={{ margin: 0 }}>Yours {inr(-d.yours)} · 95% of reshuffles above {inr(-d.p95)} · worst {inr(-d.worst)}</p>}
      {c.id === "costs" && d && <p className="mono small" style={{ margin: 0 }}>Gross {signed(d.gross)} · charges {inr(d.charges)} · doubled {signed(d.doubled)}</p>}
      <p className="small muted" style={{ lineHeight: 1.5, margin: 0 }}>{c.detail}</p>
      {c.id === "shuffle" && d?.unit === "rupees" && <span className="hint">Enter your trading capital (Capital and brokerage) to see this as a %.</span>}
    </div>
  );
}

/** One breakdown as a table, each row with a bar for its net P&L either side of zero. */
function BreakdownTable({ rows, label }: { rows: Row[]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.net)));
  if (!rows.length) return <p className="small muted">Nothing to show here yet. {label === "Mistakes" || label === "Feelings" ? "Tag trades in their journal entry to see this." : ""}</p>;
  return (
    <div className="table-wrap j-wrap" style={{ margin: 0 }}>
      <table className="nums" aria-label={`P&L by ${label.toLowerCase()}`}>
        <thead><tr><th>{label}</th><th>Net</th><th style={{ width: "26%" }}><span className="sr-only">Net, drawn</span></th><th>Trades</th><th>Win rate</th><th>Avg</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} title={`${r.label ?? r.key}: ${r.n} trades, ${signed(r.net)} after ${inr(r.charges)} of charges`}>
              <td>{r.label ?? r.key}</td><td className={signClass(r.net)}>{signed(r.net)}</td>
              <td>
                <div className="j-bar" aria-hidden="true">
                  <span style={r.net >= 0 ? { left: "50%", width: `${(r.net / max) * 50}%`, background: "var(--blue)" }
                    : { right: "50%", width: `${(-r.net / max) * 50}%`, background: "var(--orange)" }} />
                </div>
              </td>
              <td>{r.n}</td><td>{r.win_rate}%</td><td className={signClass(r.avg)}>{signed(r.avg)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Breakdowns({ b, r }: { b: Record<string, Row[]>; r: Journal["r"] }) {
  const [view, setView] = useState("weekday");
  const label = VIEWS.find(([k]) => k === view)?.[1] ?? "";
  return (
    <section className="card stack" style={{ gap: 14 }} aria-labelledby="j-break">
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <h2 id="j-break" className="h2">Where the P&amp;L came from</h2>
        <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <span>By</span>
          <select value={view} onChange={(e) => setView(e.target.value)} aria-label="Break the P&L down by">
            {VIEWS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
      </div>
      <BreakdownTable rows={b[view] ?? []} label={label} />
      {view === "hour" && <p className="tiny muted" style={{ margin: 0 }}>Same-day trades with times in the file, by the hour they were entered (India time).</p>}
      {r && <RChart r={r} />}
    </section>
  );
}

function RChart({ r }: { r: NonNullable<Journal["r"]> }) {
  const max = Math.max(1, ...r.buckets.map((x) => x.n));
  return (
    <div className="stack" style={{ gap: 10, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
      <h3 className="h3 row" style={{ gap: 0 }}>R-multiples<Info>R is a trade's result divided by the risk you planned: the distance from the entry to your planned stop, times the quantity. A trade that lost exactly what you planned to risk is −1R. Set a stop in a trade's journal entry to include it.</Info></h3>
      {r.n === 0 ? <p className="small muted" style={{ margin: 0 }}>No trade has a planned stop yet. Open a trade's journal entry and set its stop to see its R.</p> : (
        <>
          <div className="j-rbars" role="img" aria-label={`R-multiples of ${r.n} trades: ${r.buckets.map((x) => `${x.label} ${x.n}`).join(", ")}`}>
            {r.buckets.map((x, i) => (
              <div key={x.label} className="j-rcol" title={`${x.label}: ${x.n} trade${x.n === 1 ? "" : "s"}`}>
                <span className="mono tiny">{x.n || ""}</span>
                <span className="j-rbar" style={{ height: `${(x.n / max) * 100}%`, background: i < 3 ? "var(--orange)" : "var(--blue)" }} />
                <span className="tiny muted">{x.label}</span>
              </div>
            ))}
          </div>
          <p className="small muted" style={{ margin: 0 }}>{r.n} of {r.of} trades have a planned stop; average {r.avg}R.{r.planned_rr != null ? ` Planned reward to risk from your targets: ${r.planned_rr} to 1 (${r.planned_n} trades); ${r.hit_target} reached the target.` : ""}</p>
        </>
      )}
    </div>
  );
}

const CMP: [string, string, (v: number | null) => string][] = [["n", "Trades", (v) => String(v ?? "–")], ["win_rate", "Win rate", (v) => (v == null ? "–" : `${v}%`)],
  ["avg_win", "Average win", (v) => inr(v)], ["avg_loss", "Average loss", (v) => inr(v)], ["expectancy", "Expectancy", (v) => signed(v)],
  ["profit_factor", "Profit factor", (v) => (v == null ? "–" : String(v))], ["net", "P&L after costs", (v) => signed(v)],
  ["max_dd", "Deepest fall", (v) => (v == null ? "–" : inr(-v))], ["avg_hold_days", "Average holding (days)", (v) => (v == null ? "–" : String(v))]];

function PaperVsReal({ j }: { j: Journal }) {
  const { fail } = useApp();
  const [tag, setTag] = useState(j.tags[0] ?? "");
  const guess = (t: string) => j.links[t] ?? j.paper.find((p) => p.name.toLowerCase() === t.toLowerCase())?.id ?? "";
  const [sid, setSid] = useState(() => guess(j.tags[0] ?? ""));
  const [got, setGot] = useState<Compared | null>(null);
  useEffect(() => { setSid(guess(tag)); setGot(null); }, [tag]);   // eslint-disable-line react-hooks/exhaustive-deps
  const run = async () => {
    try {
      setGot(await api<Compared>(`/trade/journal/compare?${new URLSearchParams({ tag, session: sid })}`));
      if (j.links[tag] !== sid) api("/trade/journal/links", { method: "PUT", body: { tag, session: sid } }).catch(() => undefined);
    } catch (e) { fail(e); }
  };
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="j-paper">
      <h2 id="j-paper" className="h2">Paper vs real</h2>
      {!j.tags.length || !j.paper.length ? (
        <p className="small muted" style={{ margin: 0 }}>{!j.paper.length ? <>You have no paper sessions yet. <Link className="link" to="/paper">Paper trade a strategy</Link>, then tag</> : "Tag"} your real trades of the same setup in their journal entry to compare the two side by side.</p>
      ) : (
        <>
          <div className="row wrap" style={{ gap: 10, alignItems: "flex-end" }}>
            <label className="field">Your setup<select value={tag} onChange={(e) => setTag(e.target.value)}>{j.tags.map((t) => <option key={t}>{t}</option>)}</select></label>
            <label className="field">Paper session<select value={sid} onChange={(e) => setSid(e.target.value)}>
              <option value="">Pick one</option>{j.paper.map((p) => <option key={p.id} value={p.id}>{p.name}{p.symbol ? ` · ${p.symbol}` : ""}</option>)}
            </select></label>
            <button className="btn" disabled={!sid} onClick={run}>Compare</button>
          </div>
          {got && (
            <div className="table-wrap j-wrap" style={{ margin: 0 }}>
              <table className="nums" aria-label="Paper vs real">
                <thead><tr><th></th><th>Real: {got.tag}</th><th>Paper: {got.session.name}</th></tr></thead>
                <tbody>{CMP.map(([k, l, f]) => <tr key={k}><td>{l}</td><td>{f(got.real[k] as number | null)}</td><td>{f(got.paper[k] as number | null)}</td></tr>)}</tbody>
              </table>
            </div>
          )}
          {got && <p className="tiny muted" style={{ margin: 0 }}>{got.note}</p>}
        </>
      )}
    </section>
  );
}

function Trades({ j, onEdit }: { j: Journal; onEdit: (t: Trade) => void }) {
  const [shown, setShown] = useState(50);
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const k = q.trim().toLowerCase();
    return k ? j.trades.filter((t) => t.symbol.toLowerCase().includes(k) || (t.note.tag ?? "").toLowerCase().includes(k)) : j.trades;
  }, [j.trades, q]);
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="j-trades">
      <div className="spread" style={{ flexWrap: "wrap" }}>
        <h2 id="j-trades" className="h2">Trades</h2>
        <input className="input" style={{ maxWidth: 260 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a symbol or setup" aria-label="Find a symbol or setup" />
      </div>
      <div className="table-wrap j-wrap" style={{ margin: 0 }}>
        <table className="nums j-trades" aria-label="Trades">
          <thead><tr><th>Trade</th><th>Net</th><th>R</th><th>Exit</th><th>Qty</th><th>Entry → exit</th><th>Charges</th></tr></thead>
          <tbody>
            {rows.slice(0, shown).map((t) => (
              <tr key={t.id}>
                <td>
                  <div className="row wrap" style={{ gap: 8 }}>
                    <b>{t.symbol}</b>
                    <button className="btn quiet sm" onClick={() => onEdit(t)} aria-label={`Journal: ${t.symbol} ${when(t.exit_t)}`}><Pencil size={15} />{Object.keys(t.note).length ? "Edit" : "Note"}</button>
                  </div>
                  <div className="tiny muted">{t.side === "long" ? "Long" : t.side === "short" ? "Short" : "Side not in the file"} · {t.segment_label}</div>
                  {t.note.tag && <div className="tiny"><span className="badge fact">{t.note.tag}</span></div>}
                  {t.expired && <div className="tiny muted">Expired: counted at ₹0</div>}
                </td>
                <td className={signClass(t.net)}>{signed(t.net)}</td>
                <td>{t.r == null ? "–" : `${t.r > 0 ? "+" : ""}${t.r}R`}</td>
                <td className="small">{when(t.exit_t)}<div className="tiny muted">{holdText(t)}</div></td>
                <td>{qtyText(t.qty)}</td>
                <td className="small">{t.entry.toLocaleString("en-IN", { maximumFractionDigits: 2 })} → {t.exit.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</td>
                <td className="small" title={t.charges_from === "file" ? "As your broker listed them" : t.charges_from === "you" ? "As you entered them" : "Worked out at the published rates"}>{inr(t.charges, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > shown && <button className="btn quiet sm" style={{ alignSelf: "center" }} onClick={() => setShown((n) => n + 100)}>Show more ({rows.length - shown} left)</button>}
      {j.overlap > 0 && <p className="tiny muted" style={{ margin: 0 }}>{j.overlap} tax P&amp;L line{j.overlap === 1 ? " is" : "s are"} left out: your tradebook has the same trades, with their times.</p>}
      {j.count > j.trades.length && <p className="tiny muted" style={{ margin: 0 }}>The latest {j.trades.length.toLocaleString()} trades are listed; the stats count all {j.count.toLocaleString()}.</p>}
    </section>
  );
}

function OpenList({ j }: { j: Journal }) {
  return (
    <section className="card stack" style={{ gap: 10 }} aria-labelledby="j-open">
      <h2 id="j-open" className="h2">Not counted yet</h2>
      {j.open.length > 0 && <p className="small muted" style={{ margin: 0 }}>Still open in your files, so not a closed trade yet: {j.open.slice(0, 20).map((o) => `${o.symbol} (${o.side} ${qtyText(o.qty)} since ${day(o.since)}${o.realised ? `, ${signed(o.realised)} on the part closed` : ""})`).join("; ")}.</p>}
      {j.unmatched.length > 0 && <p className="small muted" style={{ margin: 0 }}>Sold with no purchase in your files (bought before the earliest file, or moved in from another account): {j.unmatched.slice(0, 20).map((o) => o.symbol).join(", ")}. Upload the older tradebook to pair them.</p>}
    </section>
  );
}

function NoteEditor({ j, t, onClose, onSaved }: { j: Journal; t: Trade; onClose: () => void; onSaved: (x: Journal) => void }) {
  const { fail } = useApp();
  const n = t.note;
  const [tag, setTag] = useState(n.tag ?? "");
  const [notes, setNotes] = useState(n.notes ?? "");
  const [links, setLinks] = useState((n.links ?? []).join("\n"));
  const [emo, setEmo] = useState<string[]>(n.emotions ?? []);
  const [mis, setMis] = useState<string[]>(n.mistakes ?? []);
  const [stop, setStop] = useState(n.stop != null ? String(n.stop) : "");
  const [target, setTarget] = useState(n.target != null ? String(n.target) : "");
  const [side, setSide] = useState<"" | "long" | "short">(n.side ?? "");
  const [busy, setBusy] = useState(false);
  const toggle = (list: string[], set: (x: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const num = (v: string) => { const x = Number(v.replace(/,/g, "")); return v.trim() && Number.isFinite(x) && x > 0 ? x : null; };
  const save = async () => {
    setBusy(true);
    try {
      onSaved(await api<Journal>(`/trade/journal/trades/${encodeURIComponent(t.id)}/note`, { method: "PUT", body: {
        tag, notes, links: links.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5), emotions: emo, mistakes: mis,
        stop: num(stop), target: num(target), side: side || null } }));
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const del = async () => {
    if (!confirm(t.src === "manual" ? "Delete this trade?" : "Leave this trade out of the journal? You can show removed trades again at the foot of the page.")) return;
    try { onSaved(await api<Journal>(`/trade/journal/trades/${encodeURIComponent(t.id)}`, { method: "DELETE" })); } catch (e) { fail(e); }
  };
  return (
    <Modal title={`Journal: ${t.symbol}`} onClose={onClose} wide>
      <div className="stack" style={{ gap: 14 }}>
        <p className="small muted" style={{ margin: 0 }}>{when(t.entry_t)} → {when(t.exit_t)} · {qtyText(t.qty)} · {signed(t.net)} after {inr(t.charges, 2)} of charges</p>
        <div className="nw-form j-form">
          <label className="field">Setup or strategy<input value={tag} maxLength={40} list="j-tags" onChange={(e) => setTag(e.target.value)} placeholder="Opening range breakout" />
            <datalist id="j-tags">{j.tags.map((x) => <option key={x} value={x} />)}</datalist></label>
          {t.src === "pnl" && (
            <label className="field">Long or short<select value={side} onChange={(e) => setSide(e.target.value as "" | "long" | "short")}>
              <option value="">Not in the file</option><option value="long">Long (bought first)</option><option value="short">Short (sold first)</option></select></label>
          )}
          <label className="field">Planned stop<input inputMode="decimal" value={stop} onChange={(e) => setStop(e.target.value)} placeholder={String(Math.round(t.entry * 0.98 * 100) / 100)} /></label>
          <label className="field">Planned target<input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} /></label>
        </div>
        <label className="field">Notes<textarea value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} placeholder="Why you took it, what happened" /></label>
        <label className="field">Screenshots or links (one per line, up to 5)<textarea value={links} rows={2} style={{ minHeight: 64 }} onChange={(e) => setLinks(e.target.value)} placeholder="https://…" /></label>
        <fieldset className="stack" style={{ gap: 8, border: 0, padding: 0, margin: 0 }}>
          <legend className="small muted" style={{ fontWeight: 600, marginBottom: 6 }}>How you felt</legend>
          <div className="row wrap" style={{ gap: 6 }}>{j.emotions.map((x) => <button key={x} type="button" className={`chip${emo.includes(x) ? " on" : ""}`} aria-pressed={emo.includes(x)} onClick={() => toggle(emo, setEmo, x)}>{x}</button>)}</div>
        </fieldset>
        <fieldset className="stack" style={{ gap: 8, border: 0, padding: 0, margin: 0 }}>
          <legend className="small muted" style={{ fontWeight: 600, marginBottom: 6 }}>Mistakes</legend>
          <div className="row wrap" style={{ gap: 6 }}>{j.mistakes.map((x) => <button key={x} type="button" className={`chip${mis.includes(x) ? " on" : ""}`} aria-pressed={mis.includes(x)} onClick={() => toggle(mis, setMis, x)}>{x}</button>)}</div>
        </fieldset>
        <div className="spread" style={{ flexWrap: "wrap" }}>
          <button className="btn" disabled={busy} onClick={save}>Save</button>
          <button className="btn quiet sm danger" onClick={del}><Trash size={16} />{t.src === "manual" ? "Delete trade" : "Remove trade"}</button>
        </div>
      </div>
    </Modal>
  );
}

function AddTrade({ onClose, onSaved }: { onClose: () => void; onSaved: (x: Journal) => void }) {
  const { fail, notify } = useApp();
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ symbol: "", segment: "eq", side: "long", entry_date: today, entry_time: "", exit_date: today, exit_time: "", qty: "", entry_price: "", exit_price: "", charges: "" });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const n = (v: string) => Number(v.replace(/,/g, ""));
    if (!f.symbol.trim() || !(n(f.qty) > 0) || !Number.isFinite(n(f.entry_price)) || !Number.isFinite(n(f.exit_price)) || !f.entry_price || !f.exit_price) {
      notify("Fill in the symbol, quantity and both prices."); return;
    }
    setBusy(true);
    try {
      onSaved(await api<Journal>("/trade/journal/trades", { method: "POST", body: {
        ...f, qty: n(f.qty), entry_price: n(f.entry_price), exit_price: n(f.exit_price), charges: f.charges.trim() ? n(f.charges) : null,
        entry_time: f.entry_time || null, exit_time: f.exit_time || null } }));
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <Modal title="Add a trade" onClose={onClose}>
      <div className="stack" style={{ gap: 12 }}>
        <div className="nw-form j-form">
          <label className="field">Symbol<input value={f.symbol} maxLength={40} onChange={set("symbol")} placeholder="INFY or NIFTY26OCT25000CE" /></label>
          <label className="field">Segment<select value={f.segment} onChange={set("segment")}>
            <option value="eq">Equity</option><option value="fut">Futures</option><option value="opt">Options</option><option value="com">Commodity</option><option value="cur">Currency</option></select></label>
          <label className="field">Long or short<select value={f.side} onChange={set("side")}><option value="long">Long (bought first)</option><option value="short">Short (sold first)</option></select></label>
          <label className="field">Quantity<input inputMode="decimal" value={f.qty} onChange={set("qty")} /></label>
          <label className="field">Entry date<input type="date" value={f.entry_date} onChange={set("entry_date")} /></label>
          <label className="field">Entry time (optional)<input type="time" value={f.entry_time} onChange={set("entry_time")} /></label>
          <label className="field">Entry price<input inputMode="decimal" value={f.entry_price} onChange={set("entry_price")} /></label>
          <label className="field">Exit date<input type="date" value={f.exit_date} onChange={set("exit_date")} /></label>
          <label className="field">Exit time (optional)<input type="time" value={f.exit_time} onChange={set("exit_time")} /></label>
          <label className="field">Exit price<input inputMode="decimal" value={f.exit_price} onChange={set("exit_price")} /></label>
          <label className="field">Charges (₹, optional)<input inputMode="decimal" value={f.charges} onChange={set("charges")} placeholder="Worked out if empty" /></label>
        </div>
        <button className="btn" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={save}>Add trade</button>
      </div>
    </Modal>
  );
}

function Settings({ j, onClose, onSaved }: { j: Journal; onClose: () => void; onSaved: (x: Journal) => void }) {
  const { fail } = useApp();
  const [cap, setCap] = useState(j.settings.capital != null ? String(j.settings.capital) : "");
  const [del, setDel] = useState(String(j.settings.brokerage_delivery));
  const [oth, setOth] = useState(String(j.settings.brokerage_other));
  const save = async () => {
    const n = (v: string) => Number(v.replace(/,/g, ""));
    try {
      onSaved(await api<Journal>("/trade/journal/settings", { method: "PUT", body: {
        capital: cap.trim() ? n(cap) : null, brokerage_delivery: n(del) || 0, brokerage_other: Number.isFinite(n(oth)) ? n(oth) : 20 } }));
    } catch (e) { fail(e); }
  };
  return (
    <Modal title="Capital and brokerage" onClose={onClose}>
      <div className="stack" style={{ gap: 12 }}>
        <label className="field">Trading capital (₹, optional)<input inputMode="decimal" value={cap} onChange={(e) => setCap(e.target.value)} placeholder="5,00,000" />
          <span className="hint">Shows the deepest fall and the bad-luck drawdown as a % of it.</span></label>
        <label className="field">Brokerage on a delivery order (₹)<input inputMode="decimal" value={del} onChange={(e) => setDel(e.target.value)} /></label>
        <label className="field">Brokerage on an intraday, F&amp;O, commodity or currency order (₹)<input inputMode="decimal" value={oth} onChange={(e) => setOth(e.target.value)} />
          <span className="hint">Counted on each line of a tradebook. Tax P&amp;L lines keep the charges your broker listed.</span></label>
        <button className="btn" style={{ alignSelf: "flex-start" }} onClick={save}>Save</button>
      </div>
    </Modal>
  );
}
