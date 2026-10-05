import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";
import { Earlier } from "./Earlier";

type Key = { id: string; name: string; paper: boolean; hint: string; created_at: string; last_used_at: string | null; revoked_at: string | null };
type Entry = { at: string; key_id: string; key: string; tool: string; args: string; result: "ok" | "error" | "refused" | "rate_limited"; detail: string; ms: number };
export type AssistantPage = {
  allowed: boolean; plan: string; endpoint: string; keys: Key[]; max_keys: number; log: Entry[];
  tools: { name: string; title: string; paper: boolean }[];
  limits: { per_minute: number; per_day: number; paper_per_hour: number; scans_per_hour: number };
};

const RESULT: Record<Entry["result"], [string, string]> = {
  ok: ["Done", "pass"], error: ["Couldn't", "warn"], refused: ["Refused", "warn"], rate_limited: ["Too many", "warn"],
};
const SHOWN = 15;    // log lines before the rest fold away

/** A block of text to copy: a command, a URL or a config. */
function Copyable({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* shown to copy by hand */ }
  };
  return (
    <div className="stack" style={{ gap: 4, minWidth: 0 }}>
      <pre className="small mono" aria-label={label} style={{ margin: 0, padding: 10, background: "var(--paper-2)", borderRadius: 8, overflowX: "auto", whiteSpace: "pre", maxWidth: "100%" }}>{text}</pre>
      <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={copy}>{done ? "Copied" : `Copy ${label.toLowerCase()}`}</button>
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
    <div className="stack" style={{ gap: 14 }}>
      <div className="stack" style={{ gap: 6 }}><b style={{ fontSize: 14.5 }}>Server address</b><Copyable text={endpoint} label="Address" /></div>
      <div className="stack" style={{ gap: 6 }}>
        <b style={{ fontSize: 14.5 }}>Claude Code</b>
        <span className="small muted">Run this in a terminal.</span>
        <Copyable text={claudeCode} label="Command" />
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <b style={{ fontSize: 14.5 }}>Claude Desktop</b>
        <span className="small muted">Settings → Developer → Edit Config, add this to claude_desktop_config.json, and restart Claude. Needs Node.js.</span>
        <Copyable text={desktop} label="Config" />
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <b style={{ fontSize: 14.5 }}>ChatGPT, through the OpenAI API</b>
        <span className="small muted">In a Responses API request, add StratLab as a remote MCP tool with your key as a header.</span>
        <Copyable text={openai} label="Tool" />
      </div>
      <p className="small muted">The Claude and ChatGPT apps' own connector screens sign in with OAuth, which StratLab doesn't offer yet: use one of the ways above. Any other assistant that can send a header to a Streamable HTTP MCP server works the same way.</p>
    </div>
  );
}

/** Account → AI assistant: keys for Claude or ChatGPT, how to set them up, and every tool call they made. Pro. */
export function AssistantCard() {
  const { fail, notify } = useApp();
  const [p, setP] = useState<AssistantPage | null>(null);
  const [name, setName] = useState("");
  const [paper, setPaper] = useState(false);
  const [made, setMade] = useState<{ token: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<AssistantPage>("/me/assistant").then(setP).catch(fail); }, [fail]);

  const create = async () => {
    setBusy(true);
    try {
      const r = await api<AssistantPage & { token: string; key: Key }>("/me/assistant/keys", { method: "POST", body: { name: name.trim(), paper } });
      setP(r); setMade({ token: r.token, name: r.key.name }); setName(""); setPaper(false);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const revoke = async (k: Key) => {
    if (!confirm(`Revoke "${k.name}"? Any assistant using it stops reaching StratLab at once.`)) return;
    try { setP(await api<AssistantPage>(`/me/assistant/keys/${k.id}`, { method: "DELETE" })); notify("Key revoked."); } catch (e) { fail(e); }
  };

  const live = p?.keys.filter((k) => !k.revoked_at) ?? [];
  const gone = p?.keys.filter((k) => k.revoked_at) ?? [];
  const row = (k: Key) => (
    <div key={k.id} className="spread" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", gap: 10, flexWrap: "wrap" }}>
      <span className="stack" style={{ gap: 0, minWidth: 0 }}>
        <b style={{ fontSize: 14.5, overflowWrap: "anywhere" }}>{k.name} <span className="mono muted small">…{k.hint}</span>{k.paper && <span className="badge next" style={{ marginLeft: 6 }}>Paper orders</span>}</b>
        <span className="small muted">Made {dateOnly(k.created_at)} · {k.revoked_at ? `revoked ${dateOnly(k.revoked_at)}` : k.last_used_at ? `last used ${ago(k.last_used_at)}` : "not used yet"}</span>
      </span>
      {!k.revoked_at && <button className="btn quiet sm danger" onClick={() => revoke(k)}>Revoke</button>}
    </div>
  );
  const line = (e: Entry, i: number) => (
    <div key={`${e.at}-${i}`} className="spread" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)", gap: 10 }}>
      <span className="stack" style={{ gap: 0, minWidth: 0 }}>
        <b className="mono" style={{ fontSize: 13.5, overflowWrap: "anywhere" }}>{e.tool}</b>
        <span className="small muted" style={{ overflowWrap: "anywhere" }}>{ago(e.at)} · {e.key}{e.args ? ` · ${e.args}` : ""}{e.detail ? ` · ${e.detail}` : ""}</span>
      </span>
      <span className={`badge ${RESULT[e.result]?.[1] ?? "skip"}`}>{RESULT[e.result]?.[0] ?? e.result}</span>
    </div>
  );

  return (
    <section className="card stack" style={{ gap: 14 }} aria-labelledby="assistant-h">
      <div className="spread"><h2 className="h2" id="assistant-h">AI assistant</h2>{p && !p.allowed && <span className="badge next">{p.plan}</span>}</div>
      <p className="small muted">Use StratLab in Claude or ChatGPT: your watchlist, holdings, a company's facts, the watchlist scan, alerts, and paper sessions with their P&amp;L. Keys read only, unless you let one open and close positions in your own paper sessions. No key can place a real order with a broker. Facts only, not advice.</p>
      {!p ? <p className="small muted">Loading…</p> : !p.allowed ? (
        <div className="row wrap" style={{ gap: 8 }}><span className="small">On the {p.plan} plan.</span><Link to="/plans" className="btn outline sm">See plans</Link></div>
      ) : (
        <>
          {made && (
            <div className="stack" style={{ gap: 8, padding: 12, border: "1px solid var(--line-2)", borderRadius: 10 }} role="status">
              <b style={{ fontSize: 14.5 }}>Your new key for {made.name}</b>
              <span className="small">Copy it now: StratLab keeps only a fingerprint of it and can't show it again.</span>
              <Copyable text={made.token} label="Key" />
              <details open><summary className="small" style={{ cursor: "pointer" }}>Set it up</summary><div style={{ marginTop: 10 }}><SetupGuide endpoint={p.endpoint} token={made.token} /></div></details>
              <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setMade(null)}>Done</button>
            </div>
          )}
          <div className="stack" style={{ gap: 0 }}>
            {live.length ? live.map(row) : <p className="small muted">No keys yet. Make one for each assistant, so you can revoke one without the others.</p>}
          </div>
          <Earlier label="Revoked keys" count={gone.length}>{gone.map(row)}</Earlier>
          {live.length < p.max_keys ? (
            <div className="stack" style={{ gap: 10, maxWidth: 520 }}>
              <label className="field">Name of the assistant<input value={name} maxLength={40} placeholder="Claude on my laptop" onChange={(e) => setName(e.target.value)} /></label>
              <label className="row" style={{ gap: 10, fontWeight: 600, alignItems: "flex-start" }}>
                <input type="checkbox" style={{ width: 20, height: 20, flex: "none" }} checked={paper} onChange={(e) => setPaper(e.target.checked)} />
                <span>Allow paper orders<span className="small muted" style={{ display: "block", fontWeight: 400 }}>It can open and close positions in your own running paper sessions (simulated, no money). Without this the key only reads.</span></span>
              </label>
              <button className="btn sm" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={create}>{busy ? "Making…" : "Make a key"}</button>
            </div>
          ) : <p className="small muted">You have {p.max_keys} keys, the most at a time. Revoke one to make another.</p>}
          {!made && <details>
            <summary className="small" style={{ cursor: "pointer" }}>How to set up Claude or ChatGPT</summary>
            <div style={{ marginTop: 10 }}><SetupGuide endpoint={p.endpoint} /></div>
          </details>}
          <div className="stack" style={{ gap: 4 }}>
            <b style={{ fontSize: 14.5 }}>What your assistants did</b>
            <span className="small muted">Every tool call, newest first. Up to {p.limits.per_minute} calls a minute and {p.limits.per_day.toLocaleString("en-IN")} a day per key; {p.limits.paper_per_hour} paper orders and {p.limits.scans_per_hour} scans an hour.</span>
            {p.log.length ? <div className="stack" style={{ gap: 0 }}>{p.log.slice(0, SHOWN).map(line)}</div> : <p className="small muted">Nothing yet.</p>}
            <Earlier label="Earlier calls" count={Math.max(0, p.log.length - SHOWN)}>{p.log.slice(SHOWN).map((e, i) => line(e, i + SHOWN))}</Earlier>
          </div>
        </>
      )}
    </section>
  );
}
