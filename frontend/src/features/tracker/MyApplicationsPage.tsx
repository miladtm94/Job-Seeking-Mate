import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  addJATSEvent,
  deleteJATSApplication,
  fetchJATSApplication,
  fetchJATSApplications,
  updateJATSApplication,
} from "../../api/client";
import type { JATSApplicationDetail, JATSApplicationSummary } from "../../api/client";

const STATUS_COLORS: Record<string, string> = {
  saved: "tag-neutral",
  applied: "tag-primary",
  interview: "tag-warning",
  offer: "tag-success",
  rejected: "tag-danger",
  withdrawn: "tag-neutral",
};

const STATUS_TRANSITIONS: Record<string, { label: string; status: string }[]> = {
  saved: [{ label: "Mark Applied", status: "applied" }],
  applied: [
    { label: "Got Interview", status: "interview" },
    { label: "Rejected", status: "rejected" },
    { label: "Withdrawn", status: "withdrawn" },
  ],
  interview: [
    { label: "Got Offer!", status: "offer" },
    { label: "Rejected", status: "rejected" },
  ],
  offer: [{ label: "Withdrawn", status: "withdrawn" }],
};

function salaryDisplay(app: JATSApplicationSummary) {
  if (!app.salary_min && !app.salary_max) return null;
  const parts: string[] = [];
  if (app.salary_min) parts.push(`${app.currency} ${(app.salary_min / 1000).toFixed(0)}k`);
  if (app.salary_max) parts.push(`${(app.salary_max / 1000).toFixed(0)}k`);
  return parts.join("–");
}

function EventTimeline({ events }: { events: JATSApplicationDetail["events"] }) {
  if (!events.length) return <p className="muted" style={{ fontSize: "0.85rem" }}>No events yet</p>;
  return (
    <div className="event-timeline">
      {events.map((e) => (
        <div key={e.id} className="event-row">
          <div className="event-dot" />
          <div className="event-content">
            <span className="event-type capitalize">{e.event_type.replace("_", " ")}</span>
            <span className="event-date muted">{e.event_date}</span>
            {e.notes && <p className="event-notes muted">{e.notes}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function MyApplicationsPage() {
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [addingEvent, setAddingEvent] = useState(false);
  const [newEventType, setNewEventType] = useState("interview_scheduled");
  const [newEventDate, setNewEventDate] = useState(new Date().toISOString().slice(0, 10));
  const [newEventNote, setNewEventNote] = useState("");

  const appsQuery = useQuery({
    queryKey: ["jats-applications", statusFilter, platformFilter, search],
    queryFn: () =>
      fetchJATSApplications({
        status: statusFilter || undefined,
        platform: platformFilter || undefined,
        search: search || undefined,
      }),
  });

  const detailQuery = useQuery({
    queryKey: ["jats-application", selectedId],
    queryFn: () => (selectedId ? fetchJATSApplication(selectedId) : null),
    enabled: !!selectedId,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, string> }) =>
      updateJATSApplication(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jats-applications"] });
      queryClient.invalidateQueries({ queryKey: ["jats-application", selectedId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteJATSApplication(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jats-applications"] });
      setSelectedId(null);
    },
  });

  const addEventMutation = useMutation({
    mutationFn: () =>
      addJATSEvent(selectedId!, {
        event_type: newEventType,
        event_date: newEventDate,
        notes: newEventNote,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jats-application", selectedId] });
      setAddingEvent(false);
      setNewEventNote("");
    },
  });

  const apps = appsQuery.data?.applications ?? [];
  const total = appsQuery.data?.total ?? 0;
  const detail = detailQuery.data;

  // Unique platforms for filter dropdown
  const platforms = [...new Set(apps.map((a) => a.platform).filter(Boolean))];

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2>My Applications</h2>
          <p className="muted">
            {total} application{total !== 1 ? "s" : ""} tracked
          </p>
        </div>
        <Link to="/log-application" className="btn btn-accent">
          + Log Application
        </Link>
      </div>

      {/* Filters */}
      <section className="panel" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--muted)" }}>
            Search
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Company or role..."
              style={{ display: "block", marginTop: 4, padding: "7px 10px", border: "1px solid var(--border)", borderRadius: 7, fontSize: "0.88rem", minWidth: 200 }}
            />
          </label>
          <label style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--muted)" }}>
            Status
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ display: "block", marginTop: 4, padding: "7px 10px", border: "1px solid var(--border)", borderRadius: 7, fontSize: "0.88rem" }}
            >
              <option value="">All Statuses</option>
              {["applied", "interview", "offer", "rejected", "saved", "withdrawn"].map((s) => (
                <option key={s} value={s} className="capitalize">{s}</option>
              ))}
            </select>
          </label>
          {platforms.length > 0 && (
            <label style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--muted)" }}>
              Platform
              <select
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value)}
                style={{ display: "block", marginTop: 4, padding: "7px 10px", border: "1px solid var(--border)", borderRadius: 7, fontSize: "0.88rem" }}
              >
                <option value="">All Platforms</option>
                {platforms.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          )}
          {(statusFilter || platformFilter || search) && (
            <button
              className="btn-small"
              onClick={() => { setStatusFilter(""); setPlatformFilter(""); setSearch(""); }}
              style={{ alignSelf: "flex-end", marginBottom: 1 }}
            >
              Clear filters
            </button>
          )}
        </div>
      </section>

      {appsQuery.isLoading && (
        <div className="panel" style={{ marginTop: 12, textAlign: "center", padding: 32 }}>
          <span className="spinner" style={{ display: "inline-block" }} />
        </div>
      )}

      {!appsQuery.isLoading && apps.length === 0 && (
        <section className="panel" style={{ marginTop: 12, textAlign: "center", padding: "40px 24px" }}>
          <p className="muted" style={{ marginBottom: 16 }}>
            {statusFilter || platformFilter || search
              ? "No applications match your filters."
              : "No applications logged yet."}
          </p>
          <Link to="/log-application" className="btn btn-accent">
            Log Your First Application
          </Link>
        </section>
      )}

      {apps.length > 0 && (
        <div className="grid two-col" style={{ marginTop: 12, alignItems: "start" }}>
          {/* Application list */}
          <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ overflowY: "auto", maxHeight: 640 }}>
              {apps.map((app) => (
                <div
                  key={app.id}
                  onClick={() => setSelectedId(app.id)}
                  style={{
                    padding: "14px 16px",
                    borderBottom: "1px solid var(--border)",
                    cursor: "pointer",
                    background: selectedId === app.id ? "rgba(203,95,54,0.06)" : "transparent",
                    transition: "background 120ms",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: "0.92rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {app.role_title}
                      </div>
                      <div className="muted" style={{ fontSize: "0.82rem", marginTop: 2 }}>
                        {app.company}
                        {app.platform && <span> · {app.platform}</span>}
                        {app.date_applied && <span> · {app.date_applied}</span>}
                      </div>
                      <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <span className={`tag ${STATUS_COLORS[app.status] ?? "tag-neutral"}`}>
                          {app.status}
                        </span>
                        {app.remote_type && (
                          <span className="tag tag-info capitalize">{app.remote_type}</span>
                        )}
                        {salaryDisplay(app) && (
                          <span className="tag tag-skill">{salaryDisplay(app)}</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Detail panel */}
          <section className="panel">
            {selectedId && detail ? (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <h3 style={{ marginBottom: 2 }}>{detail.role_title}</h3>
                    <p className="muted">{detail.company}</p>
                  </div>
                  <span className={`tag ${STATUS_COLORS[detail.status] ?? ""}`}>
                    {detail.status}
                  </span>
                </div>

                {/* Meta */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", margin: "14px 0", fontSize: "0.85rem" }}>
                  {[
                    ["Platform", detail.platform],
                    ["Applied", detail.date_applied],
                    ["Location", [detail.location_city, detail.location_country].filter(Boolean).join(", ")],
                    ["Work Type", detail.remote_type],
                    ["Industry", detail.industry],
                    ["Seniority", detail.seniority],
                    ["Employment", detail.employment_type],
                    ["Salary", salaryDisplay(detail)],
                  ]
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <div key={k as string} style={{ display: "flex", justifyContent: "space-between" }}>
                        <span className="muted">{k}</span>
                        <strong className="capitalize">{v}</strong>
                      </div>
                    ))}
                </div>

                {/* Status transitions */}
                {(STATUS_TRANSITIONS[detail.status] ?? []).length > 0 && (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
                    {STATUS_TRANSITIONS[detail.status].map((t) => (
                      <button
                        key={t.status}
                        className="btn-small"
                        style={{ background: t.status === "offer" ? "var(--green)" : undefined, color: t.status === "offer" ? "#fff" : undefined }}
                        onClick={() => updateMutation.mutate({ id: detail.id, data: { status: t.status } })}
                        disabled={updateMutation.isPending}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Skills */}
                {detail.skills.length > 0 && (
                  <>
                    <h4>Skills Required</h4>
                    <div className="tag-list">
                      {detail.skills.filter((s) => s.skill_type === "required").map((s) => (
                        <span key={s.skill_name} className="tag tag-skill" style={{ fontSize: "0.75rem" }}>{s.skill_name}</span>
                      ))}
                      {detail.skills.filter((s) => s.skill_type === "preferred").map((s) => (
                        <span key={s.skill_name} className="tag" style={{ fontSize: "0.75rem" }}>{s.skill_name}</span>
                      ))}
                    </div>
                  </>
                )}

                {/* Resume */}
                {detail.resume_used && (
                  <div style={{ marginTop: 12, fontSize: "0.85rem" }}>
                    <span className="muted">Resume used: </span>
                    <strong>{detail.resume_used}</strong>
                  </div>
                )}

                {/* Notes */}
                {detail.notes && (
                  <>
                    <h4>Notes</h4>
                    <p style={{ fontSize: "0.88rem", lineHeight: 1.6 }}>{detail.notes}</p>
                  </>
                )}

                {/* Timeline */}
                <h4 style={{ marginTop: 14 }}>Timeline</h4>
                <EventTimeline events={detail.events} />

                {/* Add event */}
                {!addingEvent ? (
                  <button
                    className="btn-small"
                    style={{ marginTop: 10 }}
                    onClick={() => setAddingEvent(true)}
                  >
                    + Add Event
                  </button>
                ) : (
                  <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ display: "flex", gap: 8 }}>
                      <select
                        value={newEventType}
                        onChange={(e) => setNewEventType(e.target.value)}
                        style={{ flex: 1, padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", fontSize: "0.85rem" }}
                      >
                        {["applied", "email_received", "phone_screen", "interview_scheduled",
                          "interview_completed", "rejection", "offer", "withdrawn", "other"].map((t) => (
                          <option key={t} value={t}>{t.replace("_", " ")}</option>
                        ))}
                      </select>
                      <input
                        type="date"
                        value={newEventDate}
                        onChange={(e) => setNewEventDate(e.target.value)}
                        style={{ padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", fontSize: "0.85rem" }}
                      />
                    </div>
                    <input
                      value={newEventNote}
                      onChange={(e) => setNewEventNote(e.target.value)}
                      placeholder="Notes (optional)"
                      style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)", fontSize: "0.85rem" }}
                    />
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        className="btn-small"
                        style={{ background: "var(--accent)", color: "#fff", borderColor: "var(--accent)" }}
                        onClick={() => addEventMutation.mutate()}
                        disabled={addEventMutation.isPending}
                      >
                        Save Event
                      </button>
                      <button className="btn-small" onClick={() => setAddingEvent(false)}>Cancel</button>
                    </div>
                  </div>
                )}

                {/* Danger zone */}
                <div style={{ marginTop: 20, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
                  <button
                    className="btn-small"
                    style={{ color: "var(--red)", borderColor: "var(--red)" }}
                    onClick={() => {
                      if (confirm("Delete this application?")) {
                        deleteMutation.mutate(detail.id);
                      }
                    }}
                    disabled={deleteMutation.isPending}
                  >
                    Delete Application
                  </button>
                </div>
              </>
            ) : (
              <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)" }}>
                <p style={{ fontSize: "2rem", marginBottom: 8 }}>←</p>
                <p>Select an application to view details, update status, and track events</p>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
