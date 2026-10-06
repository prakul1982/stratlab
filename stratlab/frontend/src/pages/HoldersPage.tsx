import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { eyebrowOf } from "../lib/eyebrow";
import { changeText, quarterEnd, shares, type HolderChange } from "../components/NamedHolders";
import { useRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { asOf, safeHref } from "../lib/format";
import { Card, CardHead, CheckField, DataTable, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, PageHeader, Pager, PlanNote, Seg, Skeleton, StockPicker, Suggest, type SuggestItem } from "../components/kit";

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

/** Named holders: India's (every company's shareholding pattern) or the US's (13D and 13G filings above 5%). */
export function HoldersPage() {
  const [region, setRegion] = useRegion();
  const toolbar = <div className="k-toolbar"><RegionSwitch region={region} setRegion={setRegion} /></div>;
  return region === "US" ? <UsHolders toolbar={toolbar} /> : <IndiaHolders toolbar={toolbar} />;
}

function IndiaHolders({ toolbar }: { toolbar: React.ReactNode }) {
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
      {toolbar}

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

interface UsItem {
  id: string; symbol: string; company: string | null; at: string; form: string; kind: "13D" | "13G"; amendment: boolean; label: string; url: string;
  holder: string | null; pct: number | null; shares: number | null; read: boolean; others?: number;
}
interface UsOut { region: Region; symbol: string; items: UsItem[]; total: number; page: number; pages: number; form: string; as_of: string | null; updated_at: string | null; unread: number; note: string }
const FORMS = [{ value: "", label: "All" }, { value: "13D", label: "13D · active" }, { value: "13G", label: "13G · passive" }];

/** US holders above 5%: the Schedule 13D and 13G filings of one company (any plan) or of every S&P 500 company (Basic and
 * up), newest first. Facts as the filer's cover page states them. */
function UsHolders({ toolbar }: { toolbar: React.ReactNode }) {
  const [params, setParams] = useSearchParams();
  const symbol = (params.get("symbol") ?? "").toUpperCase();
  const form = params.get("form") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [data, setData] = useState<UsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [tries, setTries] = useState(0);
  const setParam = (changes: Record<string, string | null>, keepPage = false) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) { if (v) p.set(k, v); else p.delete(k); }
    if (!keepPage) p.delete("page");
    setParams(p, { replace: true });
  };

  useEffect(() => {
    let live = true;
    setError(null); setLocked(false);
    const qs = new URLSearchParams({ symbol, form, page: String(page), size: "25" });
    api<UsOut>(`/research/holders-us?${qs}`).then((x) => live && setData(x))
      .catch((e) => { if (!live) return; if ((e as ApiError).status === 402) { setLocked(true); setData(null); } else setError((e as Error).message); });
    return () => { live = false; };
  }, [symbol, form, page, tries]);

  return (
    <div className="k-page holders-page">
      <PageHeader eyebrow={eyebrowOf("/invest/holders")} title="Holders above 5%"
        lede="Anyone who holds more than 5% of a US company's shares files a Schedule 13D (an active stake) or 13G (a passive one) with the SEC, and an amendment when it changes. Find a company's, or see the latest from every S&P 500 company. Facts as filed, not advice."
        asOf={data?.as_of} asOfLabel="Filings read through" info={data ? <>{data.note} Names and percentages are read from each filing's cover page{data.unread > 0 ? `; ${data.unread} of these filings are still waiting to be read` : ""}.</> : undefined}
        infoLabel="Where the names come from" />
      {toolbar}
      <Card>
        <CardHead title="Which filings" />
        <FormGrid label="Which filings" onSubmit={(e) => e.preventDefault()}>
          <Field label="Company" optional>
            {(id) => <StockPicker id={id} market="US" value={symbol} placeholder="A US ticker or name, like AAPL" onPick={(s) => setParam({ symbol: s })} />}
          </Field>
          <FieldGroup label="Kind of filing" info="A 13D is filed by an investor who may want to influence the company; a 13G by one that holds a stake without that aim. An amendment updates an earlier filing.">
            <Seg label="Kind of filing" value={form} onChange={(v) => setParam({ form: v || null })} options={FORMS} />
          </FieldGroup>
          <FormActions>
            {symbol && <button className="btn quiet" type="button" onClick={() => setParam({ symbol: null })}>Show every company</button>}
          </FormActions>
        </FormGrid>
      </Card>
      {locked && <PlanNote>The latest 13D and 13G filings across every company are on the Basic plan. Pick a company above to see its own, on every plan.</PlanNote>}
      {error && <ErrorState title="The filings couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>}
      {!data && !error && !locked && <Card><Skeleton label="Opening the stored filings" lines={4} /></Card>}
      {data && (
        <Card>
          <CardHead title={`${data.total.toLocaleString("en-IN")} filing${data.total === 1 ? "" : "s"}${symbol ? ` for ${symbol}` : " across companies"}`}
            actions={data.updated_at ? <span className="k-small k-muted">Read {asOf(data.updated_at)}</span> : undefined} />
          <DataTable label="13D and 13G filings, newest first" rows={data.items} rowKey={(r) => r.id} empty={symbol ? `No 13D or 13G filing found for ${symbol} in the last 13 months.` : "No filings stored yet."}
            columns={[
              { key: "d", header: "Filed", cell: (r) => asOf(r.at) ?? "–" },
              { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (r) => (
                <><Link className="link" to={`/research/US/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
                  {r.company && <span className="k-sub-line">{r.company}</span>}</>) },
              { key: "h", header: "Holder", wrap: true, cell: (r) => (
                r.holder ? <>{r.holder}{!!r.others && <span className="k-sub-line">and {r.others} other reporting person{r.others === 1 ? "" : "s"} on the cover</span>}</>
                  : <span className="k-muted">{r.read ? "Name not in the cover page" : "Not read yet: open the filing"}</span>) },
              { key: "p", header: "Share of the class", numeric: true, cell: (r) => (r.pct == null ? "–" : `${r.pct.toFixed(2)}%`) },
              { key: "f", header: "Filing", wrap: true, cell: (r) => <>{r.label}<span className="k-sub-line"><a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">Open the filing ↗</a></span></> },
            ]} />
          <Pager page={data.page} pages={data.pages} total={data.total} noun="filings" onPage={(n) => setParam({ page: n > 1 ? String(n) : null }, true)} />
        </Card>
      )}
    </div>
  );
}
