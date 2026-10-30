import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { dateOnly } from "../../lib/format";
import { Card, CardHead, DataTable, Skeleton, type Column } from "../../components/kit";

type Why = "unreadable" | "not_fetched" | "none_found";
type Without = { symbol: string; why: Why; why_text: string; newest_filed: string | null; checked_at: string | null; problem: string | null };
export type IndexCoverage = { index: string; days: number; as_of: string; companies: number; covered: number; counts: Record<Why, number>; without: Without[]; rule: string };

const WHY: { key: Why; label: string; about: string }[] = [
  { key: "none_found", label: "No filing found", about: "Looked through; no business update filed in the window" },
  { key: "unreadable", label: "Filing unreadable", about: "An update was read but gave no figure checked against it" },
  { key: "not_fetched", label: "Not fetched yet", about: "Never looked through, or its newest update isn't read yet" },
];

const COLUMNS: Column<Without>[] = [
  { key: "s", header: "Company", rowHeader: true, cell: (r) => r.symbol },
  { key: "w", header: "Why", cell: (r) => r.why_text },
  { key: "n", header: "Newest update filed", cell: (r) => (r.newest_filed ? dateOnly(r.newest_filed) : "–") },
  { key: "p", header: "Problem", wrap: true, cell: (r) => (r.problem ? <span className="k-muted">{r.problem}</span> : "–") },
];

/** Admin → Data: the NIFTY 100's business updates coverage, from what is stored (LO1-3): how many have one read in the last 120 days,
 * the count for each reason the others haven't, and the companies by name. */
export function BizCoveragePanel() {
  const [cov, setCov] = useState<IndexCoverage | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api<IndexCoverage>("/admin/business-updates/index").then(setCov).catch((e) => setErr(e instanceof Error ? e.message : "Couldn't load the coverage."));
  }, []);
  return (
    <Card label="Business updates coverage" testId="adm-biz-coverage">
      <CardHead title="Business updates coverage" info={cov?.rule ?? "From what is stored: the filings already read for each company."} />
      {err ? <p className="k-small k-down" role="alert">{err}</p> : !cov ? <Skeleton label="Loading the coverage" /> : !cov.companies ? (
        <p className="k-small k-muted">The NIFTY 100's list of stocks couldn't be read from the exchange yet; it is kept once read.</p>
      ) : (
        <>
          <p className="k-small" data-testid="adm-biz-coverage-line"><b>{cov.index}: {cov.covered} of {cov.companies}</b> have a business update read in the last {cov.days} days.</p>
          <DataTable label="Why the others have none" rows={WHY} rowKey={(r) => r.key} columns={[
            { key: "r", header: "Reason", rowHeader: true, cell: (r) => r.label },
            { key: "c", header: "Companies", numeric: true, cell: (r) => String(cov.counts[r.key] ?? 0) },
            { key: "a", header: "Meaning", wrap: true, cell: (r) => <span className="k-muted">{r.about}</span> },
          ]} />
          {cov.without.length > 0 && <DataTable label={`${cov.index} companies without a business update`} rows={cov.without} rowKey={(r) => r.symbol} columns={COLUMNS} stack phonePage={10} />}
        </>
      )}
    </Card>
  );
}
