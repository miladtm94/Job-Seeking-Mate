import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchApplicationStats, fetchCandidates, fetchHealth, fetchJATSApplications } from "../../api/client";
import type { CandidateProfile } from "../../api/client";

export function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const stats = useQuery({ queryKey: ["app-stats"], queryFn: () => fetchApplicationStats() });
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const jatsApps = useQuery({
    queryKey: ["jats-applications"],
    queryFn: () => fetchJATSApplications(),
    staleTime: 60_000,
  });

  const profile: CandidateProfile | undefined = candidates.data?.at(-1);

  const today = new Date().toISOString().slice(0, 10);
  const allApps = jatsApps.data?.applications ?? [];
  const overdueFollowups = allApps.filter(
    (a) => a.follow_up_date && a.follow_up_date <= today && ["applied", "interview", "saved"].includes(a.status)
  );
  const upcomingFollowups = allApps.filter((a) => {
    if (!a.follow_up_date || a.follow_up_date <= today) return false;
    const due = new Date(a.follow_up_date).getTime();
    return due <= Date.now() + 7 * 24 * 60 * 60 * 1000;
  });

  return (
    <div className="page">
      <h2>Dashboard</h2>
      <p className="muted">System overview and key metrics</p>

      <div className="grid">
        {/* System Status */}
        <section className="panel">
          <h3>System Status</h3>
          <div className="status-row">
            <span>API</span>
            <strong className={health.data?.status === "ok" ? "text-green" : "text-red"}>
              {health.data?.status ?? (health.isLoading ? "checking..." : "offline")}
            </strong>
          </div>
          <div className="status-row">
            <span>Service</span>
            <strong>{health.data?.service ?? "n/a"}</strong>
          </div>
        </section>

        {/* Profile Summary */}
        <section className="panel">
          <h3>Your Profile</h3>
          {profile ? (
            <>
              <div className="status-row">
                <span>Name</span>
                <strong>{profile.name}</strong>
              </div>
              <div className="status-row">
                <span>Seniority</span>
                <strong className="capitalize">{profile.seniority}</strong>
              </div>
              <div className="status-row">
                <span>Skills</span>
                <strong>{profile.skills.length}</strong>
              </div>
              <div className="status-row">
                <span>Experience</span>
                <strong>{profile.years_experience} years</strong>
              </div>
            </>
          ) : (
            <p className="muted">
              No profile yet.{" "}
              <a href="/profile" className="link">
                Create one
              </a>
            </p>
          )}
        </section>

        {/* JATS Tracker Stats */}
        <section className="panel">
          <h3>Job Tracker</h3>
          {jatsApps.data ? (
            <>
              <div className="status-row">
                <span>Total Tracked</span>
                <strong>{jatsApps.data.total}</strong>
              </div>
              {(["applied", "interview", "offer", "saved"] as const).map((s) => {
                const count = allApps.filter((a) => a.status === s).length;
                return count > 0 ? (
                  <div className="status-row" key={s}>
                    <span className="capitalize">{s}</span>
                    <strong>{count}</strong>
                  </div>
                ) : null;
              })}
              <div style={{ marginTop: 10 }}>
                <Link to="/log-application" className="btn btn-accent" style={{ fontSize: "0.82rem", padding: "6px 12px" }}>
                  + Log Application
                </Link>
              </div>
            </>
          ) : (
            <p className="muted">
              No applications tracked.{" "}
              <Link to="/log-application" className="link">Start now</Link>
            </p>
          )}
        </section>

        {/* Application Stats */}
        <section className="panel">
          <h3>Application Metrics</h3>
          {stats.data ? (
            <>
              <div className="status-row">
                <span>Total Applications</span>
                <strong>{stats.data.total}</strong>
              </div>
              <div className="status-row">
                <span>Interview Rate</span>
                <strong>{stats.data.interview_rate}%</strong>
              </div>
              <div className="status-row">
                <span>Offers</span>
                <strong className="text-green">{stats.data.offers}</strong>
              </div>
              {Object.entries(stats.data.by_status).map(([status, count]) => (
                <div className="status-row" key={status}>
                  <span className="capitalize">{status}</span>
                  <strong>{count}</strong>
                </div>
              ))}
            </>
          ) : (
            <p className="muted">No applications tracked yet</p>
          )}
        </section>
      </div>

      {/* Quick Actions */}
      <section className="panel" style={{ marginTop: 16 }}>
        <h3>Quick Actions</h3>
        <div className="button-row">
          <a href="/profile" className="btn">
            Setup Profile
          </a>
          <a href="/jobs" className="btn btn-secondary">
            Search Jobs
          </a>
          <a href="/pipeline" className="btn btn-accent">
            Run Full Pipeline
          </a>
        </div>
      </section>

      {/* Follow-up Reminders */}
      {(overdueFollowups.length > 0 || upcomingFollowups.length > 0) && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h3>
            Follow-up Reminders
            {overdueFollowups.length > 0 && (
              <span style={{
                marginLeft: 10, padding: "2px 8px", borderRadius: 12,
                background: "var(--red)", color: "#fff", fontSize: "0.75rem", fontWeight: 700,
              }}>
                {overdueFollowups.length} overdue
              </span>
            )}
          </h3>

          {overdueFollowups.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <p style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--red)", marginBottom: 6 }}>Overdue</p>
              {overdueFollowups.map((app) => (
                <Link
                  key={app.id}
                  to="/my-applications"
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "8px 12px", borderRadius: 7, marginBottom: 4,
                    background: "#fff5f5", border: "1px solid #fecaca", textDecoration: "none",
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--ink)" }}>{app.role_title}</span>
                    <span className="muted" style={{ fontSize: "0.8rem" }}> · {app.company}</span>
                  </div>
                  <span style={{ fontSize: "0.78rem", color: "var(--red)" }}>Due {app.follow_up_date}</span>
                </Link>
              ))}
            </div>
          )}

          {upcomingFollowups.length > 0 && (
            <div>
              <p style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--muted)", marginBottom: 6 }}>This week</p>
              {upcomingFollowups.map((app) => (
                <Link
                  key={app.id}
                  to="/my-applications"
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "8px 12px", borderRadius: 7, marginBottom: 4,
                    background: "#f8faff", border: "1px solid var(--border)", textDecoration: "none",
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--ink)" }}>{app.role_title}</span>
                    <span className="muted" style={{ fontSize: "0.8rem" }}> · {app.company}</span>
                  </div>
                  <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Due {app.follow_up_date}</span>
                </Link>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
