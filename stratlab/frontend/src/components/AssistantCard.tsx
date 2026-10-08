import { useEffect, useState } from "react";
import { api, CFG } from "../lib/api";
import { mcpEndpoint } from "../lib/mcp";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";
import { Earlier } from "./Earlier";
import { Badge, Card, CardHead, CheckField, ConfirmDialog, Disclosure, EmptyState, Field, FormActions, FormGrid, Notice, PlanNote, Skeleton } from "./kit";

type Key = { id: string; name: string; paper: boolean; hint: string; created_at: string; last_used_at: string | null; revoked_at: string | null };
type Entry = { at: string; key_id: string; key: string; tool: string; args: string; result: "ok" | "error" | "refused" | "rate_limited"; detail: string; ms: number };
export type AssistantPage = {
  /** plan: the plan the feature is on; your_plan: the plan this page is seen on (View as included) */
  allowed: boolean; plan: string; your_plan?: string; endpoint: string; keys: Key[]; max_keys: number; log: Entry[];
  tools: { name: string; title: string; paper: boolean }[];
  limits: { per_minute: number; per_day: number; paper_per_hour: number; scans_per_hour: number };
};

const RESULT: Record<Entry["result"], [string, "ok" | "warn"]> = {
  ok: ["Done", "ok"], error: ["Couldn't", "warn"], refused: ["Refused", "warn"], rate_limited: ["Too many", "warn"],
};
const SHOWN = 15;    // log lines before the rest fold away
const NAME_ID = "assistant-key-name";

/** A block of text to copy: a command, a URL or a config. */
function Copyable({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* shown to copy by hand */ }
  };
  return (
    <div className="k-stack">
      <pre className="k-code" aria-label={label}>{text}</pre>
      <button type="button" className="btn quiet sm k-btn-end" onClick={() => void copy()}>{done ? "Copied" : `Copy ${label.toLowerCase()}`}</button>
    </div>
  );
}

/** The setup steps for each assistant, with the user's endpoint (and the new key, while it's on screen). */
export function SetupGuide({ endpoint, token }: { endpoint: string; token?: string }) {
  const key = token ?? "slm_YOUR_KEY";
  const claudeCode = `claude mcp add --transport http stratlab ${endpoint} \\\n  --header "Authorization: Bearer ${key}"`;
  const desktop = JSON.stringify({ mcpServers: { stratlab: { command: "npx", args: ["mcp-remote", endpoint, "--header", "Authorization:${STRATLAB_AUTH}"],
    env: { STRATLAB_AUTH: `Bearer ${key}` } } } }, null, 2);
  const openai = `tools=[{\n  "type": "mcp",\n  "server_label": "stratlab",\n  "server_url": "${endpoint}",\n  "headers": {"Authorization": "Bearer ${key}"},\n  "require_approval": "always"\n}]`;
  return (
    <div className="k-stack">
      <div className="k-stack"><b>Server address</b><Copyable text={endpoint} label="Address" /></div>
      <div className="k-stack">
        <b>Claude Code</b>
        <span className="k-small k-muted">Run this in a terminal.</span>
        <Copyable text={claudeCode} label="Command" />
      </div>
      <div className="k-stack">
        <b>Claude Desktop</b>
        <span className="k-small k-muted">Settings → Developer → Edit Config, add this to claude_desktop_config.json, and restart Claude. Needs Node.js.</span>
        <Copyable text={desktop} label="Config" />
      </div>
      <div className="k-stack">
        <b>ChatGPT, through the OpenAI API</b>
        <span className="k-small k-muted">In a Responses API request, add StratLab as a remote MCP tool with your key as a header.</span>
        <Copyable text={openai} label="Tool" />
      </div>
      <p className="k-small k-muted">The Claude and ChatGPT apps' own connector screens sign in with OAuth, which StratLab doesn't offer yet: use one of the ways above. Any other assistant that can send a header to a Streamable HTTP MCP server works the same way.</p>
    </div>
  );
}

/** The /assistant page's cards: keys for Claude or ChatGPT, how to set them up, and every tool call they made. Pro. */
export function AssistantCards() {
  const { fail, notify } = useApp();
  const [p, setP] = useState<AssistantPage | null>(null);
  const [name, setName] = useState("");
  const [paper, setPaper] = useState(false);
  const [made, setMade] = useState<{ token: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState<Key | null>(null);
  useEffect(() => { api<AssistantPage>("/me/assistant").then(setP).catch(fail); }, [fail]);

  const [nameMissing, setNameMissing] = useState(false);
  const create = async () => {
    if (!name.trim()) { setNameMissing(true); document.getElementById(NAME_ID)?.focus(); return; }   // a key needs a name to tell it apart
    setNameMissing(false);
    setBusy(true);
    try {
      const r = await api<AssistantPage & { token: string; key: Key }>("/me/assistant/keys", { method: "POST", body: { name: name.trim(), paper } });
      setP(r); setMade({ token: r.token, name: r.key.name }); setName(""); setPaper(false);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const revoke = async () => {
    if (!asking) return;
    setBusy(true);
    try { setP(await api<AssistantPage>(`/me/assistant/keys/${asking.id}`, { method: "DELETE" })); notify("Key revoked."); setAsking(null); } catch (e) { fail(e); } finally { setBusy(false); }
  };

  if (!p) return <Card label="Your assistants"><Skeleton label="Loading your assistants" /></Card>;
  // the plan the page is seen on (View as included), never the feature's own plan read as the reader's (R6O-005)
  if (!p.allowed) return <PlanNote>Connecting an AI assistant is on the {p.plan} plan.{p.your_plan ? ` You are on the ${p.your_plan} plan.` : ""}</PlanNote>;

  const endpoint = mcpEndpoint(CFG.API_BASE, location.origin, p.endpoint);
  const live = p.keys.filter((k) => !k.revoked_at);
  const gone = p.keys.filter((k) => k.revoked_at);
  const row = (k: Key) => (
    <div key={k.id} className="k-line-row">
      <span className="k-line-text">
        <b>{k.name} <span className="k-mono k-muted k-small">…{k.hint}</span>{k.paper && <span className="k-inline-badge"><Badge tone="warn">Paper orders</Badge></span>}</b>
        <span className="k-sub-line">Made {dateOnly(k.created_at)} · {k.revoked_at ? `revoked ${dateOnly(k.revoked_at)}` : k.last_used_at ? `last used ${ago(k.last_used_at)}` : "not used yet"}</span>
      </span>
      {!k.revoked_at && <button type="button" className="btn quiet sm danger" onClick={() => setAsking(k)}>Revoke</button>}
    </div>
  );
  const line = (e: Entry, i: number) => (
    <div key={`${e.at}-${i}`} className="k-line-row">
      <span className="k-line-text">
        <b className="k-mono">{e.tool}</b>
        <span className="k-sub-line">{ago(e.at)} · {e.key}{e.args ? ` · ${e.args}` : ""}{e.detail ? ` · ${e.detail}` : ""}</span>
      </span>
      <Badge tone={RESULT[e.result]?.[1] ?? "plain"}>{RESULT[e.result]?.[0] ?? e.result}</Badge>
    </div>
  );

  return (
    <>
      <Card label="Your assistants">
        <CardHead title="Your assistants" info="Make one key for each assistant, so you can revoke one without the others." />
        {made && (
          <div className="k-callout" role="status">
            <b>Your new key for {made.name}</b>
            <span className="k-small">Copy it now: StratLab keeps only a fingerprint of it and can't show it again.</span>
            <Copyable text={made.token} label="Key" />
            <Disclosure summary="Set it up" open><SetupGuide endpoint={endpoint} token={made.token} /></Disclosure>
            <button type="button" className="btn quiet sm k-btn-end" onClick={() => setMade(null)}>Done</button>
          </div>
        )}
        <div>
          {live.length ? live.map(row) : <EmptyState title="No keys yet">Make one for each assistant, so you can revoke one without the others.</EmptyState>}
        </div>
        <Earlier label="Revoked keys" count={gone.length}>{gone.map(row)}</Earlier>
        {live.length < p.max_keys ? (
          <FormGrid label="Make a key" onSubmit={(e) => { e.preventDefault(); void create(); }}>
            <Field id={NAME_ID} label="Name of the assistant" value={name} maxLength={40} placeholder="Claude on my laptop" aria-required="true"
              aria-invalid={nameMissing || undefined} aria-describedby={nameMissing ? `${NAME_ID}-need` : undefined}
              onChange={(e) => { setName(e.target.value); if (e.target.value.trim()) setNameMissing(false); }} />
            {nameMissing && <p className="k-field wide k-small k-warn-text" id={`${NAME_ID}-need`} role="alert">Name the key after the assistant that will use it, like "Claude on my laptop".</p>}
            <div className="k-field wide">
              <CheckField checked={paper} onChange={setPaper} label={<span>Allow paper orders<span className="k-check-note">It can open and close positions in your own running paper sessions (simulated, no money). Without this the key only reads.</span></span>} />
            </div>
            <FormActions><button type="submit" className="btn" disabled={busy}>{busy ? "Making…" : "Make a key"}</button></FormActions>
          </FormGrid>
        ) : <p className="k-small k-muted">You have {p.max_keys} keys, the most at a time. Revoke one to make another.</p>}
      </Card>

      {!made && (
        <Card label="Set up Claude or ChatGPT">
          <CardHead title="Set up Claude or ChatGPT" />
          <Disclosure summary="Show the setup steps"><SetupGuide endpoint={endpoint} /></Disclosure>
        </Card>
      )}

      <Card label="What your assistants did">
        <CardHead title="What your assistants did" info={<>Every tool call, newest first. Up to {p.limits.per_minute} calls a minute and {p.limits.per_day.toLocaleString("en-IN")} a day per key; {p.limits.paper_per_hour} paper orders and {p.limits.scans_per_hour} scans an hour.</>} />
        {p.log.length ? <div>{p.log.slice(0, SHOWN).map(line)}</div> : <p className="k-small k-muted">Nothing yet.</p>}
        <Earlier label="Earlier calls" count={Math.max(0, p.log.length - SHOWN)}>{p.log.slice(SHOWN).map((e, i) => line(e, i + SHOWN))}</Earlier>
      </Card>

      {asking && <ConfirmDialog title={`Revoke "${asking.name}"?`} confirmLabel="Revoke key" busy={busy} onConfirm={() => void revoke()} onClose={() => setAsking(null)}>
        Any assistant using it stops reaching StratLab at once.</ConfirmDialog>}
    </>
  );
}

export const AssistantNotice = () => (
  <Notice label="What the assistant can do">Keys read only, unless you let one open and close positions in your own paper sessions. No key can place a real order with a broker. Facts only, not advice.</Notice>
);
