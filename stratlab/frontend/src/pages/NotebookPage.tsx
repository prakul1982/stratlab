import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { notebookTitle, useDocTitle } from "../lib/title";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { fillsLine } from "../lib/paperText";
import { currencySymbol, dateOnly, money, pct, periodName, TF_NAME } from "../lib/format";
import { isAutoNotebookName, rebuiltRisk, riskForCurrency, statedIn, usesPro } from "../lib/rules";
import { runCopy, runTime } from "../lib/notebookText";
import type { Experiment, Instrument, LiveRow, Notebook, Strategy, Tf } from "../lib/types";
import { getUpload } from "../lib/upload";
import { fitGaps, makeSaver, type SaveState } from "../lib/notebookSave";
import { track, trackBacktest } from "../lib/analytics";
import { spanCheck, spanDays, SPAN_UNITS } from "../lib/intervals";
import { GapsCard, type GapInfo } from "../components/Gaps";
import { Copy, Download, Pin, Pulse, Sparkle, Trash } from "../components/Icons";
import { MoreMenu } from "../components/MoreMenu";
import { RulesCard } from "../components/Rules";
import { AutoGrow, Info, Modal, VerdictBadge } from "../components/ui";
import { Card, CardHead, CheckField, ChipBar, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, FormActions, FormGrid, Notice, PageHeader, Signed, Skeleton, type Column } from "../components/kit";
import { HELP } from "../lib/help";
import { sipTestLink } from "../lib/sip";
import { isLegacyEmptied, legacyNote } from "../lib/legacyRun";
import { IdeaComposer } from "../components/IdeaComposer";
import "./trade/trade.css";
import { usePlansAction, usePlansToast } from "../components/PlanInterest";
import { badgeLabel } from "../lib/tradeUi";
import { LIMITS } from "../lib/plans";

/* /n/:id: one notebook: its question, what it tests on, the rules, and every experiment run on them. Built from the kit
 * (components/kit); the two-column layout with the lab notes beside it stays. */

const DEFAULT_DAILY_DAYS = 1825;
const PERIODS: Record<Tf, number[]> = {
  "1d": [182, 365, 730, 1095, 1825, 3650], "1h": [30, 90, 180, 365, 730], "15m": [30, 60, 90, 180, 365], "5m": [15, 30, 60, 120],
};

/** `page` names a sub-page of the notebook for the tab ("Run v2", "Compare runs"); the notebook's own page has none. */
export function useNotebook(id: string | undefined, page?: string) {
  const { fail, refreshNotebooks } = useApp();
  const [nb, setNb] = useState<Notebook | null>(null);
  useDocTitle(notebookTitle(nb?.name, page));          // the notebook's own name in the tab, not "Notebooks"; a run or the compare page says which
  // why there's no notebook to show: none at this address (deleted, mistyped, another account's), or it couldn't be read
  const [problem, setProblem] = useState<"missing" | "error" | null>(null);
  // "failed": the last save didn't reach the server; its edits wait for Retry (or the next save)
  const [saving, setSaving] = useState<SaveState>("idle");
  const timer = useRef<number>(undefined);

  const seq = useRef(0);       // a slower answer for the notebook just left must not land on this one
  const load = useCallback(async () => {
    if (!id) return;
    const n = ++seq.current;
    setProblem(null);
    try { const x = await api<Notebook>(`/notebooks/${id}`); if (n === seq.current) setNb(x); } catch (e) {
      if (n !== seq.current) return;
      const status = (e as ApiError).status;
      if (status === 404 || status === 400 || status === 422) setProblem("missing");      // a page says so; no toast
      else { setProblem("error"); fail(e); }
    }
  }, [id, fail]);
  useEffect(() => { setNb(null); load(); }, [load]);

  // the edits on their way to the server (lib/notebookSave): a failed save keeps them for Retry or the next save
  const failRef = useRef(fail);
  failRef.current = fail;
  const refreshRef = useRef(refreshNotebooks);
  refreshRef.current = refreshNotebooks;
  const saver = useMemo(() => makeSaver((body) => api(`/notebooks/${id}`, { method: "PUT", body }), {
    state: setSaving,
    saved: (body) => { if ("name" in body || "instrument" in body || "question" in body) refreshRef.current(); },
    failed: (e, quiet) => { if (!quiet) failRef.current(e); },
  }), [id]);
  const flush = useCallback((quiet = false): Promise<boolean> => (id ? saver.flush(quiet) : Promise.resolve(true)), [id, saver]);

  const patch = useCallback((p: Partial<Notebook> & { instrumentId?: string | null }, now = false) => {
    setNb((cur) => (cur ? { ...cur, ...p } : cur));
    const body: Record<string, unknown> = {};
    if (p.name !== undefined) body.name = p.name;
    if (p.question !== undefined) body.question = p.question;
    if (p.notes !== undefined) body.notes = p.notes;
    if (p.strategy !== undefined) body.strategy = p.strategy;
    // the questions go through the same queue as the pick they follow: two requests at once could each write over the other's
    // field, and a pick made just before leaving was lost while its question stayed ticked (DA-003)
    if (p.gaps !== undefined) { if (p.gaps) body.gaps = fitGaps(p.gaps); else body.clearGaps = true; }
    if (p.instrumentId !== undefined) body.instrument = p.instrumentId ?? "";
    // an upload's currency is the one picked for it (the server can't tell from the file)
    if (p.instrumentId?.startsWith("CSV:") && p.instrument && "currency" in p.instrument && p.instrument.currency) body.currency = p.instrument.currency;
    saver.add(body);
    window.clearTimeout(timer.current);
    if (now) void flush(); else timer.current = window.setTimeout(() => void flush(), 700);
  }, [flush, saver]);

  useEffect(() => () => { window.clearTimeout(timer.current); void flush(); }, [flush]);
  return { nb, setNb, patch, saving, reload: load, flush, problem };
}

/** What a notebook page shows instead of skeletons when there's no notebook to open: not found (with the way to your
 * notebooks, like the site's own not-found page), or couldn't be read (with Try again). Undefined while it loads. */
export function NotebookProblem({ problem, retry }: { problem: "missing" | "error" | null; retry: () => void }) {
  if (problem === "missing") return (
    <div className="k-page">
      <PageHeader eyebrow="Not found" title="Notebook not found"
        lede="There's no notebook at this address. It may have been deleted, or the link may be mistyped or from another account." />
      <div className="gate-actions">
        <Link className="btn" to="/notebooks">Go to notebooks</Link>
        <Link className="btn quiet" to="/new">Start a new notebook</Link>
      </div>
    </div>
  );
  if (problem === "error") return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Notebook" />
      <ErrorState title="The notebook couldn't be opened" action={{ label: "Try again", onClick: retry }}>
        Nothing in it has changed. Try again in a moment, or go to <Link className="link" to="/notebooks">your notebooks</Link>.
      </ErrorState>
    </div>
  );
  return null;
}

/** A return at the account's floor says the money was lost, not just "−100.0%" (R30-012: the engine holds a wiped-out account's loss to −100%). */
const lost = (v: number | null | undefined) => (typeof v === "number" && v <= -100 ? `Capital lost (${pct(v)})` : pct(v));

function marketName(inst: Instrument | null, markets: { id: string; name: string }[]) {
  if (!inst) return null;
  return markets.find((m) => m.id === inst.market)?.name ?? (inst.market === "IN" ? "India" : inst.market);
}

/** One notebook's page, started fresh for each notebook: what was typed for the run, the test period, the paper-session
 * lookup and any open editor belong to the notebook they were set on. */
export function NotebookPage() {
  const { id } = useParams();
  return <NotebookView key={id} />;
}

function NotebookView() {
  const { id } = useParams();
  const nav = useNavigate();
  const plansToast = usePlansToast();
  const plansAction = usePlansAction();
  const loc = useLocation();
  const { markets, fail, notify, refreshMe, refreshNotebooks, me, allIndicators, fno } = useApp();
  const feats = me?.plan_info.features;
  const canExport = !!feats?.export;
  // what the plan allows, known before Start (the server says the same at Start): paper trading a group (Basic), and its
  // faster entries and spread limit (Pro)
  const groupOk = feats ? !!feats.group_live : true, fastOk = feats ? !!feats.fast_entries : true;
  const { nb, patch, saving, setNb, flush, problem, reload } = useNotebook(id);
  const [gaps, setGaps] = useState<GapInfo | null>((loc.state as { gaps?: GapInfo } | null)?.gaps ?? null);
  const [days, setDays] = useState("");
  const [label, setLabel] = useState("");
  const [running, setRunning] = useState(false);
  const mounted = useRef(true);       // a run finishing after you've gone to another page doesn't take you back
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const starting = useRef(false);     // set before the flush, so a second click can't start another run
  // how long the run has taken so far, said on the button: a group's first run reads every stock's prices and can take a
  // minute or two (R11C-018: over 2 minutes with no sign of progress under "Takes a few seconds")
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) { setElapsed(0); return; }
    const t0 = Date.now();
    const t = window.setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => window.clearInterval(t);
  }, [running]);
  const [rewrite, setRewrite] = useState(false);
  const [groupStart, setGroupStart] = useState(false);
  const [paperAsk, setPaperAsk] = useState(false);
  // a paper session already running these rules: the button opens it instead of starting another
  const [live, setLive] = useState<LiveRow | null>(null);
  useEffect(() => {
    if (!nb?.id) return;
    let on = true;
    const instId = nb.instrument && "id" in nb.instrument ? nb.instrument.id : null;
    api<LiveRow[]>("/live/sessions").then((rows) => {
      if (on) setLive(rows.find((r) => r.status === "running" && r.name === nb.name && (!instId || r.instrument?.id === instId)) ?? null);
    }).catch(() => undefined);
    return () => { on = false; };
  }, [nb?.id, nb?.name]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [removing, setRemoving] = useState(false);
  const [fast, setFast] = useState({ ticks: false, maxSpreadPct: 0, minPrice: 0 });
  const notesRef = useRef<HTMLTextAreaElement>(null);

  // the questions about the idea are kept with the notebook: the ones a new notebook arrives with are saved, and a
  // notebook opened again shows the ones still open (R5O-010)
  const saveGaps = useCallback((g: GapInfo) => {
    setGaps(g);
    if (id) patch({ gaps: g }, true);
  }, [id, patch]);
  const arrived = (loc.state as { gaps?: GapInfo } | null)?.gaps ?? null;
  const loadedId = nb?.id;
  useEffect(() => {
    if (!loadedId) { setGaps(arrived); return; }
    if (arrived) { if (!nb?.gaps) saveGaps(arrived); else setGaps(nb.gaps); }
    else setGaps(nb?.gaps ?? null);
  }, [id, loc.state, loadedId]);    // eslint-disable-line react-hooks/exhaustive-deps
  const applyRef = useRef<(action: string) => void>(undefined);
  const runRef = useRef<() => void>(undefined);
  const pendingAction = useRef<string | null>(null);
  useEffect(() => { pendingAction.current = (loc.state as { action?: string } | null)?.action ?? null; }, [loc.state]);
  useEffect(() => {
    // a suggestion picked on a verdict page is applied once the notebook has loaded
    if (!nb || !pendingAction.current) return;
    const act = pendingAction.current;
    pendingAction.current = null;
    setTimeout(() => applyRef.current?.(act), 50);
  }, [nb?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !document.querySelector(".modal")) { e.preventDefault(); runRef.current?.(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!nb && problem) return <NotebookProblem problem={problem} retry={reload} />;
  if (!nb) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Notebook" /><Card><Skeleton label="Opening notebook" /></Card></div>;
  const s = nb.strategy;
  const inst = nb.instrument && "symbol" in nb.instrument ? nb.instrument : null;
  const group = nb.group && nb.group.members?.length ? nb.group : null;
  const market = markets.find((m) => m.id === (group?.market ?? inst?.market));
  const currency = group ? (market?.currency ?? "") : inst?.currency || (inst?.market === "IN" || !inst ? "INR" : "");
  const maxDays = market?.max_days?.[s.tf] ?? 3650;
  const periods = PERIODS[s.tf].filter((d) => d <= maxDays);
  const picked = spanDays(days) ?? Number(days);
  // the first test covers years of prices, as the page promises: 5 years of daily candles (or all there is), a
  // shorter span of intraday ones (R5O-010)
  const last = (nb.experiments ?? []).slice(-1)[0] as Experiment | undefined;
  // the test period the last run used, when this notebook still offers it: the next run starts there, not back at 5 years (round 39)
  const lastDays = last && last.tf === s.tf && periods.includes(last.days) ? last.days : undefined;
  const fallbackPeriod = lastDays ?? (s.tf === "1d" ? [...periods].reverse().find((d) => d <= DEFAULT_DAILY_DAYS) : periods[Math.min(1, periods.length - 1)]);
  const period = periods.includes(picked) || spanDays(days) != null ? picked : fallbackPeriod ?? 365;
  const periodValue = periods.includes(period) ? String(period) : days;
  const isUpload = inst?.market === "CSV";
  const experiments = [...(nb.experiments || [])].reverse();
  const nextV = ((nb.experiments ?? []).slice(-1)[0]?.v ?? 0) + 1;

  // saving rules saves the rules: the notebook's name is the person's, and only a name the notebook was given (none, or
  // the strategy's own) follows a new strategy name (R11C-001: every rule edit put "TCS SMA Crossover" over the name typed)
  const setStrategy = (st: Strategy) => patch({ strategy: st,
    ...(st.name !== s.name && st.name && isAutoNotebookName(nb.name, s.name) ? { name: st.name } : {}) });

  // this month's experiments are used up on the plan (also when viewing as a smaller plan than the owner's own use, R17-004)
  const outOfRuns = me?.usage.backtests_limit != null && me.usage.backtests_used >= me.usage.backtests_limit;
  // what the plan won't run, said under the Run button before it's pressed, not only after (R92-002)
  const groupCap = me?.plan_info.group_size;
  const planBlock = !fno && inst?.fno ? "Indian F&O is on the Pro plan."
    : !allIndicators && usesPro(s) ? "These rules use indicators beyond price, SMA, EMA and RSI. Basic unlocks all of them."
    : group && groupCap != null && group.members.length > groupCap
      ? `Your ${me!.plan_info.name} plan tests up to ${groupCap} instruments in a group and this one has ${group.members.length}: pick fewer, or ${group.members.length <= LIMITS.basic.group_size ? `Basic tests up to ${LIMITS.basic.group_size}` : `Pro tests up to ${LIMITS.pro.group_size}`}.`
    : null;
  const run = async () => {
    if (running || starting.current) return;
    if (!s.entry.length && !(s.shortEntry ?? []).length) { notify("Add at least one entry rule first."); return; }
    if (planBlock) { plansToast(planBlock); return; }
    // nothing chosen to test on: the run would go to the default instrument and its defaults for money (BTC/USD with $500,000
    // and a $20 order fee, DA-003), so it waits for a choice
    if (!inst && !group) { notify("Choose what to test it on first: a market and an instrument, or a group.", { label: "Choose market", run: () => nav(`/n/${nb.id}/market`) }); return; }
    const body: Record<string, unknown> = { label: label.trim(), days: period };
    if (isUpload) {
      const up = getUpload(nb.id);
      if (!up) { notify("Upload your CSV again: this browser no longer has it."); nav(`/n/${nb.id}/market`); return; }
      Object.assign(body, { bars: up.bars, upload: { name: up.name, currency: up.currency, step: up.step } });
    }
    starting.current = true;
    setRunning(true);
    try {
      // the run tests the rules on the server: a save that didn't get there would test the old ones
      if (!(await flush(true))) {
        notify("The rules couldn't be saved, so nothing was run. The experiment would have tested the rules as they were before your edit.",
          { label: "Retry the save", run: () => void flush() });
        return;
      }
      const out = await api<{ experiment: Experiment; defaulted?: string | null; instrument?: Instrument | null }>(`/notebooks/${nb.id}/experiments`, { method: "POST", body });
      trackBacktest(group ? "group" : "notebook");
      setNb((cur) => (cur ? { ...cur, ...(out.instrument ? { instrument: out.instrument } : {}), experiments: [...(cur.experiments || []), out.experiment] } : cur));
      setLabel("");
      refreshMe();
      refreshNotebooks();
      // nothing was picked, so it ran on the default; say which, and where to change it
      if (out.defaulted) notify(`Tested on ${out.defaulted}, the default. Change it under Testing on.`, { label: "Change market", run: () => nav(`/n/${nb.id}/market`) });
      if (mounted.current) nav(`/n/${nb.id}/e/${out.experiment.v}`);
      else notify(`Experiment v${out.experiment.v} of "${nb.name}" finished.`, { label: `Open v${out.experiment.v}`, run: () => nav(`/n/${nb.id}/e/${out.experiment.v}`) });
    } catch (e) {
      const same = e instanceof ApiError && e.code === "unchanged" ? last : undefined;
      if (same) notify(e instanceof Error ? e.message : "Nothing has changed since the last run.", { label: `Open v${same.v}`, run: () => nav(`/n/${nb.id}/e/${same.v}`) });
      else fail(e);
    } finally { starting.current = false; if (mounted.current) setRunning(false); }
  };

  runRef.current = run;

  const del = async () => {
    setRemoving(false);
    try { await api(`/notebooks/${nb.id}`, { method: "DELETE" }); await refreshNotebooks(); nav("/notebooks"); } catch (e) { fail(e); }
  };

  const togglePin = async () => {
    const pinned = !nb.pinned;
    setNb({ ...nb, pinned });
    try { await api(`/notebooks/${nb.id}`, { method: "PUT", body: { pinned } }); await refreshNotebooks(); notify(pinned ? "Pinned to the top of your notebooks." : "Unpinned."); }
    catch (e) { setNb({ ...nb, pinned: !pinned }); fail(e); }
  };

  const duplicate = async () => {
    try {
      // copy the rules as they are on screen, including an edit that hasn't saved yet
      if (!(await flush(true))) { notify("The rules couldn't be saved, so no copy was made.", { label: "Retry the save", run: () => void flush() }); return; }
      const copy = await api<Notebook>(`/notebooks/${nb.id}/duplicate`, { method: "POST" });
      await refreshNotebooks();
      nav(`/n/${copy.id}`);
      notify("Made a copy with the same rules and market. Its experiments start fresh.");
    } catch (e) { fail(e); }
  };

  const exportStrategy = async () => {
    if (!canExport) { plansToast("Strategy export is on the Pro plan."); return; }
    try {
      // the group a notebook tests on goes with its rules, so an import sets up the same group (R11C-013)
      const r = await api<Response>("/export/strategy", { method: "POST", raw: true,
        body: { strategy: { ...s, name: nb.name }, instrument: group ? null : inst?.id ?? null, ...(group ? { group } : {}) } });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob());
      a.download = (nb.name.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "") || "strategy") + ".json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { fail(e); }
  };

  const paperTrade = async () => {
    if (group) {
      if (!groupOk) { plansToast("Paper trading a group is on the Basic plan."); return; }
      if (s.tf === "1d") { notify("Paper trading a group needs intraday candles. Switch the rules to 5-minute, 15-minute or 1-hour candles first."); return; }
      setGroupStart(true);
      return;
    }
    if (!inst || isUpload) { notify(isUpload ? "Paper trading needs live prices, so it doesn't work on uploaded data." : "Pick what to trade first."); return; }
    setPaperAsk(true);         // what is about to start, said first (R1-031)
  };
  const startSingle = async () => {
    setPaperAsk(false);
    if (!inst) return;
    try {
      const snap = await api<{ id: string }>("/live/sessions", { method: "POST", body: { strategy: { ...s, name: nb.name }, instrument: inst.id } });
      track("paper trading started", { kind: "single" });
      refreshMe();
      nav(`/paper/${snap.id}`);
    } catch (e) { fail(e); }
  };

  const startGroup = async () => {
    try {
      const snap = await api<{ id: string }>("/live/groups", { method: "POST", body: { strategy: { ...s, name: nb.name }, group, fast } });
      track("paper trading started", { kind: "group" });
      refreshMe();
      nav(`/paper/${snap.id}`);
    } catch (e) { fail(e); }
  };

  const apply = (action: string) => {
    if (action === "longer_period") setDays(String(periods[periods.length - 1]));
    else if (action === "other_instrument") nav(`/n/${nb.id}/market`);
    else if (action === "paper_trade") paperTrade();
    else if (action === "note") notesRef.current?.focus();
    else if (action === "edit_rules") document.getElementById("rules-h")?.scrollIntoView({ behavior: "smooth", block: "start" });
    else if (action === "loosen_entry") setStrategy({ ...s, entry: s.entry.map((c) => ({ ...c, op: c.op === "xa" ? "gt" : c.op === "xb" ? "lt" : c.op })) });
    else if (action === "trend_filter") setStrategy({ ...s, entryJoin: "all", entry: [...s.entry, { l: { t: "price" }, op: s.side === "short" ? "lt" : "gt", r: { t: "sma", p: 200 } }] });
    if (["loosen_entry", "trend_filter", "longer_period"].includes(action)) notify("Rules updated. Run the next experiment to compare.");
  };
  applyRef.current = apply;

  const steps = [
    // a group is something to test on too (R11C-017: a library copy set to a group showed step 1 as next)
    { done: !!inst || !!group, text: "Pick what to test it on", act: () => nav(`/n/${nb.id}/market`) },
    { done: s.entry.length > 0, text: "Check the rules", act: () => document.getElementById("rules-h")?.scrollIntoView({ behavior: "smooth" }) },
    { done: experiments.length > 0, text: "Run an experiment", act: () => document.getElementById("exp-h")?.scrollIntoView({ behavior: "smooth" }) },
  ];
  const nextStep = steps.findIndex((x) => !x.done);

  const cols: Column<Experiment>[] = [
    { key: "v", header: "Run", rowHeader: true, cell: (e) => <Link className="link" to={`/n/${nb.id}/e/${e.v}`}><b>v{e.v}</b></Link> },
    // a run whose figures contradict each other says so in its row, never "Capital lost" (R38-001)
    { key: "ret", header: "Overall", numeric: true, cell: (e) => isLegacyEmptied(e) ? "Not shown" : <Signed value={e.stats.ret}>{lost(e.stats.ret)}</Signed> },
    { key: "what", header: "What changed", wrap: true, cell: (e) => <><Link className="link" to={`/n/${nb.id}/e/${e.v}`}><b>{e.label}</b></Link><span className="k-sub-line">{dateOnly(e.created_at)} · {e.instrument.symbol} · {periodName(e.days)}{isLegacyEmptied(e) ? "" : ` · ${e.stats.n} trade${e.stats.n === 1 ? "" : "s"}`}</span>{isLegacyEmptied(e) && <span className="k-sub-line">{legacyNote(e)}</span>}</> },
    { key: "unseen", header: "Unseen part", numeric: true, cell: (e) => { if (isLegacyEmptied(e)) return "–"; const u = e.verdict.checks.find((c) => c.id === "unseen")?.data; return u ? <Signed value={u.unseen_ret}>{lost(u.unseen_ret)}</Signed> : "–"; } },
    { key: "verdict", header: "Verdict", cell: (e) => isLegacyEmptied(e) ? "Not shown" : <VerdictBadge v={e.verdict.verdict} label={badgeLabel(e.verdict)} /> },
  ];

  return (
    <div className="nb-grid">
      <div className="k-page">
        <PageHeader eyebrow="Trade · Build and test" title={nb.name}
          lede={nb.question ? <span title={s.text && s.text.trim() !== nb.question ? s.text.trim() : undefined} data-testid="nb-question">{nb.question}</span> : "Write the question this notebook should answer."}
          actions={<span className="k-note" aria-live="polite">{saving === "failed"
            ? <button type="button" className="link k-down" data-testid="save-retry" onClick={() => void flush()}>Not saved · Retry</button>
            : saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : ""}</span>} />

        <Card label="About this notebook">
          <CardHead title="About this notebook" info={HELP.notebook} infoLabel="About notebooks" actions={<>
            <button type="button" className="btn quiet sm" onClick={() => setRewrite(true)}><Sparkle size={17} />Describe the idea again</button>
            {live ? <Link className="btn quiet sm" to={`/paper/${live.id}`} title={`Running since ${dateOnly(live.started_at)}`}><Pulse size={17} />Paper trading · open</Link>
              : <button type="button" className="btn quiet sm" onClick={paperTrade} disabled={(!inst && !group) || isUpload}><Pulse size={17} />Paper trade{group && !groupOk ? " (Basic)" : ""}</button>}
            <button type="button" className="btn quiet sm" onClick={togglePin} aria-pressed={!!nb.pinned}><Pin size={17} filled={!!nb.pinned} />{nb.pinned ? "Pinned" : "Pin"}</button>
            <MoreMenu align="right" items={[
              { label: "Make a copy", icon: <Copy size={16} />, run: duplicate },
              { label: `Export${canExport ? "" : " (Pro)"}`, icon: <Download size={16} />, run: exportStrategy },
              { label: "Delete notebook", icon: <Trash size={16} />, run: () => setRemoving(true), danger: true },
            ]} />
          </>} />
          <FormGrid label="Notebook name and question">
            <Field label="Notebook name" wide maxLength={80} value={nb.name} onChange={(e) => patch({ name: e.target.value })}
              onBlur={(e) => { if (!e.target.value.trim()) patch({ name: "Untitled notebook" }, true); }} />
            <Field label="The question this notebook tests" wide>{(fid) => (
              <AutoGrow id={fid} className="k-textarea" aria-label="The question this notebook tests" value={nb.question ?? ""} maxLength={300}
                placeholder="The question you want answered, e.g. Does buying NIFTY on RSI dips beat just holding it?" onChange={(e) => patch({ question: e.target.value })} />
            )}</Field>
          </FormGrid>
          <div className="k-row">
            <Link to={`/n/${nb.id}/market`} className={`market-btn${inst || group ? "" : " empty"}`}>
              <span className="k-eyebrow">{inst || group ? "Testing on" : "Not chosen yet"}</span>
              <span className="market-btn-main">
                {group ? <>{group.name}<span className="muted"> · {group.members.length} {group.market === "CRYPTO" ? "coins" : "stocks"}, up to {group.maxOpen} at once · {market?.name ?? group.market} · {TF_NAME[s.tf]} candles</span>{group.maxOpen < group.members.length && <span className="muted k-small"> · when more signal at once than there are free slots, the members listed first take them</span>}
                  {/* the plan's cap on a group, said before a run is refused for it (R44-003) */}
                  {me?.plan_info.group_size != null && group.members.length > me.plan_info.group_size && <span className="k-small" data-testid="group-over-cap"> · Your {me.plan_info.name} plan tests up to {me.plan_info.group_size} instruments in a group: pick fewer, or {group.members.length <= LIMITS.basic.group_size ? `Basic tests up to ${LIMITS.basic.group_size}` : `Pro tests up to ${LIMITS.pro.group_size}`}</span>}</>
                  : inst ? <>{inst.symbol}<span className="muted">{marketName(inst, markets) ? ` · ${marketName(inst, markets)}` : ""}{currency ? ` · ${currency}` : ""} · {TF_NAME[s.tf]} candles</span></>
                  : "Pick a market and instrument"}
              </span>
              <span className="market-btn-cta">{inst || group ? "Change" : "Choose"}<span aria-hidden="true"> →</span></span>
            </Link>
            {sipTestLink(inst, group) && <Link className="btn quiet sm" to={sipTestLink(inst, group)!}>Test as a SIP</Link>}
          </div>
        </Card>

        {nextStep !== -1 && (
          <ol className="steps" aria-label="Getting started">
            {steps.map((st, i) => (
              <li key={st.text} className={st.done ? "done" : i === nextStep ? "next" : ""}>
                <button type="button" onClick={st.act}>
                  <span className="num" aria-hidden="true">{st.done ? "✓" : i + 1}</span>
                  <span>{st.text}{i === nextStep && <span className="sr-only"> (next step)</span>}</span>
                </button>
              </li>
            ))}
          </ol>
        )}

        {/* the questions are for before the first run: once the idea has been tested they are answered or no longer matter, and
            "Question 1 of 3" beside a finished experiment reads as unfinished (DA-011) */}
        {gaps && experiments.length === 0 && (
          <GapsCard s={s} gaps={gaps} hasInstrument={!!inst || !!group} currency={currency}
            onStrategy={setStrategy}
            onInstrument={(i) => patch({ instrument: i, instrumentId: i.id, strategy: { ...s, risk: riskForCurrency(s.risk, i.currency) } }, true)}
            onPickMarket={() => nav(`/n/${nb.id}/market`)} onDone={() => { setGaps(null); patch({ gaps: null }, true); }}
            onAnswered={(answered) => saveGaps({ ...gaps, answered })} />
        )}
        {(!gaps || experiments.length > 0) && s.entry.length > 0 && !s.exit.length && !(s.shortExit ?? []).length && (
          <Notice tone="warn" role="status">No sell rule is set: {(() => {
            // what closes a trade without a sell rule: the stop, the target, the trailing stop, a time limit, the day's square-off
            const ways = [s.risk.sl > 0 && "stop loss", s.risk.tgt > 0 && "target", (s.risk.trail ?? 0) > 0 && "trailing stop", (s.risk.maxBars ?? 0) > 0 && "time limit",
              s.tf !== "1d" && s.session?.squareoff && `${s.session.squareoff} square-off`].filter(Boolean);
            return ways.length ? `a trade closes only at the ${ways.join(" or the ")}, or at the end of the test.` : "a trade stays open until the end of the test.";
          })()} Add one under The rules.</Notice>
        )}

        <RulesCard s={s} currency={currency} onChange={setStrategy} defaultStop={!!gaps && experiments.length === 0 && !gaps.mentioned.includes("sl") && !gaps.answered?.sl && !statedIn(s.text).includes("sl")}
          onRebuilt={(g) => { if (gaps) saveGaps({ ...gaps, mentioned: [...new Set([...gaps.mentioned, ...g.mentioned])], notes: g.notes, warnings: g.warnings }); }} />

        <Card id="exp-h" label="Experiments">
          <CardHead title="Experiments" info={HELP.experiments} infoLabel="About experiments"
            actions={nb.experiments.length >= 2 ? <Link className="link" to={`/n/${nb.id}/compare`}>Compare experiments →</Link> : undefined} />
          {!isUpload && (
            <div className="k-field">
              <div className="k-label-row"><span className="k-lbl">Test period</span><Info label="About the test period">{HELP.period} Add your own with + Custom: any whole number of days, weeks, months or years up to the {maxDays.toLocaleString("en-IN")} days stored for {TF_NAME[s.tf].toLowerCase()} candles here.</Info></div>
              <ChipBar label="Test period" value={periodValue} onChange={setDays}
                options={periods.map((d) => ({ value: String(d), label: periodName(d) }))}
                custom={{ storageKey: `stratlab.chips.period.${me?.id ?? "anon"}`, units: SPAN_UNITS, defaultUnit: "months", validate: spanCheck(maxDays, 5) }} />
            </div>
          )}
          <FormGrid label="Run an experiment" onSubmit={(e) => { e.preventDefault(); void run(); }}>
            <Field label="What's different this time?" optional wide maxLength={120} value={label} placeholder={nextV === 1 ? "e.g. First try" : "e.g. Tighter stop loss"} onChange={(e) => setLabel(e.target.value)} />
            <FormActions>
              <button type="submit" className="btn" disabled={running || outOfRuns} title={outOfRuns ? "This month's experiments are used up on your plan" : undefined}>{running ? `Running 4 honesty checks…${elapsed >= 3 ? ` ${runTime(elapsed)}` : ""}` : `Run experiment v${nextV}`}</button>
              <span className="k-small k-muted kbd-hint">or press <kbd>{navigator.platform.includes("Mac") ? "⌘" : "Ctrl"}</kbd>+<kbd>Enter</kbd></span>
              <Info label="What happens when I run an experiment?">{HELP.runExperiment}</Info>
            </FormActions>
          </FormGrid>
          {!inst && !group && (
            <div data-testid="run-needs-market">
              <Notice tone="warn" role="status" action={{ label: "Choose market", to: `/n/${nb.id}/market` }}>Choose what to test it on before you run it: the rules need a market and an instrument, or a group.</Notice>
            </div>
          )}
          {planBlock && <p className="k-note" data-testid="run-plan-block">🔒 {planBlock} <Link className="link" to="/plans">Plans</Link></p>}
          <p className="k-note">
            {me?.usage.backtests_limit != null ? `${Math.max(0, me.usage.backtests_limit - me.usage.backtests_used)} of ${me.usage.backtests_limit} backtests left this month${outOfRuns ? " (limit reached)" : ""}. ` : ""}
            {runCopy(group?.members.length ?? 0, running, elapsed)}
            {outOfRuns && <> <Link className="link" to="/plans">Plans</Link></>}
          </p>
          {experiments.length === 0
            ? <EmptyState title="No experiments yet">Your first run shows whether the idea holds up.</EmptyState>
            : <DataTable stack label="Experiments" columns={cols} rows={experiments} rowKey={(e) => String(e.v)} />}
        </Card>
      </div>

      <aside className="k-page">
        <Card label="Lab notes">
          <CardHead title="Lab notes" level={3} info={HELP.labNotes} infoLabel="About lab notes" />
          <label className="sr-only" htmlFor="notes">Lab notes</label>
          <textarea id="notes" ref={notesRef} className="lab-note" value={nb.notes ?? ""} maxLength={4000}
            placeholder="What did you notice? What do you want to try next?" onChange={(e) => patch({ notes: e.target.value })} />
        </Card>
      </aside>

      {paperAsk && inst && (
        <ConfirmDialog title={`Paper trade on ${inst.symbol}?`} confirmLabel="Start paper trading" danger={false} onConfirm={() => void startSingle()} onClose={() => setPaperAsk(false)}>
          <span className="k-stack k-tight">
            {/* how fills and fees really work, not "at live prices" (DB-021) */}
            <span>The rules of "{nb.name}" on {TF_NAME[s.tf]} candles, live, with {money(s.risk.capital, currency)} of fake money. Nothing real is ever placed.</span>
            <span className="k-note" data-testid="paper-fills">{fillsLine(s.risk, markets.find((m) => m.id === inst.market)?.costs, money(s.risk.brokerage, currency, 2))}</span>
            <span className="k-note">It runs until you stop it and counts as one of your plan's paper sessions. A message for each paper trade is {me?.alerts.enabled ? "on" : "off"} in Settings (Notifications).</span>
          </span>
        </ConfirmDialog>
      )}
      {groupStart && group && (
        <Modal title="Paper trade this group" onClose={() => setGroupStart(false)}>
          <div className="k-stack">
            <p className="k-small k-muted">{group.name}: {group.members.length} instruments, up to {group.maxOpen} open at once, on {TF_NAME[s.tf]} candles, with fake money.</p>
            {group.market === "IN" && (
              <div className="k-stack k-tight">
                <CheckField label={<><b>Faster entries</b>{!fastOk && " (Pro)"}</>} checked={fast.ticks} disabled={!fastOk && !fast.ticks} onChange={(on) => setFast({ ...fast, ticks: on })} />
                <span className="k-note">Check the entry rules on the live price every 15 seconds, and enter as soon as they hold, instead of waiting for the candle to close. Exits still wait for the close. A backtest can't see inside a candle, so paper results will differ from it.</span>
              </div>
            )}
            <FormGrid label="Group limits">
              {group.market === "IN" && (
                <Field label={`Skip if the spread is over${fastOk ? "" : " (Pro)"}`} unit="% of price" disabled={!fastOk && !fast.maxSpreadPct} info="The spread is the gap between the best bid and ask. With a spread limit set, an entry is skipped when the order book is too thin or unknown; the session counts how many were skipped." type="number" min={0} max={5} step={0.05}
                  value={fast.maxSpreadPct || ""} placeholder="Off" onChange={(e) => setFast({ ...fast, maxSpreadPct: Math.max(0, Math.min(5, +e.target.value || 0)) })} />
              )}
              <Field label="Skip anything cheaper than" unit={currencySymbol(currency) || undefined} type="number" min={0} step={1} value={fast.minPrice || ""} placeholder="Off"
                onChange={(e) => setFast({ ...fast, minPrice: Math.max(0, +e.target.value || 0) })} />
            </FormGrid>
            {group.market === "IN" && !fastOk && <Notice action={plansAction}>Faster entries and the spread limit are on the Pro plan.</Notice>}
            <div className="k-row">
              <button type="button" className="btn" onClick={() => { setGroupStart(false); startGroup(); }}>Start paper trading</button>
              <button type="button" className="btn quiet" onClick={() => setGroupStart(false)}>Cancel</button>
            </div>
          </div>
        </Modal>
      )}

      {rewrite && (
        <Modal title="Describe the idea again" onClose={() => setRewrite(false)}>
          <p className="k-small k-muted">This replaces the rules in this notebook. Your experiments stay as they are.</p>
          <IdeaComposer busyLabel="Replace the rules" autoFocus byHand={false} market={group?.market ?? inst?.market} symbol={inst?.symbol ?? null} onBuilt={async (b) => {
            // the rules are replaced; the capital, costs, sizing and risk per trade stay unless the new words give them
            const picked = b.instrument && !inst ? b.instrument : null;
            const kept = rebuiltRisk(s.risk, b.strategy.risk, b.gaps.mentioned);
            const risk = picked ? riskForCurrency(kept, picked.currency) : kept;
            patch({ strategy: { ...b.strategy, name: nb.name, risk }, ...(picked ? { instrument: picked, instrumentId: picked.id } : {}) }, true);
            saveGaps(b.gaps);
            setRewrite(false);
          }} />
        </Modal>
      )}

      {removing && (
        <ConfirmDialog title={`Delete the notebook "${nb.name}"?`} confirmLabel="Delete notebook" onConfirm={del} onClose={() => setRemoving(false)}>
          This removes the notebook and all its experiments. It can't be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}
