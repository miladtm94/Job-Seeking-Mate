import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  fetchApplicationStats,
  fetchCandidates,
  fetchHealth,
  fetchJATSApplications,
  fetchSettings,
} from "../../api/client";
import type { CandidateProfile } from "../../api/client";

function MetricCard({
  value,
  label,
  accent,
}: {
  value: string | number;
  label: string;
  accent?: string;
}) {
  return (
    <div className="stat-card">
      <span className="stat-card-value" style={accent ? { color: accent } : undefined}>
        {value}
      </span>
      <span className="stat-card-label">{label}</span>
    </div>
  );
}

export function DashboardPage() {
  const health     = useQuery({ queryKey: ["health"],         queryFn: fetchHealth,                    staleTime: 30_000 });
  const settings   = useQuery({ queryKey: ["settings"],       queryFn: fetchSettings,                  staleTime: 60_000, retry: false });
  const stats      = useQuery({ queryKey: ["app-stats"],      queryFn: () => fetchApplicationStats(),  staleTime: 60_000 });
  const candidates = useQuery({ queryKey: ["candidates"],     queryFn: fetchCandidates,                staleTime: 60_000 });
  const jatsApps   = useQuery({ queryKey: ["jats-applications"], queryFn: () => fetchJATSApplications(), staleTime: 60_000 });

  const profile: CandidateProfile | undefined = candidates.data?.at(-1);

  const today   = new Date().toISOString().slice(0, 10);
  const allApps = jatsApps.data?.applications ?? [];

  const overdueFollowups = allApps.filter(
    (a) => a.follow_up_date && a.follow_up_date <= today && ["applied", "interview", "saved"].includes(a.status)
  );
  const upcomingFollowups = allApps.filter((a) => {
    if (!a.follow_up_date || a.follow_up_date <= today) return false;
    return new Date(a.follow_up_date).getTime() <= Date.now() + 7 * 24 * 60 * 60 * 1000;
  });

  const applied   = allApps.filter((a) => a.status === "applied").length;
  const interview = allApps.filter((a) => a.status === "interview").length;
  const offers    = allApps.filter((a) => a.status === "offer").length;
  const saved     = allApps.filter((a) => a.status === "saved").length;

  const aiProvider = settings.data?.ai_provider ?? "—";
  const aiModel    = aiProvider === "lmstudio"
    ? (settings.data?.lmstudio_model ?? "")
    : (settings.data?.ai_model ?? "");
  const apiOk      = health.data?.status === "ok";

  return (
    <div className="page">
      <div className="page-header">
        <h2>Dashboard</h2>
        <p className="muted">Your AI-powered job hunt at a glance</p>
      </div>

      {/* ── Top metrics row ───────────────────────────────────────────── */}
      <div className="stat-cards" style={{ marginBottom: 20 }}>
        <MetricCard value={jatsApps.data?.total ?? 0} label="Total tracked" />
        <MetricCard value={applied}   label="Applied"   accent="var(--blue)" />
        <MetricCard value={interview} label="Interviews" accent="var(--yellow)" />
        <MetricCard value={offers}    label="Offers"     accent="var(--green)" />
        <MetricCard value={saved}     label="Saved"      accent="var(--muted)" />
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>

        {/* System Status */}
        <section className="panel">
          <h3>System Status</h3>

          <div className="status-row">
            <span>API</span>
            <span style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: "0.85rem" }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: apiOk ? "var(--green)" : "var(--red)",
                boxShadow: apiOk ? "0 0 6px var(--green)" : "none",
                display: "inline-block",
              }} />
              {health.isLoading ? "checking…" : (health.data?.status ?? "offline")}
            </span>
          </div>

          <div className="status-row">
            <span>AI Provider</span>
            <span style={{ fontWeight: 700, fontSize: "0.85rem", textTransform: "capitalize" }}>
              {aiProvider}
            </span>
          </div>

          <div className="status-row">
            <span>AI Model</span>
            <span style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--muted)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {aiModel || "—"}
            </span>
          </div>

          <div style={{ marginTop: 12 }}>
            <Link to="/settings" className="btn btn-small">Configure AI →</Link>
          </div>
        </section>

        {/* Resume / Profile */}
        <section className="panel">
          <h3>Your Profile</h3>
          {profile ? (
            <>
              <div className="status-row">
                <span>Name</span>
                <strong style={{ fontSize: "0.88rem" }}>{profile.name}</strong>
              </div>
              <div className="status-row">
                <span>Seniority</span>
                <strong style={{ fontSize: "0.88rem", textTransform: "capitalize" }}>{profile.seniority}</strong>
              </div>
              <div className="status-row">
                <span>Experience</span>
                <strong style={{ fontSize: "0.88rem" }}>{profile.years_experience}y</strong>
              </div>
              <div className="status-row">
                <span>Skills</span>
                <strong style={{ fontSize: "0.88rem" }}>{profile.skills.length}</strong>
              </div>
              <div style={{ marginTop: 10 }}>
                <div className="tag-list">
                  {profile.skills.slice(0, 6).map((s) => (
                    <span key={s} className="tag tag-skill">{s}</span>
                  ))}
                  {profile.skills.length > 6 && (
                    <span className="tag">+{profile.skills.length - 6}</span>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "24px 0" }}>
              <div style={{ fontSize: "2rem", marginBottom: 10 }}>📄</div>
              <p className="muted" style={{ marginBottom: 12 }}>No resume uploaded yet.</p>
              <Link to="/find-jobs" className="btn btn-accent" style={{ fontSize: "0.84rem" }}>
                Upload Resume
              </Link>
            </div>
          )}
        </section>

        {/* Quick actions */}
        <section className="panel">
          <h3>Quick Actions</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <Link to="/find-jobs" className="btn btn-accent" style={{ justifyContent: "center" }}>
              🎯 Start Job Hunting
            </Link>
            <Link to="/log-application" className="btn" style={{ justifyContent: "center" }}>
              + Log Application
            </Link>
            <Link to="/my-applications" className="btn" style={{ justifyContent: "center" }}>
              📋 View All Applications
            </Link>
            <Link to="/analytics" className="btn" style={{ justifyContent: "center" }}>
              📊 Analytics
            </Link>
          </div>
        </section>

        {/* Job pipeline */}
        {jatsApps.data && (
          <section className="panel">
            <h3>Application Pipeline</h3>
            {[
              { label: "Saved",      count: saved,     color: "var(--muted)", bar: "var(--dim)" },
              { label: "Applied",    count: applied,   color: "var(--blue)",  bar: "var(--blue)" },
              { label: "Interview",  count: interview, color: "var(--yellow)",bar: "var(--yellow)" },
              { label: "Offer",      count: offers,    color: "var(--green)", bar: "var(--green)" },
            ].map((row) => {
              const pct = jatsApps.data.total > 0 ? (row.count / jatsApps.data.total) * 100 : 0;
              return (
                <div key={row.label} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", marginBottom: 4 }}>
                    <span style={{ color: "var(--muted)" }}>{row.label}</span>
                    <span style={{ fontWeight: 700, color: row.color }}>{row.count}</span>
                  </div>
                  <div style={{ height: 5, background: "var(--bg-2)", borderRadius: 3 }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: row.bar, borderRadius: 3, transition: "width 400ms" }} />
                  </div>
                </div>
              );
            })}
          </section>
        )}
      </div>

      {/* ── Follow-up Reminders ────────────────────────────────────────── */}
      {(overdueFollowups.length > 0 || upcomingFollowups.length > 0) && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h3>
            Follow-up Reminders
            {overdueFollowups.length > 0 && (
              <span style={{
                marginLeft: 10, padding: "2px 8px", borderRadius: 999,
                background: "var(--tag-red-bg)", color: "var(--red)",
                border: "1px solid rgba(248,113,113,0.2)",
                fontSize: "0.72rem", fontWeight: 700,
              }}>
                {overdueFollowups.length} overdue
              </span>
            )}
          </h3>

          {overdueFollowups.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--red)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>Overdue</p>
              {overdueFollowups.map((app) => (
                <Link key={app.id} to={`/my-applications?id=${app.id}`} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "8px 12px", borderRadius: "var(--radius-sm)", marginBottom: 4,
                  background: "var(--tag-red-bg)", border: "1px solid rgba(248,113,113,0.15)",
                  textDecoration: "none",
                }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>{app.role_title}</span>
                    <span className="muted" style={{ fontSize: "0.8rem" }}> · {app.company}</span>
                  </div>
                  <span style={{ fontSize: "0.76rem", color: "var(--red)" }}>Due {app.follow_up_date}</span>
                </Link>
              ))}
            </div>
          )}

          {upcomingFollowups.length > 0 && (
            <div>
              <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>This week</p>
              {upcomingFollowups.map((app) => (
                <Link key={app.id} to={`/my-applications?id=${app.id}`} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "8px 12px", borderRadius: "var(--radius-sm)", marginBottom: 4,
                  background: "var(--bg-card)", border: "1px solid var(--border)",
                  textDecoration: "none",
                }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>{app.role_title}</span>
                    <span className="muted" style={{ fontSize: "0.8rem" }}> · {app.company}</span>
                  </div>
                  <span style={{ fontSize: "0.76rem", color: "var(--muted)" }}>Due {app.follow_up_date}</span>
                </Link>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── Stats from application service ────────────────────────────── */}
      {stats.data && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h3>Application Metrics</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12 }}>
            {[
              { label: "Total",          value: stats.data.total },
              { label: "Interview Rate", value: `${stats.data.interview_rate}%` },
              { label: "Offers",         value: stats.data.offers },
            ].map((m) => (
              <div key={m.label} style={{ textAlign: "center", padding: "14px 10px", background: "var(--bg-2)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: "1.5rem", fontWeight: 800, letterSpacing: "-0.03em" }}>{m.value}</div>
                <div style={{ fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginTop: 4 }}>{m.label}</div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
