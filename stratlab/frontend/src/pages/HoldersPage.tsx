import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { safeHref } from "../lib/format";
import { RegionSwitch } from "../components/Research";
import { changeText, quarterEnd, shares, type HolderChange } from "../components/NamedHolders";
import { Info, Loading } from "../components/ui";

/* Named holders across companies: search a name in every company's latest shareholding pattern (holders above 1%),
 * pick the spellings that are the same holder, see each company alphabetically with the change since the quarter
 * before, and follow the holder for a message when a new quarter's filing changes their list. Facts as filed: nobody
 * is ranked or called anything. */

interface NameGroup { label: string; companies: number; names: { key: string; name: string; companies: number }[] }
interface Follow { id: string; label: string; names: string[]; created_at: string }
interface Coverage { companies: number; latest_quarter: string | null; queued: number }
interface SearchAnswer { q: string; groups: NameGroup[]; coverage: Coverage; follows: Follow[]; note: string }
interface HoldingRow {
  symbol: string; company: string; quarter: string; prev_quarter: string | null; filed: string | null; url: string | null; names: string[];
  kind: string; group: string; shares: number | null; pct: number | null; prev_shares: number | null; prev_pct: number | null;
  change: HolderChange; pct_change: number | null;
}
interface Holdings { rows: HoldingRow[]; count: number; dropped: number; new: number; keys: string[]; coverage: Coverage; note: string }

const SHOW: [string, string][] = [["held", "Held now"], ["all", "With dropped"]];

export function HoldersPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [ans, setAns] = useState<SearchAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [group, setGroup] = useState<NameGroup | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [hold, setHold] = useState<Holdings | null>(null);
  const [show, setShow] = useState("all");
  const [follows, setFollows] = useState<Follow[]>([]);

  useEffect(() => {
    let live = true;
    setBusy(true); setError(null); setGroup(null); setHold(null);
    api<SearchAnswer>(`/invest/holders${q ? `?q=${encodeURIComponent(q)}` : ""}`)
      .then((a) => { if (!live) return; setAns(a); setFollows(a.follows); if (a.groups.length === 1) choose(a.groups[0]); })
      .catch((e) => { if (!live) return; if ((e as ApiError).status === 402) setLocked(true); else setError((e as Error).message); })
      .finally(() => live && setBusy(false));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  useEffect(() => {
    if (!picked.length) { setHold(null); return; }
    let live = true;
    api<Holdings>("/invest/holders/holdings", { method: "POST", body: { names: picked } })
      .then((h) => live && setHold(h)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [picked]);

  function choose(g: NameGroup) { setGroup(g); setPicked(g.names.map((n) => n.key)); }
  const search = (e: React.FormEvent) => { e.preventDefault(); const p = new URLSearchParams(params); if (text.trim()) p.set("q", text.trim()); else p.delete("q"); setParams(p); };
  const toggle = (k: string) => setPicked((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const following = follows.find((f) => picked.length && f.names.length === picked.length && f.names.every((n) => picked.includes(n)));
  const follow = async () => {
    if (!group) return;
    try {
      const r = await api<{ follows: Follow[] }>("/invest/holders/follow", { method: "PUT", body: { label: group.label, names: picked } });
      setFollows(r.follows);
    } catch (e) { setError((e as Error).message); }
  };
  const unfollow = async (id: string) => {
    try { setFollows((await api<{ follows: Follow[] }>(`/invest/holders/follow/${id}`, { method: "DELETE" })).follows); } catch (e) { setError((e as Error).message); }
  };
  const openFollow = (f: Follow) => { setGroup({ label: f.label, companies: 0, names: f.names.map((k) => ({ key: k, name: k, companies: 0 })) }); setPicked(f.names); };
  const rows = (hold?.rows ?? []).filter((r) => show === "all" || r.pct != null);

  return (
    <div className="stack holders-page" style={{ gap: 24 }}>
      <RegionSwitch region="IN" />
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Company news · India</span>
        <h1 className="page-title">Named holders across companies</h1>
        <p className="page-sub">Every quarter, each listed company names its promoter group and every public holder above 1% in its shareholding
          pattern. Search a name to see the companies it appears in, and what changed since the quarter before. Facts as filed, not advice.</p>
      </div>

      {locked ? (
        <section className="card stack" style={{ gap: 10 }}>
          <p className="small" style={{ margin: 0 }}>Searching a holder across companies and following one is on the <Link className="link" to="/plans">Basic plan</Link>.
            Each company page shows its own named holders for everyone.</p>
        </section>
      ) : (
        <>
          <form className="row wrap" style={{ gap: 10 }} onSubmit={search} role="search">
            <input className="input holder-search" type="search" aria-label="Holder's name" placeholder="A holder's name, e.g. a fund or a person"
              value={text} onChange={(e) => setText(e.target.value)} minLength={3} maxLength={80} />
            <button className="btn" type="submit" disabled={busy}>Search</button>
          </form>
          {ans && <p className="tiny muted" style={{ margin: 0 }}>{ans.coverage.companies.toLocaleString("en-IN")} companies read
            {ans.coverage.latest_quarter && <>, filings up to the quarter to {quarterEnd(ans.coverage.latest_quarter)}</>}
            {ans.coverage.queued > 0 && <>; {ans.coverage.queued.toLocaleString("en-IN")} more filings being read</>}.
            <Info label="Where the names come from">{ans.note}</Info></p>}
          {error && <p className="small muted" role="alert">{error}</p>}

          {follows.length > 0 && (
            <section className="card stack" style={{ gap: 10 }} aria-label="Holders you follow">
              <h2 className="h3">Holders you follow</h2>
              <div className="row wrap" style={{ gap: 8 }}>
                {follows.map((f) => (
                  <span key={f.id} className="chip">
                    <button className="link-btn" onClick={() => openFollow(f)}>{f.label}</button>
                    <button className="chip-x" aria-label={`Stop following ${f.label}`} onClick={() => unfollow(f.id)}>×</button>
                  </span>))}
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>You get a message when a company's new shareholding filing changes a followed holder's line: new above 1%, more or fewer shares, or no longer listed.</p>
            </section>
          )}

          {busy && !ans ? <Loading label="Searching the shareholding filings" /> : ans && q && (
            ans.groups.length === 0 ? <p className="small muted">No holder above 1% by that name in the filings read so far.</p> : (
              <section className="card stack" style={{ gap: 10 }} aria-label="Names found">
                <h2 className="h3">Names found</h2>
                <ul className="holder-groups">
                  {ans.groups.map((g) => (
                    <li key={g.label}><button className={`link-btn${group?.label === g.label ? " on" : ""}`} onClick={() => choose(g)}>{g.label}</button>
                      <span className="tiny muted"> {g.companies} compan{g.companies === 1 ? "y" : "ies"}{g.names.length > 1 ? ` · ${g.names.length} spellings` : ""}</span></li>))}
                </ul>
              </section>
            )
          )}

          {group && (
            <section className="card stack" style={{ gap: 14 }} id="holder" aria-label={`${group.label}'s holdings`}>
              <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
                <h2 className="h3">{group.label}</h2>
                {following ? <button className="btn quiet sm" onClick={() => unfollow(following.id)}>Following · stop</button>
                  : <button className="btn quiet sm" onClick={follow} disabled={!picked.length}>Follow this holder</button>}
              </div>
              {group.names.length > 1 && (
                <fieldset className="stack holder-names" style={{ gap: 6 }}>
                  <legend className="small muted">Spellings counted as this holder (untick any that's someone else)</legend>
                  {group.names.map((n) => (
                    <label key={n.key} className="row small" style={{ gap: 8 }}>
                      <input type="checkbox" checked={picked.includes(n.key)} onChange={() => toggle(n.key)} />{n.name}
                      {n.companies > 0 && <span className="tiny muted">{n.companies} compan{n.companies === 1 ? "y" : "ies"}</span>}
                    </label>))}
                </fieldset>
              )}
              {!hold ? (picked.length ? <Loading label="Reading their holdings" /> : <p className="small muted">Tick at least one spelling.</p>) : (
                <>
                  <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
                    <span className="small">Listed in <b>{hold.count}</b> compan{hold.count === 1 ? "y" : "ies"}
                      {hold.new > 0 && <> · new in {hold.new}</>}{hold.dropped > 0 && <> · no longer listed in {hold.dropped}</>}</span>
                    {hold.dropped > 0 && <div className="seg" role="radiogroup" aria-label="Which companies">
                      {SHOW.map(([id, label]) => <button key={id} role="radio" aria-checked={show === id} aria-pressed={show === id} onClick={() => setShow(id)}>{label}</button>)}
                    </div>}
                  </div>
                  <div className="table-wrap">
                    <table className="holders-table" aria-label="Companies where the holder is named">
                      <thead><tr><th style={{ textAlign: "left" }}>Company</th><th>Shares</th><th>Stake</th><th>Since last quarter</th><th>Quarter</th></tr></thead>
                      <tbody>{rows.map((r) => (
                        <tr key={r.symbol} data-company={r.symbol}>
                          <td style={{ textAlign: "left" }}><Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
                            <div className="tiny muted holder-name">{r.company}</div>
                            <div className="tiny muted">{r.group === "promoter" ? "Promoter group · " : ""}{r.kind}</div></td>
                          <td className="num">{r.shares == null ? "–" : shares(r.shares)}</td>
                          <td className="num">{r.pct == null ? "–" : `${r.pct.toFixed(2)}%`}</td>
                          <td className="num small">{changeText(r.change, r.pct_change)}{r.prev_pct != null && r.change !== "same" && <div className="tiny muted">was {r.prev_pct.toFixed(2)}%</div>}</td>
                          <td className="small">{quarterEnd(r.quarter)}{r.url && <div><a className="link tiny" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">Filing ↗</a></div>}</td>
                        </tr>))}
                      </tbody>
                    </table>
                  </div>
                  <p className="tiny muted" style={{ margin: 0 }}>Companies in alphabetical order. Holdings above 1% only, at each quarter's end, as the company filed them; a holder below 1% isn't named.</p>
                </>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
