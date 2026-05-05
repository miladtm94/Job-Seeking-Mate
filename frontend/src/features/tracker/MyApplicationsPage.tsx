import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  addJATSEvent,
  deleteJATSDocument,
  deleteJATSEvent,
  deleteJATSApplication,
  fetchJATSDocumentFile,
  fetchJATSApplication,
  fetchJATSApplications,
  uploadJATSDocument,
  updateJATSEvent,
  updateJATSApplication,
} from "../../api/client";
import type {
  JATSApplicationDetail,
  JATSDocument,
  JATSApplicationSummary,
  JATSEvent,
} from "../../api/client";

const PLATFORMS = ["LinkedIn", "Seek", "Indeed", "Glassdoor", "Direct", "Referral", "Other"];
const CURRENCIES = ["AUD", "USD", "GBP", "EUR", "CAD", "NZD", "SGD"];
const REMOTE_TYPES = ["remote", "hybrid", "onsite"];
const SENIORITY_LEVELS = ["junior", "mid", "senior", "staff", "principal"];
const EMPLOYMENT_TYPES = ["fulltime", "parttime", "contract", "casual"];
const STATUSES = ["applied", "saved", "interview", "offer", "rejected", "withdrawn"];
const DOCUMENT_ACCEPT = ".pdf,.txt,.doc,.docx";

interface EditDraft {
  company: string; role_title: string; platform: string;
  date_applied: string; status: string;
  location_city: string; location_country: string; remote_type: string;
  salary_min: string; salary_max: string; currency: string;
  industry: string; seniority: string; employment_type: string;
  notes: string; job_url: string;
  contact_name: string; contact_email: string;
  follow_up_date: string; fit_score: string;
  required_skills: string; preferred_skills: string;
}

interface EventDraft {
  event_type: string;
  event_date: string;
  notes: string;
}

function fitScoreColor(score: number) {
  if (score >= 81) return "#2e8b57";
  if (score >= 61) return "#2980b9";
  if (score >= 41) return "#d4a017";
  return "#c0392b";
}

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

const EVENT_TYPES = [
  "applied",
  "email_received",
  "phone_screen",
  "interview_scheduled",
  "interview_completed",
  "rejection",
  "offer",
  "withdrawn",
  "other",
];

function salaryDisplay(app: JATSApplicationSummary) {
  if (!app.salary_min && !app.salary_max) return null;
  const parts: string[] = [];
  if (app.salary_min) parts.push(`${app.currency} ${(app.salary_min / 1000).toFixed(0)}k`);
  if (app.salary_max) parts.push(`${(app.salary_max / 1000).toFixed(0)}k`);
  return parts.join("–");
}

function formatEventType(eventType: string) {
  return eventType.replace(/_/g, " ");
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function documentLabel(category: JATSDocument["category"]) {
  if (category === "cover_letter") return "Cover letter";
  if (category === "resume") return "Resume";
  return "Other";
}

function canPreviewDocument(mimeType: string | null, filename: string) {
  if (mimeType === "application/pdf") return true;
  if (mimeType?.startsWith("text/")) return true;
  if (mimeType?.startsWith("image/")) return true;

  const lower = filename.toLowerCase();
  return lower.endsWith(".pdf") || lower.endsWith(".txt") || lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".gif");
}

function triggerBrowserDownload(url: string, filename: string) {
  const link = window.document.createElement("a");
  link.href = url;
  link.download = filename;
  window.document.body.appendChild(link);
  link.click();
  link.remove();
}

function EventEditor({
  draft,
  onChange,
  onSave,
  onCancel,
  isPending,
  submitLabel,
}: {
  draft: EventDraft;
  onChange: (key: keyof EventDraft, value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  isPending: boolean;
  submitLabel: string;
}) {
  return (
    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <select
          value={draft.event_type}
          onChange={(e) => onChange("event_type", e.target.value)}
          style={{ flex: 1, padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", fontSize: "0.85rem" }}
        >
          {EVENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {formatEventType(type)}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={draft.event_date}
          onChange={(e) => onChange("event_date", e.target.value)}
          style={{ padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", fontSize: "0.85rem" }}
        />
      </div>
      <input
        value={draft.notes}
        onChange={(e) => onChange("notes", e.target.value)}
        placeholder="Notes (optional)"
        style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)", fontSize: "0.85rem" }}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <button
          className="btn-small"
          style={{ background: "var(--accent)", color: "#fff", borderColor: "var(--accent)" }}
          onClick={onSave}
          disabled={isPending}
        >
          {isPending ? "Saving..." : submitLabel}
        </button>
        <button className="btn-small" onClick={onCancel} disabled={isPending}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function EventTimeline({
  events,
  editingEventId,
  eventDraft,
  onStartEdit,
  onChangeDraft,
  onSaveEdit,
  onCancelEdit,
  onDelete,
  isSaving,
  isDeleting,
}: {
  events: JATSEvent[];
  editingEventId: number | null;
  eventDraft: EventDraft | null;
  onStartEdit: (event: JATSEvent) => void;
  onChangeDraft: (key: keyof EventDraft, value: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDelete: (event: JATSEvent) => void;
  isSaving: boolean;
  isDeleting: boolean;
}) {
  if (!events.length) return <p className="muted" style={{ fontSize: "0.85rem" }}>No events yet</p>;
  return (
    <div className="event-timeline">
      {events.map((e) => (
        <div key={e.id} className="event-row">
          <div className="event-dot" />
          <div className="event-content">
            {editingEventId === e.id && eventDraft ? (
              <EventEditor
                draft={eventDraft}
                onChange={onChangeDraft}
                onSave={onSaveEdit}
                onCancel={onCancelEdit}
                isPending={isSaving}
                submitLabel="Update Event"
              />
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                    <span className="event-type capitalize">{formatEventType(e.event_type)}</span>
                    <span className="event-date muted">{e.event_date}</span>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn-small" onClick={() => onStartEdit(e)}>
                      Edit
                    </button>
                    <button
                      className="btn-small"
                      style={{ color: "var(--red)", borderColor: "var(--red)" }}
                      onClick={() => onDelete(e)}
                      disabled={isDeleting}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {e.notes && <p className="event-notes muted">{e.notes}</p>}
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function DocumentList({
  documents,
  onOpen,
  onDelete,
  openingDocumentId,
  isDeleting,
}: {
  documents: JATSDocument[];
  onOpen: (file: JATSDocument) => void;
  onDelete: (document: JATSDocument) => void;
  openingDocumentId: number | null;
  isDeleting: boolean;
}) {
  if (!documents.length) {
    return <p className="muted" style={{ fontSize: "0.85rem" }}>No documents attached yet.</p>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {documents.map((document) => (
        <div
          key={document.id}
          style={{
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "10px 12px",
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span className="tag tag-info">{documentLabel(document.category)}</span>
              <strong style={{ wordBreak: "break-word" }}>{document.filename}</strong>
            </div>
            <div className="muted" style={{ fontSize: "0.8rem", marginTop: 4 }}>
              {formatFileSize(document.file_size)}
              {document.mime_type ? ` • ${document.mime_type}` : ""}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              className="btn-small"
              onClick={() => onOpen(document)}
              disabled={openingDocumentId === document.id}
            >
              {openingDocumentId === document.id
                ? "Opening..."
                : canPreviewDocument(document.mime_type, document.filename) ? "Open" : "Download"}
            </button>
            <button
              className="btn-small"
              style={{ color: "var(--red)", borderColor: "var(--red)" }}
              onClick={() => onDelete(document)}
              disabled={isDeleting}
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export function MyApplicationsPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  const [statusFilter, setStatusFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Open a specific application when arriving from a deep link (e.g. dashboard follow-up)
  useEffect(() => {
    const idFromUrl = searchParams.get("id");
    if (idFromUrl) setSelectedId(idFromUrl);
  }, [searchParams]);
  const [isEditing, setIsEditing] = useState(false);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [addingEvent, setAddingEvent] = useState(false);
  const [eventDraft, setEventDraft] = useState<EventDraft>({
    event_type: "interview_scheduled",
    event_date: new Date().toISOString().slice(0, 10),
    notes: "",
  });
  const [editingEventId, setEditingEventId] = useState<number | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [openingDocumentId, setOpeningDocumentId] = useState<number | null>(null);

  const startEdit = (d: typeof detail) => {
    if (!d) return;
    setEditDraft({
      company: d.company,
      role_title: d.role_title,
      platform: d.platform,
      date_applied: d.date_applied,
      status: d.status,
      location_city: d.location_city ?? "",
      location_country: d.location_country ?? "",
      remote_type: d.remote_type ?? "",
      salary_min: d.salary_min ? String(d.salary_min) : "",
      salary_max: d.salary_max ? String(d.salary_max) : "",
      currency: d.currency,
      industry: d.industry ?? "",
      seniority: d.seniority ?? "",
      employment_type: d.employment_type ?? "",
      notes: d.notes,
      job_url: d.job_url ?? "",
      contact_name: d.contact_name ?? "",
      contact_email: d.contact_email ?? "",
      follow_up_date: d.follow_up_date ?? "",
      fit_score: d.fit_score != null ? String(d.fit_score) : "",
      required_skills: d.skills.filter((s) => s.skill_type === "required").map((s) => s.skill_name).join(", "),
      preferred_skills: d.skills.filter((s) => s.skill_type === "preferred").map((s) => s.skill_name).join(", "),
    });
    setIsEditing(true);
  };

  const set = (key: keyof EditDraft) => (e: { target: { value: string } }) =>
    setEditDraft((d) => d ? { ...d, [key]: e.target.value } : d);

  const setEventField = (key: keyof EventDraft, value: string) =>
    setEventDraft((draft) => ({ ...draft, [key]: value }));

  const resetEventDraft = () =>
    setEventDraft({
      event_type: "interview_scheduled",
      event_date: new Date().toISOString().slice(0, 10),
      notes: "",
    });

  const refreshTrackerQueries = () => {
    queryClient.invalidateQueries({ queryKey: ["jats-applications"] });
    if (selectedId) {
      queryClient.invalidateQueries({ queryKey: ["jats-application", selectedId] });
    }
    queryClient.invalidateQueries({ queryKey: ["analytics"] });
  };

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
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      updateJATSApplication(id, data),
    onSuccess: refreshTrackerQueries,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteJATSApplication(id),
    onSuccess: () => {
      refreshTrackerQueries();
      setSelectedId(null);
    },
  });

  const addEventMutation = useMutation({
    mutationFn: () =>
      addJATSEvent(selectedId!, {
        event_type: eventDraft.event_type,
        event_date: eventDraft.event_date,
        notes: eventDraft.notes,
      }),
    onSuccess: () => {
      refreshTrackerQueries();
      setAddingEvent(false);
      resetEventDraft();
    },
  });

  const updateEventMutation = useMutation({
    mutationFn: () => {
      if (!selectedId || editingEventId == null) {
        return Promise.reject(new Error("No event selected"));
      }
      return updateJATSEvent(selectedId, editingEventId, eventDraft);
    },
    onSuccess: () => {
      refreshTrackerQueries();
      setEditingEventId(null);
      resetEventDraft();
    },
  });

  const deleteEventMutation = useMutation({
    mutationFn: ({ appId, eventId }: { appId: string; eventId: number }) =>
      deleteJATSEvent(appId, eventId),
    onSuccess: () => {
      refreshTrackerQueries();
      setEditingEventId(null);
      resetEventDraft();
    },
  });

  const editMutation = useMutation({
    mutationFn: () => {
      if (!detail || !editDraft) return Promise.reject(new Error("No data"));
      return updateJATSApplication(detail.id, {
        company: editDraft.company,
        role_title: editDraft.role_title,
        platform: editDraft.platform,
        date_applied: editDraft.date_applied,
        status: editDraft.status,
        location_city: editDraft.location_city || null,
        location_country: editDraft.location_country || null,
        remote_type: editDraft.remote_type || null,
        salary_min: editDraft.salary_min ? parseInt(editDraft.salary_min, 10) : null,
        salary_max: editDraft.salary_max ? parseInt(editDraft.salary_max, 10) : null,
        currency: editDraft.currency,
        industry: editDraft.industry.trim() || null,
        seniority: editDraft.seniority || null,
        employment_type: editDraft.employment_type || null,
        notes: editDraft.notes,
        job_url: editDraft.job_url || null,
        contact_name: editDraft.contact_name || null,
        contact_email: editDraft.contact_email || null,
        follow_up_date: editDraft.follow_up_date || null,
        fit_score: editDraft.fit_score !== ""
          ? Math.min(100, Math.max(0, parseInt(editDraft.fit_score, 10)))
          : null,
        required_skills: editDraft.required_skills.split(",").map((s) => s.trim()).filter(Boolean),
        preferred_skills: editDraft.preferred_skills.split(",").map((s) => s.trim()).filter(Boolean),
      });
    },
    onSuccess: () => {
      refreshTrackerQueries();
      setIsEditing(false);
      setEditDraft(null);
    },
  });

  const uploadDocumentMutation = useMutation({
    mutationFn: ({ appId, category, file }: { appId: string; category: "resume" | "cover_letter" | "other"; file: File }) =>
      uploadJATSDocument(appId, { category, file }),
    onSuccess: () => {
      setDocumentError(null);
      refreshTrackerQueries();
    },
    onError: (error: Error) => {
      setDocumentError(error.message);
    },
  });

  const deleteDocumentMutation = useMutation({
    mutationFn: ({ appId, documentId }: { appId: string; documentId: number }) =>
      deleteJATSDocument(appId, documentId),
    onSuccess: () => {
      setDocumentError(null);
      refreshTrackerQueries();
    },
    onError: (error: Error) => {
      setDocumentError(error.message);
    },
  });

  const startEventEdit = (event: JATSEvent) => {
    setAddingEvent(false);
    setEditingEventId(event.id);
    setEventDraft({
      event_type: event.event_type,
      event_date: event.event_date,
      notes: event.notes,
    });
  };

  const cancelEventEdit = () => {
    setEditingEventId(null);
    resetEventDraft();
  };

  const handleDocumentSelection = async (
    category: "resume" | "cover_letter" | "other",
    files: FileList | null
  ) => {
    if (!selectedId || !files?.length) return;
    setDocumentError(null);
    for (const file of Array.from(files)) {
      try {
        await uploadDocumentMutation.mutateAsync({ appId: selectedId, category, file });
      } catch {
        // Error state is already handled by the mutation; continue with any remaining files.
      }
    }
  };

  const handleOpenDocument = async (file: JATSDocument) => {
    if (!selectedId) return;

    const shouldPreview = canPreviewDocument(file.mime_type, file.filename);
    const previewWindow = shouldPreview ? window.open("", "_blank") : null;

    setDocumentError(null);
    setOpeningDocumentId(file.id);

    try {
      const { blob, filename } = await fetchJATSDocumentFile(selectedId, file.id);
      const objectUrl = URL.createObjectURL(blob);
      const resolvedFilename = filename ?? file.filename;

      if (shouldPreview) {
        if (previewWindow) {
          previewWindow.location.href = objectUrl;
        } else {
          triggerBrowserDownload(objectUrl, resolvedFilename);
        }
      } else {
        triggerBrowserDownload(objectUrl, resolvedFilename);
      }

      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (error) {
      if (previewWindow && !previewWindow.closed) {
        previewWindow.close();
      }
      setDocumentError(error instanceof Error ? error.message : "Unable to open document.");
    } finally {
      setOpeningDocumentId(null);
    }
  };

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
                  onClick={() => {
                    setSelectedId(app.id);
                    setIsEditing(false);
                    setEditDraft(null);
                    setAddingEvent(false);
                    setEditingEventId(null);
                    setDocumentError(null);
                    resetEventDraft();
                  }}
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
                        {app.follow_up_date && app.follow_up_date <= new Date().toISOString().slice(0, 10) && (
                          <span className="tag tag-danger" style={{ fontSize: "0.72rem" }}>Follow up!</span>
                        )}
                        {app.fit_score != null && (
                          <span style={{
                            fontSize: "0.72rem", fontWeight: 700, padding: "1px 7px",
                            borderRadius: 10, background: fitScoreColor(app.fit_score) + "22",
                            color: fitScoreColor(app.fit_score), border: `1px solid ${fitScoreColor(app.fit_score)}44`,
                          }}>
                            Fit {app.fit_score}
                          </span>
                        )}
                        {app.document_count > 0 && (
                          <span className="tag tag-neutral">
                            {app.document_count} doc{app.document_count !== 1 ? "s" : ""}
                          </span>
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
            {selectedId && detail && isEditing && editDraft ? (
              /* ── Edit Form ── */
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                  <h3 style={{ margin: 0 }}>Edit Application</h3>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn-small"
                      style={{ background: "var(--accent)", color: "#fff", borderColor: "var(--accent)" }}
                      onClick={() => editMutation.mutate()}
                      disabled={editMutation.isPending}
                    >
                      {editMutation.isPending ? "Saving..." : "Save Changes"}
                    </button>
                    <button className="btn-small" onClick={() => { setIsEditing(false); setEditDraft(null); }}>
                      Cancel
                    </button>
                  </div>
                </div>

                {editMutation.isError && (
                  <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: 10 }}>
                    {(editMutation.error as Error).message}
                  </p>
                )}

                <div className="form" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {/* Core */}
                  <div className="form-row">
                    <label>Company *<input value={editDraft.company} onChange={set("company")} required /></label>
                    <label>Role Title *<input value={editDraft.role_title} onChange={set("role_title")} required /></label>
                  </div>
                  <div className="form-row">
                    <label>Platform
                      <select value={editDraft.platform} onChange={set("platform")}>
                        {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
                      </select>
                    </label>
                    <label>Date Applied<input type="date" value={editDraft.date_applied} onChange={set("date_applied")} /></label>
                    <label>Status
                      <select value={editDraft.status} onChange={set("status")}>
                        {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </label>
                  </div>

                  {/* Location */}
                  <div className="form-row">
                    <label>City<input value={editDraft.location_city} onChange={set("location_city")} placeholder="Sydney" /></label>
                    <label>Country<input value={editDraft.location_country} onChange={set("location_country")} placeholder="Australia" /></label>
                    <label>Work Type
                      <select value={editDraft.remote_type} onChange={set("remote_type")}>
                        <option value="">— Not specified</option>
                        {REMOTE_TYPES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </label>
                  </div>

                  {/* Salary */}
                  <div className="form-row">
                    <label>Salary Min<input type="number" value={editDraft.salary_min} onChange={set("salary_min")} placeholder="120000" /></label>
                    <label>Salary Max<input type="number" value={editDraft.salary_max} onChange={set("salary_max")} placeholder="160000" /></label>
                    <label>Currency
                      <select value={editDraft.currency} onChange={set("currency")}>
                        {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </label>
                  </div>

                  {/* Classification */}
                  <div className="form-row">
                    <label>Industry
                      <input value={editDraft.industry} onChange={set("industry")} placeholder="Government, Education, Climate Tech..." />
                    </label>
                    <label>Seniority
                      <select value={editDraft.seniority} onChange={set("seniority")}>
                        <option value="">— Not specified</option>
                        {SENIORITY_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                      </select>
                    </label>
                    <label>Employment Type
                      <select value={editDraft.employment_type} onChange={set("employment_type")}>
                        <option value="">— Not specified</option>
                        {EMPLOYMENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </label>
                  </div>

                  {/* Job URL */}
                  <label>Job Posting URL<input type="url" value={editDraft.job_url} onChange={set("job_url")} placeholder="https://..." /></label>

                  {/* Contact */}
                  <div className="form-row">
                    <label>Recruiter Name<input value={editDraft.contact_name} onChange={set("contact_name")} placeholder="Jane Smith" /></label>
                    <label>Contact Email<input type="email" value={editDraft.contact_email} onChange={set("contact_email")} placeholder="jane@..." /></label>
                  </div>
                  {/* Follow-up */}
                  <label>Follow-up Reminder<input type="date" value={editDraft.follow_up_date} onChange={set("follow_up_date")} /></label>

                  {/* Fit Score */}
                  <div>
                    <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>Fit to Role <span className="muted" style={{ fontWeight: 400 }}>(0–100)</span></span>
                      {editDraft.fit_score !== "" && (
                        <span style={{ fontWeight: 700, color: fitScoreColor(parseInt(editDraft.fit_score, 10)) }}>
                          {editDraft.fit_score}
                        </span>
                      )}
                    </label>
                    <input
                      type="range" min={0} max={100} step={1}
                      value={editDraft.fit_score === "" ? 50 : editDraft.fit_score}
                      onChange={(e) => setEditDraft((d) => d ? { ...d, fit_score: e.target.value } : d)}
                      onMouseDown={() => {
                        if (editDraft.fit_score === "")
                          setEditDraft((d) => d ? { ...d, fit_score: "50" } : d);
                      }}
                      style={{ width: "100%", marginTop: 4 }}
                    />
                  </div>

                  {/* Skills */}
                  <label>Required Skills <span className="muted">(comma-separated)</span>
                    <input value={editDraft.required_skills} onChange={set("required_skills")} placeholder="Python, React, AWS" />
                  </label>
                  <label>Preferred Skills <span className="muted">(comma-separated)</span>
                    <input value={editDraft.preferred_skills} onChange={set("preferred_skills")} placeholder="Kubernetes, GraphQL" />
                  </label>

                  {/* Notes */}
                  <label>Notes
                    <textarea value={editDraft.notes} onChange={set("notes")} rows={3} placeholder="Any notes..." />
                  </label>
                </div>
              </div>
            ) : selectedId && detail ? (
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
                    ["Follow-up", detail.follow_up_date && (
                      detail.follow_up_date <= new Date().toISOString().slice(0, 10)
                        ? `${detail.follow_up_date} ⚠ overdue`
                        : detail.follow_up_date
                    )],
                    ["Contact", detail.contact_name],
                  ]
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <div key={k as string} style={{ display: "flex", justifyContent: "space-between" }}>
                        <span className="muted">{k}</span>
                        <strong className="capitalize">{v as string}</strong>
                      </div>
                    ))}
                  {detail.fit_score != null && (
                    <div style={{ display: "flex", justifyContent: "space-between", gridColumn: "1/-1" }}>
                      <span className="muted">Fit to Role</span>
                      <strong style={{ color: fitScoreColor(detail.fit_score) }}>
                        {detail.fit_score} / 100
                      </strong>
                    </div>
                  )}
                </div>

                {/* Job URL */}
                {detail.job_url && (
                  <div style={{ marginBottom: 12, fontSize: "0.85rem" }}>
                    <a href={detail.job_url} target="_blank" rel="noopener noreferrer"
                      style={{ color: "var(--accent)", wordBreak: "break-all" }}>
                      View Job Posting ↗
                    </a>
                  </div>
                )}

                {/* Contact details */}
                {detail.contact_email && (
                  <div style={{ marginBottom: 12, fontSize: "0.85rem" }}>
                    <a href={`mailto:${detail.contact_email}`} style={{ color: "var(--accent)" }}>
                      {detail.contact_email}
                    </a>
                  </div>
                )}

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

                <div style={{ marginTop: 16 }}>
                  <h4>Documents</h4>
                  <DocumentList
                    documents={detail.documents}
                    onOpen={(file) => {
                      void handleOpenDocument(file);
                    }}
                    onDelete={(document) => {
                      if (confirm(`Delete ${document.filename}?`)) {
                        deleteDocumentMutation.mutate({ appId: detail.id, documentId: document.id });
                      }
                    }}
                    openingDocumentId={openingDocumentId}
                    isDeleting={deleteDocumentMutation.isPending}
                  />
                  {documentError && (
                    <p style={{ color: "var(--red)", fontSize: "0.85rem", marginTop: 8 }}>
                      {documentError}
                    </p>
                  )}
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
                    <label>
                      Replace Resume
                      <input
                        type="file"
                        accept={DOCUMENT_ACCEPT}
                        disabled={uploadDocumentMutation.isPending}
                        onChange={(e) => {
                          void handleDocumentSelection("resume", e.target.files).catch(() => {});
                          e.target.value = "";
                        }}
                      />
                    </label>
                    <label>
                      Replace Cover Letter
                      <input
                        type="file"
                        accept={DOCUMENT_ACCEPT}
                        disabled={uploadDocumentMutation.isPending}
                        onChange={(e) => {
                          void handleDocumentSelection("cover_letter", e.target.files).catch(() => {});
                          e.target.value = "";
                        }}
                      />
                    </label>
                    <label>
                      Add Supporting Documents
                      <input
                        type="file"
                        accept={DOCUMENT_ACCEPT}
                        multiple
                        disabled={uploadDocumentMutation.isPending}
                        onChange={(e) => {
                          void handleDocumentSelection("other", e.target.files).catch(() => {});
                          e.target.value = "";
                        }}
                      />
                    </label>
                  </div>
                </div>

                {/* Notes */}
                {detail.notes && (
                  <>
                    <h4>Notes</h4>
                    <p style={{ fontSize: "0.88rem", lineHeight: 1.6 }}>{detail.notes}</p>
                  </>
                )}

                {/* Timeline */}
                <h4 style={{ marginTop: 14 }}>Timeline</h4>
                <EventTimeline
                  events={detail.events}
                  editingEventId={editingEventId}
                  eventDraft={eventDraft}
                  onStartEdit={startEventEdit}
                  onChangeDraft={setEventField}
                  onSaveEdit={() => updateEventMutation.mutate()}
                  onCancelEdit={cancelEventEdit}
                  onDelete={(event) => {
                    if (confirm(`Delete the ${formatEventType(event.event_type)} event?`)) {
                      deleteEventMutation.mutate({ appId: detail.id, eventId: event.id });
                    }
                  }}
                  isSaving={updateEventMutation.isPending}
                  isDeleting={deleteEventMutation.isPending}
                />

                {/* Add event */}
                {!addingEvent ? (
                  <button
                    className="btn-small"
                    style={{ marginTop: 10 }}
                    onClick={() => {
                      cancelEventEdit();
                      setAddingEvent(true);
                    }}
                  >
                    + Add Event
                  </button>
                ) : (
                  <EventEditor
                    draft={eventDraft}
                    onChange={setEventField}
                    onSave={() => addEventMutation.mutate()}
                    onCancel={() => {
                      setAddingEvent(false);
                      resetEventDraft();
                    }}
                    isPending={addEventMutation.isPending}
                    submitLabel="Save Event"
                  />
                )}

                {/* Actions */}
                <div style={{ marginTop: 20, paddingTop: 14, borderTop: "1px solid var(--border)", display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    className="btn-small"
                    style={{ background: "var(--accent)", color: "#fff", borderColor: "var(--accent)" }}
                    onClick={() => startEdit(detail)}
                  >
                    Edit Application
                  </button>
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
