import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchApplications, fetchApplicationStats, updateApplicationStatus } from "../../api/client";

const STATUS_COLORS: Record<string, string> = {
  saved: "tag-neutral",
  prepared: "tag-info",
  applied: "tag-primary",
  interview: "tag-warning",
  offer: "tag-success",
  rejected: "tag-danger",
  withdrawn: "tag-neutral",
};

const NEXT_ACTIONS: Record<string, { label: string; status: string }[]> = {
  saved: [{ label: "Prepare", status: "prepared" }],
  prepared: [
    { label: "Mark Applied", status: "applied" },
    { label: "Back to Saved", status: "saved" },
  ],
  applied: [
    { label: "Got Interview", status: "interview" },
    { label: "Rejected", status: "rejected" },
  ],
  interview: [
    { label: "Got Offer!", status: "offer" },
    { label: "Rejected", status: "rejected" },
  ],
  offer: [{ label: "Withdraw", status: "withdrawn" }],
};

export function ApplicationsPage() {
  const queryClient = useQueryClient();
  const apps = useQuery({
    queryKey: ["applications"],
    queryFn: () => fetchApplications(),
  });
  const stats = useQuery({
    queryKey: ["app-stats"],
    queryFn: () => fetchApplicationStats(),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      updateApplicationStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["app-stats"] });
    },
  });

  const applications = apps.data?.applications ?? [];

  return (
    <div className="page">
      <h2>Application Tracker</h2>
      <p className="muted">Track your applications through the hiring pipeline</p>

      {/* Stats Bar */}
      {stats.data && (
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-value">{stats.data.total}</span>
            <span className="stat-label">Total</span>
          </div>
          <div className="stat">
            <span className="stat-value">{stats.data.interview_rate}%</span>
            <span className="stat-label">Interview Rate</span>
          </div>
          <div className="stat">
            <span className="stat-value text-green">{stats.data.offers}</span>
            <span className="stat-label">Offers</span>
          </div>
          {Object.entries(stats.data.by_status).map(([status, count]) => (
            <div className="stat" key={status}>
              <span className="stat-value">{count}</span>
              <span className="stat-label capitalize">{status}</span>
            </div>
          ))}
        </div>
      )}

      {/* Applications Table */}
      {applications.length > 0 ? (
        <section className="panel">
          <table className="app-table">
            <thead>
              <tr>
                <th>Role</th>
                <th>Company</th>
                <th>Score</th>
                <th>Status</th>
                <th>Mode</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((app) => (
                <tr key={app.application_id}>
                  <td>
                    <strong>{app.role}</strong>
                  </td>
                  <td>{app.company}</td>
                  <td>
                    <span className={`score score-${scoreClass(app.match_score)}`}>
                      {app.match_score}
                    </span>
                  </td>
                  <td>
                    <span className={`tag ${STATUS_COLORS[app.status] ?? ""}`}>{app.status}</span>
                  </td>
                  <td className="capitalize">{app.mode}</td>
                  <td>{new Date(app.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="action-buttons">
                      {(NEXT_ACTIONS[app.status] ?? []).map((action) => (
                        <button
                          key={action.status}
                          className="btn-small"
                          onClick={() =>
                            statusMutation.mutate({
                              id: app.application_id,
                              status: action.status,
                            })
                          }
                          disabled={statusMutation.isPending}
                        >
                          {action.label}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : (
        <section className="panel">
          <p className="muted">
            No applications yet. Search for jobs and generate applications to get started.
          </p>
        </section>
      )}
    </div>
  );
}

function scoreClass(score: number): string {
  if (score >= 75) return "high";
  if (score >= 55) return "medium";
  return "low";
}
