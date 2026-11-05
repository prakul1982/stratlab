import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { brokerBadge, brokerLine, type BrokerStatus } from "../lib/brokers";
import { EMAIL_STEPS, GUIDE_BROKERS, STATEMENT_SENDERS, guideFor, readLine, waysFor, type GuideBroker, type GuideWay } from "../lib/brokerGuide";
import { zerodhaLine } from "../lib/zerodha";
import { Badge, Card, CardHead, ChipBar, DataTable, Working, type Column } from "./kit";

/* "Pick your broker" (owner, 5 Nov) on Settings -> Connected accounts and My Holdings: pick one and see its ways to bring holdings
 * in, a row each: the live connection (where there is one, in its real state), the holdings file (where that broker keeps it)
 * and the monthly statement by email. The pick is kept on the account, so a returning person sees their broker first. */

type KiteLike = Omit<BrokerStatus, "key" | "name"> & { configured?: boolean };
export type GuideConn = { kite: KiteLike; brokers?: BrokerStatus[]; inbox: { ready: boolean; address: string | null } };

const TITLES: Record<GuideWay, { title: string; sub: string }> = {
  connect: { title: "Connect", sub: "Live, read-only" },
  file: { title: "Upload a file", sub: "Any time" },
  email: { title: "Email the monthly statement", sub: "Every broker, by itself" },
};

/** `where`: the page it's on (Settings links to My Holdings for the upload; My Holdings opens its own upload). */
export function BrokerGuide({ conn: given, where, onUpload }: { conn?: GuideConn | null; where: "settings" | "holdings"; onUpload?: () => void }) {
  const { me, savePrefs, notify, fail } = useApp();
  const [picked, setPicked] = useState<string | null>(null);
  const [fetched, setFetched] = useState<GuideConn | null | undefined>(given === undefined ? undefined : given);
  const [busy, setBusy] = useState(false);
  const conn = given !== undefined ? given : fetched;
  useEffect(() => {
    if (given !== undefined) return;
    api<GuideConn>("/connect").then(setFetched).catch(() => setFetched(null));     // no connection facts: the steps still show
  }, [given]);
  const sel = guideFor(picked ?? me?.prefs?.broker ?? null);
  const pick = (id: string) => {
    setPicked(id);
    if (id !== me?.prefs?.broker) void savePrefs({ broker: id }, true);
  };

  const status = (b: GuideBroker): (KiteLike & { name: string; path: string }) | null => {
    if (!b.connect || !conn) return null;
    if (b.connect === "kite") return { ...conn.kite, name: "Zerodha", path: "kite" };
    const s = conn.brokers?.find((x) => x.key === b.connect);
    return s ? { ...s, path: s.key } : null;
  };
  const login = async (path: string) => {
    setBusy(true);
    try { const r = await api<{ url: string }>(`/connect/${path}/login`); window.location.href = r.url; } catch (e) { fail(e); setBusy(false); }
  };
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); notify("Address copied."); } catch { notify("Select the address and copy it."); }
  };

  const how = (b: GuideBroker, w: GuideWay) => {
    if (w === "connect") {
      const s = status(b);
      if (!s) return conn === undefined ? <Working small label="Reading the connection" /> : <span className="k-small k-muted">The connection's state couldn't be read. Settings shows it.</span>;
      const badge = brokerBadge(s);
      const line = s.path === "kite" ? (s.available && s.connected ? zerodhaLine(s) : "") : brokerLine({ ...s, key: s.path });
      const words = s.configured === false ? "The live connection isn't switched on on this site yet."
        : !s.available ? "Open to the site owner's own account for now, not yet to every account."
        : !s.connected ? `Log in to ${b.name} once and your holdings are read for you. StratLab can't place orders or move money.` : line;
      return <span className="k-line-text"><Badge tone={badge.tone}>{badge.text}</Badge><span className="k-sub-line">{words}</span></span>;
    }
    if (w === "file") {
      return (
        <div className="k-stack tight">
          <ol className="k-steps">{b.file.steps.map((x) => <li key={x}>{x}</li>)}</ol>
          <p className="k-small k-muted">{readLine(b)}{b.file.help && <> <a className="link" href={b.file.help} target="_blank" rel="noopener noreferrer">{b.name}'s help page</a></>}</p>
        </div>
      );
    }
    const box = conn?.inbox;
    return (
      <div className="k-stack tight">
        <ol className="k-steps">{EMAIL_STEPS.map((x) => <li key={x}>{x}</li>)}</ol>
        {box?.address
          ? <><code className="k-address" data-testid="guide-address">{box.address}</code>
              <p className="k-small k-muted">Your private address. The email filter forwards mail from {STATEMENT_SENDERS.split(" OR ").join(", ")}.</p></>
          : <p className="k-small k-muted">{box && !box.ready ? "The statement inbox isn't set up on this site yet." : "Set up your private address in Settings, then forward mail from those senders to it."}</p>}
      </div>
    );
  };

  const act = (b: GuideBroker, w: GuideWay) => {
    if (w === "connect") {
      const s = status(b);
      if (!s || !s.available || (s.connected && s.live)) return null;
      return <button type="button" className="btn" disabled={busy} onClick={() => void login(s.path)}>{s.connected ? `Log in to ${b.name}` : `Connect ${b.name}`}</button>;
    }
    if (w === "file") {
      return where === "holdings" && onUpload
        ? <button type="button" className="btn" onClick={onUpload}>Upload holdings file</button>
        : <Link className="btn" to="/holdings">Upload in My Holdings</Link>;
    }
    const box = conn?.inbox;
    if (box?.address) return <button type="button" className="btn quiet" onClick={() => void copy(box.address ?? "")}>Copy address</button>;
    if (box && !box.ready) return null;
    return where === "settings"
      ? <a className="btn quiet" href="#inbox">Set up my inbox</a>
      : <Link className="btn quiet" to="/settings#inbox">Set up my inbox</Link>;
  };

  const columns: Column<GuideWay>[] = sel ? [
    { key: "way", header: "Way", rowHeader: true, cell: (w) => <span className="k-line-text"><b>{TITLES[w].title}</b><span className="k-sub-line">{TITLES[w].sub}</span></span> },
    { key: "how", header: "How", wrap: true, lead: true, cell: (w) => how(sel, w) },
    { key: "act", header: "", action: true, cell: (w) => act(sel, w) },
  ] : [];

  return (
    <Card id="pick-broker" label="Pick your broker">
      <CardHead title="Pick your broker" info="Each broker's ways to bring your holdings into StratLab: a live connection where there is one, the holdings file it lets you download, and the monthly statement by email, which lists your shares at every broker. Your pick is remembered." />
      <ChipBar label="Your broker" wrap options={GUIDE_BROKERS.map((b) => ({ value: b.id, label: b.name }))} value={sel?.id ?? ""} onChange={pick} />
      {sel
        ? <DataTable label={`Ways to bring in your ${sel.id === "other" ? "" : `${sel.name} `}holdings`} columns={columns} rows={waysFor(sel)} rowKey={(w) => w} stack
            rowAttrs={(w) => ({ "data-testid": `guide-${w}` })} />
        : <p className="k-small k-muted">Pick your broker to see the ways to bring its holdings in.</p>}
    </Card>
  );
}
