import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, CFG, supabase } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { HELP } from "../lib/help";
import { viewForFocus } from "../lib/spaces";
import type { Focus, Level } from "../lib/types";
import { FOCUSES, LEVELS } from "../components/LevelPrompt";
import { AlertSettingsCard } from "../components/AlertSettings";
import { NewslettersCard } from "../components/NewslettersCard";
import { TipsCard } from "../components/TipsCard";
import { Badge, Card, CardHead, FieldGroup, LinkCard, Notice, PageHeader, Seg, Skeleton } from "../components/kit";

/* /settings: the things you set once. Four sections behind one Seg: where alerts and emails go, what you see first and the
 * theme, the accounts and files StratLab reads, and the connection check. The section is in the address (#notifications). */

const SECTIONS = [
  { value: "notifications", label: "Notifications" },
  { value: "experience", label: "Experience" },
  { value: "accounts", label: "Connected accounts" },
  { value: "check", label: "Connection check" },
];
/** Older links and the ids of the cards inside a section. */
const ALIAS: Record<string, string> = { newsletters: "notifications", emails: "notifications", alerts: "notifications", connected: "accounts", connection: "check" };

type Row = { t: string; s: "pass" | "fail" | "warn"; d: string };
const TONE = { pass: "ok", warn: "warn", fail: "warn" } as const;
const WORD = { pass: "OK", warn: "Check", fail: "Problem" } as const;

export function SettingsPage() {
  const { me } = useApp();
  const loc = useLocation();
  const nav = useNavigate();
  const asked = loc.hash.replace("#", "");
  const section = SECTIONS.some((s) => s.value === asked) ? asked : ALIAS[asked] ?? "notifications";
  const go = (v: string) => nav({ hash: v }, { replace: true });

  return (
    <div className="k-page">
      <PageHeader eyebrow="Settings" title="Settings" lede="Where your alerts and emails go, what you see first, and the accounts and files StratLab reads." />
      <div className="k-section-nav"><Seg label="Settings sections" options={SECTIONS} value={section} onChange={go} /></div>
      {!me ? <Card label="Loading your settings"><Skeleton label="Loading your settings" /></Card> : <>
        {section === "notifications" && <><AlertSettingsCard /><TipsCard /><NewslettersCard /></>}
        {section === "experience" && <ExperienceCards />}
        {section === "accounts" && <ConnectedAccounts />}
        {section === "check" && <ConnectionCheck />}
      </>}
    </div>
  );
}

function ExperienceCards() {
  const { focus, level, savePrefs, setLevel, theme, setTheme } = useApp();
  return (
    <>
      <Card id="experience" label="What you see first">
        <CardHead title="What you see first" info="Changes only which space the menu and home page open in, and which settings start open. Every tool stays available." />
        <FieldGroup label="What you're here for">
          <Seg label="What you're here for" options={FOCUSES.map(([f, title]) => ({ value: f, label: title }))} value={focus ?? ""}
            onChange={(f) => void savePrefs({ focus: f as Focus, space: viewForFocus(f as Focus)! })} />
          {focus && <p className="k-small k-muted k-hint-line">{FOCUSES.find(([f]) => f === focus)?.[2]}</p>}
        </FieldGroup>
        <FieldGroup label="Experience">
          <Seg label="Experience" options={LEVELS.map(([l, title]) => ({ value: l, label: title }))} value={level ?? ""} onChange={(l) => void setLevel(l as Level)} />
          {level && <p className="k-small k-muted k-hint-line">{LEVELS.find(([l]) => l === level)?.[2]}</p>}
        </FieldGroup>
      </Card>
      <Card id="theme" label="Theme">
        <CardHead title="Theme" />
        <Seg label="Theme" options={[{ value: "system", label: "Same as my device" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]}
          value={theme} onChange={(t) => setTheme(t as "light" | "dark" | "system")} />
      </Card>
    </>
  );
}

type Held = { updated_at: string | null; source?: string | null; count?: number | null };
const noun = (n: number | null | undefined, one: string, many: string) => (n == null ? "" : `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`);

/** The places StratLab reads your accounts from. Each is a file you upload, with when it last changed; there is no broker
 * login, so there is nothing to connect or disconnect here. */
function ConnectedAccounts() {
  const [h, setH] = useState<Held | null | undefined>(undefined);
  const [mf, setMf] = useState<Held | null | undefined>(undefined);
  const [tax, setTax] = useState<Held | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    const get = <T,>(path: string, pick: (x: T) => Held, set: (v: Held | null) => void) =>
      api<T>(path).then((x) => { if (live) set(pick(x)); }).catch(() => { if (live) set(null); });
    void get<{ updated_at: string | null; source: string | null; totals: { count: number } }>("/holdings", (x) => ({ updated_at: x.updated_at, source: x.source, count: x.totals?.count }), setH);
    void get<{ updated_at: string | null; total: { schemes: number } }>("/money/mutual-funds", (x) => ({ updated_at: x.updated_at, count: x.total?.schemes }), setMf);
    void get<{ updated_at: string | null; files: unknown[] }>("/tax", (x) => ({ updated_at: x.updated_at, count: x.files?.length }), setTax);
    return () => { live = false; };
  }, []);
  const note = (v: Held | null | undefined, what: string) => v === undefined ? "Checking…" : v === null ? "" : v.updated_at ? `${what} · updated ${ago(v.updated_at)}` : "Nothing uploaded yet";
  return (
    <Card id="accounts" label="Connected accounts">
      <CardHead title="Connected accounts" info="StratLab does not log in to your broker. Your holdings, funds and trades come from files you upload (or numbers you type), and each one shows when it last changed." />
      <div className="k-linkcards">
        <LinkCard to="/holdings" title="My Holdings" note={note(h, noun(h?.count, "stock", "stocks"))}>
          {h?.source ? `From ${h.source === "Manual" ? "your own entries" : h.source === "CSV" ? "a CSV file" : `your ${h.source} file`}. Import a broker file or type them in.` : "Import a broker file or type your shares in."}
        </LinkCard>
        <LinkCard to="/money/mutual-funds" title="Mutual funds statement" note={note(mf, noun(mf?.count, "scheme", "schemes"))}>Upload your Consolidated Account Statement (PDF or CSV).</LinkCard>
        <LinkCard to="/tax-report" title="Broker tradebooks" note={note(tax, noun(tax?.count, "file", "files"))}>Upload tradebooks and tax P&amp;L files from any broker for your capital gains.</LinkCard>
      </div>
      <Notice label="No broker login">StratLab does not log in to a broker, so nothing here refreshes by itself: upload a newer file to bring a page up to date.</Notice>
    </Card>
  );
}

function ConnectionCheck() {
  const { me, fail } = useApp();
  const [checks, setChecks] = useState<Row[] | null>(null);
  const [checking, setChecking] = useState(false);
  if (!me) return null;
  const u = me.usage;

  const run = async () => {
    setChecking(true);
    const rows: Row[] = [];
    const add = (r: Row) => { rows.push(r); setChecks([...rows]); };
    try {
      const { data } = await supabase.auth.getSession();
      add({ t: "Signed in", s: data.session ? "pass" : "fail", d: data.session?.user.email || "Not signed in. Sign out and in again." });
      let health: { data_online: boolean; ai_configured: boolean } | null = null;
      try { health = await (await fetch(CFG.API_BASE + "/health")).json(); add({ t: "StratLab server", s: "pass", d: CFG.API_BASE.replace("https://", "") }); }
      catch { add({ t: "StratLab server", s: "fail", d: me.is_admin ? "Can't reach the server. Check the Railway service is running and FRONTEND_ORIGIN lists this site." : "Can't reach the server. Check your connection and try again in a minute." }); return; }
      const markets = await api<{ name: string; status: string }[]>("/markets");
      for (const m of markets.filter((x) => x.status !== "soon")) {
        add({ t: /data$/i.test(m.name) ? m.name : `${m.name} data`, s: m.status === "live" ? "pass" : "warn", d: m.status === "live" ? "Online" : "Offline right now" });
      }
      if (!health?.ai_configured) add({ t: "AI strategy builder", s: me.is_admin ? "fail" : "warn",
        d: me.is_admin ? "No AI key on the server, so the simple converter is used. Add a free GROQ_API_KEY (console.groq.com) in Railway → Variables, then redeploy."
          : "Using the simple converter right now. Describing ideas still works." });
      else if (!me.is_admin) add({ t: "AI strategy builder", s: "pass", d: "Online" });
      else {
        // only the owner tests every provider: each test spends the shared free AI allowance
        add({ t: "AI strategy builder", s: "warn", d: "Testing each provider…" });
        try {
          const r = await api<{ providers: { label: string; ok: boolean; quota?: boolean; error: string | null; model: string | null; ms: number }[] }>("/admin/ai/test", { method: "POST" });
          rows.pop();
          const working = r.providers.filter((p) => p.ok).length;
          add({ t: "AI strategy builder", s: working ? "pass" : "fail",
            d: working ? `${working} of ${r.providers.length} providers working` : "No provider answered, so the simple converter is used. See the reasons below." });
          for (const p of r.providers) {
            add({ t: `AI: ${p.label}`, s: p.ok ? "pass" : p.quota ? "warn" : "fail",
              d: p.ok ? `Working${p.model ? ` with ${p.model}` : ""}, answered in ${(p.ms / 1000).toFixed(1)}s` : p.error || "Failed" });
          }
        } catch (e) {
          rows.pop();
          add({ t: "AI strategy builder", s: "warn", d: `Couldn't run the AI test: ${(e as Error).message}` });
        }
      }
      add({ t: "Your account", s: "pass", d: `${me.plan_info.name} plan, ${u.backtests_used} experiments this month` });
    } catch (e) { fail(e); } finally { setChecking(false); }
  };

  return (
    <Card id="check" label="Connection check">
      <CardHead title="Connection check" info={HELP.connection}
        actions={<button type="button" className="btn quiet sm" disabled={checking} onClick={() => void run()}>{checking ? "Checking…" : "Run check"}</button>} />
      {!checks && <p className="k-small k-muted k-hint-line">If something isn't loading: checks your sign-in, the server, each market's data and the AI builder.</p>}
      {checks?.map((r) => (
        <div key={r.t} className="k-line-row">
          <span className="k-line-text"><b>{r.t}</b><span className="k-sub-line">{r.d}</span></span>
          <Badge tone={TONE[r.s]}>{WORD[r.s]}</Badge>
        </div>
      ))}
    </Card>
  );
}
