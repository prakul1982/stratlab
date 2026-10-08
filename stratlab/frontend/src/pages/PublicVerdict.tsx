import { useEffect, useState } from "react";
import { publicGet, type ApiError } from "../lib/http";
import { money, pct, TF_NAME } from "../lib/format";
import { upDown, checkTone } from "../lib/tradeUi";
import type { CheckStatus, Stats, VerdictKind } from "../lib/types";
import { XYChart } from "../components/Charts";
import { moneyCompact } from "../lib/chartFormat";
import { PublicFrame } from "../components/PublicFrame";
import { STATUS_NAME } from "../components/ui";
import { Badge } from "../components/kit/Badge";
import { Card, CardHead } from "../components/kit/Card";
import { DataTable, type Column } from "../components/kit/DataTable";
import { Stat, StatRow } from "../components/kit/Stat";
import { ErrorState, Skeleton } from "../components/kit/States";
import "./trade/trade.css";

/* /verdict/:token: a verdict someone shared, readable without an account. Built from the kit (components/kit). */

interface Snapshot {
  name: string; question: string; instrument: { symbol: string; name?: string; market?: string; currency?: string; type?: string };
  tf: string; range: { from: string; to: string } | null; side: string; created_at: string;
  verdict: { verdict: VerdictKind; headline: string; summary: string; passed: number; total: number;
    checks: { id: string; title: string; status: CheckStatus; detail: string }[] };
  stats: Stats; series: { t: string[]; equity: (number | null)[]; buy_hold: (number | null)[]; split: number | null };
  group: { name: string; max_open: number; members: { symbol: string; trades: number; pnl: number; win: number | null; buy_hold: number | null }[] } | null;
}
type Member = NonNullable<Snapshot["group"]>["members"][number];

const d = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric" });

/** A verdict someone shared: readable without an account, with no rules and no owner details. */
export function PublicVerdict({ token }: { token: string }) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  useEffect(() => {
    publicGet<Snapshot>(`/public/v/${encodeURIComponent(token)}`).then(setSnap).catch((e: ApiError) => { setGone(e.message); document.title = "Verdict not available · StratLab"; });
  }, [token]);

  const v = snap?.verdict;
  const cur = snap?.instrument.currency || (snap?.instrument.market === "IN" ? "INR" : "");
  useEffect(() => { if (snap) document.title = `${snap.verdict.headline} ${snap.name} · StratLab`; }, [snap]);

  const cols: Column<Member>[] = [
    { key: "sym", header: "Symbol", rowHeader: true, cell: (m) => <b>{m.symbol}</b> },
    { key: "n", header: "Trades", numeric: true, cell: (m) => m.trades },
    { key: "pnl", header: "P&L", numeric: true, cell: (m) => <span className={upDown(m.pnl)}>{money(m.pnl, cur)}</span> },
    { key: "win", header: "Win rate", numeric: true, cell: (m) => (m.win == null ? "–" : `${m.win}%`) },
    { key: "bh", header: "Buy and hold", numeric: true, cell: (m) => (m.buy_hold == null ? "–" : <span className={upDown(m.buy_hold)}>{pct(m.buy_hold)}</span>) },
  ];

  return (
    <PublicFrame action={<a className="btn sm" href="/">Test your own idea free</a>}>
        {!snap && !gone && <Card><Skeleton label="Opening the verdict" /></Card>}
        {gone && (
          <ErrorState title="This verdict isn't available" action={{ label: "See what StratLab does", to: "/" }}>
            {gone} The person who shared it may have turned the link off.
          </ErrorState>
        )}
        {snap && v && (
          <>
            <div className="k-stack">
              <span className="k-eyebrow">
                {snap.name} · {snap.group ? `${snap.group.name} (${snap.group.members.length})` : snap.instrument.symbol} · {TF_NAME[snap.tf] ?? snap.tf} candles
                {snap.range ? ` · ${d(snap.range.from)} – ${d(snap.range.to)}` : ""}
              </span>
              <h1 className={`verdict-head pub-head ${v.verdict}`}>{v.headline}</h1>
              <p className="k-lede">{v.summary}</p>
              {snap.question && <p className="k-small k-muted">The question: {snap.question}</p>}
            </div>

            <Card label="Return after costs">
              <CardHead title="Return after costs" actions={<span className="k-note">{v.checks.length} honesty checks · {v.passed} passed</span>} />
              {snap.series.t.length > 1 && (
                <XYChart ariaLabel="Strategy against buy and hold" height={240} split={snap.series.split} times={snap.series.t} compare
                  splitNotes={["tuned on these years", "never seen"]}
                  format={(x) => money(x, cur)} axisFormat={(x) => moneyCompact(x, cur ?? "USD")}
                  series={[{ id: "strategy", label: "Strategy", values: snap.series.equity, color: "var(--ink)", width: 2 },
                    { id: "hold", label: "Buy and hold", values: snap.series.buy_hold, color: "var(--muted)", width: 1.5, dash: "5 4" }]} />
              )}
              <StatRow label="Results">
                <Stat item label="Return after costs" value={pct(snap.stats.ret)} tone={snap.stats.ret > 0 ? "up" : snap.stats.ret < 0 ? "down" : undefined} />
                <Stat item label="Buy and hold" value={pct(snap.stats.buy_hold_ret)} tone={snap.stats.buy_hold_ret > 0 ? "up" : snap.stats.buy_hold_ret < 0 ? "down" : undefined} />
                <Stat item label="Worst fall" value={pct(snap.stats.mdd)} tone="down" />
                <Stat item label="Trades" value={String(snap.stats.n)} />
              </StatRow>
            </Card>

            <section className="pub-checks" aria-label="The honesty checks">
              {v.checks.map((c) => (
                <Card key={c.id} label={c.title}>
                  <CardHead level={3} title={c.title} actions={<Badge tone={checkTone(c.status)}>{STATUS_NAME[c.status]}</Badge>} />
                  <p className="k-small k-muted">{c.detail}</p>
                </Card>
              ))}
            </section>

            {snap.group && (
              <Card label="Group members">
                <CardHead title={`${snap.group.name}: member by member`} />
                <DataTable label="Group members" columns={cols} rows={snap.group.members} rowKey={(m) => m.symbol} />
              </Card>
            )}

            <Card label="Test your own idea">
              <CardHead title="Is your idea real, or just lucky?" />
              <p className="k-small k-muted">Describe a strategy in plain words. StratLab tests it on years of real prices, after real costs, and runs the same four honesty checks.</p>
              <a className="btn k-btn-end" href="/">Test your own idea free</a>
            </Card>
            <p className="k-note">Shared from StratLab. Research and paper trading only: past results don't predict future returns, and this isn't investment advice. The strategy's rules are private to the person who shared it.</p>
          </>
        )}
    </PublicFrame>
  );
}
