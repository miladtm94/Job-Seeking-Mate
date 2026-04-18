/**
 * Job Hunting workspace: Resume → Search → Score → Review → Apply → Log
 *
 * Replaces the three separate Find Jobs / Quick Apply / Auto-Hunt pages.
 *
 * How it works:
 *  1. Upload or select a resume  →  fields auto-populate from the parsed profile
 *  2. Pick a platform (Seek / Indeed / LinkedIn) and tweak the settings
 *  3. Click Start  →  a real (Camoufox) browser opens, agent searches + scores every job
 *  4. For each job above your threshold the agent pauses and shows you the match card
 *     You decide: Apply | Skip | Stop All
 *  5. Cover letter is shown for review before it's typed; final submit always needs your ✓
 *  6. Every application is auto-logged to My Applications
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteCandidate,
  fetchCandidates,
  getCredentialFull,
  saveCredential,
  deleteCredential,
  ingestPdf,
} from "../../api/client";
import type { CandidateProfile } from "../../api/client";

const WS_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1")
  .replace(/^http/, "ws")
  .replace("/api/v1", "");

// ── types ─────────────────────────────────────────────────────────────────────

type Platform   = "seek" | "indeed" | "linkedin";
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
  missing?: string[];
  match_summary?: string;
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
  has_quick_apply?: boolean;
  description_excerpt?: string;
  missing?: string[];
  match_summary?: string;
}

interface FoundJob {
  job_id: string;
  title: string;
  company: string;
  location: string;
  score?: number;
  recommendation?: string;
  missing?: string[];
  match_summary?: string;
  status: "found" | "scoring" | "applying" | "applied" | "skipped";
  skipReason?: string;
}

// ── constants ─────────────────────────────────────────────────────────────────

const PLATFORM_LABELS: Record<Platform, string> = {
  seek:     "Seek.com.au",
  indeed:   "Indeed.com.au",
  linkedin: "LinkedIn",
};

const REC_COLOR: Record<string, string> = {
  strong_apply: "var(--green)",
  apply:        "var(--accent)",
  maybe:        "var(--yellow)",
  skip:         "var(--muted)",
};

const STATUS_STYLE: Record<string, { icon: string; color: string }> = {
  found:    { icon: "·",  color: "var(--muted)"  },
  scoring:  { icon: "⟳",  color: "var(--accent)" },
  applying: { icon: "⟳",  color: "var(--accent)" },
  applied:  { icon: "✓",  color: "var(--green)"  },
  skipped:  { icon: "—",  color: "var(--muted)"  },
};

function stripRoleSeniority(role: string): string {
  return role.replace(/^(Junior|Senior|Staff|Principal|Lead|Mid)\s+/i, "").trim();
}

function buildResumeQuerySet(profile?: CandidateProfile, limit = 8): string[] {
  if (!profile) return [];

  const roleSeed = ((profile.preferred_roles?.length ? profile.preferred_roles : profile.target_roles) ?? [])
    .map(stripRoleSeniority);
  const stored = (profile.search_queries ?? []).filter(Boolean).map(stripRoleSeniority);
  const skills = [
    ...(profile.skill_clusters?.ml_ai ?? []).slice(0, 2),
    ...(profile.skill_clusters?.data ?? []).slice(0, 1),
    ...(profile.skill_clusters?.programming ?? []).slice(0, 2),
  ];
  const industries = (profile.industries ?? []).slice(0, 2);
  const roles = [...roleSeed, ...stored]
    .map(role => role.trim())
    .filter(Boolean);

  const queries: string[] = [];
  for (const role of roles) {
    queries.push(role);
    const shortSkill = skills.find(skill => !role.toLowerCase().includes(skill.toLowerCase()));
    if (shortSkill) queries.push(`${role} ${shortSkill}`);
    const industry = industries.find(item => !role.toLowerCase().includes(item.toLowerCase()));
    if (industry) queries.push(`${role} ${industry}`);
    if (queries.length >= limit * 2) break;
  }

  const fallback = [
    ...roleSeed,
    ...(profile.keywords ?? []).slice(0, 6),
    ...(profile.skills ?? []).slice(0, 6),
  ];

  return Array.from(new Map([...queries, ...fallback].map(query => {
    const clean = query.trim();
    return [clean.toLowerCase(), clean];
  })).values()).slice(0, limit);
}

function deriveKeywordQueries(profile?: CandidateProfile): string {
  return buildResumeQuerySet(profile).join(", ");
}
function deriveLocation(p: CandidateProfile): string {
  return (p.locations ?? [])[0] ?? "Australia";
}
function deriveIndustryFocus(profile?: CandidateProfile): string {
  return (profile?.industries ?? []).slice(0, 4).join(", ");
}

function parseSearchQueries(raw: string, profile?: CandidateProfile): string[] {
  const manual = raw
    .split(/[\n;,]+/)
    .map(q => q.trim())
    .filter(Boolean);
  const merged = [...manual, ...buildResumeQuerySet(profile)];
  return Array.from(new Map(merged.map(q => [q.toLowerCase(), q])).values()).slice(0, 8);
}

// ── sub-components ────────────────────────────────────────────────────────────

function ProfileChips({ profile }: { profile: CandidateProfile }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: "0.82rem" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
        <span style={{ color: "var(--muted)", minWidth: 70 }}>Roles</span>
        {((profile.preferred_roles?.length ? profile.preferred_roles : profile.target_roles) ?? [])
          .slice(0, 5)
          .map(stripRoleSeniority)
          .map(r => (
          <span key={r} style={{ background: "rgba(99,102,241,0.15)", color: "var(--accent)", padding: "2px 8px", borderRadius: 10, fontSize: "0.75rem" }}>{r}</span>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
        <span style={{ color: "var(--muted)", minWidth: 70 }}>Skills</span>
        {(profile.skills ?? []).slice(0, 12).map(s => (
          <span key={s} style={{ background: "rgba(34,197,94,0.1)", color: "var(--green)", padding: "2px 8px", borderRadius: 10, fontSize: "0.75rem" }}>{s}</span>
        ))}
      </div>
      {(profile.keywords ?? []).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          <span style={{ color: "var(--muted)", minWidth: 70 }}>Keywords</span>
          {profile.keywords.slice(0, 10).map(k => (
            <span key={k} style={{ background: "rgba(15,118,110,0.12)", color: "#14b8a6", padding: "2px 8px", borderRadius: 10, fontSize: "0.75rem" }}>{k}</span>
          ))}
        </div>
      )}
      {(profile.domains ?? []).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          <span style={{ color: "var(--muted)", minWidth: 70 }}>Domains</span>
          {profile.domains.slice(0, 6).map(d => (
            <span key={d} style={{ background: "rgba(234,179,8,0.1)", color: "var(--yellow)", padding: "2px 8px", borderRadius: 10, fontSize: "0.75rem" }}>{d}</span>
          ))}
        </div>
      )}
      {(profile.industries ?? []).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          <span style={{ color: "var(--muted)", minWidth: 70 }}>Industries</span>
          {profile.industries.slice(0, 5).map(industry => (
            <span key={industry} style={{ background: "rgba(14,116,144,0.12)", color: "#0f766e", padding: "2px 8px", borderRadius: 10, fontSize: "0.75rem" }}>{industry}</span>
          ))}
        </div>
      )}
      <div className="muted" style={{ fontSize: "0.76rem" }}>
        {profile.seniority} · {profile.years_experience}y exp
        {profile.salary_min ? ` · $${profile.salary_min.toLocaleString()}+ target` : ""}
      </div>
    </div>
  );
}

function QueryPreview({ queries }: { queries: string[] }) {
  if (queries.length === 0) return null;
  return (
    <div className="hunt-query-grid">
      {queries.map((query, index) => (
        <div key={query} className="hunt-query-card">
          <span className="hunt-query-index">{String(index + 1).padStart(2, "0")}</span>
          <strong>{query}</strong>
          <span>Platform-ready role search</span>
        </div>
      ))}
    </div>
  );
}

function JobCard({ job }: { job: FoundJob }) {
  const s = STATUS_STYLE[job.status] ?? STATUS_STYLE.found;
  const recColor = REC_COLOR[job.recommendation ?? ""] ?? "var(--accent)";
  return (
    <div style={{
      padding: "10px 14px", borderBottom: "1px solid var(--border)",
      opacity: job.status === "skipped" ? 0.5 : 1,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span style={{ color: s.color, minWidth: 14, paddingTop: 2, fontSize: "0.9rem" }}>{s.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: "0.88rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {job.title}
          </div>
          <div className="muted" style={{ fontSize: "0.76rem" }}>
            {job.company}{job.location ? ` · ${job.location}` : ""}
          </div>
          {job.score !== undefined && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
              <div style={{ flex: 1, height: 3, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{ width: `${job.score}%`, height: "100%", background: recColor, borderRadius: 2 }} />
              </div>
              <span style={{ fontSize: "0.73rem", fontWeight: 700, color: recColor, minWidth: 24 }}>{job.score}</span>
            </div>
          )}
          {job.match_summary && job.status !== "skipped" && (
            <div className="muted" style={{ fontSize: "0.72rem", marginTop: 3, lineHeight: 1.4 }}>{job.match_summary}</div>
          )}
          {job.status === "skipped" && job.skipReason && (
            <span className="muted" style={{ fontSize: "0.72rem" }}>{job.skipReason}</span>
          )}
          {job.status === "applied" && (
            <span style={{ fontSize: "0.72rem", color: "var(--green)", fontWeight: 600 }}>Applied ✓</span>
          )}
        </div>
      </div>
    </div>
  );
}

function JobReviewCard({ event, onApply, onSkip, onStop }: {
  event: AgentEvent;
  onApply: () => void;
  onSkip: () => void;
  onStop: () => void;
}) {
  const job = event.job;
  if (!job) return null;
  const recColor = REC_COLOR[job.recommendation] ?? "var(--accent)";
  const isQuick  = event.suggestion === "quick_apply" || job.has_quick_apply;

  return (
    <div style={{ border: "2px solid var(--accent)", borderRadius: 10, background: "rgba(99,102,241,0.05)", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
          Agent is asking — apply to this job?
        </div>
        <div style={{ fontWeight: 700, fontSize: "1rem" }}>{job.title}</div>
        <div className="muted" style={{ fontSize: "0.84rem" }}>
          {job.company}{job.location ? ` · ${job.location}` : ""}{job.salary ? ` · ${job.salary}` : ""}
        </div>
        {isQuick && (
          <span style={{ fontSize: "0.72rem", color: "var(--green)", fontWeight: 600, marginTop: 4, display: "inline-block" }}>
            ⚡ Quick Apply available
          </span>
        )}
      </div>

      {/* Score */}
      <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginBottom: 4 }}>AI match score (role 30% + skills 40% + exp 20% + domain 10%)</div>
          <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ width: `${job.score}%`, height: "100%", background: recColor, borderRadius: 3, transition: "width 0.4s" }} />
          </div>
        </div>
        <div style={{ fontWeight: 800, fontSize: "1.5rem", color: recColor }}>{job.score}</div>
        <div style={{ fontSize: "0.75rem", color: recColor, fontWeight: 600, textTransform: "capitalize" }}>
          {(job.recommendation ?? "").replace("_", " ")}
        </div>
      </div>

      {/* Match summary */}
      {job.match_summary && (
        <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--border)", fontSize: "0.82rem", color: "var(--muted)", lineHeight: 1.5 }}>
          {job.match_summary}
        </div>
      )}

      {/* Missing skills */}
      {(job.missing ?? []).length > 0 && (
        <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginBottom: 5 }}>Gaps vs job requirements:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {(job.missing ?? []).map(m => (
              <span key={m} style={{ background: "rgba(239,68,68,0.1)", color: "var(--red)", padding: "2px 8px", borderRadius: 10, fontSize: "0.73rem" }}>✗ {m}</span>
            ))}
          </div>
        </div>
      )}

      {/* Description excerpt */}
      {job.description_excerpt && (
        <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.6, maxHeight: 100, overflowY: "auto" }}>
          {job.description_excerpt}
        </div>
      )}

      {/* URL */}
      {job.url && (
        <div style={{ padding: "6px 16px", borderBottom: "1px solid var(--border)" }}>
          <a href={job.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.78rem", color: "var(--accent)" }}>
            View job posting ↗
          </a>
        </div>
      )}

      {/* Actions */}
      <div style={{ padding: "12px 16px", display: "flex", gap: 8 }}>
        <button className="btn btn-accent" style={{ flex: 2, fontWeight: 700 }} onClick={onApply}>
          {isQuick ? "⚡ Apply (Quick Apply)" : "Apply"}
        </button>
        <button className="btn" style={{ flex: 1 }} onClick={onSkip}>Skip</button>
        <button className="btn" style={{ flex: 1, color: "var(--red)", borderColor: "var(--red)" }} onClick={onStop}>Stop All</button>
      </div>
    </div>
  );
}

function ConfirmBar({ event, editValue, onChange, onConfirm, onCancel }: {
  event: AgentEvent;
  editValue: string;
  onChange: (v: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const actionOnly = ["login", "captcha", "final_submit", "manual_step", "screening_questions", "resume_upload", "external_apply"].includes(event.field ?? "");
  const isFinal    = event.field === "final_submit";
  const isExternal = event.field === "external_apply";

  return (
    <div style={{ padding: "14px 16px", borderTop: `2px solid ${isFinal ? "var(--green)" : "var(--yellow)"}`, background: isFinal ? "rgba(34,197,94,0.06)" : "rgba(234,179,8,0.06)" }}>
      <div style={{ fontWeight: 700, fontSize: "0.88rem", marginBottom: 8, color: isFinal ? "var(--green)" : "var(--yellow)" }}>
        {isFinal ? "✓" : "⚠"} {event.label}
      </div>
      {!actionOnly && (
        <textarea
          value={editValue}
          onChange={e => onChange(e.target.value)}
          rows={isExternal ? 8 : 5}
          style={{ width: "100%", marginBottom: 10, fontSize: "0.82rem", resize: "vertical", boxSizing: "border-box" }}
          autoFocus
        />
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-accent" style={{ flex: 1 }} onClick={onConfirm}>
          {isFinal ? "✓ Submit Application" : "Confirm"}
        </button>
        <button className="btn" style={{ color: "var(--red)", borderColor: "var(--red)" }} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── resume library ────────────────────────────────────────────────────────────

function ResumeLibrary({
  profiles,
  selectedId,
  onSelect,
  onUploaded,
}: {
  profiles: CandidateProfile[];
  selectedId: string;
  onSelect: (id: string) => void;
  onUploaded: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const deleteMut = useMutation({
    mutationFn: deleteCandidate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["candidates"] }),
  });

  const handleFiles = async (files: FileList | null) => {
    if (!files) return;
    setUploadErr(null);
    setUploading(true);
    try {
      let lastId = "";
      for (const file of Array.from(files)) {
        if (!file.name.toLowerCase().endsWith(".pdf")) continue;
        const result = await ingestPdf({
          file,
          name: file.name.replace(/\.pdf$/i, "").replace(/[_-]/g, " "),
          email: "me@example.com",
          preferred_roles: "",
          locations: "",
          work_type: "any",
        });
        lastId = result.candidate_id;
      }
      await queryClient.invalidateQueries({ queryKey: ["candidates"] });
      if (lastId) onSelect(lastId);
      onUploaded();
    } catch (e) {
      setUploadErr((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="panel">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Resume Library</h3>
        <button
          className="btn btn-accent"
          style={{ fontSize: "0.8rem", padding: "0.3rem 0.8rem" }}
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? "Uploading…" : "+ Upload PDF"}
        </button>
        <input ref={fileRef} type="file" accept=".pdf" multiple style={{ display: "none" }}
          onChange={e => handleFiles(e.target.files)} />
      </div>

      {uploadErr && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: 8 }}>{uploadErr}</p>}

      {profiles.length === 0 ? (
        <div
          className="pdf-drop-zone"
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
          onClick={() => fileRef.current?.click()}
          style={{ margin: 0 }}
        >
          <span>Drop PDF resumes here or click to browse</span>
        </div>
      ) : (
        <div
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
        >
          {profiles.map(p => {
            const label  = p.filename || p.name || p.candidate_id.slice(0, 8);
            const active = p.candidate_id === selectedId;
            return (
              <div
                key={p.candidate_id}
                onClick={() => onSelect(p.candidate_id)}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "10px 12px", borderRadius: 7, marginBottom: 4, cursor: "pointer",
                  border: `1.5px solid ${active ? "var(--accent)" : "var(--border)"}`,
                  background: active ? "rgba(203,95,54,0.07)" : "transparent",
                  transition: "border-color 0.15s, background 0.15s",
                }}
              >
                <div style={{
                  width: 14, height: 14, borderRadius: "50%", flexShrink: 0,
                  border: `2px solid ${active ? "var(--accent)" : "var(--border)"}`,
                  background: active ? "var(--accent)" : "transparent",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {active && <div style={{ width: 5, height: 5, borderRadius: "50%", background: "#fff" }} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: "0.88rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</div>
                  <div className="muted" style={{ fontSize: "0.74rem" }}>
                    {p.seniority} · {p.years_experience}y · {p.skills.length} skills
                  </div>
                </div>
                <button
                  className="btn"
                  style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem", color: "var(--red)", borderColor: "var(--red)", flexShrink: 0 }}
                  onClick={e => { e.stopPropagation(); deleteMut.mutate(p.candidate_id); }}
                  disabled={deleteMut.isPending}
                >
                  ✕
                </button>
              </div>
            );
          })}
          <p className="muted" style={{ fontSize: "0.72rem", marginTop: 6 }}>Drop more PDFs here to add</p>
        </div>
      )}
    </section>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export function HuntPage() {
  const queryClient    = useQueryClient();
  const candidatesQ    = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profiles       = candidatesQ.data ?? [];

  // ── config state ───────────────────────────────────────────────────────────
  const [platform, setPlatform]       = useState<Platform>("seek");
  const [selectedId, setSelectedId]   = useState("");
  const [keywords, setKeywords]       = useState("");
  const [location, setLocation]       = useState("Australia");
  const [maxJobs, setMaxJobs]         = useState(100);
  const [minScore, setMinScore]       = useState(70);
  const [dateRange, setDateRange]     = useState(7);
  const [salaryFloor, setSalaryFloor] = useState("");
  const [industryFocus, setIndustryFocus] = useState("");
  const [workType, setWorkType]       = useState("any");

  // LinkedIn credentials
  const [email, setEmail]             = useState("");
  const [password, setPassword]       = useState("");
  const [showPwd, setShowPwd]         = useState(false);
  const [saveForNext, setSaveForNext] = useState(false);
  const [savedLoaded, setSavedLoaded] = useState(false);

  // ── agent state ────────────────────────────────────────────────────────────
  const [agentState, setAgentState]         = useState<AgentState>("idle");
  const [events, setEvents]                 = useState<AgentEvent[]>([]);
  const [jobs, setJobs]                     = useState<FoundJob[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<AgentEvent | null>(null);
  const [editValue, setEditValue]           = useState("");
  const [screenshot, setScreenshot]         = useState<string | null>(null);
  const [summary, setSummary]               = useState("");

  const wsRef  = useRef<WebSocket | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // Auto-select first profile
  useEffect(() => {
    if (profiles.length > 0 && !selectedId) setSelectedId(profiles[0].candidate_id);
  }, [profiles, selectedId]);

  // ── Auto-populate fields when resume is (re-)selected ─────────────────────
  const prevSelectedIdRef = useRef<string>("");
  const lastAutofillRef = useRef({
    keywords: "",
    location: "Australia",
    salaryFloor: "",
    industryFocus: "",
    workType: "any",
  });
  const selectedProfile = profiles.find(p => p.candidate_id === selectedId);
  const selectedProfileFingerprint = selectedProfile
    ? JSON.stringify({
        candidate_id: selectedProfile.candidate_id,
        search_queries: selectedProfile.search_queries,
        target_roles: selectedProfile.target_roles,
        preferred_roles: selectedProfile.preferred_roles,
        keywords: selectedProfile.keywords,
        industries: selectedProfile.industries,
        locations: selectedProfile.locations,
        salary_min: selectedProfile.salary_min,
        work_type: selectedProfile.work_type,
      })
    : "";

  useEffect(() => {
    if (!selectedProfile) return;
    const isResumeSwitch = selectedId !== prevSelectedIdRef.current;
    prevSelectedIdRef.current = selectedId;

    const nextAutofill = {
      keywords: deriveKeywordQueries(selectedProfile),
      location: deriveLocation(selectedProfile),
      salaryFloor: selectedProfile.salary_min ? String(selectedProfile.salary_min) : "",
      industryFocus: deriveIndustryFocus(selectedProfile),
      workType: selectedProfile.work_type ?? "any",
    };
    const previousAutofill = lastAutofillRef.current;

    setKeywords(current =>
      isResumeSwitch || !current.trim() || current === previousAutofill.keywords
        ? nextAutofill.keywords
        : current
    );
    setLocation(current =>
      isResumeSwitch || !current.trim() || current === previousAutofill.location
        ? nextAutofill.location
        : current
    );
    setSalaryFloor(current =>
      isResumeSwitch || !current.trim() || current === previousAutofill.salaryFloor
        ? nextAutofill.salaryFloor
        : current
    );
    setIndustryFocus(current =>
      isResumeSwitch || !current.trim() || current === previousAutofill.industryFocus
        ? nextAutofill.industryFocus
        : current
    );
    setWorkType(current =>
      isResumeSwitch || current === previousAutofill.workType
        ? nextAutofill.workType
        : current
    );

    lastAutofillRef.current = nextAutofill;
  }, [selectedId, selectedProfile, selectedProfileFingerprint]);

  // Load LinkedIn creds when switching to LinkedIn
  useEffect(() => {
    if (platform !== "linkedin") return;
    getCredentialFull("linkedin")
      .then(c => { setEmail(c.email); setPassword(c.password); setSavedLoaded(true); })
      .catch(() => {});
  }, [platform]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  // Populate edit box when confirm arrives
  useEffect(() => {
    if (pendingConfirm) setEditValue(pendingConfirm.suggestion ?? "");
  }, [pendingConfirm]);

  const appendEvent = (ev: AgentEvent) => setEvents(prev => [...prev, ev]);
  const sendWs = (msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(msg));
  };

  // ── start hunt ─────────────────────────────────────────────────────────────
  const handleStart = () => {
    if (!selectedProfile || searchPlan.length === 0) return;
    if (platform === "linkedin" && (!email || !password)) return;

    if (platform === "linkedin" && saveForNext)
      saveCredential("linkedin", email, password).catch(() => {});

    setEvents([]); setJobs([]); setPendingConfirm(null);
    setScreenshot(null); setSummary("");
    setAgentState("connecting");

    const sessionId = `hunt_${Date.now()}`;
    const ws = new WebSocket(`${WS_BASE}/ws/agent/${platform}/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setAgentState("running");
      const profilePayload = {
        name:             selectedProfile.name,
        email:            selectedProfile.email,
        phone:            (selectedProfile as any).phone ?? "",
        skills:           selectedProfile.skills,
        skill_clusters:   selectedProfile.skill_clusters,
        domains:          selectedProfile.domains,
        industries:       selectedProfile.industries,
        target_roles:     selectedProfile.target_roles,
        preferred_roles:  selectedProfile.preferred_roles,
        keywords:         selectedProfile.keywords,
        search_queries:   selectedProfile.search_queries,
        seniority:        selectedProfile.seniority,
        years_experience: selectedProfile.years_experience,
        locations:        selectedProfile.locations,
        salary_min:       selectedProfile.salary_min,
        work_type:        selectedProfile.work_type,
        summary:          selectedProfile.summary,
        raw_cv_text:      selectedProfile.raw_cv_text ?? "",
      };
      const criteriaPayload = {
        keywords,
        queries: searchPlan,
        location,
        salary_min: salaryFloor ? Number(salaryFloor) : selectedProfile.salary_min,
        industries: industryFocus.split(",").map(item => item.trim()).filter(Boolean),
        work_type: workType,
        max_jobs: maxJobs,
        min_score: minScore,
        date_range: dateRange,
      };
      const msg = platform === "linkedin"
        ? { credentials: { email, password }, profile: profilePayload, criteria: criteriaPayload }
        : { profile: profilePayload, criteria: criteriaPayload };
      ws.send(JSON.stringify(msg));
    };

    ws.onmessage = evt => {
      const ev: AgentEvent = JSON.parse(evt.data);

      if (ev.type === "screenshot") { setScreenshot(ev.data ?? null); return; }

      if (ev.type === "job_found") {
        const j = (ev as any).job ?? {};
        setJobs(prev => prev.some(existing => existing.job_id === j.job_id) ? prev : [...prev, { ...j, status: "found" }]);
        return;
      }

      if (ev.type === "job_scored") {
        setJobs(prev => prev.map(j =>
          j.job_id === ev.job_id
            ? { ...j, score: ev.score, recommendation: ev.recommendation,
                missing: ev.missing, match_summary: ev.match_summary, status: "scoring" }
            : j
        ));
        return;
      }

      if (ev.type === "applying") {
        setJobs(prev => prev.map(j => j.job_id === ev.job_id ? { ...j, status: "applying" } : j));
        appendEvent(ev); return;
      }

      if (ev.type === "applied") {
        setJobs(prev => prev.map(j => j.job_id === ev.job_id ? { ...j, status: "applied" } : j));
        appendEvent(ev); return;
      }

      if (ev.type === "skipped") {
        setJobs(prev => prev.map(j =>
          j.job_id === ev.job_id ? { ...j, status: "skipped", skipReason: ev.reason } : j
        ));
        return;
      }

      if (ev.type === "confirm") {
        setAgentState("waiting_confirm");
        setPendingConfirm(ev);
        if (ev.field !== "review_job") appendEvent(ev);
        return;
      }

      if (ev.type === "success") {
        setAgentState("done"); setSummary(ev.message ?? "");
        setPendingConfirm(null); appendEvent(ev); return;
      }

      if (ev.type === "error") {
        setAgentState("error"); setPendingConfirm(null); appendEvent(ev); return;
      }

      appendEvent(ev);
    };

    ws.onerror = () => { appendEvent({ type: "error", message: "WebSocket connection failed" }); setAgentState("error"); };
    ws.onclose = () => { if (agentState !== "done" && agentState !== "error") setAgentState("idle"); };
  };

  // ── confirm handlers ───────────────────────────────────────────────────────
  const handleApply = () => { sendWs({ action: "confirm" }); setPendingConfirm(null); setAgentState("running"); };
  const handleSkip  = () => { sendWs({ action: "skip" });    setPendingConfirm(null); setAgentState("running"); };
  const handleStop  = () => { sendWs({ action: "cancel" }); wsRef.current?.close(); setAgentState("idle"); setPendingConfirm(null); };

  const handleConfirm = () => {
    if (!pendingConfirm) return;
    const noEdit = ["final_submit", "login", "manual_step", "screening_questions", "resume_upload", "captcha"].includes(pendingConfirm.field ?? "");
    sendWs(noEdit ? { action: "confirm" } : { action: "edit", value: editValue });
    setPendingConfirm(null); setAgentState("running");
  };

  // ── derived ────────────────────────────────────────────────────────────────
  const isRunning     = ["running", "connecting", "waiting_confirm"].includes(agentState);
  const appliedCount  = jobs.filter(j => j.status === "applied").length;
  const isReviewJob   = pendingConfirm?.field === "review_job";
  const canStart      = !!selectedProfile && parseSearchQueries(keywords, selectedProfile).length > 0 &&
                        (platform !== "linkedin" || (!!email && !!password));
  const searchPlan = useMemo(
    () => parseSearchQueries(keywords, selectedProfile),
    [keywords, selectedProfile],
  );
  const skippedCount = jobs.filter(j => j.status === "skipped").length;

  return (
    <div className="page">
      <section className="hunt-hero">
        <div className="hunt-hero-copy">
          <span className="hunt-kicker">Unified Job Hunting</span>
          <h2 style={{ marginBottom: 8 }}>Modern resume-to-application workspace for real job platforms</h2>
          <p className="muted" style={{ maxWidth: 720, lineHeight: 1.8, fontSize: "0.96rem" }}>
            Pick a resume and the workspace preloads related platform-style job titles, skills, industries,
            salary targets, and work preferences so the browser agent can search with cleaner signals instead of
            relying on manual typing.
          </p>
        </div>
        <div className="hunt-hero-metrics">
          <div className="hunt-metric-card">
            <strong>{selectedProfile ? searchPlan.length : 0}</strong>
            <span>role queries</span>
          </div>
          <div className="hunt-metric-card">
            <strong>{maxJobs}</strong>
            <span>jobs per run</span>
          </div>
          <div className="hunt-metric-card">
            <strong>{selectedProfile?.target_roles?.length ?? 0}</strong>
            <span>matched roles</span>
          </div>
        </div>
      </section>

      <div className="grid two-col" style={{ alignItems: "flex-start", gap: 20 }}>

        {/* ── LEFT: setup ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Resume library */}
          <ResumeLibrary
            profiles={profiles}
            selectedId={selectedId}
            onSelect={id => !isRunning && setSelectedId(id)}
            onUploaded={() => queryClient.invalidateQueries({ queryKey: ["candidates"] })}
          />

          {/* Profile preview */}
          {selectedProfile && (
            <section className="panel hunt-profile-panel" style={{ padding: "14px 16px" }}>
              <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>
                Extracted from resume
              </div>
              <ProfileChips profile={selectedProfile} />
            </section>
          )}

          {/* Platform tabs */}
          <section className="panel hunt-controls-panel" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
              {(["seek", "indeed", "linkedin"] as Platform[]).map(p => (
                <button
                  key={p}
                  onClick={() => { if (!isRunning) setPlatform(p); }}
                  disabled={isRunning}
                  style={{
                    flex: 1, padding: "0.5rem 0", fontSize: "0.82rem",
                    fontWeight: platform === p ? 700 : 400, border: "none",
                    borderBottom: platform === p ? "2px solid var(--accent)" : "2px solid transparent",
                    background: "none", cursor: isRunning ? "not-allowed" : "pointer",
                    color: platform === p ? "var(--accent)" : "var(--muted)",
                  }}
                >
                  {PLATFORM_LABELS[p]}
                </button>
              ))}
            </div>

            <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
              {/* LinkedIn creds (inside platform panel) */}
              {platform === "linkedin" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
                  {savedLoaded && (
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 10px", background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.25)", borderRadius: 6, fontSize: "0.8rem" }}>
                      <span style={{ color: "var(--green)" }}>✓ Saved credentials loaded</span>
                      <button className="btn" style={{ fontSize: "0.7rem", padding: "0.1rem 0.5rem", color: "var(--red)", borderColor: "var(--red)" }}
                        onClick={() => { deleteCredential("linkedin").catch(() => {}); setEmail(""); setPassword(""); setSavedLoaded(false); }}>
                        Forget
                      </button>
                    </div>
                  )}
                  <label style={{ fontSize: "0.84rem" }}>
                    LinkedIn email
                    <input type="email" value={email}
                      onChange={e => { setEmail(e.target.value); setSavedLoaded(false); }}
                      placeholder="you@example.com" style={{ marginTop: 5, display: "block", width: "100%", boxSizing: "border-box" }} />
                  </label>
                  <label style={{ fontSize: "0.84rem" }}>
                    Password
                    <div style={{ display: "flex", gap: 6, marginTop: 5 }}>
                      <input type={showPwd ? "text" : "password"} value={password}
                        onChange={e => { setPassword(e.target.value); setSavedLoaded(false); }}
                        placeholder="••••••••" style={{ flex: 1 }} />
                      <button className="btn" style={{ padding: "0.3rem 0.7rem" }} onClick={() => setShowPwd(v => !v)}>
                        {showPwd ? "Hide" : "Show"}
                      </button>
                    </div>
                  </label>
                  {!savedLoaded && (
                    <label className="checkbox-label" style={{ fontSize: "0.8rem" }}>
                      <input type="checkbox" checked={saveForNext} onChange={e => setSaveForNext(e.target.checked)} />
                      Save (AES-128, local only)
                    </label>
                  )}
                </div>
              )}

              {(platform === "seek" || platform === "indeed") && (
                <p className="muted" style={{ fontSize: "0.82rem", margin: 0 }}>
                  A browser window will open at the {PLATFORM_LABELS[platform]} login page.
                  Sign in yourself, then click Confirm here — the agent takes over.
                </p>
              )}

              {/* Search criteria — auto-populated from resume */}
              <div className="hunt-section-header">
                <div>
                  <strong>Search plan</strong>
                  <p className="muted">Auto-filled from the selected resume. Use comma-separated platform-ready role queries.</p>
                </div>
                <button
                  className="btn"
                  style={{ padding: "0.35rem 0.75rem", fontSize: "0.76rem" }}
                  type="button"
                  onClick={() => {
                    if (!selectedProfile) return;
                    const nextKeywords = deriveKeywordQueries(selectedProfile);
                    const nextLocation = deriveLocation(selectedProfile);
                    const nextIndustry = deriveIndustryFocus(selectedProfile);
                    const nextSalary = selectedProfile.salary_min ? String(selectedProfile.salary_min) : "";
                    const nextWorkType = selectedProfile.work_type ?? "any";
                    setKeywords(nextKeywords);
                    setLocation(nextLocation);
                    setIndustryFocus(nextIndustry);
                    setSalaryFloor(nextSalary);
                    setWorkType(nextWorkType);
                    lastAutofillRef.current = {
                      keywords: nextKeywords,
                      location: nextLocation,
                      industryFocus: nextIndustry,
                      salaryFloor: nextSalary,
                      workType: nextWorkType,
                    };
                  }}
                >
                  Reset from resume
                </button>
              </div>

              <label style={{ fontSize: "0.84rem" }}>
                Search queries
                <textarea
                  value={keywords}
                  onChange={e => setKeywords(e.target.value)}
                  placeholder={"Machine Learning Engineer, Data Scientist, Applied Scientist"}
                  rows={4}
                  className="hunt-query-textarea"
                  style={{ marginTop: 5, display: "block", width: "100%", boxSizing: "border-box", resize: "vertical" }}
                />
              </label>

              <QueryPreview queries={searchPlan} />

              <label style={{ fontSize: "0.84rem" }}>
                Location
                <input type="text" value={location} onChange={e => setLocation(e.target.value)}
                  placeholder="Sydney, Australia"
                  style={{ marginTop: 5, display: "block", width: "100%", boxSizing: "border-box" }} />
              </label>

              <div className="form-row">
                <label style={{ fontSize: "0.84rem", flex: 1 }}>
                  Salary floor
                  <input
                    type="number"
                    value={salaryFloor}
                    onChange={e => setSalaryFloor(e.target.value)}
                    placeholder="140000"
                    style={{ marginTop: 5, display: "block", width: "100%", boxSizing: "border-box" }}
                  />
                </label>
                <label style={{ fontSize: "0.84rem", flex: 1 }}>
                  Work style
                  <select value={workType} onChange={e => setWorkType(e.target.value)} style={{ marginTop: 5, display: "block", width: "100%" }}>
                    <option value="any">Any</option>
                    <option value="remote">Remote</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">On-site</option>
                  </select>
                </label>
              </div>

              <label style={{ fontSize: "0.84rem" }}>
                Industry categories
                <span className="muted" style={{ fontWeight: 400, marginLeft: 6, fontSize: "0.76rem" }}>(auto-filled from resume, editable)</span>
                <input
                  type="text"
                  value={industryFocus}
                  onChange={e => setIndustryFocus(e.target.value)}
                  placeholder="FinTech, SaaS, Healthcare"
                  style={{ marginTop: 5, display: "block", width: "100%", boxSizing: "border-box" }}
                />
              </label>

              <div className="form-row">
                <label style={{ fontSize: "0.84rem", flex: 1 }}>
                  Max jobs
                  <select value={maxJobs} onChange={e => setMaxJobs(Number(e.target.value))} style={{ marginTop: 5, display: "block", width: "100%" }}>
                    {[25, 50, 75, 100].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <label style={{ fontSize: "0.84rem", flex: 1 }}>
                  Min score
                  <select value={minScore} onChange={e => setMinScore(Number(e.target.value))} style={{ marginTop: 5, display: "block", width: "100%" }}>
                    {[50, 55, 60, 65, 70, 75, 80].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                {platform !== "linkedin" && (
                  <label style={{ fontSize: "0.84rem", flex: 1 }}>
                    Posted within
                    <select value={dateRange} onChange={e => setDateRange(Number(e.target.value))} style={{ marginTop: 5, display: "block", width: "100%" }}>
                      {[1, 3, 7, 14, 30].map(n => <option key={n} value={n}>{n === 1 ? "24 h" : `${n}d`}</option>)}
                    </select>
                  </label>
                )}
              </div>
            </div>
          </section>

          {/* Start / Stop */}
          {!isRunning ? (
            <button
              className="btn btn-accent hunt-start-button"
              style={{ width: "100%", fontSize: "1rem", padding: "0.95rem", fontWeight: 800 }}
              onClick={handleStart}
              disabled={!canStart}
            >
              {!selectedProfile ? "Select a resume above"
                : platform === "linkedin" && (!email || !password) ? "Enter LinkedIn credentials"
                : `Start on ${PLATFORM_LABELS[platform]}`}
            </button>
          ) : (
            <button className="btn" style={{ width: "100%", color: "var(--red)", borderColor: "var(--red)" }} onClick={handleStop}>
              Stop Agent
            </button>
          )}

          {(agentState === "done" || agentState === "error") && (
            <div style={{
              padding: "12px 14px", borderRadius: 8, fontWeight: 600, fontSize: "0.88rem",
              background: agentState === "done" ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
              color: agentState === "done" ? "var(--green)" : "var(--red)",
            }}>
              {agentState === "done" ? `✓ ${summary}` : "Error — see activity log"}
            </div>
          )}
        </div>

        {/* ── RIGHT: live feed ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Live session */}
          {(isRunning || agentState === "done") && (
            <section className="panel hunt-live-panel" style={{ padding: "18px 18px" }}>
              <div className="hunt-section-header" style={{ marginBottom: 14 }}>
                <div>
                  <strong>Live session</strong>
                  <p className="muted">
                    {agentState === "waiting_confirm"
                      ? "Waiting for your decision on the next job."
                      : agentState === "done"
                        ? "Run complete."
                        : "Browser agent is searching and scoring jobs."}
                  </p>
                </div>
              </div>
              <div className="hunt-live-stats">
                <div className="hunt-live-stat">
                  <strong>{jobs.length}</strong>
                  <span>scanned</span>
                </div>
                <div className="hunt-live-stat">
                  <strong>{appliedCount}</strong>
                  <span>applied</span>
                </div>
                <div className="hunt-live-stat">
                  <strong>{skippedCount}</strong>
                  <span>skipped</span>
                </div>
                <div className="hunt-live-stat">
                  <strong>{searchPlan.length}</strong>
                  <span>queries</span>
                </div>
              </div>
              {searchPlan.length > 0 && (
                <div className="hunt-inline-tags" style={{ marginTop: 14 }}>
                  {searchPlan.slice(0, 6).map(query => (
                    <span key={query} className="hunt-inline-tag">{query}</span>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Job review card */}
          {agentState === "waiting_confirm" && pendingConfirm && isReviewJob && (
            <JobReviewCard event={pendingConfirm} onApply={handleApply} onSkip={handleSkip} onStop={handleStop} />
          )}

          {/* Generic confirm bar */}
          {agentState === "waiting_confirm" && pendingConfirm && !isReviewJob && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <ConfirmBar event={pendingConfirm} editValue={editValue} onChange={setEditValue} onConfirm={handleConfirm} onCancel={handleStop} />
            </section>
          )}

          {/* Job list */}
          {jobs.length > 0 && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong style={{ fontSize: "0.88rem" }}>Jobs ({jobs.length})</strong>
                <div style={{ fontSize: "0.78rem", display: "flex", gap: 12 }}>
                  {appliedCount > 0 && <span style={{ color: "var(--green)", fontWeight: 700 }}>{appliedCount} applied</span>}
                  {jobs.filter(j => j.status === "skipped").length > 0 && (
                    <span className="muted">{jobs.filter(j => j.status === "skipped").length} skipped</span>
                  )}
                </div>
              </div>
              <div style={{ maxHeight: 400, overflowY: "auto" }}>
                {jobs.map(j => <JobCard key={j.job_id} job={j} />)}
              </div>
            </section>
          )}

          {/* Live browser screenshot */}
          {screenshot && (
            <section className="panel" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)", fontSize: "0.78rem", fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", display: "inline-block", background: isRunning ? "var(--green)" : "var(--muted)", flexShrink: 0 }} />
                Live browser
              </div>
              <div style={{ background: "#0a0a0a" }}>
                <img src={`data:image/jpeg;base64,${screenshot}`} alt="Live browser" style={{ width: "100%", display: "block" }} />
              </div>
            </section>
          )}

          {/* Activity log */}
          {events.length > 0 && (
            <section className="panel">
              <strong style={{ fontSize: "0.85rem", display: "block", marginBottom: 8 }}>Activity log</strong>
              <div ref={logRef} style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
                {events.map((ev, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, fontSize: "0.8rem" }}>
                    <span style={{
                      color: ev.type === "error" ? "var(--red)" : ev.type === "success" || ev.type === "applied" ? "var(--green)" : ev.type === "confirm" ? "var(--yellow)" : "var(--muted)",
                      minWidth: 12, flexShrink: 0,
                    }}>
                      {ev.type === "error" ? "✗" : ev.type === "success" || ev.type === "applied" ? "✓" : ev.type === "confirm" ? "?" : "·"}
                    </span>
                    <span style={{ lineHeight: 1.5, color: ev.type === "error" ? "var(--red)" : undefined }}>
                      {ev.message || ev.label}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Empty state */}
          {agentState === "idle" && jobs.length === 0 && (
            <div style={{ padding: "56px 20px", textAlign: "center", color: "var(--muted)" }}>
              <div style={{ fontSize: "2.8rem", marginBottom: 14 }}>🎯</div>
              <p style={{ fontSize: "0.92rem", lineHeight: 1.8, maxWidth: 420, margin: "0 auto" }}>
                Upload or select a resume — the fields will auto-fill from your profile.
                <br />Pick a platform, review the search queries, then click <strong>Start Hunting</strong>.
                <br />The agent finds and scores every job — <em>you</em> decide what to apply to.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
