import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { checkDuplicate, extractJobData, logApplication, uploadJATSDocument } from "../../api/client";
import type { ExtractedJobData, LogApplicationRequest } from "../../api/client";

const PLATFORMS = ["LinkedIn", "Seek", "Indeed", "Glassdoor", "Direct", "Referral", "Other"];
const CURRENCIES = ["AUD", "USD", "GBP", "EUR", "CAD", "NZD", "SGD"];
const REMOTE_TYPES = ["remote", "hybrid", "onsite"];
const SENIORITY_LEVELS = ["junior", "mid", "senior", "staff", "principal"];
const EMPLOYMENT_TYPES = ["fulltime", "parttime", "contract", "casual"];
const STATUSES = ["applied", "saved", "interview", "offer", "rejected", "withdrawn"];
const DOCUMENT_ACCEPT = ".pdf,.txt,.doc,.docx";

function fitScoreColor(score: number) {
  if (score >= 81) return "#2e8b57";   // green
  if (score >= 61) return "#2980b9";   // blue
  if (score >= 41) return "#d4a017";   // amber
  return "#c0392b";                     // red
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function formatSelectedFiles(files: File[]) {
  if (!files.length) return "No files selected";
  return files.map((file) => file.name).join(", ");
}

export function LogApplicationPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // NLP extract
  const [jobDescription, setJobDescription] = useState("");
  const [showExtract, setShowExtract] = useState(true);

  // Form fields
  const [company, setCompany] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [platform, setPlatform] = useState("LinkedIn");
  const [dateApplied, setDateApplied] = useState(today());
  const [status, setStatus] = useState("applied");
  const [locationCity, setLocationCity] = useState("");
  const [locationCountry, setLocationCountry] = useState("Australia");
  const [remoteType, setRemoteType] = useState("");
  const [salaryMin, setSalaryMin] = useState("");
  const [salaryMax, setSalaryMax] = useState("");
  const [currency, setCurrency] = useState("AUD");
  const [industry, setIndustry] = useState("");
  const [seniority, setSeniority] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [notes, setNotes] = useState("");
  const [requiredSkills, setRequiredSkills] = useState("");
  const [preferredSkills, setPreferredSkills] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [fitScore, setFitScore] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [coverLetterFile, setCoverLetterFile] = useState<File | null>(null);
  const [otherFiles, setOtherFiles] = useState<File[]>([]);
  const [dupWarning, setDupWarning] = useState<{ id: string; status: string; date_applied: string } | null>(null);
  const [dupConfirmed, setDupConfirmed] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [savedDocumentCount, setSavedDocumentCount] = useState(0);
  const [uploadWarning, setUploadWarning] = useState<string | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);

  const [extractedAny, setExtractedAny] = useState(false);

  const extractMutation = useMutation({
    mutationFn: () => extractJobData(jobDescription),
    onSuccess: (data: ExtractedJobData) => {
      let anyField = false;
      if (data.role_title) { setRoleTitle(data.role_title); anyField = true; }
      if (data.company) { setCompany(data.company); anyField = true; }
      if (data.location_city) { setLocationCity(data.location_city); anyField = true; }
      if (data.location_country) { setLocationCountry(data.location_country); anyField = true; }
      if (data.remote_type) { setRemoteType(data.remote_type); anyField = true; }
      if (data.salary_min) { setSalaryMin(String(data.salary_min)); anyField = true; }
      if (data.salary_max) { setSalaryMax(String(data.salary_max)); anyField = true; }
      if (data.currency) { setCurrency(data.currency); anyField = true; }
      if (data.industry) { setIndustry(data.industry); anyField = true; }
      if (data.seniority) { setSeniority(data.seniority); anyField = true; }
      if (data.employment_type) { setEmploymentType(data.employment_type); anyField = true; }
      if (data.required_skills?.length) { setRequiredSkills(data.required_skills.join(", ")); anyField = true; }
      if (data.preferred_skills?.length) { setPreferredSkills(data.preferred_skills.join(", ")); anyField = true; }
      // Extra fields from structured form paste
      if (data.platform && PLATFORMS.includes(data.platform)) { setPlatform(data.platform); anyField = true; }
      if (data.date_applied) { setDateApplied(data.date_applied); anyField = true; }
      if (data.contact_name) { setContactName(data.contact_name); anyField = true; }
      if (data.contact_email) { setContactEmail(data.contact_email); anyField = true; }
      if (data.job_url) { setJobUrl(data.job_url); anyField = true; }
      if (data.notes) { setNotes(data.notes); anyField = true; }
      if (data.fit_score != null) { setFitScore(String(data.fit_score)); anyField = true; }
      setExtractedAny(anyField);
      setShowExtract(false);
      // Run duplicate check with the just-extracted values (state hasn't updated yet)
      const extractedCompany = data.company?.trim() ?? "";
      const extractedRole = data.role_title?.trim() ?? "";
      if (extractedCompany.length > 1 && extractedRole.length > 1) {
        checkDuplicate(extractedCompany, extractedRole)
          .then((dup) => {
            if (dup.exists) {
              setDupWarning({ id: dup.id!, status: dup.status!, date_applied: dup.date_applied! });
              setDupConfirmed(false);
            }
          })
          .catch(() => {});
      }
    },
  });

  const dupMutation = useMutation({
    mutationFn: () => checkDuplicate(company.trim(), roleTitle.trim()),
    onSuccess: (data) => {
      if (data.exists) {
        setDupWarning({ id: data.id!, status: data.status!, date_applied: data.date_applied! });
      } else {
        setDupWarning(null);
      }
    },
  });

  const logMutation = useMutation({
    mutationFn: async (payload: LogApplicationRequest) => {
      const saved = await logApplication(payload);
      const uploads: Array<Promise<unknown>> = [];
      const failures: string[] = [];

      const queueUpload = (category: "resume" | "cover_letter" | "other", file: File) => {
        uploads.push(
          uploadJATSDocument(saved.id, { category, file }).catch((error: Error) => {
            failures.push(`${file.name}: ${error.message}`);
          })
        );
      };

      if (resumeFile) queueUpload("resume", resumeFile);
      if (coverLetterFile) queueUpload("cover_letter", coverLetterFile);
      otherFiles.forEach((file) => queueUpload("other", file));

      if (uploads.length) {
        await Promise.all(uploads);
      }

      return {
        saved,
        uploadedCount: [resumeFile, coverLetterFile, ...otherFiles].filter(Boolean).length - failures.length,
        failures,
      };
    },
    onSuccess: ({ saved, uploadedCount, failures }) => {
      setSavedId(saved.id);
      setSavedDocumentCount(uploadedCount);
      setUploadWarning(failures.length ? failures.join(" | ") : null);
      queryClient.invalidateQueries({ queryKey: ["jats-applications"] });
      queryClient.invalidateQueries({ queryKey: ["jats-application", saved.id] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
  });

  const handleDuplicateCheck = () => {
    if (company.trim().length > 1 && roleTitle.trim().length > 1) {
      setDupConfirmed(false);
      dupMutation.mutate();
    }
  };

  const addDays = (n: number) => {
    const d = new Date();
    d.setDate(d.getDate() + n);
    setFollowUpDate(d.toISOString().slice(0, 10));
  };

  const handleExtract = () => {
    if (jobDescription.trim().length < 50) return;
    extractMutation.mutate();
  };

  const resetDocumentInputs = () => {
    setResumeFile(null);
    setCoverLetterFile(null);
    setOtherFiles([]);
    setFileInputKey((key) => key + 1);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!company.trim() || !roleTitle.trim()) return;
    if (dupWarning && !dupConfirmed) return; // block until user explicitly confirms
    setUploadWarning(null);
    logMutation.mutate({
      company: company.trim(),
      role_title: roleTitle.trim(),
      platform,
      date_applied: dateApplied,
      status,
      location_city: locationCity || null,
      location_country: locationCountry || null,
      remote_type: remoteType || null,
      salary_min: salaryMin ? parseInt(salaryMin, 10) : null,
      salary_max: salaryMax ? parseInt(salaryMax, 10) : null,
      currency,
      industry: industry.trim() || null,
      seniority: seniority || null,
      employment_type: employmentType || null,
      description_raw: jobDescription,
      notes,
      required_skills: requiredSkills.split(",").map((s) => s.trim()).filter(Boolean),
      preferred_skills: preferredSkills.split(",").map((s) => s.trim()).filter(Boolean),
      job_url: jobUrl || null,
      contact_name: contactName || null,
      contact_email: contactEmail || null,
      follow_up_date: followUpDate || null,
      fit_score: fitScore ? Math.min(100, Math.max(0, parseInt(fitScore, 10))) : null,
    });
  };

  if (savedId) {
    return (
      <div className="page">
        <div className="panel" style={{ textAlign: "center", padding: "48px 24px" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: 12 }}>✓</div>
          <h2 style={{ marginBottom: 8 }}>Application Logged</h2>
          <p className="muted" style={{ marginBottom: 24 }}>
            {roleTitle} at {company} has been saved to your tracker.
          </p>
          {savedDocumentCount > 0 && (
            <p className="muted" style={{ marginBottom: 12 }}>
              {savedDocumentCount} document{savedDocumentCount !== 1 ? "s" : ""} attached.
            </p>
          )}
          {uploadWarning && (
            <p className="text-red" style={{ marginBottom: 24, fontSize: "0.88rem" }}>
              Application saved, but some uploads failed: {uploadWarning}
            </p>
          )}
          <div className="button-row" style={{ justifyContent: "center" }}>
            <button className="btn btn-accent" onClick={() => navigate("/my-applications")}>
              View All Applications
            </button>
            <button
              className="btn"
              onClick={() => {
                setSavedId(null);
                setSavedDocumentCount(0);
                setUploadWarning(null);
                setCompany(""); setRoleTitle(""); setJobDescription("");
                setLocationCity(""); setLocationCountry("Australia"); setRemoteType("");
                setSalaryMin(""); setSalaryMax(""); setIndustry("");
                setSeniority(""); setEmploymentType(""); setNotes("");
                setRequiredSkills(""); setPreferredSkills("");
                setPlatform("LinkedIn"); setDateApplied(today()); setStatus("applied");
                setJobUrl(""); setContactName(""); setContactEmail("");
                setFollowUpDate(""); setFitScore(""); setDupWarning(null); setDupConfirmed(false);
                resetDocumentInputs();
                setShowExtract(true);
              }}
            >
              Log Another
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>Log Application</h2>
      <p className="muted">Record a job application — paste the job description for AI-assisted field extraction</p>

      <div className="grid two-col" style={{ marginTop: 16, alignItems: "start" }}>
        {/* Left: NLP Extractor */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {showExtract && (
            <section className="panel">
              <h3>Step 1 — Paste Job Description</h3>
              <p className="muted" style={{ marginBottom: 12, fontSize: "0.85rem" }}>
                Paste the job posting text and let AI extract company, role, skills, salary and more.
              </p>
              <textarea
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                placeholder="Paste the full job description here..."
                rows={10}
                style={{
                  width: "100%", padding: "10px 12px", border: "1px solid var(--border-2)",
                  borderRadius: 8, fontSize: "0.88rem", fontFamily: "inherit",
                  resize: "vertical", color: "var(--ink)", background: "var(--bg-2)",
                  lineHeight: 1.6,
                }}
              />
              <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                <button
                  className="btn btn-accent"
                  onClick={handleExtract}
                  disabled={extractMutation.isPending || jobDescription.trim().length < 50}
                >
                  {extractMutation.isPending ? (
                    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                      Extracting...
                    </span>
                  ) : "Extract with AI"}
                </button>
                <button className="btn" onClick={() => setShowExtract(false)}>
                  Skip — Fill Manually
                </button>
              </div>
              {extractMutation.isError && (
                <p className="text-red" style={{ marginTop: 8, fontSize: "0.85rem" }}>
                  Extraction failed — fields will be empty, fill manually.
                </p>
              )}
            </section>
          )}

          {!showExtract && (
            <section className="panel" style={{ padding: "12px 16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{
                  fontSize: "0.88rem", fontWeight: 600,
                  color: extractMutation.isSuccess
                    ? (extractedAny ? "var(--green)" : "var(--amber, #c8860a)")
                    : "var(--ink)",
                }}>
                  {extractMutation.isSuccess
                    ? (extractedAny
                      ? "Extraction complete — fields pre-filled"
                      : "Nothing extracted — AI may not be configured, fill manually")
                    : "Filling manually"}
                </span>
                <button className="btn-small" onClick={() => setShowExtract(true)}>
                  Re-extract
                </button>
              </div>
            </section>
          )}
        </div>

        {/* Right: Form */}
        <section className="panel">
          <h3>Step 2 — Application Details</h3>
          <form onSubmit={handleSubmit} className="form" style={{ marginTop: 12 }}>
            {/* Core */}
            <div className="form-row">
              <label>
                Company *
                <input value={company} onChange={(e) => { setCompany(e.target.value); setDupWarning(null); setDupConfirmed(false); }}
                  onBlur={handleDuplicateCheck}
                  placeholder="Google" required />
              </label>
              <label>
                Role Title *
                <input value={roleTitle} onChange={(e) => { setRoleTitle(e.target.value); setDupWarning(null); setDupConfirmed(false); }}
                  onBlur={handleDuplicateCheck}
                  placeholder="Senior Software Engineer" required />
              </label>
            </div>

            <div className="form-row">
              <label>
                Platform
                <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
                  {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              <label>
                Date Applied
                <input type="date" value={dateApplied}
                  onChange={(e) => setDateApplied(e.target.value)} />
              </label>
              <label>
                Status
                <select value={status} onChange={(e) => setStatus(e.target.value)}>
                  {STATUSES.map((s) => (
                    <option key={s} value={s} className="capitalize">{s}</option>
                  ))}
                </select>
              </label>
            </div>

            {/* Location */}
            <div className="form-row">
              <label>
                City
                <input value={locationCity} onChange={(e) => setLocationCity(e.target.value)}
                  placeholder="Sydney" />
              </label>
              <label>
                Country
                <input value={locationCountry} onChange={(e) => setLocationCountry(e.target.value)}
                  placeholder="Australia" />
              </label>
              <label>
                Work Type
                <select value={remoteType} onChange={(e) => setRemoteType(e.target.value)}>
                  <option value="">— Not specified</option>
                  {REMOTE_TYPES.map((r) => (
                    <option key={r} value={r} className="capitalize">{r}</option>
                  ))}
                </select>
              </label>
            </div>

            {/* Salary */}
            <div className="form-row">
              <label>
                Salary Min
                <input type="number" value={salaryMin}
                  onChange={(e) => setSalaryMin(e.target.value)} placeholder="120000" />
              </label>
              <label>
                Salary Max
                <input type="number" value={salaryMax}
                  onChange={(e) => setSalaryMax(e.target.value)} placeholder="160000" />
              </label>
              <label>
                Currency
                <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>

            {/* Classification */}
            <div className="form-row">
              <label>
                Industry
                <input
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  placeholder="Government, Education, Climate Tech..."
                />
              </label>
              <label>
                Seniority
                <select value={seniority} onChange={(e) => setSeniority(e.target.value)}>
                  <option value="">— Not specified</option>
                  {SENIORITY_LEVELS.map((l) => (
                    <option key={l} value={l} className="capitalize">{l}</option>
                  ))}
                </select>
              </label>
              <label>
                Employment Type
                <select value={employmentType} onChange={(e) => setEmploymentType(e.target.value)}>
                  <option value="">— Not specified</option>
                  {EMPLOYMENT_TYPES.map((t) => (
                    <option key={t} value={t} className="capitalize">{t}</option>
                  ))}
                </select>
              </label>
            </div>

            {/* Job URL */}
            <label>
              Job Posting URL
              <input value={jobUrl} onChange={(e) => setJobUrl(e.target.value)}
                placeholder="https://linkedin.com/jobs/view/..." type="url" />
            </label>

            {/* Contact */}
            <div className="form-row">
              <label>
                Recruiter / Contact Name
                <input value={contactName} onChange={(e) => setContactName(e.target.value)}
                  placeholder="Jane Smith" />
              </label>
              <label>
                Contact Email
                <input value={contactEmail} onChange={(e) => setContactEmail(e.target.value)}
                  placeholder="jane@company.com" type="email" />
              </label>
            </div>

            {/* Follow-up */}
            <div>
              <label>
                Follow-up Reminder
                <input type="date" value={followUpDate} onChange={(e) => setFollowUpDate(e.target.value)} />
              </label>
              <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                {[7, 14, 21, 30].map((n) => (
                  <button key={n} type="button" className="btn-small" onClick={() => addDays(n)}>
                    +{n}d
                  </button>
                ))}
                {followUpDate && (
                  <button type="button" className="btn-small" onClick={() => setFollowUpDate("")}>
                    Clear
                  </button>
                )}
              </div>
            </div>

            {/* Fit Score */}
            <div>
              <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>
                  Fit to Role
                  <span className="muted" style={{ fontWeight: 400, marginLeft: 6 }}>(0 – 100, your estimate)</span>
                </span>
                {fitScore !== "" && (
                  <span style={{
                    fontWeight: 700, fontSize: "1.1rem",
                    color: fitScoreColor(parseInt(fitScore, 10)),
                  }}>
                    {fitScore}
                  </span>
                )}
              </label>
              <input
                type="range" min={0} max={100} step={1}
                value={fitScore === "" ? 50 : fitScore}
                onChange={(e) => setFitScore(e.target.value)}
                onMouseDown={() => { if (fitScore === "") setFitScore("50"); }}
                style={{ width: "100%", marginTop: 4 }}
              />
              {fitScore === "" && (
                <p className="muted" style={{ fontSize: "0.78rem", marginTop: 2 }}>
                  Move the slider to set a score
                </p>
              )}
            </div>

            {/* Skills */}
            <label>
              Required Skills <span className="muted">(comma-separated)</span>
              <input value={requiredSkills} onChange={(e) => setRequiredSkills(e.target.value)}
                placeholder="Python, React, AWS, SQL" />
            </label>
            <label>
              Preferred Skills <span className="muted">(comma-separated)</span>
              <input value={preferredSkills} onChange={(e) => setPreferredSkills(e.target.value)}
                placeholder="Kubernetes, GraphQL" />
            </label>

            <label>
              Notes
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                placeholder="Any notes about this application..." rows={3} />
            </label>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <h4 style={{ margin: 0 }}>Submitted Documents</h4>
              <label>
                Resume File
                <input
                  key={`resume-${fileInputKey}`}
                  type="file"
                  accept={DOCUMENT_ACCEPT}
                  onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
                />
                <span className="muted" style={{ fontSize: "0.8rem" }}>
                  {resumeFile ? resumeFile.name : "PDF, DOC, DOCX, or TXT"}
                </span>
              </label>
              <label>
                Cover Letter File
                <input
                  key={`cover-${fileInputKey}`}
                  type="file"
                  accept={DOCUMENT_ACCEPT}
                  onChange={(e) => setCoverLetterFile(e.target.files?.[0] ?? null)}
                />
                <span className="muted" style={{ fontSize: "0.8rem" }}>
                  {coverLetterFile ? coverLetterFile.name : "Optional attachment for the submitted cover letter"}
                </span>
              </label>
              <label>
                Other Supporting Documents
                <input
                  key={`other-${fileInputKey}`}
                  type="file"
                  accept={DOCUMENT_ACCEPT}
                  multiple
                  onChange={(e) => setOtherFiles(Array.from(e.target.files ?? []))}
                />
                <span className="muted" style={{ fontSize: "0.8rem" }}>
                  {formatSelectedFiles(otherFiles)}
                </span>
              </label>
            </div>

            {dupWarning && (
              <div style={{
                padding: "10px 14px", borderRadius: 8,
                background: dupConfirmed ? "#f0fff4" : "#fff8e1",
                border: `1px solid ${dupConfirmed ? "#4caf50" : "#f0c040"}`,
                fontSize: "0.85rem",
                color: dupConfirmed ? "#2e7d32" : "#7a5800",
              }}>
                {dupConfirmed ? (
                  <span>
                    <strong>Duplicate confirmed —</strong> saving as a new application.{" "}
                    <button type="button" className="btn-small"
                      onClick={() => setDupConfirmed(false)}
                      style={{ marginLeft: 8 }}>Undo</button>
                  </span>
                ) : (
                  <>
                    <strong>Duplicate detected:</strong> You already have{" "}
                    <em>{roleTitle}</em> at <em>{company}</em> logged on{" "}
                    {dupWarning.date_applied} (status: <em>{dupWarning.status}</em>).
                    <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 10 }}>
                      <button
                        type="button"
                        className="btn btn-accent"
                        style={{ fontSize: "0.82rem", padding: "4px 12px" }}
                        onClick={() => setDupConfirmed(true)}
                      >
                        Save Anyway
                      </button>
                      <span style={{ fontSize: "0.8rem", opacity: 0.8 }}>
                        Only if this is genuinely a new application
                      </span>
                    </div>
                  </>
                )}
              </div>
            )}

            {logMutation.isError && (
              <p className="text-red" style={{ fontSize: "0.88rem" }}>
                Error: {(logMutation.error as Error).message}
              </p>
            )}

            <button
              type="submit"
              className="btn btn-accent"
              disabled={logMutation.isPending || !company.trim() || !roleTitle.trim() || (!!dupWarning && !dupConfirmed)}
            >
              {logMutation.isPending ? (
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  Saving...
                </span>
              ) : "Save Application"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
