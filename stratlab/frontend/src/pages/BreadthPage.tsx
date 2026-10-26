import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import {
  BROAD_GROUP, breadthApi, breadthChipLabel, dailyTitle, breadthStart, count, delta, liveReadLine, MOVES_LABEL, MOVES_TITLE, liveSeries, sectorColumnLabel, liveNoticeTone, liveTag, liveTitle, orderGroups, revisionLines, savePick, share, shortDay, spikeCap, thrustDays,
  type BreadthAlerts, type BreadthView, type Group, type GroupId, type History, type LiveView, type Revision, type SectorTable, type Today,
} from "../lib/breadth";
import { cutSeries, firstInPeriod, isPeriod, offeredPresets, periodDays, spanDays } from "../lib/period";
import { eyebrowOf } from "../lib/eyebrow";
import { flatZero } from "../lib/chartFormat";
import { latestDue, marketTz, minus, softHyphens, type Pending } from "../lib/format";
import { homeRegion } from "../lib/homeMarket";
import { LineChart, PairBars } from "../components/Charts";
import { Info } from "../components/ui";
import {
  Badge, Card, CardHead, ChartFrame, ChipBar, DataTable, Delta, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, Notice, PageHeader, PlanNote, Skeleton, Stat, StatRow,
  type Column,
} from "../components/kit";

/* Market breadth: how many stocks in a group take part in the market's moves. Today's numbers for everyone; the
 * history as small charts (one measure each, never two scales on one chart) on Basic and up. Facts only.
 * The page asks for the whole stored history once per group and cuts it by the period chosen, so the period buttons
 * answer at once and a period the stored days can't tell apart from "All" isn't offered. */

const A = "var(--bx-a)", B = "var(--bx-b)";
const fmt1 = (v: number) => minus(v.toLocaleString("en-IN", { maximumFractionDigits: 1 }));
const fmtPct = (v: number) => minus(`${v.toFixed(1)}%`);
const fmtInt = (v: number) => minus(Math.round(v).toLocaleString("en-IN"));
const PERIOD_UNITS = [
  { value: "days", label: "day", plural: "days" }, { value: "weeks", label: "week", plural: "weeks" },
  { value: "months", label: "month", plural: "months" }, { value: "years", label: "year", plural: "years" },
];

export function BreadthPage() {
  const { fail } = useApp();
  // the group or market the address names (the Invest home's card, review 5c), else the reader's market opens on its
  // own group (R6O-007: an India reader landed on the S&P 500)
  const [params, setParams] = useSearchParams();
  const [first] = useState(() => breadthStart(params, homeRegion()));
  const [group, setGroup] = useState<GroupId>(first.group);
  const [period, setPeriod] = useState<string>(first.range);
  const [data, setData] = useState<BreadthView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    const n = ++seq.current;
    setLoading(true);
    breadthApi.get(group, "all")
      .then((d) => {
        if (n !== seq.current) return;
        // a market's own group with no counts yet, not one the reader picked: its broad group, which has them
        if (!d.today && !first.picked && group === first.group && BROAD_GROUP[first.region] !== group) { setGroup(BROAD_GROUP[first.region]); return; }
        setData(d); setError(null);
      })
      .catch((e) => {
        if (n !== seq.current) return;
        if ((e as { status?: number }).status === 404 && group !== "nifty500") { setGroup("nifty500"); return; }   // a group no longer offered
        setData(null); setError((e as Error).message);     // not the last group's numbers under the new group's name
        fail(e);
      })
      .finally(() => { if (n === seq.current) setLoading(false); });
  }, [group, fail, tries]);

  // the days stored, the periods that tell apart, and the history cut to the one chosen
  const all = data?.history ?? null;
  const span = all ? spanDays(all.days) : 0;
  const presets = useMemo(() => offeredPresets(span), [span]);
  const isPreset = /^(3m|6m|1y|2y)$/.test(period);
  const chosen = !isPeriod(period) || (isPreset && !presets.some((p) => p.value === period)) ? "all" : period;     // a preset the days can't tell from All isn't kept
  const from = all ? firstInPeriod(all.days, chosen) : 0;
  const shown = useMemo(() => (all ? cutSeries(all, from) : null), [all, from]);
  const days = periodDays(chosen);
  const coversAll = !!all && days != null && days >= span;
  const pick = (p: string) => { setPeriod(p); savePick(group, p); };
  const pickGroup = (g: GroupId) => {
    setGroup(g); savePick(g, period);
    // the group picked stays in the address, so Back to this page opens it again
    setParams((p) => { const n = new URLSearchParams(p); n.set("group", g); n.delete("region"); return n; }, { replace: true });
  };

  const help = data?.help ?? {};
  return (
    <div className="k-page breadth">
      <PageHeader eyebrow={eyebrowOf("/invest/breadth")} title="Market breadth" asOf={data?.today ? data.as_of : undefined} asOfLabel={breadthChipLabel(data?.live)} asOfTz={marketTz(data?.group.region)}
        info={help.members} infoLabel="Which stocks are counted"
        lede="How many stocks in a group rose or fell, sit above their averages, or made new highs and lows, day by day, from daily closes. Every stock counts once: facts about what happened, not a forecast." />

      <Card>
        <FormGrid label="What to show">
          <Field label="Group of stocks">
            {(id) => (
              <select id={id} className="k-input" aria-label="Group of stocks" value={group} onChange={(e) => pickGroup(e.target.value as GroupId)}>
                {(["IN", "US"] as const).map((r) => (
                  <optgroup key={r} label={r === "IN" ? "India" : "United States"}>
                    {orderGroups((data?.groups ?? []).filter((x) => x.region === r), r).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                    {!data && r === "IN" && <option value={group}>Loading…</option>}
                  </optgroup>
                ))}
              </select>
            )}
          </Field>
          {data && !data.locked && all && (
            // named for what it moves: the history charts, not the live card under it (R63-008)
            <FieldGroup label="History charts' range" wide>
              <ChipBar label="History charts' range" options={presets} value={chosen} onChange={pick} custom={{ storageKey: "stratlab.breadth.periods", units: PERIOD_UNITS, defaultUnit: "months" }} />
            </FieldGroup>
          )}
        </FormGrid>
        {coversAll && chosen !== "all" && <p className="k-note">Only {Math.round(span).toLocaleString("en-IN")} days of data so far, so this shows all of them.</p>}
      </Card>

      {!data && loading ? <Card><Skeleton label="Counting the market" lines={4} /></Card>
        : !data ? <ErrorState title="Market breadth couldn't be opened just now" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error ?? "Check your connection and try again."}</ErrorState>
        : (
          <div className="k-page" aria-busy={loading}>
            {!data.today ? (
              <Card testId="breadth-empty">
                <EmptyState title={`No counts for ${data.group.name} yet`}>Breadth is worked out after each market's close; the first run reads about two years of prices, so it takes a while. Check back after the next close.</EmptyState>
              </Card>
            ) : (
              <>
                {data.live && <LiveCard live={data.live} group={data.group} />}
                <Headline t={data.today} help={help} live={data.live} pending={data.pending} revised={data.revised} />
                {data.locked ? (
                  <div data-testid="breadth-locked"><PlanNote>Today's numbers and today's charts are on every plan. The history charts, from 3 months back, and the sector table are on the {data.plan_needed} plan.</PlanNote></div>
                ) : shown && <>
                  <AlertBox group={data.group} />
                  <Charts data={data} h={shown} help={help} />
                </>}
              </>
            )}
          </div>
        )}
    </div>
  );
}

/* ---------- today's numbers ---------- */
const LIVE_INFO = "Worked out every 15 minutes while the market is open, from live prices: each stock's price against the previous close "
  + "(rose, fell, unchanged), and against its 20-, 50- and 200-day averages with the live price counted as the latest close. "
  + "The numbers for the close, further down, are worked out after the market shuts and are not changed by these.";

/** While the market is open: the counts so far today, with a line through the day. When live prices can't be read it says so
 * in words and the last close below stands. */
function LiveCard({ live, group }: { live: LiveView; group: Group }) {
  if ((live.state !== "live" && live.state !== "final") || !live.latest) {
    return (
      <Card label="Breadth today" testId="breadth-live-off">
        <CardHead title="Today, live" info={LIVE_INFO} infoLabel="About the live numbers" />
        <Notice tone={liveNoticeTone(live)} role="status">{live.message ?? "Live prices aren't available right now. The numbers below are the last close."}</Notice>
      </Card>
    );
  }
  const s = liveSeries(live);
  const l = live.latest;
  const tag = liveTag(live), read = liveReadLine(l);
  const several = s.times.length > 1;
  const at = (i: number) => `${group.name}, ${s.times[i]}`;
  return (
    <div className="k-page" data-testid="breadth-live">
      <Card label="Breadth today, live">
        <CardHead title={liveTitle(live)} info={LIVE_INFO} infoLabel="About the live numbers" actions={<span data-testid="breadth-live-tag"><Badge tone={tag.tone}>{tag.text}</Badge></span>} />
        {live.late && <Notice tone="warn" role="status">The newest live point is {live.age_minutes} minutes old. A point is added every {live.every_minutes} minutes while the market is open; the next one comes when live prices are read again.</Notice>}
        <StatRow>
          <Stat label="Rose / fell" value={<><span className="k-up">{count(l.adv)}</span> <span className="k-muted">/</span> <span className="k-down">{count(l.dec)}</span></>} note={`${count(l.unch)} unchanged · against the previous close`} />
          <Stat label="Above 20-day average" value={share(l.pct20)} />
          <Stat label="Above 50-day average" value={share(l.pct50)} />
          <Stat label="Above 200-day average" value={share(l.pct200)} />
          {l.idx != null && <Stat label={group.index_name} value={l.idx.toLocaleString("en-IN", { maximumFractionDigits: 2 })} note="latest level" />}
        </StatRow>
        {read && <p className="k-note" data-testid="breadth-live-read">{read}.</p>}
        {!several && live.state !== "final" && <p className="k-note">A point is added every {live.every_minutes} minutes while the market is open, so the line through the day starts after the second.</p>}
      </Card>
      {several && (
        <div className="k-cols">
          <ChartFrame title="Rose and fell through the day" info="How many stocks are above and below the previous close at each point."
            table={{ label: "Rose and fell through the day", columns: [{ key: "t", header: "Time", rowHeader: true, cell: (i: number) => s.times[i] },
              { key: "a", header: "Rose", numeric: true, cell: (i: number) => count(s.adv[i]) }, { key: "d", header: "Fell", numeric: true, cell: (i: number) => count(s.dec[i]) }],
              rows: s.times.map((_, i) => s.times.length - 1 - i), rowKey: (i: number) => s.times[i] }}>
            <LineChart lines={[{ values: s.adv, color: A, label: "Rose", width: 2 }, { values: s.dec, color: B, label: "Fell", width: 2 }]} legend labels={s.times.map((_, i) => at(i))}
              axisLabels={s.times} ranges={false} table={false} height={200} format={fmtInt} ariaLabel={`Stocks that rose and fell today, ${s.times[0]} to ${s.times[s.times.length - 1]}`} />
          </ChartFrame>
          <ChartFrame title="Above their averages today" info="The share of stocks above their 20-, 50- and 200-day averages at each point, with the live price as the latest close."
            table={{ label: "Above their averages today", columns: [{ key: "t", header: "Time", rowHeader: true, cell: (i: number) => s.times[i] },
              { key: "p20", header: "20-day", numeric: true, cell: (i: number) => share(s.pct20[i]) }, { key: "p50", header: "50-day", numeric: true, cell: (i: number) => share(s.pct50[i]) },
              { key: "p200", header: "200-day", numeric: true, cell: (i: number) => share(s.pct200[i]) }],
              rows: s.times.map((_, i) => s.times.length - 1 - i), rowKey: (i: number) => s.times[i] }}>
            <LineChart lines={[{ values: s.pct20, color: "var(--ink-2)", label: "20-day", width: 2 }, { values: s.pct50, color: A, label: "50-day", width: 2 }, { values: s.pct200, color: B, label: "200-day", width: 2 }]} legend
              labels={s.times.map((_, i) => at(i))} axisLabels={s.times} ranges={false} table={false} height={200} format={fmtPct} axisFormat={(v) => `${Math.round(v)}%`}
              ariaLabel={`Share of stocks above their 20-, 50- and 200-day averages today, ${s.times[0]} to ${s.times[s.times.length - 1]}`} />
          </ChartFrame>
        </div>
      )}
    </div>
  );
}

function Headline({ t, help, live, pending, revised }: { t: Today; help: Record<string, string>; live?: unknown; pending?: Pending; revised?: Revision[] }) {
  const changed = revisionLines(revised, shortDay);
  const vs = t.prev_day ? ` vs ${shortDay(t.prev_day)}` : "";
  const lab = (label: string, info?: string) => <>{label}{info && <Info label={`About ${label.toLowerCase()}`}>{info}</Info>}</>;
  // a change in a share or an oscillator is up or down in colour; TRIN is the one inverted figure (a rise in it is selling pressure), so its change keeps the direction without judging
  const chg = (v: number | null | undefined, unit: "" | "pts", dp: number, neutral = false) => {
    if (v == null) return undefined;
    const text = delta(v, unit, dp);
    return text ? <Delta value={Number(v.toFixed(dp))} tone={neutral ? "neutral" : "auto"}>{text}{vs}</Delta> : undefined;
  };
  const pts = (k: "pct20" | "pct50" | "pct200" | "stage2") => chg(t[k].change, "pts", 1);
  // two counts: the day before's pair, which reads more plainly than two signed changes
  const pair = (a: keyof Today, b: keyof Today) => {
    const x = t[a] as Today["adv"], y = t[b] as Today["adv"];
    if (!t.prev_day || (x.prev == null && y.prev == null)) return undefined;
    // DE-023: "Same as 22 Oct" didn't say what was the same
    return x.change === 0 && y.change === 0 ? `${shortDay(t.prev_day)}: the same ${count(x.prev)} / ${count(y.prev)}` : `${shortDay(t.prev_day)}: ${count(x.prev)} / ${count(y.prev)}`;
  };
  return (
    <Card label={`Breadth on ${shortDay(t.day)}`} testId="breadth-today">
      <CardHead title={latestDue(t.day, pending) ?? dailyTitle(shortDay(t.day), live)} />
      <StatRow>
        <Stat label={lab("Rose / fell", help.ad)} value={<><span className="k-up">{count(t.adv.value)}</span> <span className="k-muted">/</span> <span className="k-down">{count(t.dec.value)}</span></>}
          note={<>Ratio {t.ad_ratio.value == null ? "–" : t.ad_ratio.value.toFixed(2)} · {count(t.unch.value)} unchanged · {count(t.stocks.value)} stocks{pair("adv", "dec") ? ` · ${pair("adv", "dec")}` : ""}</>} />
        <Stat label={lab("Above 50-day average", help.ma)} value={share(t.pct50.value)} delta={pts("pct50")} note={<span className="nowrap">{`20\u2011day: ${share(t.pct20.value)}`}</span>} />
        <Stat label={lab("Above 200-day average", help.ma)} value={share(t.pct200.value)} delta={pts("pct200")} />
        <Stat label={lab("52-week highs / lows", help.highs_lows)} value={<><span className="k-up">{count(t.highs.value)}</span> <span className="k-muted">/</span> <span className="k-down">{count(t.lows.value)}</span></>} note={pair("highs", "lows")} />
        <Stat label={lab(MOVES_LABEL, help.moves)} value={<><span className="k-up">{count(t.up4.value)}</span> <span className="k-muted">/</span> <span className="k-down">{count(t.down4.value)}</span></>} note={pair("up4", "down4")} />
        <Stat label={lab("In Stage 2", help.stage2)} value={share(t.stage2.value)} delta={pts("stage2")} />
        <Stat label={lab("McClellan oscillator", help.mcclellan)} value={t.mcclellan.value == null ? "–" : fmt1(t.mcclellan.value)}
          delta={chg(t.mcclellan.change, "", 1)} note={t.summation.value == null ? undefined : `Summation ${fmt1(t.summation.value)}`} />
        <Stat label={lab("TRIN", help.trin)} value={t.trin.value == null ? "–" : t.trin.value.toFixed(2)} delta={chg(t.trin.change, "", 2, true)} />
      </StatRow>
      {/* DE-023: the correction is one short line with its details behind the (i), not a paragraph in the headline card */}
      {changed.length > 0 && <p className="k-note" data-testid="breadth-revised">{changed.length === 1 ? "An earlier day's count was revised" : `${changed.length} earlier counts were revised`}
        <Info label="About the revision">{changed.join(". ")}. A stock's price was corrected after the day was first counted.</Info></p>}
    </Card>
  );
}

/* ---------- an alert on the share above the 50-day average ---------- */
function AlertBox({ group }: { group: Group }) {
  const { fail, notify } = useApp();
  const [alerts, setAlerts] = useState<BreadthAlerts | null>(null);
  const [level, setLevel] = useState("60");
  const [busy, setBusy] = useState(false);
  useEffect(() => { breadthApi.alerts().then(setAlerts).catch(() => setAlerts(null)); }, []);
  const n = Number(level);
  const ok = level.trim() !== "" && Number.isFinite(n) && n >= 1 && n <= 99;
  // DE-024: a level the alert can't take says why, not only a greyed-out button
  const why = level.trim() === "" ? "Enter a level from 1 to 99%." : !ok ? "The level is a share of stocks: a number from 1 to 99." : null;
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    try {
      setAlerts(await breadthApi.addAlert(group.id, n));
      notify(`You'll get a message after the close when ${group.name}'s share above the 50-day average crosses ${n}%.`);
    } catch (err) { fail(err); } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    try { setAlerts(await breadthApi.deleteAlert(id)); } catch (e) { fail(e); }
  };
  const mine = alerts?.items ?? [];
  const name = (id: string) => (id === group.id ? group.name : id);
  return (
    <Card label="Breadth alerts">
      <CardHead title="Alert on the share above the 50-day average"
        info="Checked once a day, after the counts for the close are in. You get one message each time the share moves from one side of your level to the other, by phone notification, Telegram or email, whichever you set up in Settings. Up to 5." infoLabel="About breadth alerts" />
      <FormGrid label="New breadth alert" onSubmit={add} inline>
        <Field label="Alert level" unit="%" inputMode="decimal" value={level} onChange={(e) => setLevel(e.target.value)} aria-invalid={!ok}
          aria-label={`Alert me when the share of ${group.name} stocks above their 50-day average crosses`} />
        {why && <p className="k-note k-down k-field wide" role="alert" data-testid="breadth-alert-why">{why}</p>}
        {ok && alerts && mine.length >= alerts.limit && <p className="k-note k-field wide">You have the {alerts.limit} alerts a plan keeps: delete one to add another.</p>}
        <FormActions>
          <button className="btn" disabled={!ok || busy || (alerts ? mine.length >= alerts.limit : false)}>Add alert</button>
        </FormActions>
      </FormGrid>
      {mine.length > 0 && (
        <div className="inv-rows">
          {mine.map((a) => (
            <div key={a.id} className="inv-alert">
              <span className="k-small">{name(a.group)} crosses {a.level}%{a.side ? ` · now ${a.side}` : ""}{a.fired_at ? ` · last sent ${shortDay(a.fired_at.slice(0, 10))}` : ""}</span>
              <button className="btn quiet sm" aria-label={`Delete the alert at ${a.level}% on ${name(a.group)}`} onClick={() => remove(a.id)}>Delete</button>
            </div>
          ))}
        </div>
      )}
      {alerts && !alerts.channels.length && <p className="k-note">Set up a phone, Telegram or a confirmed email in <Link className="link" to="/settings#notifications">Settings</Link> for alerts to reach you.</p>}
    </Card>
  );
}

/* ---------- the charts ---------- */
type Col = { header: string; get: (i: number) => string };

/** One chart in its card, with the same numbers as a table under its Table switch (newest day first). */
function Box({ title, info, h, cols, note, none, children }: { title: string; info?: string; h: History; cols: Col[]; note?: ReactNode; none?: boolean; children: ReactNode }) {
  const idx = Array.from({ length: h.days.length }, (_, k) => h.days.length - 1 - k);
  const columns: Column<number>[] = [{ key: "day", header: "Day", rowHeader: true, cell: (i) => shortDay(h.days[i]) },
    ...cols.map((c) => ({ key: c.header, header: c.header, numeric: true, cell: (i: number) => c.get(i) }))];
  return (
    <ChartFrame title={title} info={info} table={{ label: title, columns, rows: idx, rowKey: (i) => h.days[i], empty: "No days to show." }}
      footer={note || none ? <p className="k-note">{none && <b data-testid="breadth-none">None in this period. </b>}{note}</p> : undefined}>
      {children}
    </ChartFrame>
  );
}

function Charts({ data, h, help }: { data: BreadthView; h: History; help: Record<string, string> }) {
  const labels = h.days.map(shortDay);
  const since = data.since ? shortDay(data.since) : null;
  const hasIndex = h.index.some((v) => v != null);
  const last = h.days.length ? shortDay(h.days[h.days.length - 1]) : "";
  const thrusts = (data.thrusts ?? []).filter((d) => !h.days.length || d >= h.days[0]);
  const f = (v: number | null | undefined, fn: (x: number) => string) => (v == null ? "–" : fn(v));
  // one spike (TRIN near 10) flattened every other day: the rare days above the cap are drawn at the top edge (DE-022)
  const trinCap = spikeCap(h.trin);
  const trinOver = trinCap == null ? 0 : h.trin.filter((v) => v != null && v > trinCap).length;
  return (
    <div data-testid="breadth-charts" className="k-page">
      <div className="k-cols">
        <Box title="Advance/decline line" info={help.ad_line} h={h} cols={[{ header: "A/D line", get: (i) => fmtInt(h.ad_line[i]) }, { header: "Rose", get: (i) => count(h.adv[i]) }, { header: "Fell", get: (i) => count(h.dec[i]) }]}
          note={`Running total from ${since ?? "the first day"} · last ${last}`}>
          <LineChart lines={[{ values: h.ad_line, color: A, label: "A/D line", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200}
            format={fmtInt} ariaLabel={`Advance/decline line, ${labels[0]} to ${last}`} />
        </Box>
        <Box title="Above the 50- and 200-day averages" info={help.ma} h={h} cols={[{ header: "Above 50-day", get: (i) => share(h.pct50[i]) }, { header: "Above 200-day", get: (i) => share(h.pct200[i]) }]} note={`Last ${last}`}>
          <LineChart lines={[{ values: h.pct50, color: A, label: "Above 50-day", width: 2 }, { values: h.pct200, color: B, label: "Above 200-day", width: 2 }]} legend
            labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200} format={fmtPct} axisFormat={(v) => `${Math.round(v)}%`} ariaLabel="Share of stocks above their 50- and 200-day averages" />
        </Box>
        <Box title={data.group.index_name} info={help.index} h={h} cols={[{ header: "Close", get: (i) => f(h.index[i], (v) => v.toLocaleString("en-IN", { maximumFractionDigits: 2 })) }]} note={`Closing level · last ${last}`}>
          {hasIndex ? <LineChart lines={[{ values: h.index, color: "var(--ink-2)", label: data.group.index_name, width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200}
            format={(v) => minus(v.toLocaleString("en-IN", { maximumFractionDigits: 2 }))} axisFormat={fmtInt} ariaLabel={`${data.group.index_name} closing level`} />
            : <p className="k-small k-muted">The index's prices weren't available for these days.</p>}
        </Box>
        <Box title="New 52-week highs and lows" info={help.highs_lows} h={h} cols={[{ header: "New highs", get: (i) => count(h.highs[i]) }, { header: "New lows", get: (i) => count(h.lows[i]) }]} none={flatZero(h.highs, h.lows)} note={`Highs drawn up, lows down · last ${last}`}>
          <PairBars up={h.highs} down={h.lows} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} upLabel="new highs" downLabel="new lows" upName="New highs" downName="New lows" upColor={A} downColor={B}
            format={fmtInt} ariaLabel="New 52-week highs (up) and lows (down) each day" />
        </Box>
        <Box title="McClellan oscillator" info={help.mcclellan} h={h} cols={[{ header: "Oscillator", get: (i) => fmt1(h.mcclellan[i]) }]} note={`Last ${last}`}>
          <LineChart lines={[{ values: h.mcclellan, color: A, label: "Oscillator", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200}
            baseline={0} format={fmt1} axisFormat={fmtInt} ariaLabel="McClellan oscillator" />
        </Box>
        <Box title="McClellan summation index" info={help.summation} h={h} cols={[{ header: "Summation", get: (i) => fmt1(h.summation[i]) }]}
          note={`Added up from ${since ?? "the first day"}, the first day stored for this group, so its level depends on that start: read its direction, not its level against another group's · last ${last}`}>
          <LineChart lines={[{ values: h.summation, color: A, label: "Summation", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200}
            baseline={0} format={fmt1} axisFormat={fmtInt} ariaLabel="McClellan summation index" />
        </Box>
        <Box title={MOVES_TITLE} info={help.moves} h={h} cols={[{ header: "Up 4%+", get: (i) => count(h.up4[i]) }, { header: "Down 4%+", get: (i) => count(h.down4[i]) }]} none={flatZero(h.up4, h.down4)} note={`Last ${last}`}>
          <PairBars up={h.up4} down={h.down4} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} upLabel="up 4%+" downLabel="down 4%+" upName="Up 4% or more" downName="Down 4% or more" upColor={A} downColor={B}
            format={fmtInt} ariaLabel="Stocks up 4% or more (up) and down 4% or more (down) each day" />
        </Box>
        <Box title="Share in Stage 2" info={help.stage2} h={h} cols={[{ header: "In Stage 2", get: (i) => share(h.stage2[i]) }]} none={flatZero(h.stage2)} note={`Last ${last}`}>
          <LineChart lines={[{ values: h.stage2, color: A, label: "In Stage 2", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200}
            format={fmtPct} axisFormat={(v) => `${Math.round(v)}%`} ariaLabel="Share of stocks in Stage 2" />
        </Box>
        <Box title="Breadth thrust measure" info={help.thrust} h={h} cols={[{ header: "10-day average", get: (i) => fmtPct(h.thrust[i]) }]}
          note={<span data-testid="breadth-thrusts">{thrusts.length ? `A thrust happened on ${thrustDays(thrusts)}.` : "No thrust in these days."} Dashed lines at 40% and 61.5%.</span>}>
          <LineChart lines={[{ values: h.thrust, color: A, label: "10-day average", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200}
            levels={[{ v: 40, color: "var(--dash)", label: "40%" }, { v: 61.5, color: "var(--dash)", label: "61.5%" }]}
            format={fmtPct} axisFormat={(v) => `${Math.round(v)}%`} ariaLabel="Breadth thrust measure, with lines at 40% and 61.5%" />
        </Box>
        <Box title="TRIN" info={help.trin} h={h} cols={[{ header: "TRIN", get: (i) => f(h.trin[i], (v) => v.toFixed(2)) }]}
          note={`Dashed line at 1${trinCap != null ? ` · ${trinOver} day${trinOver === 1 ? "" : "s"} above ${trinCap} drawn at the top edge (the table and the tooltip give the value)` : ""} · last ${last}`}>
          <LineChart lines={[{ values: trinCap != null ? h.trin.map((v) => (v == null ? v : Math.min(v, trinCap))) : h.trin, color: A, label: "TRIN", width: 2 }]} labels={labels} times={h.days} sync="breadth" ranges={false} table={false} height={200} refs={[{ v: 1, dash: true }]}
            format={(v) => v.toFixed(2)} tipExtra={trinCap != null ? (i) => (h.trin[i] != null && h.trin[i]! > trinCap ? <span>Actual: {h.trin[i]!.toFixed(2)}</span> : null) : undefined}
            ariaLabel="TRIN each day, with a line at 1" />
        </Box>
      </div>
      {data.sectors && data.sectors.rows.length > 0 && (
        <Card>
          <CardHead title="Sectors: share above the 50-day average" info={help.sectors} />
          <SectorHeat t={data.sectors} />
        </Card>
      )}
      <Card>
        <CardHead title="The last 20 trading days" info="The counts behind the charts, newest first." />
        <Recent h={h} />
      </Card>
    </div>
  );
}

function SectorHeat({ t }: { t: SectorTable }) {
  return (
    <div className="k-stack">
      <DataTable stack label="Share of each sector's stocks above their 50-day average" rows={t.rows} rowKey={(r) => r.sector} sticky={t.rows.length > 14}
        columns={[{ key: "s", header: "Sector", rowHeader: true, cell: (r) => <span className="hyphens">{softHyphens(r.sector)}</span> /* "Telecommunica-tion", not "Telecommunicatio / n" on a phone (R54-012, R55-001) */ }, { key: "n", header: "Stocks", numeric: true, cell: (r) => r.stocks },
          ...t.columns.map((c, i) => ({ key: c.label, header: <span title={c.day}>{sectorColumnLabel(c, shortDay)}</span>, cardLabel: sectorColumnLabel(c, shortDay), numeric: true,
            cell: (r: SectorTable["rows"][number]) => {
              const v = r.values[i];
              return <span className={`inv-heat-cell heat${v == null ? 0 : Math.min(9, Math.floor(v / 10))}`} title={`${r.sector}, ${c.label.toLowerCase()} (${c.day}): ${share(v)}`}>{share(v)}</span>;
            } }))]} />
      <div className="k-row k-small k-muted" aria-hidden="true">
        <span>0%</span><span className="inv-scale" /><span>100%</span>
        <span className="k-note">Darker: more of the sector's stocks above their 50-day average.</span>
      </div>
      {t.small && t.small.length > 0 && <p className="k-note" data-testid="breadth-small-sectors">Not shown, with fewer than {t.min_stocks ?? 5} stocks to count: {t.small.map((x) => `${x.sector} (${x.stocks})`).join(", ")}.</p>}
    </div>
  );
}

function Recent({ h }: { h: History }) {
  const n = h.days.length;
  const idx = Array.from({ length: Math.min(20, n) }, (_, k) => n - 1 - k);
  const num = (key: string, header: string, get: (i: number) => string): Column<number> => ({ key, header, numeric: true, cell: get });
  return (
    <DataTable stack label="The last 20 trading days" rows={idx} rowKey={(i) => h.days[i]} empty="No days to show."
      columns={[{ key: "d", header: "Day", rowHeader: true, cell: (i) => shortDay(h.days[i]) },
        num("adv", "Rose", (i) => count(h.adv[i])), num("dec", "Fell", (i) => count(h.dec[i])),
        num("p50", "Above 50-day", (i) => share(h.pct50[i])), num("p200", "Above 200-day", (i) => share(h.pct200[i])),
        num("hi", "Highs", (i) => count(h.highs[i])), num("lo", "Lows", (i) => count(h.lows[i])),
        num("u4", "Up 4%", (i) => count(h.up4[i])), num("d4", "Down 4%", (i) => count(h.down4[i])),
        num("mc", "McClellan", (i) => fmt1(h.mcclellan[i])), num("tr", "TRIN", (i) => (h.trin[i] == null ? "–" : h.trin[i]!.toFixed(2)))]} />
  );
}
