import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { fetchCandidates, ingestCandidate, ingestPdf } from "../../api/client";
import type { CandidateProfile } from "../../api/client";

type Mode = "pdf" | "text";

export function ProfilePage() {
  const queryClient = useQueryClient();
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: fetchCandidates });
  const profile: CandidateProfile | undefined = candidates.data?.at(-1);

  const [mode, setMode] = useState<Mode>("pdf");

  // Shared fields
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState("");
  const [locations, setLocations] = useState("");
  const [salaryMin, setSalaryMin] = useState("");
  const [workType, setWorkType] = useState("any");

  // PDF mode
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Text mode
  const [cvText, setCvText] = useState("");

  const onSuccess = () => queryClient.invalidateQueries({ queryKey: ["candidates"] });

  const pdfMutation = useMutation({ mutationFn: ingestPdf, onSuccess });
  const textMutation = useMutation({ mutationFn: ingestCandidate, onSuccess });

  const isPending = pdfMutation.isPending || textMutation.isPending;
  const error = (pdfMutation.error || textMutation.error) as Error | null;

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (mode === "pdf") {
      if (!pdfFile) return;
      pdfMutation.mutate({
        file: pdfFile,
        name,
        email,
        preferred_roles: roles,
        locations,
        salary_min: salaryMin ? parseInt(salaryMin, 10) : undefined,
        work_type: workType,
      });
    } else {
      textMutation.mutate({
        name,
        email,
        raw_cv_text: cvText,
        preferred_roles: roles.split(",").map((r) => r.trim()).filter(Boolean),
        locations: locations.split(",").map((l) => l.trim()).filter(Boolean),
        salary_min: salaryMin ? parseInt(salaryMin, 10) : undefined,
        work_type: workType,
      });
    }
  };

  return (
    <div className="page">
      <h2>Candidate Profile</h2>
      <p className="muted">Upload your resume to get started</p>

      <div className="grid two-col">
        {/* Form */}
        <section className="panel">
          <div className="mode-tabs">
            <button
              className={`tab ${mode === "pdf" ? "active" : ""}`}
              onClick={() => setMode("pdf")}
              type="button"
            >
              Upload PDF
            </button>
            <button
              className={`tab ${mode === "text" ? "active" : ""}`}
              onClick={() => setMode("text")}
              type="button"
            >
              Paste Text
            </button>
          </div>

          <form onSubmit={handleSubmit} className="form" style={{ marginTop: 16 }}>
            <div className="form-row">
              <label>
                Full Name
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Jane Smith"
                />
              </label>
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="jane@example.com"
                />
              </label>
            </div>

            {mode === "pdf" ? (
              <>
                <label>Resume PDF</label>
                <div
                  className={`pdf-drop-zone ${pdfFile ? "has-file" : ""}`}
                  onClick={() => fileRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const f = e.dataTransfer.files[0];
                    if (f?.type === "application/pdf") setPdfFile(f);
                  }}
                >
                  {pdfFile ? (
                    <span>{pdfFile.name} ({(pdfFile.size / 1024).toFixed(0)} KB)</span>
                  ) : (
                    <span>Drop PDF here or click to browse</span>
                  )}
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf"
                  style={{ display: "none" }}
                  onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
                />
              </>
            ) : (
              <label>
                CV / Resume Text
                <textarea
                  value={cvText}
                  onChange={(e) => setCvText(e.target.value)}
                  placeholder="Paste your full CV/resume text here..."
                  rows={8}
                  required={mode === "text"}
                  minLength={50}
                />
              </label>
            )}

            <label>
              Preferred Roles <span className="muted">(comma-separated)</span>
              <input
                type="text"
                value={roles}
                onChange={(e) => setRoles(e.target.value)}
                placeholder="Data Scientist, ML Engineer"
              />
            </label>

            <label>
              Preferred Locations <span className="muted">(comma-separated)</span>
              <input
                type="text"
                value={locations}
                onChange={(e) => setLocations(e.target.value)}
                placeholder="Sydney, Melbourne, Remote"
              />
            </label>

            <div className="form-row">
              <label>
                Minimum Salary
                <input
                  type="number"
                  value={salaryMin}
                  onChange={(e) => setSalaryMin(e.target.value)}
                  placeholder="120000"
                />
              </label>
              <label>
                Work Type
                <select value={workType} onChange={(e) => setWorkType(e.target.value)}>
                  <option value="any">Any</option>
                  <option value="remote">Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="onsite">On-site</option>
                </select>
              </label>
            </div>

            <button
              type="submit"
              className="btn btn-accent"
              disabled={isPending || (mode === "pdf" && !pdfFile)}
            >
              {isPending ? "Analyzing resume..." : "Analyze Resume"}
            </button>

            {error && <p className="text-red">Error: {error.message}</p>}
          </form>
        </section>

        {/* Profile Display */}
        <section className="panel">
          <h3>Analyzed Profile</h3>
          {profile ? (
            <div className="profile-details">
              <div className="status-row">
                <span>Name</span>
                <strong>{profile.name}</strong>
              </div>
              <div className="status-row">
                <span>Seniority</span>
                <strong className="capitalize">{profile.seniority}</strong>
              </div>
              <div className="status-row">
                <span>Experience</span>
                <strong>{profile.years_experience} years</strong>
              </div>
              {profile.locations.length > 0 && (
                <div className="status-row">
                  <span>Locations</span>
                  <strong>{profile.locations.join(", ")}</strong>
                </div>
              )}

              <h4>Skills ({profile.skills.length})</h4>
              <div className="tag-list">
                {profile.skills.map((s) => (
                  <span key={s} className="tag">{s}</span>
                ))}
              </div>

              <h4>Domains</h4>
              <div className="tag-list">
                {profile.domains.length > 0
                  ? profile.domains.map((d) => (
                      <span key={d} className="tag tag-domain">{d}</span>
                    ))
                  : <span className="muted">None detected</span>}
              </div>

              <h4>Strengths</h4>
              <ul>
                {profile.strengths.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>

              <h4>Skill Gaps</h4>
              <div className="tag-list">
                {profile.skill_gaps.length > 0
                  ? profile.skill_gaps.map((g) => (
                      <span key={g} className="tag tag-gap">{g}</span>
                    ))
                  : <span className="muted">None detected</span>}
              </div>

              {profile.summary && (
                <>
                  <h4>Summary</h4>
                  <p className="summary-text">{profile.summary}</p>
                </>
              )}

              <div style={{ marginTop: 16 }}>
                <a href="/pipeline" className="btn btn-accent">
                  Run Full Pipeline
                </a>
              </div>
            </div>
          ) : (
            <p className="muted">Upload your resume to see the AI-extracted profile</p>
          )}
        </section>
      </div>
    </div>
  );
}
