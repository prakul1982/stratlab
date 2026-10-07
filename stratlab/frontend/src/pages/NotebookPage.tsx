import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly, money, pct, periodName, TF_NAME } from "../lib/format";
import { riskForCurrency, usesPro } from "../lib/rules";
import type { Experiment, Instrument, LiveRow, Notebook, Strategy, Tf } from "../lib/types";
import { getUpload } from "../lib/upload";
import { track, trackBacktest } from "../lib/analytics";
import { spanCheck, spanDays, SPAN_UNITS } from "../lib/intervals";
import { GapsCard, type GapInfo } from "../components/Gaps";
import { Copy, Download, Pin, Pulse, Sparkle, Trash } from "../components/Icons";
import { MoreMenu } from "../components/MoreMenu";
import { RulesCard } from "../components/Rules";
import { AutoGrow, Info, Modal, VerdictBadge } from "../components/ui";
import { Card, CardHead, CheckField, ChipBar, ConfirmDialog, DataTable, EmptyState, Field, FormActions, FormGrid, PageHeader, Skeleton, type Column } from "../components/kit";
import { HELP } from "../lib/help";
import { sipTestLink } from "../lib/sip";
import { IdeaComposer } from "../components/IdeaComposer";
import "./trade/trade.css";

/* /n/:id: one notebook: its question, what it tests on, the rules, and every experiment run on them. Built from the kit
 * (components/kit); the two-column layout with the lab notes beside it stays. */

const PERIODS: Record<Tf, number[]> = {
  "1d": [182, 365, 730, 1095, 1825, 3650], "1h": [30, 90, 180, 365, 730], "15m": [30, 60, 90, 180, 365], "5m": [15, 30, 60, 120],
};

export function useNotebook(id: string | undefined) {
  const { fail, refreshNotebooks } = useApp();
  const [nb, setNb] = useState<Notebook | null>(null);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved">("idle");
  const timer = useRef<number>(undefined);
  const pending = useRef<Record<string, unknown>>({});

  const load = useCallback(async () => {
    if (!id) return;
    try { setNb(await api<Notebook>(`/notebooks/${id}`)); } catch (e) { fail(e); }
  }, [id, fail]);
  useEffect(() => { setNb(null); load(); }, [load]);

  const flush = useCallback(async () => {
    if (!id || !Object.keys(pending.current).length) return;
    const body = pending.current;
    pending.current = {};
    setSaving("saving");
    try {
      await api(`/notebooks/${id}`, { method: "PUT", body });
      setSaving("saved");
      if ("name" in body || "instrument" in body || "question" in body) refreshNotebooks();
    } catch (e) { fail(e); setSaving("idle"); }
  }, [id, fail, refreshNotebooks]);

  const patch = useCallback((p: Partial<Notebook> & { instrumentId?: string | null }, now = false) => {
    setNb((cur) => (cur ? { ...cur, ...p } : cur));
    const body: Record<string, unknown> = {};
    if (p.name !== undefined) body.name = p.name;
    if (p.question !== undefined) body.question = p.question;
    if (p.notes !== undefined) body.notes = p.notes;
    if (p.strategy !== undefined) body.strategy = p.strategy;
    if (p.instrumentId !== undefined) body.instrument = p.instrumentId ?? "";
    Object.assign(pending.current, body);
    window.clearTimeout(timer.current);
    if (now) flush(); else timer.current = window.setTimeout(flush, 700);
  }, [flush]);

  useEffect(() => () => { window.clearTimeout(timer.current); flush(); }, [flush]);
  return { nb, setNb, patch, saving, reload: load, flush };
}

function marketName(inst: Instrument | null, markets: { id: string; name: string }[]) {
  if (!inst) return null;
  return markets.find((m) => m.id === inst.market)?.name ?? (inst.market === "IN" ? "India" : inst.market);
}

export function NotebookPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const { markets, fail, notify, refreshMe, refreshNotebooks, me, allIndicators, fno } = useApp();
  const canExport = !!me?.plan_info.features?.export;
  const { nb, patch, saving, setNb, flush } = useNotebook(id);
  const [gaps, setGaps] = useState<GapInfo | null>((loc.state as { gaps?: GapInfo } | null)?.gaps ?? null);
  const [days, setDays] = useState("365");
  const [label, setLabel] = useState("");
  const [running, setRunning] = useState(false);
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

  useEffect(() => { setGaps((loc.state as { gaps?: GapInfo } | null)?.gaps ?? null); }, [id, loc.state]);
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

  if (!nb) return <div className="k-page"><PageHeader eyebrow="Trade · Build and test" title="Notebook" /><Card><Skeleton label="Opening notebook" /></Card></div>;
  const s = nb.strategy;
  const inst = nb.instrument && "symbol" in nb.instrument ? nb.instrument : null;
  const group = nb.group && nb.group.members?.length ? nb.group : null;
  const market = markets.find((m) => m.id === (group?.market ?? inst?.market));
  const currency = group ? (market?.currency ?? "") : inst?.currency || (inst?.market === "IN" || !inst ? "INR" : "");
  const maxDays = market?.max_days?.[s.tf] ?? 3650;
  const periods = PERIODS[s.tf].filter((d) => d <= maxDays);
  const picked = spanDays(days) ?? Number(days);
  const period = periods.includes(picked) || spanDays(days) != null ? picked : periods[Math.min(1, periods.length - 1)] ?? 365;
  const periodValue = periods.includes(period) ? String(period) : days;
  const isUpload = inst?.market === "CSV";
  const experiments = [...(nb.experiments || [])].reverse();
  const nextV = ((nb.experiments ?? []).slice(-1)[0]?.v ?? 0) + 1;
  const last = (nb.experiments ?? []).slice(-1)[0] as Experiment | undefined;

  const setStrategy = (st: Strategy) => patch({ strategy: st, name: st.name });

  const run = async () => {
    if (running) return;
    if (!s.entry.length && !(s.shortEntry ?? []).length) { notify("Add at least one entry rule first."); return; }
    if (!fno && inst?.fno) { notify("Indian F&O is on the Pro plan.", { label: "See plans", run: () => nav("/plans") }); return; }
    if (!allIndicators && usesPro(s)) { notify("This uses indicators beyond price, SMA, EMA and RSI. Basic unlocks all of them.", { label: "See plans", run: () => nav("/plans") }); return; }
    const body: Record<string, unknown> = { label: label.trim(), days: period };
    if (isUpload) {
      const up = getUpload(nb.id);
      if (!up) { notify("Upload your CSV again: this browser no longer has it."); nav(`/n/${nb.id}/market`); return; }
      Object.assign(body, { bars: up.bars, upload: { name: up.name, currency: up.currency, step: up.step } });
    }
    await flush();
    setRunning(true);
    try {
      const out = await api<{ experiment: Experiment; defaulted?: string | null; instrument?: Instrument | null }>(`/notebooks/${nb.id}/experiments`, { method: "POST", body });
      trackBacktest(group ? "group" : "notebook");
      setNb({ ...nb, ...(out.instrument ? { instrument: out.instrument } : {}), experiments: [...(nb.experiments || []), out.experiment] });
      setLabel("");
      refreshMe();
      refreshNotebooks();
      // nothing was picked, so it ran on the default; say which, and where to change it
      if (out.defaulted) notify(`Tested on ${out.defaulted}, the default. Change it under Testing on.`, { label: "Change market", run: () => nav(`/n/${nb.id}/market`) });
      nav(`/n/${nb.id}/e/${out.experiment.v}`);
    } catch (e) {
      const same = e instanceof ApiError && e.code === "unchanged" ? last : undefined;
      if (same) notify(e instanceof Error ? e.message : "Nothing has changed since the last run.", { label: `Open v${same.v}`, run: () => nav(`/n/${nb.id}/e/${same.v}`) });
      else fail(e);
    } finally { setRunning(false); }
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
      await flush();   // copy the rules as they are on screen, including an edit that hasn't saved yet
      const copy = await api<Notebook>(`/notebooks/${nb.id}/duplicate`, { method: "POST" });
      await refreshNotebooks();
      nav(`/n/${copy.id}`);
      notify("Made a copy with the same rules and market. Its experiments start fresh.");
    } catch (e) { fail(e); }
  };

  const exportStrategy = async () => {
    if (!canExport) { notify("Strategy export is on the Pro plan.", { label: "See plans", run: () => nav("/plans") }); return; }
    try {
      const r = await api<Response>("/export/strategy", { method: "POST", body: { strategy: s, instrument: inst?.id ?? null }, raw: true });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await r.blob());
      a.download = (s.name.replace(/[^a-z0-9]+/gi, "-") || "strategy") + ".json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { fail(e); }
  };

  const paperTrade = async () => {
    if (group) {
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
    else if (action === "trend_filter") setStrategy({ ...s, entryJoin: "all", entry: [...s.entry, { l: { t: "price" }, op: "gt", r: { t: "sma", p: 200 } }] });
    if (["loosen_entry", "trend_filter", "longer_period"].includes(action)) notify("Rules updated. Run the next experiment to compare.");
  };
  applyRef.current = apply;

  const steps = [
    { done: !!inst, text: "Pick what to test it on", act: () => nav(`/n/${nb.id}/market`) },
    { done: s.entry.length > 0, text: "Check the rules", act: () => document.getElementById("rules-h")?.scrollIntoView({ behavior: "smooth" }) },
    { done: experiments.length > 0, text: "Run an experiment", act: () => document.getElementById("exp-h")?.scrollIntoView({ behavior: "smooth" }) },
  ];
  const nextStep = steps.findIndex((x) => !x.done);

  const cols: Column<Experiment>[] = [
    { key: "v", header: "Run", rowHeader: true, cell: (e) => <Link className="link" to={`/n/${nb.id}/e/${e.v}`}><b>v{e.v}</b></Link> },
    { key: "what", header: "What changed", wrap: true, cell: (e) => <><Link className="link" to={`/n/${nb.id}/e/${e.v}`}><b>{e.label}</b></Link><span className="k-sub-line">{dateOnly(e.created_at)} · {e.instrument.symbol} · {periodName(e.days)} · {e.stats.n} trade{e.stats.n === 1 ? "" : "s"}</span></> },
    { key: "ret", header: "Overall", numeric: true, cell: (e) => pct(e.stats.ret) },
    { key: "unseen", header: "Unseen years", numeric: true, cell: (e) => { const u = e.verdict.checks.find((c) => c.id === "unseen")?.data; return u ? pct(u.unseen_ret) : "–"; } },
    { key: "verdict", header: "Verdict", cell: (e) => <VerdictBadge v={e.verdict.verdict} /> },
  ];

  return (
    <div className="nb-grid">
      <div className="k-page">
        <PageHeader eyebrow="Trade · Build and test" title={nb.name}
          lede={nb.question || "Write the question this notebook should answer."}
          actions={<span className="k-note" aria-live="polite">{saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : ""}</span>} />

        <Card label="About this notebook">
          <CardHead title="About this notebook" info={HELP.notebook} infoLabel="About notebooks" actions={<>
            <button type="button" className="btn quiet sm" onClick={() => setRewrite(true)}><Sparkle size={17} />Describe the idea again</button>
            {live ? <Link className="btn quiet sm" to={`/paper/${live.id}`} title={`Running since ${dateOnly(live.started_at)}`}><Pulse size={17} />Paper trading · open</Link>
              : <button type="button" className="btn quiet sm" onClick={paperTrade} disabled={(!inst && !group) || isUpload}><Pulse size={17} />Paper trade</button>}
            <button type="button" className="btn quiet sm" onClick={togglePin} aria-pressed={!!nb.pinned}><Pin size={17} filled={!!nb.pinned} />{nb.pinned ? "Pinned" : "Pin"}</button>
            <MoreMenu align="right" items={[
              { label: "Make a copy", icon: <Copy size={16} />, run: duplicate },
              { label: `Export${canExport ? "" : " (Pro)"}`, icon: <Download size={16} />, run: exportStrategy },
              { label: "Delete notebook", icon: <Trash size={16} />, run: () => setRemoving(true), danger: true },
            ]} />
          </>} />
          <FormGrid label="Notebook name and question">
            <Field label="Notebook name" maxLength={80} value={nb.name} onChange={(e) => patch({ name: e.target.value })}
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
                {group ? <>{group.name}<span className="muted"> · {group.members.length} {group.market === "CRYPTO" ? "coins" : "stocks"}, up to {group.maxOpen} at once · {market?.name ?? group.market} · {TF_NAME[s.tf]} candles</span></>
                  : inst ? <>{inst.symbol}<span className="muted">{marketName(inst, markets) ? ` · ${marketName(inst, markets)}` : ""}{currency ? ` · ${currency}` : ""} · {TF_NAME[s.tf]} candles</span></>
                  : "Pick a market and instrument"}
              </span>
              <span className="market-btn-cta">{inst || group ? "Change" : "Choose"}<span aria-hidden="true"> →</span></span>
            </Link>
            {sipTestLink(inst) && <Link className="btn quiet sm" to={sipTestLink(inst)!}>Test as a SIP</Link>}
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

        {gaps && (
          <GapsCard s={s} gaps={gaps} hasInstrument={!!inst} currency={currency}
            onStrategy={setStrategy}
            onInstrument={(i) => patch({ instrument: i, instrumentId: i.id, strategy: { ...s, risk: riskForCurrency(s.risk, i.currency) } }, true)}
            onPickMarket={() => nav(`/n/${nb.id}/market`)} onDone={() => setGaps(null)} />
        )}

        <RulesCard s={s} currency={currency} onChange={setStrategy} />

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
              <button type="submit" className="btn" disabled={running}>{running ? "Running 4 honesty checks…" : `Run experiment v${nextV}`}</button>
              <span className="k-small k-muted kbd-hint">or press <kbd>{navigator.platform.includes("Mac") ? "⌘" : "Ctrl"}</kbd>+<kbd>Enter</kbd></span>
              <Info label="What happens when I run an experiment?">{HELP.runExperiment}</Info>
            </FormActions>
          </FormGrid>
          <p className="k-note">
            {me?.usage.backtests_limit != null ? `${Math.max(0, me.usage.backtests_limit - me.usage.backtests_used)} of ${me.usage.backtests_limit} experiments left this month. ` : ""}
            Takes a few seconds.
          </p>
          {experiments.length === 0
            ? <EmptyState title="No experiments yet">Your first run shows whether the idea holds up.</EmptyState>
            : <DataTable label="Experiments" columns={cols} rows={experiments} rowKey={(e) => String(e.v)} />}
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
            <span>The rules of "{nb.name}" on {TF_NAME[s.tf]} candles, live, with {money(s.risk.capital, currency)} of fake money. Orders fill at live prices; nothing real is ever placed.</span>
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
                <CheckField label={<b>Faster entries</b>} checked={fast.ticks} onChange={(on) => setFast({ ...fast, ticks: on })} />
                <span className="k-note">Check the entry rules on the live price every 15 seconds, and enter as soon as they hold, instead of waiting for the candle to close. Exits still wait for the close. A backtest can't see inside a candle, so paper results will differ from it.</span>
              </div>
            )}
            <FormGrid label="Group limits">
              {group.market === "IN" && (
                <Field label="Skip if the spread is over" unit="% of price" info="The spread is the gap between the best bid and ask. With a spread limit set, an entry is skipped when the order book is too thin or unknown; the session counts how many were skipped." type="number" min={0} max={5} step={0.05}
                  value={fast.maxSpreadPct || ""} placeholder="Off" onChange={(e) => setFast({ ...fast, maxSpreadPct: Math.max(0, Math.min(5, +e.target.value || 0)) })} />
              )}
              <Field label="Skip anything cheaper than" type="number" min={0} step={1} value={fast.minPrice || ""} placeholder="Off"
                onChange={(e) => setFast({ ...fast, minPrice: Math.max(0, +e.target.value || 0) })} />
            </FormGrid>
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
          <IdeaComposer busyLabel="Replace the rules" autoFocus onBuilt={async (b) => {
            patch({ strategy: { ...b.strategy, name: nb.name }, ...(b.instrument && !inst ? { instrument: b.instrument, instrumentId: b.instrument.id } : {}) }, true);
            setGaps(b.gaps);
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
