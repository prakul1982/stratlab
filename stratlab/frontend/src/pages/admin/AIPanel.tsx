import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, safeHref, fmtDate } from "../../lib/format";
import { Badge, Card, CardHead, ConfirmDialog, Disclosure, Light, Skeleton } from "../../components/kit";
import { blockedLine, providerWord } from "./aiBlocks";
import { aiCountText } from "../../lib/connection";
import { shortLinks } from "./attention";

// Admin only: provider names are fine here (never on public pages).
type Model = {
  id: string; /** the model's usable name: an id Cloudflare lists as a UUID is shown by its name (R7M-008) */ name?: string;
  in_use: boolean; rank: number | null; success: number | null; tries: number; median_ms: number | null;
  probe: { ok: number; tries: number; at: number | null; error: string | null };
  last_error: string | null; last_error_at: number | null; open_until: number | null; open_reason: string | null;
  blocked: boolean; /** who blocked it and when (an epoch), kept from the day this was added */ blocked_by?: string | null; blocked_at?: number | null;
  pinned: boolean; ctx: number | null; thinks: boolean;
};
type Provider = {
  name: string; label: string; configured: boolean; missing: string[]; key_url: string; free: string; terms: "ok" | "prototype" | "paid";
  note: string; variables: string[]; model_variable: string; state: "ok" | "warn" | "fail" | "off" | "idle"; state_text: string;
  result?: string | null;
  quota: { limited: boolean; reset_at: number | null; remaining: { requests?: number; tokens?: number; requests_reset?: number; tokens_reset?: number } | null; remaining_at: number | null };
  last_ok: number | null; last_error: string | null; last_used_model: string | null; pinned: string | null; pinned_by: "admin" | "railway" | null;
  ranked_at: number | null; rank_error: string | null; discovered: number | null; skipped: Record<string, number>; probing: boolean;
  models: Model[]; blocked: string[]; blocked_info?: Record<string, { by?: string | null; at?: number | null }>;
};
type Step = { provider: string; label: string; model: string; ready: boolean; out_of_credit?: boolean };
type Route = { label: string; budget_s: number; steps: Step[] };
/** One link of "Who is asked": the provider and model, and why it won't answer now (out of free credit, or paused). */
const stepText = (s: Step) => `${s.label} · ${s.model}${s.out_of_credit ? " (out of credit)" : s.ready ? "" : " (paused)"}`;
export type AIView = {
  providers: Provider[]; routes: Record<string, Route>; cache: { entries: number; hits: number; misses: number };
  rerank_every_hours: number; last_failure: { at: number; task: string; detail: string } | null;
};
/** What is waiting for a yes: Block, Unblock, Pin and Re-rank change how every user's AI questions are routed (R13S-004). */
type Ask = { kind: "rerank"; provider?: Provider } | { kind: "block"; p: Provider; model: string; blocked: boolean }
  | { kind: "pin"; p: Provider; model: string | null };
type RankSnap = Record<string, unknown>;

type TestRow = { name: string; label: string; ok: boolean; quota?: boolean; error: string | null; model: string | null; ms: number };

/** A provider's own words with any long link cut to its address (the whole text on hover), so a 150-character link can't fill a line (R11P-007). */
function Said({ text }: { text: string | null | undefined }) {
  const s = shortLinks(text);
  return <span title={s.full}>{s.text}</span>;
}
const iso = (t: number | null | undefined) => (t ? new Date(t * 1000).toISOString() : null);
const secs = (ms: number | null) => (ms == null ? "–" : `${(ms / 1000).toFixed(1)} s`);
function until(t: number | null) {
  if (!t) return "";
  const s = t - Date.now() / 1000;
  if (s <= 60) return "in under a minute";
  if (s < 3600) return `in ${Math.round(s / 60)} min`;
  if (s < 86400) return `in ${Math.round(s / 3600)} h`;
  return `on ${fmtDate(t * 1000, { year: false })}`;
}
const SKIPPED: Record<string, string> = {
  "not a chat model": "not chat models", "not English-first": "built for another language", "too small": "too small",
  specialist: "code or maths specialists", "thinks too long": "slow reasoners", "not free": "not free", "not for this job": "not for this job",
};

/** Admin: every AI provider's state, the models in use and how they're doing, the order each job asks them in, and
 * the controls (test now, re-measure, pin or block a model). Missing keys come with where to get one. */
export function AIPanel({ onChanged }: { onChanged?: () => void }) {
  const { notify, fail } = useApp();
  const [v, setV] = useState<AIView | null>(null);
  const [tests, setTests] = useState<Record<string, TestRow> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [ask, setAsk] = useState<Ask | null>(null);
  const load = useCallback(async () => { try { setV(await api<AIView>("/admin/ai")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => { load(); }, [load]);
  const probing = v?.providers.some((p) => p.probing);
  useEffect(() => {
    if (!probing) return;
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, [probing, load]);

  const act = async (key: string, fn: () => Promise<AIView | void>) => {
    setBusy(key);
    try { const out = await fn(); if (out) setV(out); onChanged?.(); } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const testAll = () => act("test", async () => {
    const r = await api<{ providers: TestRow[]; view: AIView }>("/admin/ai/test", { method: "POST" });
    setTests(Object.fromEntries(r.providers.map((t) => [t.name, t])));
    return r.view;
  });
  const restoreRank = (snap: RankSnap) => act("rank-restore", async () => {
    const r = await api<AIView>("/admin/ai/rank-restore", { method: "POST", body: { ranks: snap } });
    notify("The earlier order is back.");
    return r;
  });
  const rerank = (provider?: string) => act(`rerank-${provider ?? "all"}`, async () => {
    const r = await api<AIView & { started: string[]; undo?: RankSnap }>("/admin/ai/rerank", { method: "POST", body: provider ? { provider } : {} });
    const msg = r.started.length ? "Measuring the models now. This takes a minute or two; the list updates by itself." : "Already measuring.";
    if (r.started.length && r.undo) notify(msg, { label: "Undo", run: () => void restoreRank(r.undo!) });
    else notify(msg);
    return r;
  });
  const pin = (p: Provider, model: string | null) => act(`pin-${p.name}`, async () => {
    const r = await api<AIView>("/admin/ai/pin", { method: "POST", body: { provider: p.name, model } });
    notify(model ? `${p.label} now uses only ${model}.` : `${p.label} is back on its measured models.`);
    return r;
  });
  const setBlocked = (p: Provider, model: string, blocked: boolean) => act(`block-${p.name}-${model}`, async () => {
    const r = await api<AIView>("/admin/ai/block", { method: "POST", body: { provider: p.name, model, blocked } });
    notify(blocked ? `${model} won't be used again.` : `${model} can be used again.`, { label: "Undo", run: () => void setBlocked(p, model, !blocked) });
    return r;
  });
  const confirm = () => {
    const a = ask;
    setAsk(null);
    if (!a) return;
    if (a.kind === "rerank") void rerank(a.provider?.name);
    else if (a.kind === "pin") void pin(a.p, a.model);
    else void setBlocked(a.p, a.model, a.blocked);
  };

  const on = v?.providers.filter((p) => p.configured) ?? [];
  const off = v?.providers.filter((p) => !p.configured) ?? [];
  // with no key at all, the two quickest to set up stay in view; every other provider's steps are one click away
  const quick = on.length ? [] : off.filter((p) => QUICK.includes(p.name));
  const rest = off.filter((p) => !quick.includes(p));
  const lastRank = Math.max(0, ...on.map((p) => p.ranked_at ?? 0));
  const reused = v && v.cache.hits + v.cache.misses ? Math.round((v.cache.hits * 100) / (v.cache.hits + v.cache.misses)) : null;

  return (
    <Card label="AI">
      <CardHead title="AI"
        actions={<>
          <button type="button" className="btn quiet sm" disabled={!!busy || !on.length} onClick={testAll}>{busy === "test" ? "Testing…" : "Test every provider"}</button>
          <button type="button" className="btn quiet sm" disabled={!!busy || !on.length || !!probing} onClick={() => setAsk({ kind: "rerank" })}>
            {probing ? "Measuring…" : busy === "rerank-all" ? "Starting…" : "Re-rank models"}</button>
        </>} />
      {!v ? <Skeleton label="Loading the AI providers" lines={3} /> : (
        <>
          <p className="k-small k-muted">
            {/* the count as Overview words it, on the same readings (R29A-014: "5 working of 10 set up (11 known)" there beside
                "10 of 11 providers set up" here) */}
            AI providers: {aiCountText(on.filter((p) => p.result === "working").length, on.length, v.providers.length)}. Each one's models are measured with a short test every {v.rerank_every_hours} hours
            {lastRank ? ` (last ${ago(iso(lastRank))})` : " (not yet)"}, and the ones that answer correctly and fast are used. A provider that fails,
            runs out of free quota or is rate limited is skipped until it's back.{reused != null && ` ${reused}% of questions since the last restart were answered from the cache.`}
          </p>
          {!on.length && <p className="k-small"><b>No AI keys yet</b>, so the idea builder and research reads are off. Groq and Google Gemini are the quickest to set up (below).</p>}
          {v.last_failure && <p className="k-small adm-warn-t" role="status">
            Last time nothing could answer ({ago(iso(v.last_failure.at))}, {v.routes[v.last_failure.task]?.label.toLowerCase() ?? v.last_failure.task}): <Said text={v.last_failure.detail} /></p>}

          {on.length > 0 && (
            <div className="k-stack k-small" aria-label="Routing order">
              <b>Who is asked, in order</b>
              {Object.entries(v.routes).map(([task, r]) => (
                <span key={task}><b>{r.label}</b> <span className="k-muted">(at most {r.budget_s} s): </span>
                  <span className="k-muted">{r.steps.length ? r.steps.slice(0, 5).map(stepText).join(" → ") : "–"}
                    {r.steps.length > 5 ? ` → ${r.steps.length - 5} more` : ""}</span></span>
              ))}
            </div>
          )}

          {on.map((p) => <ProviderBlock key={p.name} p={p} test={tests?.[p.name]} busy={busy} rerank={(name) => setAsk({ kind: "rerank", provider: v.providers.find((x) => x.name === name) })} pin={(pp, model) => setAsk({ kind: "pin", p: pp, model })}
            block={(pp, model, blocked) => setAsk({ kind: "block", p: pp, model, blocked })} />)}

          {off.length > 0 && (
            <div className="k-stack" aria-label="More free providers">
              {quick.length > 0 && <>
                <b className="k-small">Quickest to set up</b>
                {quick.map((p) => <MissingProvider key={p.name} p={p} />)}
              </>}
              {rest.length > 0 && (
                <Disclosure summary={`${quick.length ? "Other" : "More"} providers you can add (${rest.length})`} testId="ai-more-providers">
                  <div className="k-stack">{rest.map((p) => <MissingProvider key={p.name} p={p} />)}</div>
                </Disclosure>
              )}
              <p className="k-small k-muted">Each one is optional. Add the variables in Railway → Variables, redeploy, then press Re-rank models.</p>
            </div>
          )}
        </>
      )}
      {ask && (
        <ConfirmDialog title={askTitle(ask)} confirmLabel={askLabel(ask)} onConfirm={confirm} onClose={() => setAsk(null)} >
          {askBody(ask)}
        </ConfirmDialog>
      )}
    </Card>
  );
}

function askTitle(a: Ask): string {
  if (a.kind === "rerank") return a.provider ? `Re-rank ${a.provider.label}'s models?` : "Re-rank every provider's models?";
  if (a.kind === "pin") return a.model ? `Pin ${a.p.label} to ${a.model}?` : `Unpin ${a.p.label}?`;
  return `${a.blocked ? "Block" : "Unblock"} ${a.model}?`;
}
function askLabel(a: Ask): string {
  if (a.kind === "pin") return a.model ? "Pin it" : "Unpin";
  return a.kind === "rerank" ? "Re-rank" : a.blocked ? "Block it" : "Unblock it";
}
function askBody(a: Ask): string {
  if (a.kind === "rerank") return "The models are measured again, which takes a minute or two and can change the order every user's AI questions are routed in. The message that follows has an Undo.";
  if (a.kind === "pin") return a.model ? `${a.p.label} will use only ${a.model}, for every user, until it is unpinned.` : `${a.p.label} goes back to its measured models, for every user.`;
  if (!a.blocked) return `${a.p.label} can use ${a.model} again, for every user. The message that follows has an Undo.`;
  return `${a.p.label} won't use ${a.model} again, for every user, until it is unblocked. The message that follows has an Undo.`;
}

const QUICK = ["groq", "gemini"];

/** A provider with no key: its free allowance, the variables to set and where to get a key. */
function MissingProvider({ p }: { p: Provider }) {
  return (
    <div className="ai-missing">
      <div className="k-stack adm-grow">
        <span className="k-small"><b>{p.label}</b>{p.terms === "prototype" && <> <Badge tone="warn" dot={false}>Prototyping tier</Badge></>}
          {p.terms === "paid" && <> <Badge tone="warn" dot={false}>Paid</Badge></>}</span>
        <span className="k-small k-muted">{p.free}{p.note ? ` ${p.note}` : ""}</span>
        <span className="k-small k-muted">Set <span className="adm-mono">{p.missing.join(" and ")}</span>.</span>
      </div>
      <a className="btn quiet sm" href={safeHref(p.key_url)} target="_blank" rel="noopener noreferrer" aria-label={`Get a key: ${p.label}`}>Get a key</a>
    </div>
  );
}

function ProviderBlock({ p, test, busy, rerank, pin, block }: {
  p: Provider; test?: TestRow; busy: string | null; rerank: (name: string) => void;
  pin: (p: Provider, model: string | null) => void; block: (p: Provider, model: string, on: boolean) => void;
}) {
  const [light, word] = providerWord(p);
  const skipped = Object.entries(p.skipped || {}).map(([why, n]) => `${n} ${SKIPPED[why] ?? why}`).join(", ");
  const left = p.quota.remaining;
  // how soon that allowance fills again: a per-minute token allowance "nearly gone" is full again a minute later, so the
  // count alone read as a provider running out while its light said OK (R46-005)
  const refill = (sec?: number) => sec == null ? "" : sec < 90 ? ` (a per-minute allowance, full again within ${Math.max(1, Math.round(sec))} s)`
    : sec < 5400 ? ` (full again within ${Math.round(sec / 60)} min)` : ` (full again within ${Math.round(sec / 3600)} h)`;
  return (
    <div className="ai-provider" aria-label={p.label}>
      <div className="k-spread">
        <span className="k-row">
          <b>{p.label}</b>
          {light ? <Light state={light} word={word} /> : <Badge>{word}</Badge>}
          {p.terms === "prototype" && <Badge tone="warn" dot={false}>Prototyping tier</Badge>}
          {p.terms === "paid" && <Badge tone="warn" dot={false}>Paid, asked last</Badge>}
        </span>
        <button type="button" className="btn quiet sm" disabled={!!busy || p.probing} onClick={() => rerank(p.name)} aria-label={`Re-rank ${p.label} models`}>
          {p.probing ? "Measuring…" : "Re-rank"}</button>
      </div>
      <span className="k-small k-muted"><Said text={p.state_text} /></span>
      {test && <span className="k-small" role="status">Test: {test.ok ? `answered with ${test.model} in ${(test.ms / 1000).toFixed(1)} s` : <Said text={test.error} />}</span>}
      {p.quota.limited && p.quota.reset_at && <span className="k-small">Free quota resets {until(p.quota.reset_at)}.</span>}
      {p.pinned && (
        <span className="k-small k-row">
          <span>Pinned to <span className="adm-mono">{p.pinned}</span>{p.pinned_by === "railway" ? ` by ${p.model_variable} in Railway` : ""}.</span>
          {p.pinned_by === "admin" && <button type="button" className="btn quiet sm" disabled={!!busy} onClick={() => pin(p, null)}>Unpin</button>}
        </span>
      )}
      {/* one line per provider until opened (DJ-036: System was 23 phone screens, mostly model rows) */}
      <Disclosure summary={`Models, limits and controls (${p.models.length} model${p.models.length === 1 ? "" : "s"})`} testId={`ai-details-${p.name}`}>
      <div className="k-stack">
      {left && (left.requests != null || left.tokens != null) && (
        <span className="k-small k-muted">Left this period: {[left.requests != null && `${left.requests.toLocaleString("en-IN")} requests${refill(left.requests_reset)}`, left.tokens != null && `${left.tokens.toLocaleString("en-IN")} tokens${refill(left.tokens_reset)}`].filter(Boolean).join(", ")}
          {p.quota.remaining_at ? ` (as of ${ago(iso(p.quota.remaining_at))})` : ""}</span>
      )}
      <span className="k-small k-muted">Free limit: {p.free}{p.note ? ` ${p.note}` : ""}</span>
      <span className="k-small k-muted">
        {p.ranked_at && p.discovered === 0
          // a measure that listed nothing measured nothing: not "Measured" beside a provider never checked (R47-019)
          ? `Tried ${ago(iso(p.ranked_at))}, but the provider listed no models: its known-good models are used until a test answers.`
          : p.ranked_at ? `Measured ${ago(iso(p.ranked_at))}${p.discovered != null ? `: ${p.discovered} models listed${skipped ? `, left out ${skipped}` : ""}` : ""}.` : "Not measured yet: its known-good models are used until then."}
        {p.rank_error ? <> <Said text={p.rank_error} />.</> : ""}
      </span>
      <div className="k-stack" aria-label={`${p.label} models`}>
        {p.models.map((m) => (
          <div key={m.id} className="ai-model">
            <div className="k-stack adm-grow">
              <span className="k-small">
                {m.in_use ? <b>#{m.rank} </b> : <span className="k-muted">not in use </span>}
                <span className="adm-mono ai-id" title={m.name && m.name !== m.id ? m.id : undefined}>{m.name ?? m.id}</span>
                {m.pinned && <> <Badge tone="ok" dot={false}>Pinned</Badge></>}
                {m.blocked && <> <Badge tone="warn" dot={false}>Blocked</Badge></>}
              </span>
              {m.blocked && <span className="k-small k-muted" data-testid="ai-blocked-by">{blockedLine(m.blocked_by, m.blocked_at)}</span>}
              <span className="k-small k-muted">
                {m.success != null ? `${m.success}% of ${m.tries} answered well` : "no answers yet"} · median {secs(m.median_ms)}
                {m.thinks ? " · reasons first" : ""}
                {m.open_until ? ` · paused ${until(m.open_until)} (${m.open_reason})` : ""}
                {m.last_error ? <> · last problem: <Said text={m.last_error} /></> : m.probe.error ? <> · test: <Said text={m.probe.error} /></> : ""}
              </span>
            </div>
            <span className="k-row">
              {!m.blocked && !m.pinned && <button type="button" className="btn quiet sm" disabled={!!busy} onClick={() => pin(p, m.id)} aria-label={`Pin ${m.id}`}>Pin</button>}
              <button type="button" className="btn quiet sm" disabled={!!busy} onClick={() => block(p, m.id, !m.blocked)} aria-label={`${m.blocked ? "Unblock" : "Block"} ${m.id}`}>
                {m.blocked ? "Unblock" : "Block"}</button>
            </span>
          </div>
        ))}
        {p.blocked.filter((b) => !p.models.some((m) => m.id === b)).map((b) => (
          <div key={b} className="ai-model">
            <span className="k-stack"><span className="k-small"><span className="adm-mono ai-id">{b}</span> <Badge tone="warn" dot={false}>Blocked</Badge></span>
              <span className="k-small k-muted" data-testid="ai-blocked-by">{blockedLine(p.blocked_info?.[b]?.by, p.blocked_info?.[b]?.at)}</span></span>
            <button type="button" className="btn quiet sm" disabled={!!busy} onClick={() => block(p, b, false)} aria-label={`Unblock ${b}`}>Unblock</button>
          </div>
        ))}
      </div>
      </div>
      </Disclosure>
    </div>
  );
}
