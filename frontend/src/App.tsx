import { NavLink, Route, Routes } from "react-router-dom";

import { ApplicationsPage } from "./features/applications/ApplicationsPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { JobsPage } from "./features/jobs/JobsPage";
import { ProfilePage } from "./features/profile/ProfilePage";
import { PipelinePage } from "./features/pipeline/PipelinePage";
import { LogApplicationPage } from "./features/tracker/LogApplicationPage";
import { MyApplicationsPage } from "./features/tracker/MyApplicationsPage";
import { AnalyticsPage } from "./features/analytics/AnalyticsPage";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/profile", label: "Profile" },
  { to: "/jobs", label: "Job Search" },
  { to: "/log-application", label: "Log Application" },
  { to: "/my-applications", label: "My Applications" },
  { to: "/analytics", label: "Analytics" },
  { to: "/pipeline", label: "Pipeline" },
];

export function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <h1 className="logo">Job-Seeking Mate</h1>
        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/log-application" element={<LogApplicationPage />} />
          <Route path="/my-applications" element={<MyApplicationsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/pipeline" element={<PipelinePage />} />
        </Routes>
      </main>
    </div>
  );
}
