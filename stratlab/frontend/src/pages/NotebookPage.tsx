import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly, pct, periodName, TF_NAME } from "../lib/format";
import { riskForCurrency, usesPro } from "../lib/rules";
import type { Experiment, Instrument, Notebook, Strategy, Tf } from "../lib/types";
import { getUpload } from "../lib/upload";
import { track, trackBacktest } from "../lib/analytics";
import { GapsCard, type GapInfo } from "../components/Gaps";
import { Copy, Download, Pin, Pulse, Sparkle, Trash } from "../components/Icons";
import { MoreMenu } from "../components/MoreMenu";
import { RulesCard } from "../components/Rules";
import { AutoGrow, Info, Loading, Modal, VerdictBadge } from "../components/ui";
import { HELP } from "../lib/help";
import { IdeaComposer } from "../components/IdeaComposer";

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

function ExperimentRow({ e, to }: { e: Experiment; to: string }) {
  const unseen = e.verdict.checks.find((c) => c.id === "unseen")?.data;
  return (
    <Link to={to} className="exp-row">
      <span className="mono" style={{ fontSize: 15, fontWeight: 500 }}>v{e.v}</span>
      <span className="stack" style={{ gap: 2, minWidth: 0 }}>
        <b style={{ fontSize: 16 }}>{e.label}</b>
        <span className="small muted">{dateOnly(e.created_at)} · {e.instrument.symbol} · {periodName(e.days)} · {e.stats.n} trade{e.stats.n === 1 ? "" : "s"}</span>
      </span>
      <span className="nums">{pct(e.stats.ret)} overall{unseen ? <><br />{pct(unseen.unseen_ret)} unseen</> : null}</span>
      <VerdictBadge v={e.verdict.verdict} />
    </Link>
  );
}

export function NotebookPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const { markets, fail, notify, refreshMe, refreshNotebooks, me, allIndicators, fno } = useApp();
  const canExport = !!me?.plan_info.features?.export;
  const { nb, patch, saving, setNb, flush } = useNotebook(id);
  const [gaps, setGaps] = useState<GapInfo | null>((loc.state as { gaps?: GapInfo } | null)?.gaps ?? null);
  const [days, setDays] = useState(365);
  const [label, setLabel] = useState("");
  const [running, setRunning] = useState(false);
  const [rewrite, setRewrite] = useState(false);
  const [groupStart, setGroupStart] = useState(false);
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

  if (!nb) return <Loading label="Opening notebook" />;
  const s = nb.strategy;
  const inst = nb.instrument && "symbol" in nb.instrument ? nb.instrument : null;
  const group = nb.group && nb.group.members?.length ? nb.group : null;
  const market = markets.find((m) => m.id === (group?.market ?? inst?.market));
  const currency = group ? (market?.currency ?? "") : inst?.currency || (inst?.market === "IN" || !inst ? "INR" : "");
  const maxDays = market?.max_days?.[s.tf] ?? 3650;
  const periods = PERIODS[s.tf].filter((d) => d <= maxDays);
  const period = periods.includes(days) ? days : periods[Math.min(1, periods.length - 1)] ?? 365;
  const isUpload = inst?.market === "CSV";
  const experiments = [...(nb.experiments || [])].reverse();
  const nextV = ((nb.experiments ?? []).slice(-1)[0]?.v ?? 0) + 1;
  const last = (nb.experiments ?? []).slice(-1)[0] as Experiment | undefined;

  const setStrategy = (st: Strategy) => patch({ strategy: st, name: st.name });

  const run = async () => {
    if (running) return;
    if (!inst && !group) { notify("Pick what to test it on first."); nav(`/n/${nb.id}/market`); return; }
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
      const out = await api<{ experiment: Experiment }>(`/notebooks/${nb.id}/experiments`, { method: "POST", body });
      trackBacktest(group ? "group" : "notebook");
      setNb({ ...nb, experiments: [...(nb.experiments || []), out.experiment] });
      setLabel("");
      refreshMe();
      refreshNotebooks();
      nav(`/n/${nb.id}/e/${out.experiment.v}`);
    } catch (e) { fail(e); } finally { setRunning(false); }
  };

  runRef.current = run;

  const del = async () => {
    if (!confirm(`Delete the notebook "${nb.name}" and all its experiments? This can't be undone.`)) return;
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

  const suggestions = last?.verdict.suggestions ?? [];
  const apply = (action: string) => {
    if (action === "longer_period") setDays(periods[periods.length - 1]);
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

  return (
    <div className="nb-grid">
      <div className="stack" style={{ gap: 32, minWidth: 0 }}>
        <div className="stack" style={{ gap: 14 }}>
          <div className="spread" style={{ flexWrap: "wrap" }}>
            <span className="eyebrow row" style={{ gap: 0, minWidth: 0, flex: 1 }}>Notebook ·&nbsp;
              <input className="nb-name" aria-label="Notebook name (click to rename)" title="Click to rename" value={nb.name} maxLength={80}
                size={Math.max(8, Math.min(nb.name.length + 1, 48))}
                onChange={(e) => patch({ name: e.target.value })} onBlur={(e) => { if (!e.target.value.trim()) patch({ name: "Untitled notebook" }, true); }}
                onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
              <Info>{HELP.notebook}</Info></span>
            <span className="small muted" aria-live="polite">{saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : ""}</span>
          </div>
          <AutoGrow className="question" aria-label="The question this notebook tests" value={nb.question ?? ""} maxLength={300}
            placeholder="The question you want answered, e.g. Does buying NIFTY on RSI dips beat just holding it?" onChange={(e) => patch({ question: e.target.value })} />
          <div className="row" style={{ gap: 10 }}>
            <Link to={`/n/${nb.id}/market`} className={`market-btn${inst || group ? "" : " empty"}`} aria-label={group ? `Testing on the group ${group.name}. Change it` : inst ? `Testing on ${inst.symbol}. Change market or instrument` : "Pick what to test it on"}>
              <span className="eyebrow" style={{ fontSize: 11 }}>{inst || group ? "Testing on" : "Not chosen yet"}</span>
              <span className="market-btn-main">
                {group ? <>{group.name}<span className="muted"> · {group.members.length} {group.market === "CRYPTO" ? "coins" : "stocks"}, up to {group.maxOpen} at once · {market?.name ?? group.market} · {TF_NAME[s.tf]} candles</span></>
                  : inst ? <>{inst.symbol}<span className="muted">{marketName(inst, markets) ? ` · ${marketName(inst, markets)}` : ""}{currency ? ` · ${currency}` : ""} · {TF_NAME[s.tf]} candles</span></>
                  : "Pick a market and instrument"}
              </span>
              <span className="market-btn-cta">{inst || group ? "Change" : "Choose"} →</span>
            </Link>
            <Info>{HELP.market}</Info>
          </div>
          <div className="toolbar" role="toolbar" aria-label="Notebook actions">
            <button className="btn quiet sm" onClick={() => setRewrite(true)}><Sparkle size={17} />Describe the idea again</button>
            <button className="btn quiet sm" onClick={paperTrade} disabled={(!inst && !group) || isUpload}><Pulse size={17} />Paper trade</button>
            <button className="btn quiet sm" onClick={togglePin} aria-pressed={!!nb.pinned}><Pin size={17} filled={!!nb.pinned} />{nb.pinned ? "Pinned" : "Pin"}</button>
            <MoreMenu items={[
              { label: "Make a copy", icon: <Copy size={16} />, run: duplicate },
              { label: `Export${canExport ? "" : " (Pro)"}`, icon: <Download size={16} />, run: exportStrategy },
              { label: "Delete notebook", icon: <Trash size={16} />, run: del, danger: true },
            ]} />
          </div>
        </div>

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

        <section className="stack" aria-labelledby="exp-h" style={{ gap: 16 }}>
          <div className="spread" style={{ flexWrap: "wrap" }}>
            <h2 id="exp-h" className="h2 row" style={{ gap: 0 }}>Experiments<Info>{HELP.experiments}</Info></h2>
            {nb.experiments.length >= 2 && <Link className="link" to={`/n/${nb.id}/compare`}>Compare experiments →</Link>}
          </div>
          <div className="card stack" style={{ gap: 18 }}>
            {!isUpload && (
              <div className="stack" style={{ gap: 8 }}>
                <span className="label row" style={{ gap: 0 }}>Test period<Info>{HELP.period}</Info></span>
                <div className="seg" role="group" aria-label="Test period">
                  {periods.map((d) => <button key={d} aria-pressed={d === period} onClick={() => setDays(d)}>{periodName(d)}</button>)}
                </div>
              </div>
            )}
            <div className="stack" style={{ gap: 8 }}>
              <label className="label" htmlFor="exp-label">What's different this time? <span className="muted" style={{ fontWeight: 400 }}>(optional)</span></label>
              <div className="row wrap" style={{ gap: 10 }}>
                <input id="exp-label" className="input" style={{ flex: "1 1 240px" }} value={label} maxLength={120}
                  placeholder={nextV === 1 ? "e.g. First try" : "e.g. Tighter stop loss"} onChange={(e) => setLabel(e.target.value)} />
                <button className="btn blue" disabled={running} onClick={run}>{running ? "Running 4 honesty checks…" : `Run experiment v${nextV}`}</button>
                <span className="small muted kbd-hint">or press <kbd>{navigator.platform.includes("Mac") ? "⌘" : "Ctrl"}</kbd>+<kbd>Enter</kbd></span>
                <Info label="What happens when I run an experiment?">{HELP.runExperiment}</Info>
              </div>
            </div>
            <p className="hint">
              {me?.usage.backtests_limit != null ? `${Math.max(0, me.usage.backtests_limit - me.usage.backtests_used)} of ${me.usage.backtests_limit} experiments left this month. ` : ""}
              Takes a few seconds.
            </p>
          </div>
          {experiments.length === 0
            ? <p className="muted">No experiments yet. Your first run shows whether the idea holds up.</p>
            : <div className="stack" style={{ gap: 10 }}>{experiments.map((e) => <ExperimentRow key={e.v} e={e} to={`/n/${nb.id}/e/${e.v}`} />)}</div>}
        </section>
      </div>

      <aside className="stack" style={{ gap: 18 }}>
        <section className="card stack" style={{ gap: 8 }}>
          <h2 className="h3 row" style={{ gap: 0 }}>Lab notes<Info>{HELP.labNotes}</Info></h2>
          <label className="sr-only" htmlFor="notes">Lab notes</label>
          <textarea id="notes" ref={notesRef} className="lab-note" value={nb.notes ?? ""} maxLength={4000}
            placeholder="What did you notice? What do you want to try next?" onChange={(e) => patch({ notes: e.target.value })} />
        </section>
        {suggestions.length > 0 && (
          <section className="card stack" style={{ gap: 10 }}>
            <h2 className="h3 row" style={{ gap: 0 }}>Worth testing next<Info>{HELP.nextSteps}</Info></h2>
            {suggestions.map((sg) => (
              <button key={sg.action} className="btn quiet" style={{ justifyContent: "flex-start", whiteSpace: "normal", textAlign: "left", padding: "10px 14px" }}
                onClick={() => apply(sg.action)}>{sg.text}</button>
            ))}
          </section>
        )}
      </aside>

      {groupStart && group && (
        <Modal title="Paper trade this group" onClose={() => setGroupStart(false)}>
          <div className="stack" style={{ gap: 16 }}>
            <p className="muted">{group.name}: {group.members.length} instruments, up to {group.maxOpen} open at once, on {TF_NAME[s.tf]} candles, with fake money.</p>
            {group.market === "IN" && (
              <label className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                <input type="checkbox" style={{ width: 20, height: 20, marginTop: 2 }} checked={fast.ticks} onChange={(e) => setFast({ ...fast, ticks: e.target.checked })} />
                <span className="stack" style={{ gap: 2 }}><b>Faster entries</b>
                  <span className="small muted">Check the entry rules on the live price every 15 seconds, and enter as soon as they hold, instead of waiting for the candle to close. Exits still wait for the close. A backtest can't see inside a candle, so paper results will differ from it.</span></span>
              </label>
            )}
            <div className="row wrap" style={{ gap: 16 }}>
              {group.market === "IN" && (
                <label className="field" style={{ width: 200 }}>Skip if the spread is over (% of price)
                  <input className="input" type="number" min={0} max={5} step={0.05} value={fast.maxSpreadPct || ""} placeholder="Off"
                    onChange={(e) => setFast({ ...fast, maxSpreadPct: Math.max(0, Math.min(5, +e.target.value || 0)) })} /></label>
              )}
              <label className="field" style={{ width: 200 }}>Skip anything cheaper than
                <input className="input" type="number" min={0} step={1} value={fast.minPrice || ""} placeholder="Off"
                  onChange={(e) => setFast({ ...fast, minPrice: Math.max(0, +e.target.value || 0) })} /></label>
            </div>
            {group.market === "IN" && <p className="small muted">The spread is the gap between the best bid and ask. 0.1% suits large, liquid stocks. With a spread limit set, an entry is skipped when the order book is too thin or unknown; the session counts how many were skipped.</p>}
            <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
              <button className="btn quiet" onClick={() => setGroupStart(false)}>Cancel</button>
              <button className="btn blue" onClick={() => { setGroupStart(false); startGroup(); }}>Start paper trading</button>
            </div>
          </div>
        </Modal>
      )}

      {rewrite && (
        <Modal title="Describe the idea again" onClose={() => setRewrite(false)}>
          <p className="muted" style={{ marginBottom: 14 }}>This replaces the rules in this notebook. Your experiments stay as they are.</p>
          <IdeaComposer busyLabel="Replace the rules" autoFocus onBuilt={async (b) => {
            patch({ strategy: { ...b.strategy, name: nb.name }, ...(b.instrument && !inst ? { instrument: b.instrument, instrumentId: b.instrument.id } : {}) }, true);
            setGaps(b.gaps);
            setRewrite(false);
          }} />
        </Modal>
      )}
    </div>
  );
}
