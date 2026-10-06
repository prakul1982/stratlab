import { lazy, Suspense } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { useApp } from "../lib/app";
import { Card, PageHeader, Skeleton } from "../components/kit";
import { AdminData, SECTIONS, useAdmin } from "./admin/AdminContext";
import { attention } from "./admin/attention";
import { OverviewSection } from "./admin/OverviewSection";
import "./admin/admin.css";

const UsersSection = lazy(() => import("./admin/UsersSection").then((m) => ({ default: m.UsersSection })));
const MoneySection = lazy(() => import("./admin/MoneySection").then((m) => ({ default: m.MoneySection })));
const DataSection = lazy(() => import("./admin/DataSection").then((m) => ({ default: m.DataSection })));
const QualitySection = lazy(() => import("./admin/QualitySection").then((m) => ({ default: m.QualitySection })));
const SystemSection = lazy(() => import("./admin/SystemSection").then((m) => ({ default: m.SystemSection })));
const EmailSection = lazy(() => import("./admin/EmailSection").then((m) => ({ default: m.EmailSection })));

/** Old links: /admin?tab=services and the like open the section that took over from that tab. */
function OldTab() {
  const [params] = useSearchParams();
  const tab = params.get("tab") ?? "";
  const hit = SECTIONS.find((s) => s.tabs.includes(tab));
  return hit && hit.path ? <Navigate to={`/admin/${hit.path}`} replace /> : <OverviewSection />;
}

function Menu() {
  const { ov, reported, jobs } = useAdmin();
  const n = attention(ov, reported, jobs).length;
  return (
    <nav className="adm-menu" aria-label="Admin sections">
      {SECTIONS.map((s) => (
        <NavLink key={s.path} to={s.path ? `/admin/${s.path}` : "/admin"} end={s.path === ""} className="adm-link">
          {s.label}
          {s.path === "" && n > 0 && <span className="adm-count" aria-label={`${n} need attention`}>{n}</span>}
        </NavLink>
      ))}
    </nav>
  );
}

function Frame() {
  const { pathname } = useLocation();
  const { reload, loading } = useAdmin();
  const here = SECTIONS.find((s) => (s.path ? pathname === `/admin/${s.path}` || pathname.startsWith(`/admin/${s.path}/`) : pathname === "/admin" || pathname === "/admin/")) ?? SECTIONS[0];
  return (
    <div className="adm">
      <Menu />
      <div className="adm-main k-page">
        <PageHeader eyebrow={`Admin · ${here.label}`} title={here.title} lede={here.lede}
          actions={<button type="button" className="btn outline sm" disabled={loading} onClick={() => { reload(); }}>{loading ? "Refreshing…" : "Refresh"}</button>} />
        <Suspense fallback={<Card label="Loading"><Skeleton label={`Loading ${here.label}`} /></Card>}>
          <Routes>
            <Route index element={<OldTab />} />
            <Route path="users" element={<UsersSection />} />
            <Route path="money" element={<MoneySection />} />
            <Route path="data" element={<DataSection />} />
            <Route path="quality" element={<QualitySection />} />
            <Route path="system" element={<SystemSection />} />
            <Route path="emails" element={<EmailSection />} />
            <Route path="emails/:kind" element={<EmailSection />} />
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </Routes>
        </Suspense>
      </div>
    </div>
  );
}

/** Admin: its own area, with a left menu and a page per job (Overview, Users and growth, Money, Data and jobs, Quality,
 * System, Email previews) at /admin/... Only site owners get in. */
export function AdminPage() {
  const { me } = useApp();
  if (!me) return <div className="k-page"><PageHeader eyebrow="Admin" title="Admin" /><Card label="Opening admin"><Skeleton label="Opening admin" /></Card></div>;
  if (!me.is_admin) return <Navigate to="/" replace />;
  return <AdminData><Frame /></AdminData>;
}
