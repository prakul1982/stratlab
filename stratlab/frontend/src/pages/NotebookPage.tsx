import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly, pct, periodName, TF_NAME } from "../lib/format";
import { riskForCurrency, usesPro } from "../lib/rules";
import type { Experiment, Instrument, Notebook, Strategy, Tf } from "../lib/types";
import { getUpload } from "../lib/upload";
import { GapsCard, type GapInfo } from "../components/Gaps";
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
  const timer = useRef<number>();
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
  const { markets, fail, notify, refreshMe, refreshNotebooks, me, isPro } = useApp();
  const { nb, patch, saving, setNb, flush } = useNotebook(id);
  const [gaps, setGaps] = useState<GapInfo | null>((loc.state as { gaps?: GapInfo } | null)?.gaps ?? null);
  const [days, setDays] = useState(365);
  const [label, setLabel] = useState("");
  const [running, setRunning] = useState(false);
  const [rewrite, setRewrite] = useState(false);
  const notesRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setGaps((loc.state as { gaps?: GapInfo } | null)?.gaps ?? null); }, [id, loc.state]);
  const applyRef = useRef<(action: string) => void>();
  const pendingAction = useRef<string | null>(null);
  useEffect(() => { pendingAction.current = (loc.state as { action?: string } | null)?.action ?? null; }, [loc.state]);
  useEffect(() => {
    // a suggestion picked on a verdict page is applied once the notebook has loaded
    if (!nb || !pendingAction.current) return;
    const act = pendingAction.current;
    pendingAction.current = null;
    setTimeout(() => applyRef.current?.(act), 50);
  }, [nb?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!nb) return <Loading label="Opening notebook" />;
  const s = nb.strategy;
  const inst = nb.instrument && "symbol" in nb.instrument ? nb.instrument : null;
  const currency = inst?.currency || (inst?.market === "IN" || !inst ? "INR" : "");
  const market = markets.find((m) => m.id === inst?.market);
  const maxDays = market?.max_days?.[s.tf] ?? 3650;
  const periods = PERIODS[s.tf].filter((d) => d <= maxDays);
  const period = periods.includes(days) ? days : periods[Math.min(1, periods.length - 1)] ?? 365;
  const isUpload = inst?.market === "CSV";
  const experiments = [...(nb.experiments || [])].reverse();
  const nextV = ((nb.experiments ?? []).slice(-1)[0]?.v ?? 0) + 1;
  const last = (nb.experiments ?? []).slice(-1)[0] as Experiment | undefined;

  const setStrategy = (st: Strategy) => patch({ strategy: st, name: st.name });

  const run = async () => {
    if (!inst) { notify("Pick what to test it on first."); nav(`/n/${nb.id}/market`); return; }
    if (!s.entry.length) { notify("Add at least one buy rule first."); return; }
    if (!isPro && (usesPro(s) || inst.fno)) { notify("This uses Pro features (advanced indicators or F&O).", { label: "See plans", run: () => nav("/plans") }); return; }
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
      setNb({ ...nb, experiments: [...(nb.experiments || []), out.experiment] });
      setLabel("");
      refreshMe();
      refreshNotebooks();
      nav(`/n/${nb.id}/e/${out.experiment.v}`);
    } catch (e) { fail(e); } finally { setRunning(false); }
  };

  const del = async () => {
    if (!confirm(`Delete the notebook "${nb.name}" and all its experiments? This can't be undone.`)) return;
    try { await api(`/notebooks/${nb.id}`, { method: "DELETE" }); await refreshNotebooks(); nav("/"); } catch (e) { fail(e); }
  };

  const exportStrategy = async () => {
    if (!isPro) { notify("Strategy export is on the Pro plan.", { label: "See plans", run: () => nav("/plans") }); return; }
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
    if (!inst || isUpload) { notify(isUpload ? "Paper trading needs live prices, so it doesn't work on uploaded data." : "Pick what to trade first."); return; }
    try {
      const snap = await api<{ id: string }>("/live/sessions", { method: "POST", body: { strategy: { ...s, name: nb.name }, instrument: inst.id } });
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
            <span className="eyebrow row" style={{ gap: 0 }}>Notebook · {nb.name}<Info>{HELP.notebook}</Info></span>
            <span className="small muted" aria-live="polite">{saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : ""}</span>
          </div>
          <AutoGrow className="question" aria-label="The question this notebook tests" value={nb.question ?? ""} maxLength={300}
            placeholder="What are you trying to find out?" onChange={(e) => patch({ question: e.target.value })} />
          <div className="row wrap" style={{ gap: 8 }}>
            {inst ? (
              <>
                <span className="pill">{inst.symbol}{marketName(inst, markets) ? ` · ${marketName(inst, markets)}` : ""}</span>
                {currency && <span className="pill">{currency}</span>}
                <span className="pill">{TF_NAME[s.tf]} candles</span>
                <Link to={`/n/${nb.id}/market`} className="link">Change market</Link>
                <Info>{HELP.market}</Info>
              </>
            ) : (
              <Link to={`/n/${nb.id}/market`} className="btn blue sm">Pick what to test it on</Link>
            )}
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
            <button className="link" onClick={() => setRewrite(true)}>Describe the idea again</button>
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
        <section className="card stack" style={{ gap: 10 }}>
          <h2 className="h3 row" style={{ gap: 0 }}>Paper trading<Info>{HELP.paper}</Info></h2>
          <p className="small muted">
            {last?.verdict.verdict === "edge" ? "The last verdict looks like a real edge. Try it on live prices with fake money." :
              "Try these rules on live prices with fake money. Best once a verdict says the edge looks real."}
          </p>
          <button className="btn outline sm" onClick={paperTrade} disabled={!inst || isUpload}>Paper trade these rules</button>
        </section>
        <section className="card stack" style={{ gap: 10 }}>
          <h2 className="h3">More</h2>
          <button className="btn quiet sm" style={{ justifyContent: "flex-start" }} onClick={exportStrategy}>Export rules as a file{isPro ? "" : " (Pro)"}</button>
          <button className="btn danger sm" style={{ justifyContent: "flex-start" }} onClick={del}>Delete this notebook</button>
        </section>
      </aside>

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
