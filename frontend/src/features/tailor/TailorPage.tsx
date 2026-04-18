import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  evaluateTailor,
  generateCoverLetter,
  parseTailorFile,
} from "../../api/client";
import type { EvaluateResponse } from "../../api/client";

// ─── shared styles ───────────────────────────────────────────────────────────

const SECTION_LABEL: React.CSSProperties = {
  fontWeight: 700,
  fontSize: "0.82rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--muted)",
  marginBottom: 10,
};

const ACTION_BTN: React.CSSProperties = {
  minWidth: 200,
  justifyContent: "center",
  display: "flex",
  alignItems: "center",
  gap: 8,
};

const ERROR_BOX: React.CSSProperties = {
  padding: "10px 14px",
  borderRadius: 8,
  background: "rgba(248,113,113,0.08)",
  border: "1px solid var(--red)",
  fontSize: "0.84rem",
  color: "var(--red)",
};

// ─── helpers ────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="btn-small"
      style={{ minWidth: 76 }}
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        });
      }}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function ScoreBar({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: "0.85rem" }}>
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span style={{ fontWeight: 700, color, fontSize: "1rem" }}>{value}<span style={{ fontWeight: 400, fontSize: "0.78rem", color: "var(--muted)", marginLeft: 1 }}>/100</span></span>
      </div>
      <div style={{ height: 10, borderRadius: 6, background: "var(--border-2)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${value}%`, background: color, borderRadius: 6, transition: "width 0.7s ease" }} />
      </div>
    </div>
  );
}

function scoreColor(v: number) {
  if (v >= 70) return "var(--green)";
  if (v >= 50) return "var(--yellow)";
  return "var(--red)";
}

function KeywordBadge({ status }: { status: "present" | "partial" | "missing" }) {
  const map: Record<string, React.CSSProperties> = {
    present: { background: "var(--tag-green-bg)",  color: "var(--green)",  border: "1px solid rgba(34,197,94,0.3)" },
    partial:  { background: "var(--tag-yellow-bg)", color: "var(--yellow)", border: "1px solid rgba(251,191,36,0.3)" },
    missing:  { background: "var(--tag-red-bg)",    color: "var(--red)",    border: "1px solid rgba(248,113,113,0.3)" },
  };
  return (
    <span style={{ fontSize: "0.68rem", fontWeight: 700, padding: "2px 7px", borderRadius: 20, ...map[status] }}>
      {{ present: "Present", partial: "Partial", missing: "Missing" }[status]}
    </span>
  );
}

function Divider() {
  return <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "28px 0" }} />;
}

// ─── File upload zone ────────────────────────────────────────────────────────

function FileUploadZone({
  onTextReady,
  fileName,
  setFileName,
}: {
  onTextReady: (text: string) => void;
  fileName: string;
  setFileName: (name: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const parseMutation = useMutation({
    mutationFn: (file: File) => parseTailorFile(file),
    onSuccess: (data, file) => { onTextReady(data.text); setFileName(file.name); },
  });

  function handleFile(file: File) { parseMutation.mutate(file); }

  return (
    <div>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: "2px dashed var(--border-2)", borderRadius: 10,
          padding: "28px 18px", textAlign: "center", cursor: "pointer",
          background: "var(--bg-2)", transition: "border-color 0.2s, background 0.2s",
        }}
        onMouseEnter={(e) => { const d = e.currentTarget as HTMLDivElement; d.style.borderColor = "var(--accent)"; d.style.background = "rgba(108,99,255,0.05)"; }}
        onMouseLeave={(e) => { const d = e.currentTarget as HTMLDivElement; d.style.borderColor = "var(--border-2)"; d.style.background = "var(--bg-2)"; }}
      >
        {parseMutation.isPending ? (
          <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontSize: "0.85rem" }}>
            <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
            Extracting text…
          </span>
        ) : fileName ? (
          <span style={{ fontSize: "0.85rem", color: "var(--accent)" }}>
            {fileName}
            <span style={{ color: "var(--muted)", marginLeft: 6, fontSize: "0.78rem" }}>— click or drop to replace</span>
          </span>
        ) : (
          <>
            <div style={{ fontSize: "1.4rem", marginBottom: 6, opacity: 0.4 }}>↑</div>
            <div style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
              Drop your CV here, or click to browse
            </div>
            <div style={{ fontSize: "0.74rem", color: "var(--dim)", marginTop: 4 }}>PDF · .docx · .txt</div>
          </>
        )}
      </div>
      <input
        ref={inputRef} type="file" accept=".pdf,.docx,.txt" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }}
      />
      {parseMutation.isError && (
        <p style={{ fontSize: "0.78rem", color: "var(--red)", marginTop: 6 }}>
          {(parseMutation.error as Error).message}
        </p>
      )}
    </div>
  );
}

// ─── ATS evaluation results ──────────────────────────────────────────────────

function EvalResults({ result }: { result: EvaluateResponse }) {
  const recColor =
    result.recommendation.startsWith("Strong") ? "var(--green)"
    : result.recommendation.startsWith("Good")  ? "var(--green)"
    : result.recommendation.startsWith("Mod")   ? "var(--yellow)"
    : "var(--red)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Scores card */}
      <div className="panel">
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
          <span style={{
            padding: "5px 16px", borderRadius: 20, fontSize: "0.82rem",
            fontWeight: 700, color: recColor, border: `1px solid ${recColor}`,
            background: "rgba(255,255,255,0.04)",
          }}>
            {result.recommendation}
          </span>
        </div>
        <ScoreBar value={result.ats_score} label="ATS Match Score" color={scoreColor(result.ats_score)} />
        <ScoreBar value={result.interview_probability} label="Chance of Reaching Next Stage" color={scoreColor(result.interview_probability)} />
        <p style={{ margin: "14px 0 0", fontSize: "0.84rem", lineHeight: 1.65, color: "var(--muted)", textAlign: "center" }}>
          {result.summary}
        </p>
      </div>

      {/* Strengths + Gaps */}
      <div className="grid two-col" style={{ alignItems: "start" }}>
        <div className="panel">
          <p style={SECTION_LABEL}>Strengths</p>
          <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 7 }}>
            {result.strengths.map((s, i) => (
              <li key={i} style={{ fontSize: "0.84rem", lineHeight: 1.55, color: "var(--ink)" }}>{s}</li>
            ))}
          </ul>
        </div>
        <div className="panel">
          <p style={SECTION_LABEL}>Gaps to Address</p>
          <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 7 }}>
            {result.gaps.map((g, i) => (
              <li key={i} style={{ fontSize: "0.84rem", lineHeight: 1.55, color: "var(--ink)" }}>{g}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Keywords */}
      {Object.keys(result.keyword_matches).length > 0 && (
        <div className="panel">
          <p style={SECTION_LABEL}>Keyword Coverage</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {Object.entries(result.keyword_matches).map(([kw, status]) => (
              <div key={kw} style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "5px 10px", border: "1px solid var(--border-2)",
                borderRadius: 8, fontSize: "0.81rem", background: "var(--bg-2)",
              }}>
                <span style={{ fontWeight: 500 }}>{kw}</span>
                <KeywordBadge status={status as "present" | "partial" | "missing"} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main page ───────────────────────────────────────────────────────────────

export function TailorPage() {
  const [cvText, setCvText]           = useState("");
  const [jobDescription, setJD]       = useState("");
  const [cvFileName, setCvFileName]   = useState("");
  const [inputMode, setInputMode]     = useState<"upload" | "paste">("upload");
  const [evalResult, setEvalResult]   = useState<EvaluateResponse | null>(null);
  const [coverLetter, setCoverLetter] = useState("");

  const canAct = cvText.trim().length > 100 && jobDescription.trim().length > 50;

  const evalMutation = useMutation({
    mutationFn: () => evaluateTailor({ cv_text: cvText.trim(), job_description: jobDescription.trim() }),
    onSuccess: (data) => setEvalResult(data),
  });

  const clMutation = useMutation({
    mutationFn: () => generateCoverLetter({ cv_text: cvText.trim(), job_description: jobDescription.trim() }),
    onSuccess: (data) => setCoverLetter(data.cover_letter),
  });

  function resetResults() {
    setEvalResult(null);
    setCoverLetter("");
    evalMutation.reset();
    clMutation.reset();
  }

  return (
    <div className="page">

      {/* ── Page header ── */}
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <h2 style={{ marginBottom: 8 }}>Job Fit & Cover Letter</h2>
        <p className="muted" style={{ maxWidth: 560, margin: "0 auto", lineHeight: 1.65 }}>
          Upload your CV and paste a job description. Check your ATS match score and
          interview odds, or generate a tailored cover letter — independently.
        </p>
      </div>

      {/* ── Inputs ── */}
      <div className="grid two-col" style={{ alignItems: "start", gap: 20 }}>

        {/* CV column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
            <label style={{ fontWeight: 600, fontSize: "0.88rem" }}>Your CV / Resume</label>
            <div style={{ display: "flex", gap: 4 }}>
              {(["upload", "paste"] as const).map((m) => (
                <button
                  key={m}
                  className={inputMode === m ? "btn btn-accent" : "btn"}
                  style={{ fontSize: "0.74rem", padding: "3px 11px" }}
                  onClick={() => setInputMode(m)}
                >
                  {m === "upload" ? "Upload file" : "Paste text"}
                </button>
              ))}
            </div>
          </div>

          {inputMode === "upload" ? (
            <>
              <FileUploadZone onTextReady={setCvText} fileName={cvFileName} setFileName={setCvFileName} />
              {cvText && (
                <details style={{ marginTop: 2 }}>
                  <summary style={{ fontSize: "0.75rem", cursor: "pointer", color: "var(--muted)" }}>
                    Preview extracted text ({cvText.length.toLocaleString()} chars)
                  </summary>
                  <pre style={{
                    marginTop: 6, padding: "10px 12px", borderRadius: 8,
                    background: "var(--bg-2)", border: "1px solid var(--border)",
                    fontSize: "0.74rem", lineHeight: 1.6, maxHeight: 180,
                    overflowY: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word",
                  }}>
                    {cvText}
                  </pre>
                </details>
              )}
            </>
          ) : (
            <>
              <textarea
                value={cvText}
                onChange={(e) => { setCvText(e.target.value); setCvFileName(""); }}
                placeholder="Paste your full CV or resume text here…"
                rows={16}
                style={{
                  width: "100%", padding: "10px 12px",
                  border: "1px solid var(--border-2)", borderRadius: 8,
                  fontSize: "0.83rem", fontFamily: "inherit", resize: "vertical",
                  color: "var(--ink)", background: "var(--bg-2)", lineHeight: 1.6,
                }}
              />
              <span style={{ fontSize: "0.74rem", color: "var(--muted)" }}>{cvText.length.toLocaleString()} characters</span>
            </>
          )}
        </div>

        {/* JD column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label style={{ fontWeight: 600, fontSize: "0.88rem", marginBottom: 2 }}>Job Description</label>
          <textarea
            value={jobDescription}
            onChange={(e) => { setJD(e.target.value); resetResults(); }}
            placeholder="Paste the full job description here…"
            rows={16}
            style={{
              width: "100%", padding: "10px 12px",
              border: "1px solid var(--border-2)", borderRadius: 8,
              fontSize: "0.83rem", fontFamily: "inherit", resize: "vertical",
              color: "var(--ink)", background: "var(--bg-2)", lineHeight: 1.6,
            }}
          />
          <span style={{ fontSize: "0.74rem", color: "var(--muted)" }}>{jobDescription.length.toLocaleString()} characters</span>
        </div>
      </div>

      {/* ── Action buttons ── */}
      <div style={{ marginTop: 28, display: "flex", gap: 12, alignItems: "center", justifyContent: "center", flexWrap: "wrap" }}>
        <button
          className="btn btn-accent"
          style={ACTION_BTN}
          onClick={() => { setEvalResult(null); evalMutation.reset(); evalMutation.mutate(); }}
          disabled={evalMutation.isPending || !canAct}
        >
          {evalMutation.isPending
            ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Evaluating…</>
            : "Evaluate ATS Match"}
        </button>

        <button
          className="btn"
          style={ACTION_BTN}
          onClick={() => { setCoverLetter(""); clMutation.reset(); clMutation.mutate(); }}
          disabled={clMutation.isPending || !canAct}
        >
          {clMutation.isPending
            ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Writing…</>
            : "Generate Cover Letter"}
        </button>

        {!canAct && (
          <p style={{ width: "100%", textAlign: "center", fontSize: "0.8rem", color: "var(--muted)", margin: 0 }}>
            Add your CV and job description above to continue
          </p>
        )}
      </div>

      {/* ── Evaluation error ── */}
      {evalMutation.isError && (
        <div style={{ ...ERROR_BOX, marginTop: 16 }}>
          {(evalMutation.error as Error).message}
        </div>
      )}

      {/* ── ATS results ── */}
      {evalResult && (
        <>
          <Divider />
          <h3 style={{ textAlign: "center", marginBottom: 20 }}>ATS Evaluation</h3>
          <EvalResults result={evalResult} />
        </>
      )}

      {/* ── Cover letter error ── */}
      {clMutation.isError && (
        <div style={{ ...ERROR_BOX, marginTop: 16 }}>
          {(clMutation.error as Error).message}
        </div>
      )}

      {/* ── Cover letter result ── */}
      {coverLetter && (
        <>
          <Divider />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <h3 style={{ margin: 0 }}>Cover Letter</h3>
            <div style={{ display: "flex", gap: 8 }}>
              <CopyButton text={coverLetter} />
              <button
                className="btn-small"
                onClick={() => { setCoverLetter(""); clMutation.reset(); clMutation.mutate(); }}
              >
                Regenerate
              </button>
            </div>
          </div>
          <p style={{ fontSize: "0.78rem", color: "var(--muted)", marginBottom: 12 }}>
            Body only — no salutation or sign-off. Copy and paste directly into any application form.
          </p>
          <pre style={{
            whiteSpace: "pre-wrap", wordBreak: "break-word",
            fontSize: "0.85rem", lineHeight: 1.85, color: "var(--ink)",
            fontFamily: "inherit", background: "var(--bg-2)",
            padding: "20px 22px", borderRadius: 10,
            border: "1px solid var(--border)", margin: 0,
          }}>
            {coverLetter}
          </pre>
        </>
      )}
    </div>
  );
}
