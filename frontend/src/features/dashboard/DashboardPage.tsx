import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchApplicationStats, fetchCandidates } from "../../api/client";
import type { CandidateProfile } from "../../api/client";

export function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const stats = useQuery({ queryKey: ["app-stats"], queryFn: () => fetchApplicationStats() });
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });

  const profile: CandidateProfile | undefined = candidates.data?.at(-1);

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
    </div>
  );
}
