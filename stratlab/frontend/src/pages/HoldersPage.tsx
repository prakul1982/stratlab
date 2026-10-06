import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { eyebrowOf } from "../lib/eyebrow";
import { safeHref } from "../lib/format";
import { changeText, quarterEnd, shares, type HolderChange } from "../components/NamedHolders";
import { Card, CardHead, CheckField, DataTable, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, PageHeader, PlanNote, Seg, Skeleton, Suggest, type SuggestItem } from "../components/kit";

/* Named holders across companies: search a name in every company's latest shareholding pattern (holders above 1%),
 * pick the spellings that are the same holder, see each company alphabetically with the change since the quarter
 * before, and follow the holder for a message when a new quarter's filing changes their list. Facts as filed: nobody
 * is ranked or called anything. Names are suggested as you type, from the same search the Search button runs. */

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

const SHOW = [{ value: "held", label: "Held now" }, { value: "all", label: "With dropped" }];
const companies = (n: number) => `${n} compan${n === 1 ? "y" : "ies"}`;

/** Names that match what is typed: each group of spellings that look like one holder, with how many companies name it. */
async function holderNames(q: string): Promise<SuggestItem[]> {
  const a = await api<SearchAnswer>(`/invest/holders?q=${encodeURIComponent(q)}`);
  return a.groups.map((g) => ({ key: g.label, label: g.label, note: `${companies(g.companies)}${g.names.length > 1 ? ` · ${g.names.length} spellings` : ""}` }));
}

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
      .then((a) => {
        if (!live) return;
        setAns(a); setFollows(a.follows);
        const exact = a.groups.find((g) => g.label.toLowerCase() === q.toLowerCase());     // a name picked from the suggestions
        if (a.groups.length === 1) choose(a.groups[0]); else if (exact) choose(exact);
      })
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
  const go = (value: string) => {
    const v = value.trim();
    if (v.length < 3) { setError("Type at least three letters of the holder's name."); return; }
    const p = new URLSearchParams(params); p.set("q", v); setParams(p);
  };
  const search = (e: React.FormEvent) => { e.preventDefault(); go(text); };
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
    <div className="k-page holders-page">
      <PageHeader eyebrow={eyebrowOf("/invest/holders")} title="Named holders across companies"
        lede="Every quarter, each listed company names its promoter group and every public holder above 1% in its shareholding pattern. Search a name to see the companies it appears in, and what changed since the quarter before. Facts as filed, not advice."
        asOf={ans?.coverage.latest_quarter} asOfLabel="Filings up to the quarter to"
        info={ans ? <>{ans.coverage.companies.toLocaleString("en-IN")} companies read{ans.coverage.queued > 0 && <>; {ans.coverage.queued.toLocaleString("en-IN")} more filings being read</>}. {ans.note}</> : undefined}
        infoLabel="Where the names come from" />

      {locked ? (
        <PlanNote>Searching a holder across companies and following one is on the Basic plan. Each company page shows its own named holders for everyone.</PlanNote>
      ) : (
        <>
          <Card>
            <CardHead title="Search a holder" />
            <FormGrid label="Search a holder" onSubmit={search}>
              <Field label="Holder's name" wide>
                {(id) => <Suggest id={id} value={q} placeholder="A holder's name, e.g. a fund or a person" load={holderNames}
                  onText={setText} onPick={(s) => { setText(s.label); go(s.label); }} />}
              </Field>
              <FormActions>
                <button className="btn" type="submit" disabled={busy}>Search</button>
                <span className="k-small k-muted">Names appear as you type, three letters in.</span>
              </FormActions>
            </FormGrid>
          </Card>
          {error && <ErrorState title="That didn't work" action={{ label: "Dismiss", onClick: () => setError(null) }}>{error}</ErrorState>}

          {follows.length > 0 && (
            <Card label="Holders you follow">
              <CardHead title="Holders you follow" />
              <div className="k-row">
                {follows.map((f) => (
                  <span key={f.id} className="saved-screen">
                    <button className="btn quiet sm" onClick={() => openFollow(f)}>{f.label}</button>
                    <button className="btn quiet sm icon-only" aria-label={`Stop following ${f.label}`} onClick={() => unfollow(f.id)}>×</button>
                  </span>))}
              </div>
              <p className="k-note">You get a message when a company's new shareholding filing changes a followed holder's line: new above 1%, more or fewer shares, or no longer listed.</p>
            </Card>
          )}

          {busy && !ans ? <Card><Skeleton label="Searching the shareholding filings" lines={3} /></Card> : ans && q && (
            ans.groups.length === 0 ? <Card><EmptyState title="No holder found">No holder above 1% by that name in the filings read so far.</EmptyState></Card> : (
              <Card label="Names found">
                <CardHead title="Names found" />
                <div className="inv-rows">
                  {ans.groups.map((g) => (
                    <div key={g.label} className="inv-row">
                      <span><button className={`link-btn${group?.label === g.label ? " on" : ""}`} onClick={() => choose(g)}>{g.label}</button>
                        <span className="k-note"> {companies(g.companies)}{g.names.length > 1 ? ` · ${g.names.length} spellings` : ""}</span></span>
                    </div>))}
                </div>
              </Card>
            )
          )}

          {group && (
            <Card id="holder" label={`${group.label}'s holdings`}>
              <CardHead title={group.label}
                actions={following ? <button className="btn quiet sm" onClick={() => unfollow(following.id)}>Following · stop</button>
                  : <button className="btn quiet sm" onClick={follow} disabled={!picked.length}>Follow this holder</button>} />
              {group.names.length > 1 && (
                <FieldGroup label="Spellings counted as this holder (untick any that's someone else)">
                  <div className="k-stack holder-names">
                    {group.names.map((n) => (
                      <CheckField key={n.key} checked={picked.includes(n.key)} onChange={() => toggle(n.key)}
                        label={<>{n.name}{n.companies > 0 && <span className="k-note"> {companies(n.companies)}</span>}</>} />))}
                  </div>
                </FieldGroup>
              )}
              {!hold ? (picked.length ? <Skeleton label="Reading their holdings" lines={3} /> : <p className="k-small k-muted">Tick at least one spelling.</p>) : (
                <>
                  <div className="k-row">
                    <span className="k-small">Listed in <b>{hold.count}</b> compan{hold.count === 1 ? "y" : "ies"}
                      {hold.new > 0 && <> · new in {hold.new}</>}{hold.dropped > 0 && <> · no longer listed in {hold.dropped}</>}</span>
                    {hold.dropped > 0 && <Seg label="Which companies" value={show} onChange={setShow} options={SHOW} />}
                  </div>
                  <DataTable label="Companies where the holder is named" rows={rows} rowKey={(r) => r.symbol} sticky={rows.length > 14} rowAttrs={(r) => ({ "data-company": r.symbol })}
                    columns={[
                      { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (r) => (
                        <><Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
                          <span className="k-sub-line holder-name">{r.company}</span>
                          <span className="k-sub-line">{r.group === "promoter" ? "Promoter group · " : ""}{r.kind}</span></>) },
                      { key: "s", header: "Shares", numeric: true, cell: (r) => (r.shares == null ? "–" : shares(r.shares)) },
                      { key: "p", header: "Stake", numeric: true, cell: (r) => (r.pct == null ? "–" : `${r.pct.toFixed(2)}%`) },
                      { key: "ch", header: "Since last quarter", numeric: true, cell: (r) => <>{changeText(r.change, r.pct_change)}{r.prev_pct != null && r.change !== "same" && <span className="k-sub-line">was {r.prev_pct.toFixed(2)}%</span>}</> },
                      { key: "q", header: "Quarter", cell: (r) => <>{quarterEnd(r.quarter)}{r.url && <span className="k-sub-line"><a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">Filing ↗</a></span>}</> },
                    ]} />
                  <p className="k-note">Companies in alphabetical order. Holdings above 1% only, at each quarter's end, as the company filed them; a holder below 1% isn't named.</p>
                </>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
