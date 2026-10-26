import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { asOf, fmtDate, safeHref } from "../lib/format";
import { Badge, Card, CardHead, DataTable, EmptyState, ErrorState, Skeleton } from "./kit";

/* A US company's page: who reported holding more than 5% (Schedule 13D and 13G) and the Form 8-K items worth a look, from the SEC filings
 * read each evening. Facts as filed (RC2A-027: a US page had no owners, filings or red flags section). Free on every plan. */
interface Flag { id: string; at: string; label: string; severity: "red" | "amber" | "info"; subject: string; url: string | null }
interface Holder { id: string; at: string; label: string; holder: string | null; others?: number; pct: number | null; amendment: boolean; url: string; read: boolean }
interface UsOut {
  symbol: string; note: string;
  flags: { items: Flag[]; total: number; from: string; to: string; as_of: string | null; updated_at: string | null; covers: string };
  holders: { items: Holder[]; total: number; as_of: string | null; updated_at: string | null; newest: string | null; unread: number; covers: string };
}
const ET = "America/New_York";

export function UsFilingsCards({ symbol }: { symbol: string }) {
  const [d, setD] = useState<UsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let live = true;
    setD(null); setError(null);
    api<UsOut>(`/research/us-company/${encodeURIComponent(symbol)}`).then((x) => live && setD(x))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Couldn't load the filings."));
    return () => { live = false; };
  }, [symbol, tries]);
  if (error) return <Card id="filings"><CardHead title="Filings and red flags" /><ErrorState title="The filings couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState></Card>;
  if (!d) return <Card id="filings"><CardHead title="Filings and red flags" /><Skeleton label="Reading the SEC filings" lines={3} /></Card>;
  const covered = d.flags.covers;
  return (
    <>
      <Card id="us-owners" testId="us-owners">
        <CardHead title="Holders above 5%" info="Anyone who holds more than 5% of a US company's shares files a Schedule 13D (an active stake) or 13G (a passive one), and an amendment when it changes. Holders below 5% are not named in any filing. Names and percentages are as each filing's cover page gives them." infoLabel="About these holders" />
        {d.holders.total === 0 ? (
          <EmptyState title="No 13D or 13G filing found">None in the last 13 months in the SEC's list for this company{d.holders.as_of ? `, read through ${fmtDate(d.holders.as_of)}` : ""}. {covered} are covered.</EmptyState>
        ) : (
          <>
            <DataTable stack label="Holders above 5%, newest filing first" rows={d.holders.items} rowKey={(r) => r.id} columns={[
              { key: "h", header: "Holder", rowHeader: true, wrap: true, cell: (r) => (r.holder ? <>{r.holder}{!!r.others && <span className="k-sub-line">and {r.others} other reporting person{r.others === 1 ? "" : "s"}</span>}</> : <span className="k-muted">{r.read ? "Name not in the cover page" : "Not read yet: open the filing"}</span>) },
              { key: "p", header: "Share of the class", numeric: true, cell: (r) => (r.pct == null ? "–" : <>{`${r.pct.toFixed(2)}%`}{r.pct <= 5 && r.amendment && <span className="k-sub-line">at or below 5%: under the filing level</span>}</>) },
              { key: "f", header: "Filing", wrap: true, cell: (r) => <>{r.label}<span className="k-sub-line">{fmtDate(r.at)} · <a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">Open the filing ↗</a></span></> },
            ]} />
            <p className="k-note">Facts as filed{d.holders.updated_at ? `, read ${asOf(d.holders.updated_at, { tz: ET })}` : ""}. The latest filing of each holder may be older than the list's last read.</p>
          </>
        )}
      </Card>
      <Card id="filings" testId="us-filings">
        <CardHead title="Filings and red flags" info={d.note} infoLabel="About these filings" />
        {d.flags.total === 0 ? (
          <p className="k-small k-muted">No flagged Form 8-K item in the last 12 months{d.flags.as_of ? `, read through ${fmtDate(d.flags.as_of)}` : ""}. Only items such as a bankruptcy, a delisting notice, an auditor or officer change, or a material agreement are flagged; ordinary filings are not listed.</p>
        ) : (
          <>
            <p className="k-small">{d.flags.total} flagged Form 8-K item{d.flags.total === 1 ? "" : "s"} in the last 12 months.</p>
            <DataTable stack label="Flagged Form 8-K items, newest first" rows={d.flags.items} rowKey={(r) => r.id} columns={[
              { key: "d", header: "Filed", cell: (r) => fmtDate(r.at) },
              { key: "l", header: "Flag", wrap: true, cell: (r) => <Badge tone={r.severity === "red" ? "warn" : "plain"} dot={false}>{r.severity === "red" ? "⚑ " : ""}{r.label}</Badge> },
              { key: "s", header: "Filing", wrap: true, cell: (r) => <>{r.subject}{r.url && <span className="k-sub-line"><a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">Open the filing ↗</a></span>}</> },
            ]} />
          </>
        )}
      </Card>
    </>
  );
}
