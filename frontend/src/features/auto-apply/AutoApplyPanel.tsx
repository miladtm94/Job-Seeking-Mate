import { useEffect, useRef, useState } from "react";
import { useApplyWebSocket } from "./useApplyWebSocket";
import type { ApplyEvent, SessionState } from "./useApplyWebSocket";
import type { CandidateProfile, ApplicationGenerateResponse } from "../../api/client";
import { getCredentialFull, saveCredential, deleteCredential } from "../../api/client";

/** Minimal job info needed for browser automation — no Adzuna/scoring fields required */
export interface JobForApply {
  url: string;
  title: string;
  company: string;
  description: string;
}

interface AutoApplyPanelProps {
  job: JobForApply;
  bestProfile: CandidateProfile;
  appResult: ApplicationGenerateResponse | undefined;
  onClose: () => void;
}

// ── platform detection ────────────────────────────────────────────────────────

type Platform = "indeed" | "linkedin" | "seek" | "direct";

function detectPlatform(url: string): Platform {
  if (url.includes("indeed"))   return "indeed";
  if (url.includes("linkedin")) return "linkedin";
  if (url.includes("seek"))     return "seek";
  return "direct";
}

function extractHost(url: string): string {
  try { return new URL(url).hostname; }
  catch { return url; }
}

const PLATFORM_META: Record<Platform, { label: string; icon: string; loginRequired: boolean }> = {
  indeed:   { label: "Indeed",          icon: "🔵", loginRequired: true  },
  linkedin: { label: "LinkedIn",        icon: "🔗", loginRequired: true  },
  seek:     { label: "Seek",            icon: "🟢", loginRequired: true  },
  direct:   { label: "Company website", icon: "🏢", loginRequired: false },
};

// ── step indicator ────────────────────────────────────────────────────────────

const STEPS = ["Setup", "Login", "Navigate", "Fill form", "Submit"];

function stepFromState(state: SessionState, events: ApplyEvent[]): number {
  if (state === "idle" || state === "connecting") return 0;
  const steps = events.map(e => e.step ?? "");
  if (steps.some(s => s.startsWith("form_step") || s === "fill")) return 3;
  if (steps.some(s => s === "navigate" || s === "apply")) return 2;
  if (steps.some(s => s === "login")) return 1;
  if (state === "success") return 5;
  return 1;
}

function StepIndicator({ active }: { active: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, padding: "12px 24px" }}>
      {STEPS.map((label, i) => {
        const done    = i < active;
        const current = i === active;
        return (
          <div key={label} style={{ display: "flex", alignItems: "center", flex: i < STEPS.length - 1 ? 1 : 0 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, minWidth: 60 }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "0.75rem", fontWeight: 700,
                background: done ? "var(--green)" : current ? "var(--accent)" : "var(--border)",
                color: done || current ? "#fff" : "var(--muted)",
                border: current ? "2px solid var(--accent)" : "2px solid transparent",
                transition: "background 0.3s",
              }}>
                {done ? "✓" : i + 1}
              </div>
              <span style={{ fontSize: "0.68rem", color: current ? "var(--accent)" : done ? "var(--green)" : "var(--muted)", fontWeight: current ? 700 : 400, whiteSpace: "nowrap" }}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{ flex: 1, height: 2, background: done ? "var(--green)" : "var(--border)", margin: "0 4px", marginBottom: 18, transition: "background 0.3s" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── event log ─────────────────────────────────────────────────────────────────

const EVENT_STYLES: Record<string, { icon: string; color: string }> = {
  progress: { icon: "·",  color: "var(--muted)"   },
  confirm:  { icon: "?",  color: "var(--yellow)"  },
  success:  { icon: "✓",  color: "var(--green)"   },
  error:    { icon: "✗",  color: "var(--red)"     },
};

function EventLog({ events, sessionStarted, logRef }: {
  events: ApplyEvent[];
  sessionStarted: boolean;
  logRef: React.RefObject<HTMLDivElement>;
}) {
  return (
    <div ref={logRef} style={{ flex: 1, overflowY: "auto", padding: "14px 20px", display: "flex", flexDirection: "column", gap: 6 }}>
      {events.length === 0 && sessionStarted && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--muted)", fontSize: "0.9rem", paddingTop: 4 }}>
          <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2, display: "inline-block", flexShrink: 0 }} />
          Starting browser…
        </div>
      )}
      {events.map((ev, i) => {
        const style = EVENT_STYLES[ev.type] ?? EVENT_STYLES.progress;
        return (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <span style={{ fontWeight: 700, fontSize: "0.85rem", color: style.color, minWidth: 16, flexShrink: 0, paddingTop: 1 }}>
              {style.icon}
            </span>
            <span style={{ fontSize: "0.88rem", lineHeight: 1.55, color: ev.type === "error" ? "var(--red)" : ev.type === "success" ? "var(--green)" : undefined }}>
              {ev.message || ev.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── confirmation prompt ───────────────────────────────────────────────────────

function ConfirmPrompt({ pendingConfirm, editValue, onChange, onConfirm, onCancel }: {
  pendingConfirm: ApplyEvent;
  editValue: string;
  onChange: (v: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const isSubmit  = pendingConfirm.field === "final_submit";
  const isCaptcha = pendingConfirm.field === "captcha" || pendingConfirm.field === "login" || pendingConfirm.field === "apply_button";
  const showEdit  = !isSubmit && !isCaptcha;

  return (
    <div style={{
      padding: "16px 20px",
      borderTop: "2px solid var(--yellow)",
      background: "rgba(234,179,8,0.06)",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: "1.2rem", flexShrink: 0 }}>⚠</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: "0.95rem", marginBottom: 4 }}>
            {pendingConfirm.label}
          </div>
          {typeof pendingConfirm.confidence === "number" && pendingConfirm.confidence < 0.9 && (
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              AI confidence: {Math.round((pendingConfirm.confidence ?? 0) * 100)}% — please review
            </div>
          )}
        </div>
      </div>

      {showEdit && (
        <textarea
          value={editValue}
          onChange={(e) => onChange(e.target.value)}
          rows={editValue.length > 120 ? 5 : 3}
          style={{ width: "100%", marginBottom: 12, fontSize: "0.88rem", resize: "vertical", boxSizing: "border-box" }}
          autoFocus
        />
      )}

      <div style={{ display: "flex", gap: 10 }}>
        <button
          className="btn btn-accent"
          style={{ flex: 1, fontWeight: 700 }}
          onClick={onConfirm}
        >
          {isSubmit ? "✓ Submit Application" : "Confirm"}
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

// ── main component ────────────────────────────────────────────────────────────

export function AutoApplyPanel({ job, bestProfile, appResult, onClose }: AutoApplyPanelProps) {
  const { state, events, pendingConfirm, screenshot, start, confirm, edit, cancel, reset } =
    useApplyWebSocket();

  const platform   = detectPlatform(job.url);
  const meta       = PLATFORM_META[platform];
  const jobHost    = extractHost(job.url);

  const [email, setEmail]             = useState("");
  const [password, setPassword]       = useState("");
  const [skipLogin, setSkipLogin]     = useState(!meta.loginRequired);
  const [showPwd, setShowPwd]         = useState(false);
  const [saveForNext, setSaveForNext] = useState(false);
  const [savedBanner, setSavedBanner] = useState<"none" | "loaded" | "saving">("none");
  const [editValue, setEditValue]     = useState("");
  const [sessionStarted, setSessionStarted] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  // Pre-fill from encrypted store when panel opens (job-board platforms only)
  useEffect(() => {
    if (platform === "direct") return;
    getCredentialFull(platform)
      .then((cred) => {
        setEmail(cred.email);
        setPassword(cred.password);
        setSavedBanner("loaded");
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  useEffect(() => {
    if (pendingConfirm) setEditValue(pendingConfirm.suggestion ?? "");
  }, [pendingConfirm]);

  const handleStart = () => {
    if (!skipLogin && (!email || !password)) return;
    if (saveForNext && !skipLogin && platform !== "direct") {
      setSavedBanner("saving");
      saveCredential(platform, email, password).catch(() => {});
    }
    setSessionStarted(true);
    const sessionId = `apply_${Date.now()}`;
    start(sessionId, {
      job_url:     job.url,
      credentials: skipLogin ? { email: "", password: "" } : { email, password },
      profile: {
        name:             bestProfile.name,
        email:            bestProfile.email,
        skills:           bestProfile.skills,
        domains:          bestProfile.domains,
        seniority:        bestProfile.seniority,
        years_experience: bestProfile.years_experience,
        locations:        bestProfile.locations,
        salary_min:       bestProfile.salary_min,
        summary:          bestProfile.summary,
      },
      documents: {
        resume_text:     appResult?.customized_resume ?? "",
        cover_letter:    appResult?.tailored_cover_letter ?? "",
        job_title:       job.title,
        job_company:     job.company,
        job_description: job.description,
      },
    });
  };

  const handleConfirm = () => {
    if (
      pendingConfirm &&
      pendingConfirm.field !== "final_submit" &&
      pendingConfirm.field !== "captcha" &&
      pendingConfirm.field !== "login" &&
      pendingConfirm.field !== "apply_button" &&
      editValue !== pendingConfirm.suggestion
    ) {
      edit(editValue);
    } else {
      confirm();
    }
  };

  const activeStep = stepFromState(state, events);
  const isRunning  = state === "running" || state === "waiting_confirm" || state === "connecting";
  const isDone     = state === "success" || state === "error" || state === "cancelled";

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 12,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) { reset(); onClose(); } }}
    >
      <div style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        width: "100%",
        maxWidth: 1100,
        height: "92vh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}>

        {/* ── Header ── */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 20px",
          borderBottom: "1px solid var(--border)",
          background: "rgba(0,0,0,0.1)",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: "1.4rem" }}>{meta.icon}</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: "1rem" }}>
                AI Auto-Apply — {meta.label}
              </div>
              <div className="muted" style={{ fontSize: "0.82rem" }}>
                {job.title} · {job.company}
                <span style={{ marginLeft: 8, color: "var(--muted)", fontFamily: "monospace", fontSize: "0.75rem" }}>
                  {jobHost}
                </span>
              </div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {isRunning && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, display: "inline-block" }} />
                <span style={{ fontSize: "0.82rem", color: state === "waiting_confirm" ? "var(--yellow)" : "var(--accent)", fontWeight: 600 }}>
                  {state === "waiting_confirm" ? "Waiting for your input" : "Applying…"}
                </span>
              </div>
            )}
            {isDone && (
              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: state === "success" ? "var(--green)" : "var(--red)" }}>
                {state === "success" ? "✓ Done" : state === "cancelled" ? "Cancelled" : "Error"}
              </span>
            )}
            <button
              onClick={() => { reset(); onClose(); }}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: "1.5rem", lineHeight: 1, color: "var(--muted)", padding: "0 4px" }}
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* ── Step indicator (shown once running) ── */}
        {sessionStarted && (
          <div style={{ borderBottom: "1px solid var(--border)", flexShrink: 0, background: "rgba(0,0,0,0.05)" }}>
            <StepIndicator active={activeStep} />
          </div>
        )}

        {/* ── Body ── */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

          {/* Left: setup / log / confirm */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>

            {/* Setup form (before session starts) */}
            {!sessionStarted && (
              <div style={{ overflowY: "auto", flex: 1 }}>
                <div style={{ padding: "20px 24px", maxWidth: 560 }}>

                  {/* Platform notice */}
                  <div style={{
                    display: "flex", gap: 12, padding: "14px 16px",
                    background: platform === "direct" ? "rgba(234,179,8,0.07)" : "rgba(203,95,54,0.07)",
                    border: `1px solid ${platform === "direct" ? "rgba(234,179,8,0.3)" : "rgba(203,95,54,0.3)"}`,
                    borderRadius: 10, marginBottom: 20,
                  }}>
                    <span style={{ fontSize: "1.6rem", lineHeight: 1 }}>{meta.icon}</span>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "0.95rem", marginBottom: 4 }}>
                        Applying via {meta.label}
                      </div>
                      <div className="muted" style={{ fontSize: "0.85rem", lineHeight: 1.6 }}>
                        {platform === "direct"
                          ? "This is a direct company website application. Many company career portals use a public form — no login needed. If the site requires an account, uncheck the box below and enter your credentials."
                          : `Enter the email and password you use to log in to ${jobHost}. The browser will open visibly so you can watch every step.`}
                      </div>
                      {platform !== "direct" && (
                        <div style={{ marginTop: 6, fontSize: "0.8rem", color: "var(--muted)" }}>
                          Don't have an account? Create one at <strong>{jobHost}</strong> first.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Skip-login toggle for direct sites */}
                  {platform === "direct" && (
                    <label className="checkbox-label" style={{ marginBottom: 16, fontSize: "0.9rem" }}>
                      <input
                        type="checkbox"
                        checked={skipLogin}
                        onChange={(e) => setSkipLogin(e.target.checked)}
                      />
                      No login required — go straight to the application form
                    </label>
                  )}

                  {/* Credentials */}
                  {!skipLogin && (
                    <div className="form" style={{ gap: 14, marginBottom: 20 }}>
                      {/* Saved credentials banner */}
                      {savedBanner === "loaded" && (
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.25)", borderRadius: 7, fontSize: "0.82rem" }}>
                          <span style={{ color: "var(--green)" }}>✓ Saved credentials loaded for {jobHost}</span>
                          <button
                            type="button"
                            className="btn"
                            style={{ fontSize: "0.72rem", padding: "0.15rem 0.6rem", color: "var(--red)", borderColor: "var(--red)" }}
                            onClick={() => { deleteCredential(platform).catch(() => {}); setEmail(""); setPassword(""); setSavedBanner("none"); }}
                          >
                            Forget
                          </button>
                        </div>
                      )}
                      <label>
                        Email / username for <strong>{jobHost}</strong>
                        <input
                          type="email"
                          value={email}
                          onChange={(e) => { setEmail(e.target.value); setSavedBanner("none"); }}
                          placeholder="you@example.com"
                          autoComplete="off"
                          style={{ marginTop: 6 }}
                        />
                      </label>
                      <label>
                        Password for <strong>{jobHost}</strong>
                        <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                          <input
                            type={showPwd ? "text" : "password"}
                            value={password}
                            onChange={(e) => { setPassword(e.target.value); setSavedBanner("none"); }}
                            placeholder="••••••••"
                            autoComplete="new-password"
                            style={{ flex: 1 }}
                          />
                          <button type="button" className="btn" style={{ padding: "0.35rem 0.9rem" }} onClick={() => setShowPwd(v => !v)}>
                            {showPwd ? "Hide" : "Show"}
                          </button>
                        </div>
                      </label>
                      {savedBanner === "none" && (
                        <label className="checkbox-label" style={{ fontSize: "0.82rem" }}>
                          <input type="checkbox" checked={saveForNext} onChange={(e) => setSaveForNext(e.target.checked)} />
                          Save credentials for {jobHost} (encrypted on disk)
                        </label>
                      )}
                      <p className="muted" style={{ fontSize: "0.75rem", margin: 0 }}>
                        {savedBanner === "loaded"
                          ? "These were loaded from your encrypted local credential store."
                          : "Credentials are encrypted with AES-128 before being written to disk."}
                      </p>
                    </div>
                  )}

                  {/* What will be submitted */}
                  {appResult ? (
                    <div style={{ padding: "12px 14px", background: "rgba(0,0,0,0.12)", borderRadius: 8, marginBottom: 20, fontSize: "0.85rem" }}>
                      <div style={{ fontWeight: 600, marginBottom: 6 }}>Will submit:</div>
                      <div className="muted" style={{ lineHeight: 2 }}>
                        <div>✓ Tailored resume ({appResult.decision === "improve" ? "surgical improvements" : appResult.decision === "new_resume_needed" ? "full rewrite" : "as-is"})</div>
                        <div>✓ Cover letter ({appResult.tailored_cover_letter?.split(" ").length ?? 0} words)</div>
                        <div>✓ Profile data (name, email, phone, location, skills)</div>
                      </div>
                    </div>
                  ) : (
                    <div style={{ padding: "12px 14px", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, marginBottom: 20, fontSize: "0.85rem", color: "var(--red)" }}>
                      ⚠ Generate your tailored resume and cover letter first (click "Tailor Resume & Generate Cover Letter" above), then come back here.
                    </div>
                  )}

                  <button
                    className="btn btn-accent"
                    style={{ width: "100%", fontSize: "1rem", padding: "0.75rem" }}
                    onClick={handleStart}
                    disabled={(!skipLogin && (!email || !password)) || !appResult}
                  >
                    Start Auto-Apply →
                  </button>
                </div>
              </div>
            )}

            {/* Event log (during/after session) */}
            {sessionStarted && (
              <EventLog events={events} sessionStarted={sessionStarted} logRef={logRef as React.RefObject<HTMLDivElement>} />
            )}

            {/* Confirmation prompt */}
            {state === "waiting_confirm" && pendingConfirm && (
              <ConfirmPrompt
                pendingConfirm={pendingConfirm}
                editValue={editValue}
                onChange={setEditValue}
                onConfirm={handleConfirm}
                onCancel={() => cancel()}
              />
            )}

            {/* Done bar */}
            {isDone && (
              <div style={{ padding: "14px 20px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                {state === "success" && (
                  <span style={{ color: "var(--green)", fontWeight: 700, fontSize: "0.95rem", flex: 1 }}>
                    ✓ Application submitted and logged to your tracker.
                  </span>
                )}
                {state === "error" && (
                  <span style={{ color: "var(--red)", fontSize: "0.9rem", flex: 1 }}>
                    Something went wrong — check the log above for details.
                  </span>
                )}
                {state === "cancelled" && (
                  <span className="muted" style={{ fontSize: "0.9rem", flex: 1 }}>Session cancelled.</span>
                )}
                <button className="btn" onClick={() => { reset(); onClose(); }}>Close</button>
              </div>
            )}
          </div>

          {/* Right: live browser screenshot */}
          <div style={{
            width: screenshot ? 420 : 0,
            borderLeft: screenshot ? "1px solid var(--border)" : "none",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            transition: "width 0.3s",
            flexShrink: 0,
          }}>
            {screenshot && (
              <>
                <div style={{
                  padding: "10px 14px",
                  borderBottom: "1px solid var(--border)",
                  fontSize: "0.8rem",
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--green)", display: "inline-block" }} />
                  Live Browser View
                </div>
                <div style={{ flex: 1, overflowY: "auto", background: "#0a0a0a" }}>
                  <img
                    src={`data:image/jpeg;base64,${screenshot}`}
                    alt="Live browser"
                    style={{ width: "100%", display: "block" }}
                  />
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
