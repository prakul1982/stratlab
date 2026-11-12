import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { eyebrowOf } from "../lib/eyebrow";
import { CRORE, inrCompact, pct, price } from "../lib/format";
import { PERIOD_LABEL, type Period, type Tile } from "../lib/heatmap";
import { Treemap, TreemapLegend } from "../components/chart/Treemap";
import { Badge, Card, CardHead, DataTable, Disclosure, EmptyState, ErrorState, PageHeader, PlanNote, Select, Signed, Skeleton, Stat, StatRow, type Column } from "../components/kit";

/* /invest/groups and /invest/groups/:slug (f5): India's business groups, made out of the promoters each listed company names in its
 * own quarterly shareholding filing (backend groups.py: one rule for every company, no hand list; the rule and how sure it is are on
 * the page). The index lists every group with its companies' combined market value; a group's page lists its companies with their
 * last close, moves and promoter holding, and a heatmap of them. Free: the groups, their members, market value and the day's change;
 * Basic: the longer changes, the promoter holding and the heatmap (plans.py group_figures). Facts only. */

type Change = Record<"1d" | "1w" | "1m" | "3m" | "ytd" | "1y", number | null>;
interface GroupRow { slug: string; name: string; companies: number; confidence: "high" | "medium"; anchor: string | null; cap: number | null; change: Change; largest: { symbol: string; name: string }[] }
interface GroupsView { groups: GroupRow[]; as_of: string | null; companies: number; read: number; left_out: number; note: string; rule: string[]; full: boolean; plan_needed: string | null }
interface Member { symbol: string; name: string; quarter: string; promoter_pct: number | null; promoter_named_pct: number | null; anchor: boolean; ties: string[]; cap: number | null; close: number | null; change: Change; sector: string | null }
interface GroupView { slug: string; name: string; named_by: string; anchor: string | null; anchor_count: number; confidence: "high" | "medium"; companies: Member[]; tiles: Tile[]; cap: number | null; change: Change; as_of: string | null; quarter: string | null; note: string; rule: string[]; full: boolean; plan_needed: string | null }

const cr = (v: number | null | undefined) => (v == null ? "–" : inrCompact(v * CRORE));
const move = (v: number | null | undefined) => <Signed value={v}>{v == null ? "–" : pct(v, 1)}</Signed>;
const CONFIDENCE: Record<string, string> = { high: "High", medium: "Medium" };

function Rule({ rule, note }: { rule: string[]; note: string }) {
  return (
    <Disclosure summary="How the groups are made out" testId="groups-rule">
      <ol className="k-small groups-rule">{rule.map((r) => <li key={r}>{r}</li>)}</ol>
      <p className="k-note k-muted">{note}</p>
    </Disclosure>
  );
}

export function BusinessGroupsPage() {
  const [v, setV] = useState<GroupsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api<GroupsView>("/invest/groups").then((x) => live && setV(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [tries]);
  const cols: Column<GroupRow>[] = [
    { key: "name", header: "Group", rowHeader: true, wrap: true, cell: (g) => (
      <><Link className="link" to={`/invest/groups/${g.slug}`}>{g.name}</Link>
        <span className="k-sub-line">{g.largest.map((c) => c.name).join(", ")}{g.companies > g.largest.length ? "…" : ""}</span></>) },
    { key: "n", header: "Companies", numeric: true, cell: (g) => g.companies },
    { key: "cap", header: "Market value", numeric: true, cell: (g) => cr(g.cap), csv: (g) => g.cap, csvHeader: "Market value (₹ crore)" },
    { key: "1d", header: "1 day", numeric: true, cell: (g) => move(g.change["1d"]) },
    ...(v?.full ? [
      { key: "1m", header: "1 month", numeric: true, cell: (g: GroupRow) => move(g.change["1m"]) },
      { key: "1y", header: "1 year", numeric: true, cell: (g: GroupRow) => move(g.change["1y"]) }] as Column<GroupRow>[] : []),
    { key: "conf", header: "Confidence", cell: (g) => <Badge tone={g.confidence === "high" ? "ok" : "plain"}>{CONFIDENCE[g.confidence]}</Badge> },
  ];
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/invest/groups")} title="Business groups" asOf={v?.as_of ?? null} asOfPending={!v && !error}
        lede="India's business groups as the companies' own shareholding filings show them: the listed companies that name the same promoters, their combined market value and how it moved." />
      {error ? <ErrorState title="The groups couldn't be read" action={{ label: "Try again", onClick: () => setTries((x) => x + 1) }}>{error}</ErrorState>
        : !v ? <Card><Skeleton label="Reading the groups" page /></Card>
        : !v.groups.length ? <Card><EmptyState title="No groups yet">The groups are made out of the companies' shareholding filings, which are still being read. Come back after the next read.</EmptyState></Card>
        : (
          <Card label="Groups" testId="groups-table">
            <CardHead title={`${v.groups.length} groups, ${v.companies.toLocaleString("en-IN")} companies`} />
            {!v.full && <div data-testid="groups-locked"><PlanNote>Each group's companies, market value and the day's change are on every plan. The 1-month and 1-year changes, each company's promoter holding and the members' heatmap are on the {v.plan_needed} plan.</PlanNote></div>}
            <DataTable csv="business groups" stack label="Business groups by combined market value" columns={cols} rows={v.groups} rowKey={(g) => g.slug} />
            <p className="k-note k-muted">Made out of the latest shareholding filings of {v.read.toLocaleString("en-IN")} companies.{v.left_out ? ` ${v.left_out} set${v.left_out === 1 ? "" : "s"} of companies tied too loosely to be called one group ${v.left_out === 1 ? "is" : "are"} left out.` : ""}</p>
            <Rule rule={v.rule} note={v.note} />
          </Card>
        )}
    </div>
  );
}

export function BusinessGroupPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const [v, setV] = useState<GroupView | null>(null);
  const [error, setError] = useState<{ text: string; missing: boolean } | null>(null);
  const [tries, setTries] = useState(0);
  const [period, setPeriod] = useState<Period>("1d");
  useEffect(() => {
    let live = true;
    setError(null); setV(null);
    api<GroupView>(`/invest/groups/${encodeURIComponent(slug)}`).then((x) => live && setV(x))
      .catch((e) => live && setError({ text: (e as Error).message, missing: e instanceof ApiError && e.status === 404 }));
    return () => { live = false; };
  }, [slug, tries]);
  if (error) return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/invest/groups")} title="Business group" />
      {error.missing ? <Card><EmptyState title="Not a group the filings make out" action={{ label: "All business groups", onClick: () => navigate("/invest/groups") }}>{error.text}</EmptyState></Card>
        : <ErrorState title="The group couldn't be read" action={{ label: "Try again", onClick: () => setTries((x) => x + 1) }}>{error.text}</ErrorState>}
    </div>
  );
  const cols: Column<Member>[] = [
    { key: "co", header: "Company", rowHeader: true, wrap: true, cell: (m) => (
      <><Link className="link" to={`/research/IN/${encodeURIComponent(m.symbol)}`}>{m.name}</Link>
        <span className="k-sub-line">{m.symbol}{m.ties.length ? ` · tied by ${m.ties.slice(0, 2).join(", ")}` : ""}</span></>) },
    { key: "cap", header: "Market value", numeric: true, cell: (m) => cr(m.cap), csv: (m) => m.cap, csvHeader: "Market value (₹ crore)" },
    { key: "close", header: "Last close", numeric: true, cell: (m) => (m.close == null ? "–" : price(m.close, "INR", 2)) },
    { key: "1d", header: "1 day", numeric: true, cell: (m) => move(m.change["1d"]) },
    ...(v?.full ? [
      { key: "1m", header: "1 month", numeric: true, cell: (m: Member) => move(m.change["1m"]) },
      { key: "1y", header: "1 year", numeric: true, cell: (m: Member) => move(m.change["1y"]) },
      { key: "prom", header: "Promoters", numeric: true, info: "The promoter group's holding in the company, from its latest shareholding filing. Where the filing was read before its total was kept, the members named above 1% added up (marked *).",
        cell: (m: Member) => (m.promoter_pct != null ? `${m.promoter_pct.toFixed(1)}%` : m.promoter_named_pct != null ? `${m.promoter_named_pct.toFixed(1)}%*` : "–") }] as Column<Member>[] : []),
  ];
  const stamp = v?.as_of ?? null;
  return (
    <div className="k-page hm-page">{/* hm-page: the heatmap's colour tokens, for the members' map */}
      <PageHeader eyebrow={eyebrowOf("/invest/groups")} title={v ? `${v.name} group` : "Business group"} asOf={stamp} asOfPending={!v}
        lede={v ? `${v.companies.length} listed companies, ${cr(v.cap)} together. Grouped by the promoters they name in their own shareholding filings.` : undefined} />
      {!v ? <Card><Skeleton label="Reading the group" page /></Card> : (
        <>
          <StatRow label="The group's figures">
            <Stat label="Combined market value" value={cr(v.cap)} />
            <Stat label="1 day" value={v.change["1d"] == null ? "–" : pct(v.change["1d"], 2)} tone={v.change["1d"] == null || v.change["1d"] === 0 ? undefined : v.change["1d"] > 0 ? "up" : "down"} />
            {v.full && <Stat label="1 month" value={v.change["1m"] == null ? "–" : pct(v.change["1m"], 1)} tone={v.change["1m"] == null || v.change["1m"] === 0 ? undefined : v.change["1m"] > 0 ? "up" : "down"} />}
            {v.full && <Stat label="1 year" value={v.change["1y"] == null ? "–" : pct(v.change["1y"], 1)} tone={v.change["1y"] == null || v.change["1y"] === 0 ? undefined : v.change["1y"] > 0 ? "up" : "down"} />}
          </StatRow>
          {!v.full && <div data-testid="group-locked"><PlanNote>The companies, their market value and the day's change are on every plan. Each company's 1-month and 1-year change, its promoter holding and the members' heatmap are on the {v.plan_needed} plan.</PlanNote></div>}
          {v.full && v.tiles.length > 0 && (
            <Card label="Members" testId="group-map">
              <CardHead title="Members by market value" actions={
                <Select small label="Colour by the change over" value={period} onChange={(x) => setPeriod(x as Period)}
                  options={(["1d", "1w", "1m", "1y"] as Period[]).map((p) => ({ value: p, label: PERIOD_LABEL[p] }))} />} />
              <Treemap tiles={v.tiles} size="cap" color="change" period={period} group="none" label={`${v.name} group: each company sized by its market value, coloured by its change over ${PERIOD_LABEL[period]}`}
                href={(t) => `/research/IN/${encodeURIComponent(t.s)}`} figure={(x) => (x == null ? "–" : pct(x, 1))}
                tip={(p) => <><b>{p.tile.n}</b><br />{cr(p.tile.cap)} · {p.value == null ? "–" : pct(p.value, 1)} over {PERIOD_LABEL[period]}</>} />
              <TreemapLegend color="change" period={period} title={`Change over ${PERIOD_LABEL[period]}`} />
            </Card>
          )}
          <Card label="Companies" testId="group-table">
            <CardHead title="Companies" />
            <DataTable csv={`${v.slug} group`} stack label={`${v.name} group's listed companies`} columns={cols} rows={v.companies} rowKey={(m) => m.symbol} />
            <p className="k-note k-muted" data-testid="group-confidence">
              Confidence: <b>{CONFIDENCE[v.confidence]}</b>. {v.anchor ? `${v.anchor_count} of ${v.companies.length} companies name ${v.anchor} among their promoters` : "The companies are tied by shared promoters"}
              {v.anchor_count < v.companies.length ? "; the others share at least one promoter company, trust or firm, or two promoter individuals, with a member." : "."}
              {v.named_by === "company names" ? " The group is named after the word most of its companies' names share." : " The group is named after that promoter."}
            </p>
            <Rule rule={v.rule} note={v.note} />
          </Card>
          <p className="k-small"><Link className="link" to="/invest/groups">All business groups</Link></p>
        </>
      )}
    </div>
  );
}
