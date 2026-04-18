/**
 * Auto-Hunt — AI job search agent for LinkedIn, Seek.com.au, and Indeed.com.au.
 *
 * Human-in-the-loop design:
 *  • The browser is always visible — you watch every action in real time.
 *  • LinkedIn: enter/save credentials here; agent logs in automatically.
 *  • Seek / Indeed: browser opens login page and waits for YOU to sign in.
 *  • Every job is scored against YOUR resume before being shown to you.
 *  • You see the score, reasoning, and description before deciding to apply.
 *  • Cover letters are shown for review before being typed.
 *  • The agent always pauses before hitting Submit. No surprises.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchCandidates,
  fetchSearchPlan,
  getCredentialFull,
  saveCredential,
  deleteCredential,
} from "../../api/client";
import type { CandidateProfile } from "../../api/client";

const WS_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1")
  .replace(/^http/, "ws")
  .replace("/api/v1", "");

type Platform   = "linkedin" | "seek" | "indeed";
type AgentState = "idle" | "connecting" | "running" | "waiting_confirm" | "done" | "error";

interface AgentEvent {
  type: string;
  step?: string;
  message?: string;
  job_id?: string;
  title?: string;
  company?: string;
  score?: number;
  recommendation?: string;
  reason?: string;
  field?: string;
  label?: string;
  suggestion?: string;
  confidence?: number;
  data?: string;
  job?: JobDetail;
}

interface JobDetail {
  job_id: string;
  title: string;
  company: string;
  location: string;
  salary?: string;
  score: number;
  recommendation: string;
  url: string;
  description_excerpt?: string;
  missing_requirements?: string[];
  match_summary?: string;
}

interface FoundJob {
  job_id: string;
  title: string;
  company: string;
  location: string;
  easy_apply?: boolean;
  quick_apply?: boolean;
  score?: number;
  recommendation?: string;
  status: "found" | "scoring" | "applying" | "applied" | "skipped";
  skipReason?: string;
}

interface SearchPlan {
  queries: string[];
  location: string;
  max_jobs: number;
  min_score: number;
  date_range: number;
  salary_min?: number | null;
  work_type: string;
  target_roles?: string[];
}

// ── constants ──────────────────────────────────────────────────────────────────

const PLATFORM_META: Record<Platform, { label: string; icon: string; color: string; applyLabel: string }> = {
  linkedin: { label: "LinkedIn",      icon: "in", color: "#0a66c2", applyLabel: "Easy Apply" },
  seek:     { label: "Seek.com.au",   icon: "S",  color: "#e85d04", applyLabel: "Quick Apply" },
  indeed:   { label: "Indeed.com.au", icon: "I",  color: "#2164f3", applyLabel: "Easy Apply" },
};

const REC_COLOR: Record<string, string> = {
  strong_apply: "var(--green)",
  apply:        "var(--blue)",
  maybe:        "var(--yellow)",
  skip:         "var(--muted)",
};

const REC_LABEL: Record<string, string> = {
  strong_apply: "Strong Match",
  apply:        "Good Match",
  maybe:        "Possible",
  skip:         "Weak Match",
};

const STATUS_ICON: Record<string, { icon: string; color: string }> = {
  found:    { icon: "·",  color: "var(--muted)"  },
  scoring:  { icon: "⟳",  color: "var(--accent)" },
  applying: { icon: "⟳",  color: "var(--accent)" },
  applied:  { icon: "✓",  color: "var(--green)"  },
  skipped:  { icon: "—",  color: "var(--dim)"    },
};

// ── sub-components ─────────────────────────────────────────────────────────────

function ResumeSelect({ profiles, selectedId, onSelect }: {
  profiles: CandidateProfile[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  if (profiles.length === 0)
    return (
      <p className="muted" style={{ fontSize: "0.85rem" }}>
        Go to <strong>Job Hunting → Find Jobs</strong> and upload a resume first.
      </p>
    );
  return (
    <select
      value={selectedId}
      onChange={(e) => onSelect(e.target.value)}
      style={{ width: "100%" }}
    >
      {profiles.map((p) => (
        <option key={p.candidate_id} value={p.candidate_id}>
          {p.filename || p.name || p.candidate_id.slice(0, 8)} — {p.seniority}, {p.years_experience}y exp
        </option>
      ))}
    </select>
  );
}

function JobRow({ job }: { job: FoundJob }) {
  const s   = STATUS_ICON[job.status] ?? STATUS_ICON.found;
  const rec = job.recommendation ?? "";
  return (
    <div style={{
      display: "flex",
      alignItems: "flex-start",
      gap: 12,
      padding: "10px 16px",
      borderBottom: "1px solid var(--border)",
      opacity: job.status === "skipped" ? 0.45 : 1,
    }}>
      <span style={{ fontSize: "1rem", color: s.color, minWidth: 16, paddingTop: 2, flexShrink: 0 }}>
        {s.icon}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: "0.88rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {job.title}
        </div>
        <div className="muted" style={{ fontSize: "0.76rem" }}>
          {job.company}{job.location ? ` · ${job.location}` : ""}
        </div>
        {job.score !== undefined && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
            <div style={{ flex: 1, height: 3, background: "var(--bg-2)", borderRadius: 2 }}>
              <div style={{
                width: `${job.score}%`, height: "100%", borderRadius: 2,
                background: REC_COLOR[rec] ?? "var(--accent)",
                transition: "width 400ms",
              }} />
            </div>
            <span style={{ fontSize: "0.72rem", fontWeight: 800, color: REC_COLOR[rec] ?? "var(--accent)", minWidth: 24 }}>
              {job.score}
            </span>
            <span style={{ fontSize: "0.7rem", color: REC_COLOR[rec] ?? "var(--muted)" }}>
              {REC_LABEL[rec] ?? rec}
            </span>
          </div>
        )}
        {job.status === "applied" && (
          <span style={{ fontSize: "0.7rem", color: "var(--green)", fontWeight: 700 }}>Applied ✓</span>
        )}
        {job.status === "skipped" && job.skipReason && (
          <span style={{ fontSize: "0.7rem", color: "var(--dim)" }}>{job.skipReason}</span>
        )}
      </div>
    </div>
  );
}

/** Full-detail card shown when agent scores a job and asks: apply? */
function JobReviewCard({ event, onApply, onSkip, onStopAll }: {
  event: AgentEvent;
  onApply: () => void;
  onSkip: () => void;
  onStopAll: () => void;
}) {
  const job = event.job;
  if (!job) return null;

  const recColor = REC_COLOR[job.recommendation] ?? "var(--accent)";
  const recLabel = REC_LABEL[job.recommendation] ?? job.recommendation;

  return (
    <div style={{
      border: `2px solid ${recColor}`,
      borderRadius: "var(--radius-lg)",
      overflow: "hidden",
      background: "var(--bg-card)",
    }}>
      {/* Header */}
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ fontSize: "0.7rem", fontWeight: 800, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
          AI found a match — apply to this job?
        </div>
        <div style={{ fontWeight: 800, fontSize: "1.05rem", lineHeight: 1.2 }}>{job.title}</div>
        <div className="muted" style={{ fontSize: "0.86rem", marginTop: 3 }}>
          {job.company}{job.location ? ` · ${job.location}` : ""}{job.salary ? ` · ${job.salary}` : ""}
        </div>
      </div>

      {/* Score breakdown */}
      <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginBottom: 5, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Resume match score
          </div>
          <div style={{ height: 8, background: "var(--bg-2)", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ width: `${job.score}%`, height: "100%", background: recColor, borderRadius: 4, transition: "width 600ms" }} />
          </div>
          {job.match_summary && (
            <div style={{ fontSize: "0.76rem", color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
              {job.match_summary}
            </div>
          )}
        </div>
        <div style={{ textAlign: "center", flexShrink: 0 }}>
          <div style={{ fontWeight: 900, fontSize: "2rem", color: recColor, lineHeight: 1, letterSpacing: "-0.04em" }}>
            {job.score}
          </div>
          <div style={{ fontSize: "0.72rem", color: recColor, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 2 }}>
            {recLabel}
          </div>
        </div>
      </div>

      {/* Missing skills */}
      {job.missing_requirements && job.missing_requirements.length > 0 && (
        <div style={{ padding: "8px 18px", borderBottom: "1px solid var(--border)" }}>
          <span style={{ fontSize: "0.7rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Skill gaps: </span>
          <span className="tag-list" style={{ display: "inline-flex", gap: 4, marginLeft: 4 }}>
            {job.missing_requirements.slice(0, 5).map((s) => (
              <span key={s} className="tag tag-gap" style={{ fontSize: "0.7rem" }}>{s}</span>
            ))}
          </span>
        </div>
      )}

      {/* Description excerpt */}
      {job.description_excerpt && (
        <div style={{ padding: "10px 18px", borderBottom: "1px solid var(--border)", fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.6, maxHeight: 100, overflowY: "auto" }}>
          {job.description_excerpt}
        </div>
      )}

      {/* View posting link */}
      {job.url && (
        <div style={{ padding: "8px 18px", borderBottom: "1px solid var(--border)" }}>
          <a href={job.url} target="_blank" rel="noopener noreferrer"
            style={{ fontSize: "0.78rem", color: "var(--accent)", textDecoration: "none" }}>
            View full job posting ↗
          </a>
        </div>
      )}

      {/* Action buttons */}
      <div style={{ padding: "14px 18px", display: "flex", gap: 8 }}>
        <button
          className="btn btn-accent"
          style={{ flex: 2, fontWeight: 700, justifyContent: "center" }}
          onClick={onApply}
        >
          ✓ Apply to this job
        </button>
        <button className="btn" style={{ flex: 1, justifyContent: "center" }} onClick={onSkip}>
          Skip
        </button>
        <button
          className="btn"
          style={{ flex: 1, color: "var(--red)", borderColor: "var(--red)", justifyContent: "center" }}
          onClick={onStopAll}
        >
          Stop All
        </button>
      </div>
    </div>
  );
}

/** Visual search plan editor — shown instead of raw JSON textarea when field === "search_plan" */
function SearchPlanEditor({ suggestion, platform, onConfirm, onCancel }: {
  suggestion: string;
  platform: Platform;
  onConfirm: (plan: SearchPlan) => void;
  onCancel: () => void;
}) {
  const initial = useMemo<SearchPlan>(() => {
    try { return JSON.parse(suggestion) as SearchPlan; }
    catch { return { queries: [], location: "Australia", max_jobs: 20, min_score: 60, date_range: 7, work_type: "any" }; }
  }, [suggestion]);

  const [queries,  setQueries]  = useState<string[]>(initial.queries ?? []);
  const [newQuery, setNewQuery] = useState("");
  const [location, setLocation] = useState(initial.location ?? "Australia");
  const [maxJobs,  setMaxJobs]  = useState(initial.max_jobs ?? 20);
  const [minScore, setMinScore] = useState(initial.min_score ?? 60);
  const [dateRange,setDateRange]= useState(initial.date_range ?? 7);
  const [workType, setWorkType] = useState(initial.work_type ?? "any");
  const [salaryMin,setSalaryMin]= useState(initial.salary_min ? String(initial.salary_min) : "");

  const addQuery = () => {
    const q = newQuery.trim();
    if (q && !queries.includes(q)) setQueries((prev) => [...prev, q]);
    setNewQuery("");
  };

  const chipStyle: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", gap: 5,
    padding: "4px 10px", borderRadius: 999,
    background: "var(--bg-2)", border: "1px solid var(--border)",
    fontSize: "0.8rem", fontWeight: 500, color: "var(--ink)",
  };

  const removeChipBtn: React.CSSProperties = {
    background: "none", border: "none", cursor: "pointer",
    color: "var(--muted)", padding: 0, fontSize: "1rem", lineHeight: 1,
    display: "flex", alignItems: "center",
  };

  return (
    <div style={{ padding: "20px 22px" }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: "0.68rem", fontWeight: 800, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
          Review Search Plan
        </div>
        <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--muted)", lineHeight: 1.5 }}>
          These are the job-title phrases the agent will type into {PLATFORM_META[platform].label}'s search box.
          Edit, add, or remove queries — only proper job title phrases produce results.
        </p>
      </div>

      {/* Query chips */}
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: "0.73rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", display: "block", marginBottom: 8 }}>
          Search Queries
        </label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8, minHeight: 34 }}>
          {queries.length === 0 && (
            <span style={{ fontSize: "0.8rem", color: "var(--dim)", fontStyle: "italic" }}>No queries — add at least one below</span>
          )}
          {queries.map((q) => (
            <span key={q} style={chipStyle}>
              {q}
              <button
                style={removeChipBtn}
                onClick={() => setQueries((prev) => prev.filter((x) => x !== q))}
                title="Remove"
              >×</button>
            </span>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={newQuery}
            onChange={(e) => setNewQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addQuery(); } }}
            placeholder="e.g. Senior Machine Learning Engineer"
            style={{ flex: 1, fontSize: "0.88rem" }}
          />
          <button className="btn" style={{ whiteSpace: "nowrap", padding: "8px 14px" }} onClick={addQuery}>
            + Add
          </button>
        </div>
        <p style={{ margin: "6px 0 0", fontSize: "0.74rem", color: "var(--dim)" }}>
          Use job title phrases only — skill keywords like "PyTorch" or "MLOps" won't match platform autocomplete.
        </p>
      </div>

      {/* Location */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: "0.73rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", display: "block", marginBottom: 6 }}>
          Location
        </label>
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Sydney, NSW  or  All Australia"
          style={{ width: "100%", boxSizing: "border-box" }}
        />
      </div>

      {/* Settings grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 12 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: "0.73rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>Max Jobs</span>
          <select value={maxJobs} onChange={(e) => setMaxJobs(Number(e.target.value))}>
            {[5, 10, 20, 30, 50].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: "0.73rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>Min Score</span>
          <select value={minScore} onChange={(e) => setMinScore(Number(e.target.value))}>
            {[50, 55, 60, 65, 70, 75].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>

        {platform !== "linkedin" && (
          <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <span style={{ fontSize: "0.73rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>Posted Within</span>
            <select value={dateRange} onChange={(e) => setDateRange(Number(e.target.value))}>
              {[1, 3, 7, 14, 30].map((n) => (
                <option key={n} value={n}>{n === 1 ? "Last 24h" : `Last ${n}d`}</option>
              ))}
            </select>
          </label>
        )}

        <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: "0.73rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>Work Type</span>
          <select value={workType} onChange={(e) => setWorkType(e.target.value)}>
            <option value="any">Any</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
          </select>
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <span style={{ fontSize: "0.73rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>Min Salary ($)</span>
          <input
            type="number"
            value={salaryMin}
            onChange={(e) => setSalaryMin(e.target.value)}
            placeholder="optional"
            style={{ fontSize: "0.88rem" }}
          />
        </label>
      </div>

      {/* Confirm / Cancel */}
      <div style={{ display: "flex", gap: 8, marginTop: 18, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
        <button
          className="btn btn-accent"
          style={{ flex: 2, justifyContent: "center", fontWeight: 700 }}
          disabled={queries.length === 0}
          onClick={() => onConfirm({
            queries,
            location,
            max_jobs: maxJobs,
            min_score: minScore,
            date_range: dateRange,
            work_type: workType,
            salary_min: salaryMin ? Number(salaryMin) : null,
          })}
        >
          Start Hunting →
        </button>
        <button
          className="btn"
          style={{ color: "var(--red)", borderColor: "var(--red)" }}
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

/** Confirm bar for cover letters, form fields, manual steps, and final submit. */
function ConfirmBar({ event, editValue, onChange, onConfirm, onCancel }: {
  event: AgentEvent;
  editValue: string;
  onChange: (v: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const field    = event.field ?? "";
  const isAction = ["login", "captcha", "apply_button", "final_submit",
                    "manual_step", "screening_questions", "resume_upload"].includes(field);
  const isFinal  = field === "final_submit";
  const isCover  = field === "cover_letter";

  const accentColor  = isFinal ? "var(--green)" : isCover ? "var(--accent)" : "var(--yellow)";
  const bgColor      = isFinal ? "rgba(34,197,94,0.06)" : isCover ? "rgba(108,99,255,0.06)" : "rgba(251,191,36,0.06)";
  const borderColor  = isFinal ? "var(--green)" : isCover ? "var(--accent)" : "var(--yellow)";

  const fieldIcon: Record<string, string> = {
    cover_letter:        "✉",
    final_submit:        "✓",
    login:               "🔒",
    captcha:             "🛡",
    resume_upload:       "📄",
    screening_questions: "❓",
    manual_step:         "👆",
  };
  const icon = fieldIcon[field] ?? "⚠";

  return (
    <div style={{ padding: "16px 20px", borderTop: `2px solid ${borderColor}`, background: bgColor }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: isFinal || isAction ? 14 : 10 }}>
        <span style={{ fontSize: "1.1rem", lineHeight: 1.2, flexShrink: 0 }}>{icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: "0.88rem", color: accentColor }}>
            {isFinal ? "Ready to submit — confirm?" : event.label ?? "Action required"}
          </div>
          {isFinal && (
            <div style={{ fontSize: "0.78rem", color: "var(--muted)", marginTop: 3 }}>
              The agent will now click Submit. This cannot be undone.
            </div>
          )}
          {isCover && (
            <div style={{ fontSize: "0.78rem", color: "var(--muted)", marginTop: 3 }}>
              Review and edit your cover letter before it's typed into the form.
            </div>
          )}
          {!isFinal && !isCover && field === "screening_questions" && (
            <div style={{ fontSize: "0.78rem", color: "var(--muted)", marginTop: 3 }}>
              The agent has drafted an answer — edit if needed.
            </div>
          )}
        </div>
        {event.confidence !== undefined && event.confidence < 0.9 && !isAction && (
          <span style={{
            flexShrink: 0, fontSize: "0.7rem", fontWeight: 700, padding: "3px 8px",
            borderRadius: 999, background: "rgba(251,191,36,0.15)", color: "var(--yellow)",
          }}>
            {Math.round(event.confidence * 100)}% confident
          </span>
        )}
      </div>

      {/* Editable area (cover letters, text answers) */}
      {!isAction && (
        <>
          {isCover ? (
            <div style={{ position: "relative", marginBottom: 12 }}>
              <textarea
                value={editValue}
                onChange={(e) => onChange(e.target.value)}
                rows={10}
                style={{ width: "100%", boxSizing: "border-box", fontSize: "0.84rem", lineHeight: 1.6, resize: "vertical" }}
                autoFocus
              />
              <div style={{ position: "absolute", bottom: 8, right: 10, fontSize: "0.7rem", color: "var(--dim)" }}>
                {editValue.length} chars
              </div>
            </div>
          ) : (
            <textarea
              value={editValue}
              onChange={(e) => onChange(e.target.value)}
              rows={4}
              style={{ width: "100%", marginBottom: 12, fontSize: "0.84rem", resize: "vertical", boxSizing: "border-box" }}
              autoFocus
            />
          )}
        </>
      )}

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          className={isFinal ? "btn btn-accent" : "btn btn-accent"}
          style={{
            flex: 2, justifyContent: "center", fontWeight: 700,
            background: isFinal ? "linear-gradient(135deg, #22c55e, #16a34a)" : undefined,
          }}
          onClick={onConfirm}
        >
          {isFinal ? "✓ Submit Application" : isCover ? "Use this Cover Letter" : "Confirm"}
        </button>
        <button
          className="btn"
          style={{ color: "var(--red)", borderColor: "var(--red)" }}
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── main page ───────────────────────────────────────────────────────────────────

export function AutoHuntPage() {
  const candidatesQ = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profiles    = candidatesQ.data ?? [];

  // ── form state ──────────────────────────────────────────────────────────────
  const [platform, setPlatform]       = useState<Platform>("linkedin");
  const [selectedId, setSelectedId]   = useState("");
  const [keywords, setKeywords]       = useState("");
  const [location, setLocation]       = useState("Australia");
  const [locationHint, setLocationHint] = useState("");
  const [workType, setWorkType]       = useState("any");
  const [maxJobs, setMaxJobs]         = useState(10);
  const [minScore, setMinScore]       = useState(60);
  const [dateRange, setDateRange]     = useState(7);

  // LinkedIn creds
  const [email, setEmail]             = useState("");
  const [password, setPassword]       = useState("");
  const [showPwd, setShowPwd]         = useState(false);
  const [saveForNext, setSaveForNext] = useState(false);
  const [savedLoaded, setSavedLoaded] = useState(false);

  // ── agent state ─────────────────────────────────────────────────────────────
  const [agentState, setAgentState]           = useState<AgentState>("idle");
  const [events, setEvents]                   = useState<AgentEvent[]>([]);
  const [jobs, setJobs]                       = useState<FoundJob[]>([]);
  const [pendingConfirm, setPendingConfirm]   = useState<AgentEvent | null>(null);
  const [editValue, setEditValue]             = useState("");
  const [screenshot, setScreenshot]           = useState<string | null>(null);
  const [summary, setSummary]                 = useState("");

  const wsRef  = useRef<WebSocket | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // Auto-select first profile
  if (profiles.length > 0 && !selectedId) setSelectedId(profiles[0].candidate_id);

  // Auto-populate search criteria from the selected profile + platform
  useEffect(() => {
    if (!selectedId) return;
    fetchSearchPlan(selectedId, platform)
      .then((plan) => {
        setLocation(plan.location || "Australia");
        setLocationHint(plan.location_hint || "");
        setWorkType(plan.work_type || "any");
        setMaxJobs(plan.max_jobs || 10);
        setMinScore(plan.min_score || 60);
        setDateRange(plan.date_range || 7);
        // Join the first few queries as keywords hint (user can edit/extend)
        if (plan.queries.length > 0) setKeywords(plan.queries.join(", "));
      })
      .catch(() => {});
  }, [selectedId, platform]);

  // Load saved LinkedIn credentials when switching to LinkedIn tab
  useEffect(() => {
    if (platform !== "linkedin") return;
    getCredentialFull("linkedin")
      .then((cred) => { setEmail(cred.email); setPassword(cred.password); setSavedLoaded(true); })
      .catch(() => {});
  }, [platform]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  // Populate edit value when confirm arrives
  useEffect(() => {
    if (pendingConfirm) setEditValue(pendingConfirm.suggestion ?? "");
  }, [pendingConfirm]);

  const selectedProfile = profiles.find((p) => p.candidate_id === selectedId);
  const appendEvent     = (ev: AgentEvent) => setEvents((prev) => [...prev, ev]);
  const sendWs          = (msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify(msg));
  };

  // ── start agent ─────────────────────────────────────────────────────────────
  const handleStart = () => {
    if (!selectedProfile) return;
    if (platform === "linkedin" && (!email || !password)) return;

    if (platform === "linkedin" && saveForNext)
      saveCredential("linkedin", email, password).catch(() => {});

    setEvents([]);
    setJobs([]);
    setPendingConfirm(null);
    setScreenshot(null);
    setSummary("");
    setAgentState("connecting");

    const sessionId = `hunt_${Date.now()}`;
    const ws = new WebSocket(`${WS_BASE}/ws/agent/${platform}/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setAgentState("running");

      const profilePayload = {
        name:             selectedProfile.name,
        email:            selectedProfile.email,
        skills:           selectedProfile.skills,
        domains:          selectedProfile.domains,
        seniority:        selectedProfile.seniority,
        years_experience: selectedProfile.years_experience,
        locations:        selectedProfile.locations,
        salary_min:       selectedProfile.salary_min,
        summary:          selectedProfile.summary,
        raw_cv_text:      selectedProfile.raw_cv_text ?? "",
        preferred_roles:  selectedProfile.preferred_roles ?? [],
        target_roles:     (selectedProfile as any).target_roles ?? [],
        skill_clusters:   (selectedProfile as any).skill_clusters ?? {},
        industries:       (selectedProfile as any).industries ?? [],
      };

      const criteriaPayload = {
        keywords: keywords.trim() || undefined,
        location,
        work_type:  workType,
        max_jobs:   maxJobs,
        min_score:  minScore,
        date_range: dateRange,
      };

      const msg = platform === "linkedin"
        ? { credentials: { email, password }, profile: profilePayload, criteria: criteriaPayload }
        : { profile: profilePayload, criteria: criteriaPayload };

      ws.send(JSON.stringify(msg));
    };

    ws.onmessage = (evt) => {
      const ev: AgentEvent = JSON.parse(evt.data);

      if (ev.type === "screenshot") {
        setScreenshot(ev.data ?? null);
        return;
      }

      if (ev.type === "job_found" && (ev as any).job) {
        const j = (ev as any).job;
        setJobs((prev) => [...prev, { ...j, status: "found" }]);
        return;
      }

      if (ev.type === "job_scored") {
        setJobs((prev) =>
          prev.map((j) =>
            j.job_id === ev.job_id
              ? { ...j, score: ev.score, recommendation: ev.recommendation, status: "scoring" }
              : j
          )
        );
        return;
      }

      if (ev.type === "applying") {
        setJobs((prev) => prev.map((j) => j.job_id === ev.job_id ? { ...j, status: "applying" } : j));
        appendEvent(ev);
        return;
      }

      if (ev.type === "applied") {
        setJobs((prev) => prev.map((j) => j.job_id === ev.job_id ? { ...j, status: "applied" } : j));
        appendEvent(ev);
        return;
      }

      if (ev.type === "skipped") {
        setJobs((prev) =>
          prev.map((j) => j.job_id === ev.job_id ? { ...j, status: "skipped", skipReason: ev.reason } : j)
        );
        return;
      }

      if (ev.type === "confirm") {
        setAgentState("waiting_confirm");
        setPendingConfirm(ev);
        if (ev.field !== "review_job") appendEvent(ev);
        return;
      }

      if (ev.type === "success") {
        setAgentState("done");
        setSummary(ev.message ?? "");
        setPendingConfirm(null);
        appendEvent(ev);
        return;
      }

      if (ev.type === "error") {
        setAgentState("error");
        setPendingConfirm(null);
        appendEvent(ev);
        return;
      }

      appendEvent(ev);
    };

    ws.onerror = () => {
      appendEvent({ type: "error", message: "WebSocket connection failed" });
      setAgentState("error");
    };

    ws.onclose = () => {
      if (agentState !== "done" && agentState !== "error") setAgentState("idle");
    };
  };

  // ── confirm handlers ─────────────────────────────────────────────────────────
  const handleApply = () => {
    sendWs({ action: "confirm" });
    setPendingConfirm(null);
    setAgentState("running");
  };

  const handleSkip = () => {
    sendWs({ action: "skip" });
    setPendingConfirm(null);
    setAgentState("running");
  };

  const handleConfirm = () => {
    if (!pendingConfirm) return;
    const noEdit = ["final_submit", "captcha", "login", "manual_step", "screening_questions", "resume_upload"].includes(pendingConfirm.field ?? "");
    const isEdited = !noEdit && editValue !== pendingConfirm.suggestion;
    sendWs(isEdited ? { action: "edit", value: editValue } : { action: "confirm" });
    setPendingConfirm(null);
    setAgentState("running");
  };

  const handleSearchPlanConfirm = (plan: SearchPlan) => {
    sendWs({ action: "edit", value: JSON.stringify(plan) });
    setPendingConfirm(null);
    setAgentState("running");
  };

  const handleCancel = () => {
    sendWs({ action: "cancel" });
    wsRef.current?.close();
    setAgentState("idle");
    setPendingConfirm(null);
  };

  // ── derived ───────────────────────────────────────────────────────────────────
  const isRunning      = ["running", "connecting", "waiting_confirm"].includes(agentState);
  const appliedCount   = jobs.filter((j) => j.status === "applied").length;
  const scoredCount    = jobs.filter((j) => j.score !== undefined).length;
  const isReviewJob    = pendingConfirm?.field === "review_job";
  const isSearchPlan   = pendingConfirm?.field === "search_plan";
  const canStart       = !!selectedProfile &&
                         (platform !== "linkedin" || (!!email && !!password));

  const meta = PLATFORM_META[platform];

  return (
    <div className="page">
      <div className="page-header">
        <h2>Auto-Hunt</h2>
        <p className="muted" style={{ maxWidth: 680 }}>
          The AI searches, scores every job against your resume, and fills application forms — all in a
          {" "}<strong>visible browser you control</strong>. You approve every application before it's submitted.
        </p>
      </div>

      {/* ── Platform tabs ────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 2, marginBottom: 22, borderBottom: "1px solid var(--border)", paddingBottom: 0 }}>
        {(["linkedin", "seek", "indeed"] as Platform[]).map((p) => {
          const m = PLATFORM_META[p];
          return (
            <button
              key={p}
              onClick={() => {
                if (!isRunning) {
                  setPlatform(p);
                  setPendingConfirm(null);
                  setJobs([]);
                  setEvents([]);
                  setScreenshot(null);
                }
              }}
              disabled={isRunning}
              style={{
                padding: "8px 18px",
                fontSize: "0.88rem",
                fontWeight: platform === p ? 700 : 500,
                border: "none",
                borderBottom: platform === p ? `2px solid ${m.color}` : "2px solid transparent",
                background: "none",
                color: platform === p ? m.color : "var(--muted)",
                cursor: isRunning ? "not-allowed" : "pointer",
                borderRadius: "6px 6px 0 0",
                transition: "all 0.15s",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: 20, height: 20, borderRadius: 4, background: platform === p ? m.color : "var(--bg-2)",
                color: platform === p ? "#fff" : "var(--muted)", fontSize: "0.7rem", fontWeight: 900,
              }}>
                {m.icon}
              </span>
              {m.label}
            </button>
          );
        })}
      </div>

      <div className="grid two-col" style={{ alignItems: "flex-start", gap: 18 }}>

        {/* ── Left: setup panel ─────────────────────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

          {/* LinkedIn credentials */}
          {platform === "linkedin" && (
            <section className="panel">
              <h3 style={{ marginBottom: 6 }}>LinkedIn Credentials</h3>
              <p className="muted" style={{ fontSize: "0.82rem", marginBottom: 12 }}>
                The agent signs in automatically and uses {meta.applyLabel} only.
              </p>

              {savedLoaded && (
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "8px 12px",
                  background: "var(--tag-green-bg)",
                  border: "1px solid rgba(34,197,94,0.2)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "0.82rem", marginBottom: 12,
                }}>
                  <span style={{ color: "var(--green)" }}>✓ Saved credentials loaded</span>
                  <button
                    className="btn-small"
                    style={{ color: "var(--red)", borderColor: "var(--red)" }}
                    onClick={() => {
                      deleteCredential("linkedin").catch(() => {});
                      setEmail(""); setPassword(""); setSavedLoaded(false);
                    }}
                  >
                    Forget
                  </button>
                </div>
              )}

              <div className="form" style={{ gap: 10 }}>
                <label>
                  Email
                  <input type="email" value={email}
                    onChange={(e) => { setEmail(e.target.value); setSavedLoaded(false); }}
                    placeholder="you@example.com" style={{ marginTop: 5 }} />
                </label>
                <label>
                  Password
                  <div style={{ display: "flex", gap: 8, marginTop: 5 }}>
                    <input
                      type={showPwd ? "text" : "password"} value={password}
                      onChange={(e) => { setPassword(e.target.value); setSavedLoaded(false); }}
                      placeholder="••••••••" style={{ flex: 1 }}
                    />
                    <button type="button" className="btn-small" onClick={() => setShowPwd((v) => !v)}>
                      {showPwd ? "Hide" : "Show"}
                    </button>
                  </div>
                </label>
                {!savedLoaded && (
                  <label className="checkbox-label">
                    <input type="checkbox" checked={saveForNext}
                      onChange={(e) => setSaveForNext(e.target.checked)} />
                    Save credentials (AES-128 encrypted, local only)
                  </label>
                )}
              </div>
            </section>
          )}

          {/* Seek / Indeed manual login notice */}
          {(platform === "seek" || platform === "indeed") && (
            <section className="panel" style={{ background: "var(--tag-blue-bg)", borderColor: "rgba(96,165,250,0.2)" }}>
              <h3 style={{ marginBottom: 6, color: "var(--blue)" }}>Manual Login for {meta.label}</h3>
              <p className="muted" style={{ fontSize: "0.84rem", lineHeight: 1.7, margin: 0 }}>
                When you click <strong style={{ color: "var(--ink)" }}>Start</strong>, a browser window opens
                at the {meta.label} login page. Sign in yourself (including 2FA), then click{" "}
                <strong style={{ color: "var(--ink)" }}>Confirm</strong> back here.
                The agent takes over and hunts jobs while you watch.
              </p>
            </section>
          )}

          {/* Resume selection */}
          <section className="panel">
            <h3 style={{ marginBottom: 10 }}>Resume to Match Against</h3>
            <ResumeSelect profiles={profiles} selectedId={selectedId} onSelect={setSelectedId} />
            {selectedProfile && (
              <div style={{ marginTop: 10 }}>
                <div className="tag-list">
                  {selectedProfile.skills.slice(0, 8).map((s) => (
                    <span key={s} className="tag tag-skill" style={{ fontSize: "0.72rem" }}>{s}</span>
                  ))}
                  {selectedProfile.skills.length > 8 && (
                    <span className="tag" style={{ fontSize: "0.72rem" }}>+{selectedProfile.skills.length - 8}</span>
                  )}
                </div>
              </div>
            )}
          </section>

          {/* Search criteria */}
          <section className="panel">
            <h3 style={{ marginBottom: 4 }}>Search Criteria</h3>
            <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 12 }}>
              AI will generate job-title queries from your resume. Add extra keywords below to refine.
            </p>
            <div className="form" style={{ gap: 10 }}>
              <label>
                Extra Keywords <span className="muted" style={{ fontSize: "0.75rem" }}>(optional)</span>
                <input type="text" value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="e.g. Staff Engineer, NLP Researcher"
                  style={{ marginTop: 5 }} />
                <span className="muted" style={{ marginTop: 4, fontSize: "0.76rem" }}>
                  Use job title phrases — AI adds resume-based queries automatically.
                </span>
              </label>

              <label>
                Location
                <input type="text" value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="Sydney, Australia" style={{ marginTop: 5 }} />
                {locationHint && (
                  <span className="muted" style={{ marginTop: 4, fontSize: "0.76rem" }}>
                    {locationHint}
                  </span>
                )}
              </label>

              <label>
                Work Type
                <select value={workType} onChange={(e) => setWorkType(e.target.value)} style={{ marginTop: 5 }}>
                  <option value="any">Any</option>
                  <option value="remote">Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="onsite">On-site</option>
                </select>
              </label>

              <div className="form-row">
                <label>
                  Max jobs to scan
                  <select value={maxJobs} onChange={(e) => setMaxJobs(Number(e.target.value))} style={{ marginTop: 5 }}>
                    {[5, 10, 20, 30].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <label>
                  Min score to show
                  <select value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} style={{ marginTop: 5 }}>
                    {[50, 55, 60, 65, 70, 75].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
              </div>

              {platform !== "linkedin" && (
                <label>
                  Posted within
                  <select value={dateRange} onChange={(e) => setDateRange(Number(e.target.value))} style={{ marginTop: 5 }}>
                    {[1, 3, 7, 14, 30].map((n) => (
                      <option key={n} value={n}>{n === 1 ? "Last 24 hours" : `Last ${n} days`}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </section>

          {/* Start / Stop */}
          {!isRunning ? (
            <button
              className="btn btn-accent hunt-start-button"
              style={{ width: "100%", fontSize: "0.96rem", padding: "12px", fontWeight: 700, justifyContent: "center" }}
              onClick={handleStart}
              disabled={!canStart}
            >
              {platform === "linkedin" && (!email || !password)
                ? "Enter LinkedIn credentials above"
                : !selectedProfile
                  ? "Upload a resume first"
                  : `Start Auto-Hunt on ${meta.label} →`}
            </button>
          ) : (
            <button
              className="btn"
              style={{ width: "100%", color: "var(--red)", borderColor: "var(--red)", justifyContent: "center" }}
              onClick={handleCancel}
            >
              ■ Stop Agent
            </button>
          )}

          {(agentState === "done" || agentState === "error") && (
            <div style={{
              padding: "12px 16px", borderRadius: "var(--radius)", fontWeight: 600, fontSize: "0.88rem",
              background: agentState === "done" ? "var(--tag-green-bg)" : "var(--tag-red-bg)",
              border: `1px solid ${agentState === "done" ? "rgba(34,197,94,0.2)" : "rgba(248,113,113,0.2)"}`,
              color: agentState === "done" ? "var(--green)" : "var(--red)",
            }}>
              {agentState === "done" ? `✓ ${summary}` : "Error — see the activity log below"}
            </div>
          )}
        </div>

        {/* ── Right: live feed ───────────────────────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Live stats row (shown during run) */}
          {isRunning && (
            <div className="hunt-live-stats">
              {[
                { label: "Found",     value: jobs.length },
                { label: "Scored",    value: scoredCount },
                { label: "Applied",   value: appliedCount },
                { label: "Skipped",   value: jobs.filter((j) => j.status === "skipped").length },
              ].map((s) => (
                <div key={s.label} className="hunt-live-stat">
                  <strong>{s.value}</strong>
                  <span>{s.label}</span>
                </div>
              ))}
            </div>
          )}

          {/* Search plan editor (highest priority, before job review) */}
          {agentState === "waiting_confirm" && pendingConfirm && isSearchPlan && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <SearchPlanEditor
                suggestion={pendingConfirm.suggestion ?? "{}"}
                platform={platform}
                onConfirm={handleSearchPlanConfirm}
                onCancel={handleCancel}
              />
            </section>
          )}

          {/* Job review prompt */}
          {agentState === "waiting_confirm" && pendingConfirm && isReviewJob && (
            <JobReviewCard
              event={pendingConfirm}
              onApply={handleApply}
              onSkip={handleSkip}
              onStopAll={handleCancel}
            />
          )}

          {/* Generic confirm (cover letter, form fields, submit, etc.) */}
          {agentState === "waiting_confirm" && pendingConfirm && !isReviewJob && !isSearchPlan && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <ConfirmBar
                event={pendingConfirm}
                editValue={editValue}
                onChange={setEditValue}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
              />
            </section>
          )}

          {/* Job list */}
          {jobs.length > 0 && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{
                padding: "11px 16px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}>
                <strong style={{ fontSize: "0.88rem" }}>Jobs found ({jobs.length})</strong>
                {appliedCount > 0 && (
                  <span style={{ fontSize: "0.78rem", color: "var(--green)", fontWeight: 700 }}>
                    {appliedCount} applied ✓
                  </span>
                )}
              </div>
              <div style={{ maxHeight: 400, overflowY: "auto" }}>
                {jobs.map((j) => <JobRow key={j.job_id} job={j} />)}
              </div>
            </section>
          )}

          {/* Live browser screenshot */}
          {screenshot && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{
                padding: "9px 14px",
                borderBottom: "1px solid var(--border)",
                fontSize: "0.78rem",
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                gap: 8,
                color: "var(--muted)",
              }}>
                <span style={{
                  width: 7, height: 7, borderRadius: "50%",
                  background: isRunning ? "var(--green)" : "var(--dim)",
                  boxShadow: isRunning ? "0 0 6px var(--green)" : "none",
                  display: "inline-block",
                  animation: isRunning ? "pulse-dot 2s infinite" : "none",
                }} />
                Live browser — {meta.label}
              </div>
              <div style={{ background: "#000" }}>
                <img
                  src={`data:image/jpeg;base64,${screenshot}`}
                  alt="Live browser view"
                  style={{ width: "100%", display: "block" }}
                />
              </div>
            </section>
          )}

          {/* Activity log */}
          {events.length > 0 && (
            <section className="panel">
              <strong style={{ fontSize: "0.84rem", display: "block", marginBottom: 10 }}>Activity Log</strong>
              <div ref={logRef} style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
                {events.map((ev, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, fontSize: "0.8rem" }}>
                    <span style={{
                      color: ev.type === "error" ? "var(--red)"
                           : ev.type === "success" || ev.type === "applied" ? "var(--green)"
                           : ev.type === "confirm" ? "var(--yellow)"
                           : "var(--dim)",
                      minWidth: 14,
                      flexShrink: 0,
                    }}>
                      {ev.type === "error" ? "✗" : ev.type === "success" || ev.type === "applied" ? "✓" : ev.type === "confirm" ? "?" : "·"}
                    </span>
                    <span style={{ lineHeight: 1.5, color: "var(--muted)" }}>{ev.message || ev.label}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Empty state */}
          {agentState === "idle" && jobs.length === 0 && (
            <div style={{ padding: "60px 20px", textAlign: "center", color: "var(--muted)" }}>
              <div style={{ fontSize: "3rem", marginBottom: 14, opacity: 0.4 }}>🎯</div>
              <p style={{ fontSize: "0.9rem", lineHeight: 1.8, maxWidth: 320, margin: "0 auto" }}>
                Select a platform, choose your resume, and click{" "}
                <strong style={{ color: "var(--ink)" }}>Start Auto-Hunt</strong>.
                <br /><br />
                The AI will generate job-title queries from your resume, show you a search plan to review,
                then scan and score every job against your profile.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
