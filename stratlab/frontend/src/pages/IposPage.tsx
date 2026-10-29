import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { eyebrowOf } from "../lib/eyebrow";
import { asOf, fmtDate, marketTz, pct, price } from "../lib/format";
import { useLiveRefresh } from "../lib/liveRefresh";
import { ipoApi, type AlertPrefs, type EventKind, type IpoList, type IpoRow, type Market, type Stage } from "../lib/ipo";
import { TAB_LINE, badgeOf, bandText, clockText, expectedText, minText, partsText, problemNote, segmentWord, sharesText, sizeText, spanText, tabsFor, timesText } from "../lib/ipoText";
import { Badge, Card, CardHead, CheckField, ChipSet, DataTable, Disclosure, EmptyState, ErrorState, PageHeader, PlanNote, Seg, Signed, Skeleton, type Column } from "../components/kit";
import "./ipo.css";

/* /invest/ipos: India's and the US's public offerings in their stages. India: upcoming, open for bidding, closed and awaiting
 * listing, recently listed; the issues' offer documents filed with SEBI that have no dates yet sit under Upcoming. US: expected to
 * price, priced and not yet trading, recently listed; the filings with no date under Upcoming. Each row opens the issue's own
 * page (IpoPage). Free for everyone; alerts (open, close, allotment, listing) are on Basic. Dates, prices and sizes from the
 * exchanges' and regulators' own pages; an allotment or listing date SEBI's timetable gives is marked expected. */

const EVENT_ORDER: EventKind[] = ["open", "close", "allotment", "listing"];
const US_EVENT: Partial<Record<EventKind, string>> = { listing: "Pricing and first trading day" };

function Company({ r }: { r: IpoRow }) {
  const seg = segmentWord(r);
  return (
    <>
      <Link className="link" to={`/invest/ipos/${encodeURIComponent(r.id)}`}><b>{r.name}</b></Link>
      <span className="k-sub-line">{[r.symbol, seg === "SME" ? "SME platform" : seg === "Mainboard" ? "Main board" : r.exchange].filter(Boolean).join(" · ")}</span>
    </>
  );
}

/* Issues that did not go ahead (withdrawn, postponed or cancelled, as the exchange names them) and the Social Stock Exchange's fund
 * raises are not in the stages: the first sit in a fold of their own with the word the exchange used, the second in another that
 * says they are not IPOs. */
function Aside({ rows, label, note, testId }: { rows: IpoRow[]; label: string; note: string; testId: string }) {
  if (!rows.length) return null;
  return (
    <Disclosure summary={`${label} (${rows.length})`} testId={testId}>
      <DataTable stack label={label} rows={rows} rowKey={(r) => r.id} rowAttrs={(r) => ({ "data-ipo": r.id, "data-stage": r.stage })}
        columns={[{ key: "name", header: "Company", rowHeader: true, wrap: true, cell: (r) => <Company r={r} /> },
          { key: "s", header: "Status", cell: (r) => <Badge tone={badgeOf(r).tone}>{badgeOf(r).word}</Badge> },
          { key: "d", header: "Bidding was to be", cell: (r) => (r.open || r.close ? spanText(r.open, r.close) : "–") },
          { key: "b", header: "Price band", numeric: true, cell: (r) => bandText(r) }]} />
      <p className="k-note">{note}</p>
    </Disclosure>
  );
}

function perfCell(r: IpoRow, which: "listing" | "now") {
  const p = r.perf;
  const v = which === "listing" ? p?.listing_change_pct : p?.change_pct;
  const px = which === "listing" ? p?.listing_price : p?.latest;
  if (px == null || v == null) return <span className="k-muted">–</span>;
  // the latest close is dated: it is the last session's close, not a live price (RC2A-002)
  const day = which === "now" && p?.latest_date ? `Close ${fmtDate(p.latest_date, { year: false })} · ` : "";
  return <>{price(px, r.currency, 2)}<span className="k-sub-line">{day}<Signed value={v} fmt={(x) => pct(x, 1)} /> on the issue price</span></>;
}

/** "2026-10-28 19:00" (the exchange's stamp, India time) as "28 Oct, 19:00". */
function bidsAt(stamp: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/.exec(stamp);
  return m ? `${fmtDate(m[1], { year: false })}, ${m[2]}` : stamp;
}

function columns(m: Market, tab: Stage): Column<IpoRow>[] {
  const name: Column<IpoRow> = { key: "name", header: "Company", rowHeader: true, wrap: true, cell: (r) => <Company r={r} /> };
  const band: Column<IpoRow> = { key: "band", header: "Price band", numeric: true, cell: (r) => bandText(r) };
  const lot: Column<IpoRow> = { key: "lot", header: "Lot and minimum", numeric: true, info: "The lot is the fewest shares one bid can be for. The minimum is the lot at the top of the price band.",
    cell: (r) => (r.lot ? <>{sharesText(r.lot)} shares<span className="k-sub-line">{minText(r)}</span></> : "–") };
  // the size says whether it is all new shares or new shares plus a sale by existing holders, when the exchange gives the two parts (LIVE1A-030)
  const size: Column<IpoRow> = { key: "size", header: "Issue size", numeric: true,
    info: "The whole issue: the new shares the company issues plus any shares existing holders put up for sale (an offer for sale). The two parts are under the total when the exchange gives both.",
    cell: (r) => <>{sizeText(r)}{r.size != null && r.size_parts?.fresh_cr != null && r.size_parts?.ofs_cr != null && <span className="k-sub-line" data-testid="ipo-size-parts">{partsText(r.size_parts)}</span>}</> };
  const times: Column<IpoRow> = { key: "times", header: tab === "open" ? "Bids so far" : "Bids received", numeric: true, info: "How many times the shares on offer the bids came to, counting the bids placed on both exchanges (NSE and BSE), as the exchange's issue page totals them. NSE's own count alone is lower. The time of the reading is under each figure.",
    cell: (r) => (r.sub_times != null ? <>{timesText(r.sub_times)}{tab === "open" && r.sub_as_of && <span className="k-sub-line" data-testid="ipo-sub-at">as of {bidsAt(r.sub_as_of)}</span>}</> : <span className="k-muted">–</span>) };
  if (m === "US") {
    if (tab === "upcoming") {
      return [name, { key: "d", header: "Expected to price", cell: (r) => (r.expected ? fmtDate(r.expected) : r.filed ? `Filed ${fmtDate(r.filed)}` : "–") }, band,
        { key: "sh", header: "Shares", numeric: true, cell: (r) => sharesText(r.shares, "US") }, size];
    }
    if (tab === "closed") return [name, { key: "d", header: "Priced", cell: (r) => fmtDate(r.priced) }, band, { key: "sh", header: "Shares", numeric: true, cell: (r) => sharesText(r.shares, "US") }, size];
    return [name, { key: "d", header: "First trading day", cell: (r) => fmtDate(r.priced) }, { key: "p", header: "Offer price", numeric: true, cell: (r) => bandText(r) },
      { key: "l", header: "Opening price", numeric: true, cell: (r) => perfCell(r, "listing") }, { key: "n", header: "Latest close", numeric: true, cell: (r) => perfCell(r, "now") }, size];
  }
  if (tab === "upcoming") {
    return [name, { key: "d", header: "Bidding", cell: (r) => spanText(r.open, r.close) }, band, lot, size,
      { key: "l", header: "Listing", cell: (r) => expectedText(r.listing, r.listing_expected) }];
  }
  if (tab === "open") {
    return [name, { key: "d", header: "Closes", cell: (r) => <>{fmtDate(r.close)}{r.close_time && <span className="k-sub-line">{clockText(r.close_time)} IST</span>}</> }, band, lot, size, times];
  }
  if (tab === "closed") {
    return [name, { key: "d", header: "Closed", cell: (r) => fmtDate(r.close) }, { key: "a", header: "Allotment", cell: (r) => expectedText(r.allotment, r.allotment_expected) },
      { key: "l", header: "Listing", cell: (r) => expectedText(r.listing, r.listing_expected) }, band, times];
  }
  return [name, { key: "d", header: "Listed", cell: (r) => fmtDate(r.listing) }, { key: "p", header: "Issue price", numeric: true, cell: (r) => (r.price != null ? bandText({ ...r, low: r.price, high: r.price }) : bandText(r)) },
    { key: "l", header: "Listing price", numeric: true, info: "The first session's opening price against the issue price.", cell: (r) => perfCell(r, "listing") },
    { key: "n", header: "Latest close", numeric: true, info: "The latest daily close against the issue price.", cell: (r) => perfCell(r, "now") }, times];
}

function Filed({ rows, m }: { rows: IpoRow[]; m: Market }) {
  if (!rows.length) return null;
  const label = m === "IN" ? "Offer documents filed with SEBI, no dates yet" : "Filed with the SEC, no pricing date yet";
  return (
    <Disclosure summary={`${label} (${rows.length})`} testId="ipo-filed">
      <DataTable stack label={label} rows={rows} rowKey={(r) => r.id} rowAttrs={(r) => ({ "data-ipo": r.id })}
        columns={[{ key: "name", header: "Company", rowHeader: true, wrap: true, cell: (r) => <Company r={r} /> },
          { key: "f", header: "Filed", cell: (r) => fmtDate(r.filed) },
          { key: "d", header: "Offer document", cell: (r) => (r.docs?.length ? r.docs.join(", ") : "–") },
          ...(m === "US" ? [{ key: "s", header: "Offer size", numeric: true, cell: (r: IpoRow) => sizeText(r) } as Column<IpoRow>] : [])]} />
      <p className="k-note">{m === "IN"
        ? "A company files its draft offer document with SEBI before it can announce dates. Most take months to hear back from SEBI, and some never open for bidding."
        : "A company files its registration with the SEC before it sets a price range. Some are withdrawn."}</p>
    </Disclosure>
  );
}

function AlertsCard({ p, onSave, sme }: { p: AlertPrefs; onSave: (n: Partial<AlertPrefs>) => void; sme: number }) {
  const names = p.event_names;
  return (
    <Card label="IPO alerts" testId="ipo-alerts">
      <CardHead level={2} title="IPO alerts" info="One message on the morning an event falls (about 08:00 IST for India; for the US, the New York morning), by phone notification, Telegram or email, whichever you set up in Settings. Dates are the exchanges' own; an allotment or listing date marked expected is SEBI's timetable." infoLabel="About IPO alerts" />
      {p.allowed ? (
        <CheckField checked={p.on} onChange={(on) => onSave({ on })} label="Message me when an IPO I picked below does something" />
      ) : (
        <PlanNote plan="basic">IPO alerts are on the {p.plan} plan: a message when an issue opens, closes, is allotted or lists. The lists and every issue's page stay free.</PlanNote>
      )}
      {p.allowed && p.on && !p.channels.length && <p className="k-callout k-small" role="status" data-testid="ipo-no-channel">Alerts are on, but there is nowhere to send them yet: add a phone, Telegram or a confirmed email in <Link className="link" to="/settings#notifications">Settings</Link>.</p>}
      {/* the events and the markets are one row of chips (VR2-019: two rows made this card as tall as the list above it) */}
      <div className="ipo-alert-sets">
        <ChipSet label="Which events" options={EVENT_ORDER.map((e) => ({ value: e, label: names[e] ?? e }))} on={p.events}
          onToggle={(e) => p.allowed && onSave({ events: p.events.includes(e as EventKind) ? p.events.filter((x) => x !== e) : [...p.events, e as EventKind] })} />
        <ChipSet label="Which markets" options={[{ value: "IN", label: "India" }, { value: "US", label: "US" }]} on={p.markets}
          onToggle={(m) => p.allowed && onSave({ markets: p.markets.includes(m as Market) ? p.markets.filter((x) => x !== m) : [...p.markets, m as Market] })} />
      </div>
      <CheckField checked={p.sme} disabled={!p.allowed} onChange={(sme) => onSave({ sme })} label="Include SME issues (India)" />
      {p.allowed && !p.sme && sme > 0 && <p className="k-note" data-testid="ipo-sme-note">{sme} SME issue{sme === 1 ? " is" : "s are"} open or coming up. SME issues are left out of the alerts unless you tick the box above.</p>}
      {p.markets.includes("US") && <p className="k-note">For the US, an alert comes on the day an offering is expected to price and on the day it starts trading ({US_EVENT.listing}).</p>}
    </Card>
  );
}

export function IposPage() {
  const { fail } = useApp();
  const [params, setParams] = useSearchParams();
  const market: Market = params.get("m") === "US" ? "US" : "IN";
  const [d, setD] = useState<IpoList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tabs = tabsFor(market);
  const asked = params.get("t") as Stage | null;
  const [tab, setTab] = useState<Stage | null>(null);
  const load = useCallback((quiet = false) => {
    if (!quiet) { setD(null); setError(null); }
    ipoApi.list(market).then(setD).catch((e) => !quiet && setError(e instanceof ApiError ? e.message : "The IPO lists couldn't be read just now."));
  }, [market]);
  useEffect(() => { load(); }, [load]);
  // the open tab's bids move through the day: the page reads them again once a minute while an issue is open
  useLiveRefresh(!!d && d.counts.open > 0, () => load(true));       // each minute while an issue is open (LIVE-1; was every two)

  // the tab asked for in the address, else the first with something in it, the open tab first when issues are open
  const first = useMemo(() => {
    if (!d) return "upcoming" as Stage;
    if (asked && tabs.some((t) => t.value === asked)) return asked;
    return (["open", "upcoming", "closed", "listed"] as Stage[]).find((s) => tabs.some((t) => t.value === s) && d.counts[s] > 0) ?? "upcoming";
  }, [d, asked, tabs]);
  const now: Stage = tab && tabs.some((t) => t.value === tab) ? tab : first;
  const all = d?.tabs[now] ?? [];
  // a listed issue whose prices could not be read (small-board names mostly) is a row of dashes: those wait in a fold of their own,
  // so the list is the issues with figures (LIVE1A-031)
  const unpriced = now === "listed" ? all.filter((r) => r.perf?.latest == null && r.perf?.listing_price == null) : [];
  const rows = unpriced.length && unpriced.length < all.length ? all.filter((r) => !unpriced.includes(r)) : all;
  const unpricedShown = unpriced.length > 0 && rows !== all ? unpriced : [];
  // one stamp on the page (LIVE2-023): the bids' reading on the Open tab (they move through the day), the list's reading elsewhere
  const liveBids = !!d && now === "open" && d.counts.open > 0 && !!d.bids_read;
  const pick = (m: Market) => { const p = new URLSearchParams(params); p.set("m", m); p.delete("t"); setTab(null); setParams(p, { replace: true }); };
  const save = async (n: Partial<AlertPrefs>) => {
    if (!d) return;
    const next = { ...d.prefs, ...n };
    try {
      const got = await ipoApi.saveAlerts({ on: next.on, events: next.events, markets: next.markets, sme: next.sme });
      setD({ ...d, prefs: got });
    } catch (e) { fail(e); }
  };

  return (
    <div className="k-page ipo-page">
      <PageHeader eyebrow={eyebrowOf("/invest/ipos")} title="IPOs"
        lede="India's and the US's public offerings in their stages, from the exchanges' and regulators' own pages. Facts, not advice."
        asOf={liveBids ? d?.bids_read : d?.as_of} asOfTz={marketTz(market)} asOfLabel={liveBids ? "Bids read" : "Read"} info={<>When bidding opens and closes, the price band, the lot and the minimum, the bids received by category while an issue is open, and how a new listing has traded against its issue price.{d ? <> {d.note}</> : null}</>} infoLabel="Where this comes from" />
      <div className="k-toolbar">
        <Seg label="Market" value={market} onChange={(v) => pick(v as Market)} options={[{ value: "IN", label: "India" }, { value: "US", label: "US" }]} />
      </div>
      {error ? <ErrorState title="The IPO lists couldn't be read" action={{ label: "Try again", onClick: () => load() }}>{error}</ErrorState>
        : !d ? <Card><Skeleton label="Reading the IPO lists" lines={5} /></Card> : (
        <>
          {d.problems.length > 0 && <p className="k-callout k-small" role="status" data-testid="ipo-problems">{problemNote(d.problems, d.problems_at ? asOf(d.problems_at, { tz: marketTz(market), year: false }) : null)}</p>}
          <Card label="IPOs" testId="ipo-list">
            <div className="k-row">
              <Seg label="Stage" value={now} onChange={(v) => { setTab(v as Stage); const p = new URLSearchParams(params); p.set("t", v); setParams(p, { replace: true }); }}
                options={tabs.map((t) => ({ value: t.value, label: `${t.label} ${d.counts[t.value] ?? 0}`, short: t.label === "Recently listed" ? `Listed ${d.counts[t.value] ?? 0}` : undefined }))} />
              {now === "open" && d.counts.open > 0 && <Badge tone="live">Live</Badge>}
            </div>
            <p className="k-small k-muted" data-testid="ipo-tab-line">{TAB_LINE[market][now]}</p>
            {rows.length === 0 ? (
              <EmptyState title={`No ${tabs.find((t) => t.value === now)?.label.toLowerCase()} issues right now`}>
                {now === "open" ? "Nothing is open for bidding today. Upcoming issues are on the Upcoming tab." : now === "upcoming" ? "No dates have been announced yet." : "Nothing in the last few months."}
              </EmptyState>
            ) : (
              <DataTable stack label={`${tabs.find((t) => t.value === now)?.label} IPOs, ${market === "IN" ? "India" : "US"}`} rows={rows} rowKey={(r) => r.id}
                rowAttrs={(r) => ({ "data-ipo": r.id, "data-stage": r.stage })} columns={columns(market, now)} phonePage={25} />
            )}
            {unpricedShown.length > 0 && (
              <Disclosure summary={`Listed, no prices read yet (${unpricedShown.length})`} testId="ipo-unpriced">
                <DataTable stack label="Listed issues without prices" rows={unpricedShown} rowKey={(r) => r.id} rowAttrs={(r) => ({ "data-ipo": r.id, "data-stage": r.stage })}
                  columns={[{ key: "name", header: "Company", rowHeader: true, wrap: true, cell: (r) => <Company r={r} /> },
                    { key: "d", header: market === "US" ? "First trading day" : "Listed", cell: (r) => fmtDate(market === "US" ? r.priced : r.listing) },
                    { key: "p", header: market === "US" ? "Offer price" : "Issue price", numeric: true, cell: (r) => bandText(r) }]} />
                <p className="k-note">The exchange's price tables have no trading figures for these yet, so they are not set against the issue price.</p>
              </Disclosure>
            )}
            {market === "US" && <p className="k-note" data-testid="ipo-us-note">A US offering has no public bidding window, so there is no Open tab: the price is set the evening before trading starts.</p>}
          </Card>
          <AlertsCard p={d.prefs} onSave={save} sme={[...d.tabs.open, ...d.tabs.upcoming].filter((r) => r.segment === "sme").length} />
          {now === "upcoming" && <Filed rows={d.tabs.filed} m={market} />}
          <Aside rows={d.tabs.withdrawn ?? []} label="Withdrawn, postponed or cancelled" testId="ipo-withdrawn"
            note="The exchange names these issues withdrawn, postponed or cancelled in its list. They are not open, closed or listed, and no allotment or listing date applies." />
          <Aside rows={d.tabs.social ?? []} label="Social Stock Exchange fund raises, not IPOs" testId="ipo-social"
            note="The Social Stock Exchange lists fund raises by social enterprises beside the IPOs. They are not offers of shares to the public in the sense the stages above describe." />
          <p className="k-note">{d.note}</p>
        </>
      )}
    </div>
  );
}

export default IposPage;
