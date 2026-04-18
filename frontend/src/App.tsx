import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { LoginPage } from "./features/auth/LoginPage";
import { ApplicationsPage } from "./features/applications/ApplicationsPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { HuntPage } from "./features/hunt/HuntPage";
import { LogApplicationPage } from "./features/tracker/LogApplicationPage";
import { MyApplicationsPage } from "./features/tracker/MyApplicationsPage";
import { AnalyticsPage } from "./features/analytics/AnalyticsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { TailorPage } from "./features/tailor/TailorPage";
import { fetchSettings } from "./api/client";

const NAV_ITEMS = [
  { to: "/",                label: "Dashboard",       icon: "⌂" },
  { to: "/find-jobs",       label: "Job Hunting",     icon: "🎯" },
  { to: "/tailor",          label: "Job Fit & Cover Letter", icon: "✦" },
  { to: "/my-applications", label: "Applications",    icon: "📋" },
  { to: "/log-application", label: "Log Application", icon: "+" },
  { to: "/analytics",       label: "Analytics",       icon: "📊" },
  { to: "/settings",        label: "Settings",        icon: "⚙" },
];

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function Sidebar() {
  const { logout } = useAuth();
  const settingsQ = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
    staleTime: 60_000,
    retry: false,
  });
  const provider = settingsQ.data?.ai_provider ?? "—";
  const model = provider === "lmstudio"
    ? (settingsQ.data?.lmstudio_model ?? "")
    : (settingsQ.data?.ai_model ?? "");

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-logo">Job‑Seeking Mate</span>
        <span className="sidebar-tagline">AI Job Agent</span>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-ai-badge">
          <span className={`ai-dot${settingsQ.isError ? " offline" : ""}`} />
          <div style={{ minWidth: 0 }}>
            <span className="ai-badge-provider">{provider}</span>
            <span className="ai-badge-text">{model || "no model set"}</span>
          </div>
        </div>
        <button className="btn-signout" onClick={logout}>
          ← Sign out
        </button>
      </div>
    </aside>
  );
}

function AppShell() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-wrapper">
        <main className="main-content">
          <Routes>
            <Route path="/"                element={<DashboardPage />} />
            <Route path="/find-jobs"       element={<HuntPage />} />
            <Route path="/tailor"          element={<TailorPage />} />
            <Route path="/my-applications" element={<MyApplicationsPage />} />
            <Route path="/log-application" element={<LogApplicationPage />} />
            <Route path="/analytics"       element={<AnalyticsPage />} />
            <Route path="/settings"        element={<SettingsPage />} />
            <Route path="/applications"    element={<ApplicationsPage />} />
            {/* Legacy redirects */}
            <Route path="/quick-apply"  element={<Navigate to="/find-jobs" replace />} />
            <Route path="/auto-hunt"    element={<Navigate to="/find-jobs" replace />} />
            <Route path="/profile"      element={<Navigate to="/find-jobs" replace />} />
            <Route path="/jobs"         element={<Navigate to="/find-jobs" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        />
      </Routes>
    </AuthProvider>
  );
}
