import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ET, IST, money, fmtDate, tzLabel } from "../../lib/format";
import { track } from "../../lib/analytics";
import { CHECKS, checksLine, upDown } from "../../lib/tradeUi";
import { Info, STATUS_NAME } from "../../components/ui";
import { DrawdownBand, XYChart } from "../../components/Charts";
import { Pencil, Plus, Trash } from "../../components/Icons";
import { Badge, Card, CardHead, ChipBar, ChipSet, ConfirmDialog, DataTable, DateField, Disclosure, EmptyState, ErrorState, Field, FormGrid, Notice, PageHeader, PlanNote, Seg, Select, Skeleton, Stat, StatRow, TimeInput, UploadButton, type Column } from "../../components/kit";
import { Modal } from "../../components/ui";
import type { CheckStatus, VerdictKind } from "../../lib/types";
import { moneyCompact } from "../../lib/chartFormat";
import "./trade.css";
import "./journal.css";

/* The real-trade journal (Trade space): import a tradebook or tax P&L, see every round trip with its charges, keep a
 * note on each, and see the stats and the backtest verdict's honesty checks run on the real trades. Each market (India,
 * US stocks, crypto) is worked out on its own, in its own currency; within India a segment (equity delivery or
 * intraday, futures, options, commodity, currency) can be picked. The tax report's F&O, commodity and currency totals
 * show beside the trades. Facts about past trades only. Built from the kit (components/kit). */

type Note = { tag?: string; notes?: string; links?: string[]; emotions?: string[]; mistakes?: string[]; stop?: number; target?: number; side?: "long" | "short" };
type Trade = {
  id: string; symbol: string; u: string; segment: string; segment_label: string; currency: string; side: "long" | "short" | null; entry_t: string; exit_t: string;
  qty: number; entry: number; exit: number; gross: number; charges: number; net: number; r: number | null; hold_s: number | null; hold_days: number;
  fills: number; src: "tradebook" | "pnl" | "manual" | "practice"; expired: boolean; charges_from: string; note: Note;
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
type TaxTotal = { fy: number; seg: string; label: string; trades: number; pnl: number; charges: number; net: number; turnover: number; first: string; last: string };
type Journal = {
  as_of: string; updated_at: string | null; full: boolean; limit: number | null; count: number; total: number; beyond_limit: number; removed: number;
  trades: Trade[]; open: Open[]; unmatched: Open[]; overlap: number; summary: Summary;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number; checks: Check[] } | null;
  breakdowns: Record<string, Row[]> | null;
  r: { n: number; of: number; avg: number | null; buckets: { label: string; n: number }[]; planned_rr: number | null; planned_n: number; hit_target: number } | null;
  files: { name: string; broker: string; trades: number; at: string }[];
  settings: { capital: number | null; brokerage_delivery: number; brokerage_other: number; show?: Show };
  practice_count: number; real_count: number; show: Show;
  market: string; markets: { id: string; label: string; currency: string; symbol: string; n: number }[]; currency: string; segment: string;
  segment_counts: Record<string, number>; tax_totals: TaxTotal[];
  links: Record<string, string>; paper: { id: string; name: string; status: string; symbol?: string }[]; tags: string[];
  emotions: string[]; mistakes: string[]; segments: Record<string, string>; assumptions: string; plan_name: string;
};
type Show = "all" | "real" | "practice";
type Imported = { added: number; duplicates: number; over: number; problems: { line: number; text: string; reason: string }[]; problem_count: number;
  skipped: { name: string; reason: string }[]; broker: string; journal: Journal };
type Compared = { tag: string; session: { id: string; name: string }; note: string;
  real: Record<string, number | null>; paper: Record<string, number | null> };

/** The money of the market being shown: rupees for India, dollars for US stocks and crypto. */
const CurrencyCtx = createContext("INR");
function useMoney() {
  const cur = useContext(CurrencyCtx);
  return useMemo(() => {
    const m = (v: number | null | undefined, dp = 0) => money(v, cur, dp);
    return { cur, m, signed: (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : ""}${m(v)}`), compact: (v: number) => moneyCompact(v, cur) };
  }, [cur]);
}
const tone = (v: number | null | undefined): "up" | "down" | undefined => (v == null || v === 0 ? undefined : v > 0 ? "up" : "down");

const day = (iso: string) => fmtDate(iso.slice(0, 10));
const when = (iso: string) => (iso.length > 10 ? `${day(iso)} ${iso.slice(11, 16)}` : day(iso));
const qtyText = (q: number) => q.toLocaleString("en-IN", { maximumFractionDigits: 4 });
const fyLabel = (fy: number) => `FY ${fy}-${String(fy + 1).slice(2)}`;
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
const SEGMENT_ORDER = ["eq_delivery", "eq_intraday", "fut", "opt", "com", "cur"];

export function JournalPage() {
  const { notify, fail } = useApp();
  const [j, setJ] = useState<Journal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Imported | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Trade | null>(null);
  const [adding, setAdding] = useState(false);
  const [setup, setSetup] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const [mode, setMode] = useState<"add" | "replace">("add");
  const [market, setMarket] = useState("");
  const [segment, setSegment] = useState("all");
  // trades the tax report already has from the person's tradebooks: offered here, so an empty journal says so
  const [taxTrades, setTaxTrades] = useState(0);
  useEffect(() => { api<{ trades: number }>("/tax").then((t) => setTaxTrades(t.trades ?? 0)).catch(() => undefined); }, []);

  const load = useCallback(() => {
    const q = new URLSearchParams({ segment, market });
    return api<Journal>(`/trade/journal?${q}`).then((x) => { setJ(x); setError(null); }).catch((e) => { setError("Your journal couldn't be opened just now. Try again in a minute."); fail(e); });
  }, [fail, market, segment]);
  useEffect(() => { load(); }, [load]);
  /** What the server sends after a change is its default view; with a market or segment picked, the page asks again. */
  const adopt = (x: Journal) => { if (market || segment !== "all") load(); else setJ(x); };

  const pick = async (files: FileList | null, reset: () => void) => {
    const list = Array.from(files ?? []).filter((f) => {
      if (f.size <= MAX_MB * 1024 * 1024) return true;
      notify(`${f.name} is larger than ${MAX_MB} MB. Split it by year (or quarter) and upload each one.`);
      return false;
    });
    if (!list.length) { reset(); return; }
    setBusy(true);
    try {
      let last: Imported | null = null, added = 0, dup = 0;
      for (const [i, f] of list.entries()) {
        const q = new URLSearchParams({ filename: f.name.slice(0, 200), mode: i === 0 ? mode : "add" });
        last = await api<Imported>(`/trade/journal/import?${q}`, { method: "POST", file: f });
        added += last.added; dup += last.duplicates;
        track("journal file imported", { rows: last.added, zip: /\.zip$/i.test(f.name) });
      }
      if (last) { setResult({ ...last, added, duplicates: dup }); adopt(last.journal); setMode("add"); }
    } catch (e) { fail(e); } finally { setBusy(false); reset(); }
  };

  const fromTax = async () => {
    setBusy(true);
    try {
      const r = await api<Imported>("/trade/journal/import-tax", { method: "POST" });
      adopt(r.journal); setResult(null);
      notify(r.added ? `${r.added} trade line${r.added === 1 ? "" : "s"} brought in from the tax report.` : "Those trades are already in your journal.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const remove = () => {
    setAskDelete(false);
    api("/trade/journal", { method: "DELETE" }).then(() => { setResult(null); setMarket(""); setSegment("all"); return load(); })
      .then(() => notify("Your journal is deleted.")).catch(fail);
  };

  const showOnly = async (show: Show) => {
    if (!j || show === j.show) return;
    try { adopt(await api<Journal>("/trade/journal/settings", { method: "PUT", body: { ...j.settings, show } })); } catch (e) { fail(e); }
  };

  const header = <PageHeader eyebrow="Trade · My trades" title="Trade journal" asOf={j?.as_of}
    lede="Your broker's trades, equity, F&O, commodity and currency, and US stocks and crypto you add by hand, as round trips after charges, checked like a backtest. Only you can see them." />;
  if (error && !j) return <div className="k-page j-page">{header}<ErrorState title="Your journal couldn't be opened" action={{ label: "Try again", onClick: () => { setError(null); load(); } }}>{error}</ErrorState></div>;
  if (!j) return <div className="k-page j-page">{header}<Card><Skeleton label="Opening your journal" /></Card></div>;
  const s = j.summary;
  const has = j.total > 0;
  const anyTrades = j.markets.some((x) => x.n > 0);
  const others = j.markets.filter((x) => x.n > 0);
  const segs = SEGMENT_ORDER.filter((k) => j.segment_counts[k]);

  return (
    <CurrencyCtx.Provider value={j.currency}>
      <div className="k-page j-page">
        {header}

        <Card label="Bring in your trades">
          <CardHead title="Bring in your trades"
            actions={<>
              <button type="button" className="btn quiet sm" onClick={() => setSetup(true)}>Capital and brokerage</button>
              <button type="button" className="btn quiet sm" onClick={() => setAdding(true)}><Plus size={16} />Add a trade by hand</button>
            </>} />
          <p className="k-small k-muted">Upload the tradebook (every purchase and sale) from Zerodha Console, Groww, Upstox, Angel One, ICICI Direct or HDFC Securities, or the tax P&amp;L ZIP or its "Tradewise Exits" files (equity, F&amp;O, commodity and currency, intraday and delivery). Any CSV works with the columns Date, Symbol, Type (B or S), Quantity and Price. Trades already in the journal are skipped. US stocks and crypto are added by hand.</p>
          <div className="k-row">
            <UploadButton label="Upload files" busy={busy} multiple accept=".csv,.txt,.tsv,.xlsx,.xls,.zip" ariaLabel="Tradebook or tax P&L files" onFiles={pick} />
            {anyTrades && (
              <Select label="Add to or replace the imported trades" value={mode} onChange={(v) => setMode(v as "add" | "replace")}
                options={[{ value: "add", label: "Add to my trades" }, { value: "replace", label: "Replace imported trades" }]} />
            )}
            <button type="button" className="btn outline" disabled={busy} onClick={fromTax}>Use my tax report's trades</button>
          </div>
          <p className="k-note">The tax report keeps equity trade by trade, so those come across. Its F&amp;O, commodity and currency are kept as totals for each year: they show under the trades, and the tax P&amp;L's own files above bring them in trade by trade.</p>
          {result && (
            <div className="k-stack k-tight" role="status">
              <p className="k-small"><b>{result.added.toLocaleString("en-IN")} trade line{result.added === 1 ? "" : "s"} added</b>{result.duplicates > 0 && `, ${result.duplicates.toLocaleString("en-IN")} already in the journal (skipped)`}{result.broker !== "CSV" ? ` from a ${result.broker} file` : ""}.</p>
              {result.problem_count > 0 && (
                <Disclosure summary={`${result.problem_count} line${result.problem_count === 1 ? "" : "s"} couldn't be read`}>
                  <ul className="k-list">{result.problems.slice(0, 30).map((p, i) => <li key={i}>Line {p.line} · {p.text}: {p.reason}</li>)}</ul>
                </Disclosure>
              )}
              {result.skipped.length > 0 && (
                <Disclosure summary={`${result.skipped.length} file${result.skipped.length === 1 ? "" : "s"} left out`}>
                  <ul className="k-list">{result.skipped.map((p, i) => <li key={i}>{p.name}: {p.reason}</li>)}</ul>
                </Disclosure>
              )}
            </div>
          )}
        </Card>

        {(others.length > 1 || (j.practice_count ?? 0) > 0 || segs.length > 1) && (
          <div className="k-stack k-tight j-filters">
            {others.length > 1 && (
              <Seg label="Market" value={j.market} onChange={(v) => { setMarket(v); setSegment("all"); }}
                options={others.map((x) => ({ value: x.id, label: `${x.label} (${x.n})` }))} />
            )}
            {j.market === "in" && segs.length > 1 && (
              <ChipBar label="Segment" value={j.segment} onChange={setSegment}
                options={[{ value: "all", label: "All" }, ...segs.map((k) => ({ value: k, label: `${j.segments[k]} (${j.segment_counts[k]})` }))]} />
            )}
            {(j.practice_count ?? 0) > 0 && (
              <div className="k-row j-show">
                <Seg label="Which trades" value={j.show} onChange={(v) => showOnly(v as Show)}
                  options={[{ value: "real", label: `Real trades (${j.real_count})` }, { value: "practice", label: `Practice (${j.practice_count})` }, { value: "all", label: "Both" }]} />
                <span className="k-note">Practice trades come from <Link className="link" to="/trade/replay">chart replay</Link>: a simulation on past candles, not real trades.</span>
              </div>
            )}
          </div>
        )}

        {!has ? (
          <Card>
            {taxTrades > 0 && j.show !== "practice" ? (
              <EmptyState title={`${taxTrades.toLocaleString("en-IN")} trade${taxTrades === 1 ? "" : "s"} waiting in your tax report`}
                action={{ label: busy ? "Bringing them in…" : "Bring them in", onClick: () => { if (!busy) void fromTax(); } }}>
                The tradebooks you uploaded for tax hold your real trades. Bring them in to see them as round trips with their charges and the checks.
              </EmptyState>
            ) : (
              <EmptyState title={(j.practice_count ?? 0) > 0 ? (j.show === "practice" ? "No practice trades yet" : "No real trades yet") : "No trades yet"}>
                Upload a tradebook or tax P&amp;L above, or add a trade by hand. Once trades close, the stats and the checks appear here.
              </EmptyState>
            )}
          </Card>
        ) : (
          <>
            {j.beyond_limit > 0 && (
              <Notice action={{ label: "See plans", to: "/plans" }}>
                Your plan keeps the last {j.limit} trades, so {j.beyond_limit.toLocaleString("en-IN")} older one{j.beyond_limit === 1 ? " isn't" : "s aren't"} counted. {j.plan_name} counts every trade.
              </Notice>
            )}
            {j.verdict ? <VerdictView v={j.verdict} /> : <Locked plan={j.plan_name} what="The honesty checks on your real trades (enough trades, luck or edge, bad-luck drawdown, charges)" />}
            <Stats s={s} />
            <Card label="Running P&L after charges">
              <CardHead title="Running P&L after charges" />
              <Curve s={s} />
              <p className="k-note">Each point is a trade's exit, adding up from {money(0, j.currency)}. {s.first && s.last ? `${day(s.first)} to ${day(s.last)}.` : ""}</p>
            </Card>
            {j.breakdowns ? <Breakdowns b={j.breakdowns} r={j.r} /> : <Locked plan={j.plan_name} what="Breakdowns by day, time of day, setup, instrument and holding time, and R-multiples" />}
            {j.full && <PaperVsReal j={j} />}
            <Trades j={j} onEdit={setEditing} />
          </>
        )}
        {j.tax_totals.length > 0 && <TaxTotals rows={j.tax_totals} />}
        {has && (j.open.length > 0 || j.unmatched.length > 0) && <OpenList j={j} />}

        <section className="k-stack k-tight" aria-label="About these numbers">
          <p className="k-note">{j.assumptions} Facts about past trades, not advice.</p>
          <p className="k-note">Worked out as of {day(j.as_of)}{j.updated_at ? ` · trades saved as of ${day(j.updated_at)}` : ""}.</p>
          <div className="k-row">
            {j.removed > 0 && <button type="button" className="btn quiet sm" onClick={() => api<Journal>("/trade/journal/restore", { method: "POST" }).then(adopt).catch(fail)}>Show {j.removed} removed trade{j.removed === 1 ? "" : "s"} again</button>}
            <button type="button" className="btn quiet sm danger" onClick={() => setAskDelete(true)}><Trash size={16} />Delete my journal</button>
          </div>
        </section>

        {editing && <NoteEditor j={j} t={editing} onClose={() => setEditing(null)} onSaved={(x) => { adopt(x); setEditing(null); }} />}
        {adding && <AddTrade onClose={() => setAdding(false)} onSaved={(x) => { adopt(x); setAdding(false); notify("Trade added."); }} />}
        {setup && <Settings j={j} onClose={() => setSetup(false)} onSaved={(x) => { adopt(x); setSetup(false); notify("Saved. Charges and drawdowns are worked out again."); }} />}
        {askDelete && (
          <ConfirmDialog title="Delete my journal?" confirmLabel="Delete my journal" onConfirm={remove} onClose={() => setAskDelete(false)}>
            Every imported and added trade, your notes and settings are removed from StratLab. Your broker account isn't touched.
          </ConfirmDialog>
        )}
      </div>
    </CurrencyCtx.Provider>
  );
}

function Locked({ plan, what }: { plan: string; what: string }) {
  return <PlanNote><b>{what}</b> are on the {plan} plan. The trade list, your notes and the basic stats below are for everyone.</PlanNote>;
}

function Curve({ s }: { s: Summary }) {
  const { m, compact } = useMoney();
  return (
    <XYChart series={[{ values: s.equity.map((p) => p.v), color: "var(--series-1)", label: "P&L after charges", area: { base: 0, pos: "var(--series-1)", neg: "var(--series-2)" } }]}
      times={s.equity.map((p) => p.t)} format={(v) => m(v)} axisFormat={compact} testId="journal-curve"
      refs={[{ v: 0, strong: true }]} ariaLabel={`Running P&L after charges over ${s.n} trades, ending at ${m(s.net)}`} />
  );
}

function Stats({ s }: { s: Summary }) {
  const { m, signed } = useMoney();
  const st = s.streaks;
  const k = (label: string, help: string) => <>{label}<Info>{help}</Info></>;
  return (
    <Card label={`${s.n} closed trades`}>
      <CardHead title={`${s.n} closed trade${s.n === 1 ? "" : "s"}`} />
      <StatRow label="Stats">
        <Stat item label="P&L after charges" value={signed(s.net)} tone={tone(s.net)} />
        <Stat item label="Win rate" value={s.win_rate == null ? "–" : `${s.win_rate}%`} note={`${s.wins}W · ${s.losses}L`} />
        <Stat item label="Average win" value={m(s.avg_win)} tone="up" />
        <Stat item label="Average loss" value={m(s.avg_loss)} tone="down" />
        <Stat item label={k("Expectancy", "The average result per trade after charges: the total P&L divided by the number of trades.")} value={signed(s.expectancy)} tone={tone(s.expectancy)} />
        <Stat item label={k("Profit factor", "Money made on winning trades divided by money lost on losing ones. Above 1 means the wins added up to more than the losses.")} value={s.profit_factor ?? (s.wins ? "No losses" : "–")} />
        <Stat item label={k("Deepest fall", "The biggest drop of the running P&L from a high, after charges. As a % of your capital plus the P&L at that high, when you've entered your capital.")}
          value={m(-s.max_dd)} tone="down" note={s.max_dd_pct != null ? `${s.max_dd_pct}% of capital` : undefined} />
        <Stat item label="Longest streaks" value={`${st.longest_win}W · ${st.longest_loss}L`}
          note={st.current.kind ? `now ${st.current.n} ${st.current.kind === "win" ? "win" : "loss"}${st.current.n === 1 ? "" : st.current.kind === "win" ? "s" : "es"}` : undefined} />
        <Stat item label={k("Charges", "STT/CTT, exchange and SEBI fees, stamp duty, GST and brokerage in India, as a share of the P&L before charges. For US stocks and crypto, the charges you entered.")}
          value={m(s.charges)} note={s.charges_pct != null ? `${s.charges_pct}% of gross` : undefined} />
      </StatRow>
      {s.gross <= 0 && s.n > 0 && <p className="k-small k-muted">Before charges the trades came to {signed(s.gross)}; charges of {m(s.charges)} were on top of that.</p>}
    </Card>
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
      <section className="j-verdict" aria-label="Verdict on your real trades">
        <div className="k-stack j-verdict-main">
          <span className="k-eyebrow">Verdict on your real trades</span>
          <h2 className={`verdict-head j-verdict-head ${v.verdict}`}>{v.headline}</h2>
          <p className="j-verdict-sum">{v.summary}</p>
        </div>
        <Card>
          <span className="k-small k-muted"><b>Strength of evidence</b></span>
          <div className="dots" aria-label={checksLine(v.passed, v.total)}>
            {Array.from({ length: CHECKS }, (_, k) => <span key={k} className={k < v.passed ? "on" : k >= v.total ? "skip" : ""} />)}
          </div>
          <span className="k-small">{checksLine(v.passed, v.total)}</span>
        </Card>
      </section>
      <div className="j-checks">{v.checks.map((c) => <CheckCard key={c.id} c={c} />)}</div>
    </>
  );
}

/** Two bars, each side of nothing: the earlier and later halves of the trades. */
function Halves({ a, b, an, bn }: { a: number; b: number; an: number; bn: number }) {
  const { signed } = useMoney();
  const max = Math.max(Math.abs(a), Math.abs(b), 1);
  const bar = (v: number, label: string) => (
    <div className="k-stack k-tight" title={`${label}: ${signed(v)}`}>
      <span className="k-small k-muted">{label}</span>
      <div className="k-row">
        <svg className="j-half" viewBox="0 0 140 12" width="140" height="12" aria-hidden="true"><rect className={v >= 0 ? "j-pos" : "j-neg"} x="0" y="0" rx="4" height="12" width={Math.max(4, (Math.abs(v) / max) * 140)} /></svg>
        <span className={`k-mono k-small ${upDown(v)}`}>{signed(v)}</span>
      </div>
    </div>
  );
  return <div className="k-stack">{bar(a, `Earlier ${an} trades`)}{bar(b, `Later ${bn} trades`)}</div>;
}

function CheckCard({ c }: { c: Check }) {
  const { m, signed } = useMoney();
  const d = c.data;
  return (
    <div data-check={c.id} className="j-check">
      <Card label={c.title}>
        <div className="k-card-head">
          <div className="k-card-titlerow"><h3 className="k-card-title">{c.title}</h3><Info label={`About ${c.title}`}>{CHECK_HELP[c.id]}</Info></div>
          <span className={`badge ${c.status}`}>{STATUS_NAME[c.status]}</span>
        </div>
        {c.id === "sample" && d && <div className="j-big">{d.trades}</div>}
        {c.id === "luck" && d && <Halves a={d.earlier} b={d.later} an={d.earlier_n} bn={d.later_n} />}
        {c.id === "shuffle" && d && d.unit === "pct" && <DrawdownBand yours={d.yours} p95={d.p95} worst={d.worst} />}
        {c.id === "shuffle" && d && d.unit === "rupees" && <p className="k-mono k-small">Yours {m(-d.yours)} · 95% of reshuffles above {m(-d.p95)} · worst {m(-d.worst)}</p>}
        {c.id === "costs" && d && <p className="k-mono k-small">Gross {signed(d.gross)} · charges {m(d.charges)} · doubled {signed(d.doubled)}</p>}
        <p className="k-small k-muted">{c.detail}</p>
        {c.id === "shuffle" && d?.unit === "rupees" && <span className="k-note">Enter your trading capital (Capital and brokerage) to see this as a %.</span>}
      </Card>
    </div>
  );
}

/** One breakdown as a table, each row with a bar for its net P&L either side of zero. */
function BreakdownTable({ rows, label }: { rows: Row[]; label: string }) {
  const { m, signed } = useMoney();
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.net)));
  if (!rows.length) return <p className="k-small k-muted">Nothing to show here yet. {label === "Mistakes" || label === "Feelings" ? "Tag trades in their journal entry to see this." : ""}</p>;
  const cols: Column<Row>[] = [
    { key: "k", header: label, rowHeader: true, cell: (r) => r.label ?? r.key },
    { key: "net", header: "Net", numeric: true, cell: (r) => <span className={upDown(r.net)}>{signed(r.net)}</span> },
    { key: "bar", header: <span className="sr-only">Net, drawn</span>, cell: (r) => (
      <svg className="j-bar" viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true">
        <line x1="50" x2="50" y1="0" y2="12" className="j-zero" />
        <rect className={r.net >= 0 ? "j-pos" : "j-neg"} y="1" height="10" x={r.net >= 0 ? 50 : 50 - (-r.net / max) * 50} width={(Math.abs(r.net) / max) * 50} />
      </svg>) },
    { key: "n", header: "Trades", numeric: true, cell: (r) => r.n },
    { key: "wr", header: "Win rate", numeric: true, cell: (r) => `${r.win_rate}%` },
    { key: "avg", header: "Avg", numeric: true, cell: (r) => <span className={upDown(r.avg)}>{signed(r.avg)}</span> },
  ];
  return <DataTable label={`P&L by ${label.toLowerCase()}`} columns={cols} rows={rows} rowKey={(r) => r.key}
    rowAttrs={(r) => ({ title: `${r.label ?? r.key}: ${r.n} trades, ${signed(r.net)} after ${m(r.charges)} of charges` })} />;
}

function Breakdowns({ b, r }: { b: Record<string, Row[]>; r: Journal["r"] }) {
  const [view, setView] = useState("weekday");
  const label = VIEWS.find(([k]) => k === view)?.[1] ?? "";
  return (
    <Card label="Where the P&L came from">
      <CardHead title="Where the P&L came from"
        actions={<Select label="Break the P&L down by" value={view} onChange={setView} options={VIEWS.map(([k, l]) => ({ value: k, label: `By ${l.toLowerCase()}` }))} />} />
      <BreakdownTable rows={b[view] ?? []} label={label} />
      {view === "hour" && <p className="k-note">Same-day trades with times in the file, by the hour they were entered (IST).</p>}
      {r && <RChart r={r} />}
    </Card>
  );
}

function RChart({ r }: { r: NonNullable<Journal["r"]> }) {
  const max = Math.max(1, ...r.buckets.map((x) => x.n));
  return (
    <div className="k-stack j-rbox">
      <div className="k-card-titlerow"><h3 className="k-sub">R-multiples</h3><Info label="About R-multiples">R is a trade's result divided by the risk you planned: the distance from the entry to your planned stop, times the quantity. A trade that lost exactly what you planned to risk is −1R. Set a stop in a trade's journal entry to include it.</Info></div>
      {r.n === 0 ? <p className="k-small k-muted">No trade has a planned stop yet. Open a trade's journal entry and set its stop to see its R.</p> : (
        <>
          <div className="j-rbars" role="img" aria-label={`R-multiples of ${r.n} trades: ${r.buckets.map((x) => `${x.label} ${x.n}`).join(", ")}`}>
            {r.buckets.map((x, i) => (
              <div key={x.label} className="j-rcol" title={`${x.label}: ${x.n} trade${x.n === 1 ? "" : "s"}`}>
                <span className="k-mono k-note">{x.n || ""}</span>
                <svg className="j-rbar" viewBox="0 0 10 100" preserveAspectRatio="none" aria-hidden="true">
                  <rect className={i < 3 ? "j-neg" : "j-pos"} x="0" width="10" y={100 - (x.n / max) * 100} height={(x.n / max) * 100} />
                </svg>
                <span className="k-note">{x.label}</span>
              </div>
            ))}
          </div>
          <p className="k-small k-muted">{r.n} of {r.of} trades have a planned stop; average {r.avg}R.{r.planned_rr != null ? ` Planned reward to risk from your targets: ${r.planned_rr} to 1 (${r.planned_n} trades); ${r.hit_target} reached the target.` : ""}</p>
        </>
      )}
    </div>
  );
}

function PaperVsReal({ j }: { j: Journal }) {
  const { fail } = useApp();
  const { m, signed } = useMoney();
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
  const CMP: [string, string, (v: number | null) => string][] = [["n", "Trades", (v) => String(v ?? "–")], ["win_rate", "Win rate", (v) => (v == null ? "–" : `${v}%`)],
    ["avg_win", "Average win", (v) => m(v)], ["avg_loss", "Average loss", (v) => m(v)], ["expectancy", "Expectancy", (v) => signed(v)],
    ["profit_factor", "Profit factor", (v) => (v == null ? "–" : String(v))], ["net", "P&L after costs", (v) => signed(v)],
    ["max_dd", "Deepest fall", (v) => (v == null ? "–" : m(-v))], ["avg_hold_days", "Average holding (days)", (v) => (v == null ? "–" : String(v))]];
  type C = (typeof CMP)[number];
  const cols: Column<C>[] = got ? [
    { key: "l", header: "", rowHeader: true, cell: (c) => c[1] },
    { key: "real", header: `Real: ${got.tag}`, numeric: true, cell: (c) => c[2](got.real[c[0]] as number | null) },
    { key: "paper", header: `Paper: ${got.session.name}`, numeric: true, cell: (c) => c[2](got.paper[c[0]] as number | null) },
  ] : [];
  return (
    <Card label="Paper vs real">
      <CardHead title="Paper vs real" />
      {!j.tags.length || !j.paper.length ? (
        <p className="k-small k-muted">{!j.paper.length ? <>You have no paper sessions yet. <Link className="link" to="/paper">Paper trade a strategy</Link>, then tag</> : "Tag"} your real trades of the same setup in their journal entry to compare the two side by side.</p>
      ) : (
        <>
          <FormGrid>
            <Field label="Your setup">{(id) => <Select id={id} value={tag} onChange={setTag} options={j.tags.map((t) => ({ value: t, label: t }))} />}</Field>
            <Field label="Paper session">{(id) => <Select id={id} value={sid} onChange={setSid}
              options={[{ value: "", label: "Pick one" }, ...j.paper.map((p) => ({ value: p.id, label: `${p.name}${p.symbol ? ` · ${p.symbol}` : ""}` }))]} />}</Field>
          </FormGrid>
          <div><button type="button" className="btn" disabled={!sid} onClick={run}>Compare</button></div>
          {got && <DataTable label="Paper vs real" columns={cols} rows={CMP} rowKey={(c) => c[0]} />}
          {got && <p className="k-note">{got.note}</p>}
        </>
      )}
    </Card>
  );
}

function Trades({ j, onEdit }: { j: Journal; onEdit: (t: Trade) => void }) {
  const { m, signed } = useMoney();
  const [shown, setShown] = useState(50);
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const k = q.trim().toLowerCase();
    return k ? j.trades.filter((t) => t.symbol.toLowerCase().includes(k) || (t.note.tag ?? "").toLowerCase().includes(k)) : j.trades;
  }, [j.trades, q]);
  const cols: Column<Trade>[] = [
    { key: "trade", header: "Trade", rowHeader: true, wrap: true, cell: (t) => (
      <div className="k-stack k-tight">
        <div className="k-row">
          <b>{t.symbol}</b>
          <button type="button" className="btn quiet sm" onClick={() => onEdit(t)} aria-label={`Journal: ${t.symbol} ${when(t.exit_t)}`}><Pencil size={15} />{Object.keys(t.note).length ? "Edit" : "Note"}</button>
        </div>
        <span className="k-note">{t.side === "long" ? "Long" : t.side === "short" ? "Short" : "Side not in the file"} · {t.segment_label}</span>
        {(t.note.tag || t.src === "practice") && <div className="k-row">
          {t.src === "practice" && <Badge dot={false}>Chart replay</Badge>}
          {t.note.tag && <Badge tone="ok" dot={false}>{t.note.tag}</Badge>}</div>}
        {t.expired && <span className="k-note">Expired: counted at {money(0, t.currency)}</span>}
      </div>) },
    { key: "net", header: "Net", numeric: true, cell: (t) => <span className={upDown(t.net)}>{signed(t.net)}</span> },
    { key: "r", header: "R", numeric: true, cell: (t) => (t.r == null ? "–" : `${t.r > 0 ? "+" : ""}${t.r}R`) },
    { key: "exit", header: "Exit", numeric: true, cell: (t) => <>{when(t.exit_t)}<span className="k-sub-line">{holdText(t)}</span></> },
    { key: "qty", header: "Qty", numeric: true, cell: (t) => qtyText(t.qty) },
    { key: "px", header: "Entry → exit", numeric: true, cell: (t) => `${t.entry.toLocaleString("en-IN", { maximumFractionDigits: 2 })} → ${t.exit.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` },
    { key: "ch", header: "Charges", numeric: true, cell: (t) => (
      <span title={t.charges_from === "file" ? "As your broker listed them" : t.charges_from === "you" ? "As you entered them" : t.charges_from === "none" ? "None entered" : t.charges_from === "replay" ? "Worked out at the published rates when the replay was played" : "Worked out at the published rates"}>{m(t.charges, 2)}</span>) },
  ];
  return (
    <Card label="Trades">
      <CardHead title="Trades" actions={
        <label className="k-search j-search"><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a symbol or setup" aria-label="Find a symbol or setup" /></label>} />
      <DataTable label="Trades" columns={cols} rows={rows.slice(0, shown)} rowKey={(t) => t.id} empty="No trade matches that." />
      {rows.length > shown && <div className="k-center"><button type="button" className="btn quiet sm" onClick={() => setShown((n) => n + 100)}>Show more ({rows.length - shown} left)</button></div>}
      {j.overlap > 0 && <p className="k-note">{j.overlap} tax P&amp;L line{j.overlap === 1 ? " is" : "s are"} left out: your tradebook has the same trades, with their times.</p>}
      {j.count > j.trades.length && <p className="k-note">The latest {j.trades.length.toLocaleString("en-IN")} trades are listed; the stats count all {j.count.toLocaleString("en-IN")}.</p>}
    </Card>
  );
}

/** The tax report's F&O, commodity and currency, kept there as totals for each financial year. */
function TaxTotals({ rows }: { rows: TaxTotal[] }) {
  const { m, signed } = useMoney();
  const cols: Column<TaxTotal>[] = [
    { key: "fy", header: "Year", rowHeader: true, cell: (r) => fyLabel(r.fy) },
    { key: "seg", header: "Segment", cell: (r) => r.label },
    { key: "n", header: "Trades", numeric: true, cell: (r) => r.trades.toLocaleString("en-IN") },
    { key: "pnl", header: "Before charges", numeric: true, cell: (r) => <span className={upDown(r.pnl)}>{signed(r.pnl)}</span> },
    { key: "ch", header: "Charges", numeric: true, cell: (r) => m(r.charges) },
    { key: "net", header: "After charges", numeric: true, cell: (r) => <span className={upDown(r.net)}>{signed(r.net)}</span> },
    { key: "to", header: "Turnover", numeric: true, cell: (r) => m(r.turnover) },
  ];
  return (
    <Card label="From your tax report">
      <CardHead title="From your tax report" info="Your tax report keeps F&O, commodity and currency as totals for each financial year, not trade by trade, so they can't be paired into round trips here. They are shown as they are in the report, and are not counted in the stats above. Upload the tax P&L's trade-by-trade files to count them." infoLabel="About these totals" />
      <DataTable label="Totals from your tax report" columns={cols} rows={rows} rowKey={(r) => `${r.fy}-${r.seg}`} />
      <p className="k-note">Totals per year as in your <Link className="link" to="/tax-report">tax report</Link>.</p>
    </Card>
  );
}

function OpenList({ j }: { j: Journal }) {
  const { signed } = useMoney();
  return (
    <Card label="Not counted yet">
      <CardHead title="Not counted yet" />
      {j.open.length > 0 && <p className="k-small k-muted">Still open in your files, so not a closed trade yet: {j.open.slice(0, 20).map((o) => `${o.symbol} (${o.side} ${qtyText(o.qty)} since ${day(o.since)}${o.realised ? `, ${signed(o.realised)} on the part closed` : ""})`).join("; ")}.</p>}
      {j.unmatched.length > 0 && <p className="k-small k-muted">Sold with no purchase in your files (bought before the earliest file, or moved in from another account): {j.unmatched.slice(0, 20).map((o) => o.symbol).join(", ")}. Upload the older tradebook to pair them.</p>}
    </Card>
  );
}

function NoteEditor({ j, t, onClose, onSaved }: { j: Journal; t: Trade; onClose: () => void; onSaved: (x: Journal) => void }) {
  const { fail } = useApp();
  const { m, signed } = useMoney();
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
  const [asking, setAsking] = useState(false);
  const toggle = (list: string[], set: (x: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const num = (v: string) => { const x = Number(v.replace(/,/g, "")); return v.trim() && Number.isFinite(x) && x > 0 ? x : null; };
  const own = t.src === "manual" || t.src === "practice";
  const save = async () => {
    setBusy(true);
    try {
      onSaved(await api<Journal>(`/trade/journal/trades/${encodeURIComponent(t.id)}/note`, { method: "PUT", body: {
        tag, notes, links: links.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5), emotions: emo, mistakes: mis,
        stop: num(stop), target: num(target), side: side || null } }));
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const del = async () => {
    setAsking(false);
    try { onSaved(await api<Journal>(`/trade/journal/trades/${encodeURIComponent(t.id)}`, { method: "DELETE" })); } catch (e) { fail(e); }
  };
  return (
    <Modal title={`Journal: ${t.symbol}`} onClose={onClose} wide>
      <div className="k-stack">
        <p className="k-small k-muted">{when(t.entry_t)} → {when(t.exit_t)} · {qtyText(t.qty)} · {signed(t.net)} after {m(t.charges, 2)} of charges</p>
        <FormGrid>
          <Field label="Setup or strategy" value={tag} maxLength={40} list="j-tags" placeholder="Opening range breakout" onChange={(e) => setTag(e.target.value)} />
          {t.src === "pnl" && (
            <Field label="Long or short">{(id) => <Select id={id} value={side} onChange={(v) => setSide(v as "" | "long" | "short")}
              options={[{ value: "", label: "Not in the file" }, { value: "long", label: "Long (bought first)" }, { value: "short", label: "Short (sold first)" }]} />}</Field>
          )}
          <Field label="Planned stop" inputMode="decimal" value={stop} placeholder={String(Math.round(t.entry * 0.98 * 100) / 100)} onChange={(e) => setStop(e.target.value)} />
          <Field label="Planned target" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
        </FormGrid>
        <datalist id="j-tags">{j.tags.map((x) => <option key={x} value={x} />)}</datalist>
        <Field label="Notes" wide>{(id) => <textarea id={id} className="k-textarea" value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} placeholder="Why you took it, what happened" />}</Field>
        <Field label="Screenshots or links (one per line, up to 5)" wide>{(id) => <textarea id={id} className="k-textarea short" value={links} rows={2} onChange={(e) => setLinks(e.target.value)} placeholder="https://…" />}</Field>
        <div className="k-stack k-tight">
          <span className="k-small k-muted"><b>How you felt</b></span>
          <ChipSet label="How you felt" options={j.emotions.map((x) => ({ value: x, label: x }))} on={emo} onToggle={(v) => toggle(emo, setEmo, v)} />
        </div>
        <div className="k-stack k-tight">
          <span className="k-small k-muted"><b>Mistakes</b></span>
          <ChipSet label="Mistakes" options={j.mistakes.map((x) => ({ value: x, label: x }))} on={mis} onToggle={(v) => toggle(mis, setMis, v)} />
        </div>
        <div className="k-row j-spread">
          <button type="button" className="btn" disabled={busy} onClick={save}>Save</button>
          <button type="button" className="btn quiet sm danger" onClick={() => setAsking(true)}><Trash size={16} />{own ? "Delete trade" : "Remove trade"}</button>
        </div>
      </div>
      {asking && (
        <ConfirmDialog title={own ? "Delete this trade?" : "Leave this trade out of the journal?"} confirmLabel={own ? "Delete trade" : "Remove trade"} onConfirm={del} onClose={() => setAsking(false)}>
          {own ? "The trade is deleted from your journal." : "You can show removed trades again at the foot of the page."}
        </ConfirmDialog>
      )}
    </Modal>
  );
}

const ADD_SEGMENTS = [{ value: "eq", label: "Equity" }, { value: "fut", label: "Futures" }, { value: "opt", label: "Options" }, { value: "com", label: "Commodity" },
  { value: "cur", label: "Currency" }, { value: "us", label: "US stocks (dollars)" }, { value: "crypto", label: "Crypto (dollars)" }];

function AddTrade({ onClose, onSaved }: { onClose: () => void; onSaved: (x: Journal) => void }) {
  const { fail, notify } = useApp();
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ symbol: "", segment: "eq", side: "long", entry_date: today, entry_time: "", exit_date: today, exit_time: "", qty: "", entry_price: "", exit_price: "", charges: "" });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const abroad = f.segment === "us" || f.segment === "crypto";
  // times are the exchange's own clock: India's for the Indian segments, New York's for US stocks
  const zone = f.segment === "us" ? tzLabel(ET) : f.segment === "crypto" ? undefined : tzLabel(IST);
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
      <div className="k-stack">
        <FormGrid>
          <Field label="Symbol" value={f.symbol} maxLength={40} placeholder={abroad ? (f.segment === "us" ? "AAPL" : "BTCUSD") : "INFY or NIFTY26OCT25000CE"} onChange={set("symbol")} />
          <Field label="Segment">{(id) => <Select id={id} value={f.segment} onChange={(v) => setF({ ...f, segment: v })} options={ADD_SEGMENTS} />}</Field>
          <Field label="Long or short">{(id) => <Select id={id} value={f.side} onChange={(v) => setF({ ...f, side: v })} options={[{ value: "long", label: "Long (bought first)" }, { value: "short", label: "Short (sold first)" }]} />}</Field>
          <Field label="Quantity" inputMode="decimal" value={f.qty} onChange={set("qty")} />
          <DateField label="Entry date" value={f.entry_date} onChange={(d) => set("entry_date")({ target: { value: d } })} />
          <Field label="Entry time" optional>{(id) => <TimeInput id={id} zone={zone} value={f.entry_time} onChange={(v) => setF({ ...f, entry_time: v })} allowEmpty />}</Field>
          <Field label="Entry price" inputMode="decimal" value={f.entry_price} onChange={set("entry_price")} />
          <DateField label="Exit date" value={f.exit_date} onChange={(d) => set("exit_date")({ target: { value: d } })} />
          <Field label="Exit time" optional>{(id) => <TimeInput id={id} zone={zone} value={f.exit_time} onChange={(v) => setF({ ...f, exit_time: v })} allowEmpty />}</Field>
          <Field label="Exit price" inputMode="decimal" value={f.exit_price} onChange={set("exit_price")} />
          <Field label={abroad ? "Charges ($)" : "Charges (₹)"} optional inputMode="decimal" value={f.charges} onChange={set("charges")}
            info={abroad ? "No charges are worked out for US stocks or crypto: enter what your broker or exchange charged, or leave it empty for none." : "Worked out at the published rates when left empty."} />
        </FormGrid>
        {abroad && <p className="k-note">{f.segment === "us" ? "US stocks" : "Crypto"} are kept as their own market, in dollars: their stats are worked out apart from your Indian trades.</p>}
        <div><button type="button" className="btn" disabled={busy} onClick={save}>Add trade</button></div>
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
  const field = (label: string, value: string, set: (v: string) => void, extra?: { optional?: boolean; info?: ReactNode; placeholder?: string }) =>
    <Field label={label} inputMode="decimal" value={value} onChange={(e) => set(e.target.value)} {...extra} wide />;
  return (
    <Modal title="Capital and brokerage" onClose={onClose}>
      <div className="k-stack">
        {field("Trading capital (₹)", cap, setCap, { optional: true, placeholder: "5,00,000", info: "Shows the deepest fall and the bad-luck drawdown as a % of it." })}
        {field("Brokerage on a delivery order (₹)", del, setDel)}
        {field("Brokerage on an intraday, F&O, commodity or currency order (₹)", oth, setOth, { info: "Counted on each line of a tradebook. Tax P&L lines keep the charges your broker listed." })}
        <div><button type="button" className="btn" onClick={save}>Save</button></div>
      </div>
    </Modal>
  );
}
