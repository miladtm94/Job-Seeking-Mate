/**
 * Settings page — configure AI provider (including LM Studio), thresholds, etc.
 *
 * AI provider hierarchy:
 *   1. Anthropic         — cloud provider, API key required
 *   2. OpenAI            — cloud, very capable, API key required
 *   3. Google Gemini     — cloud, free tier available, API key required
 *   4. LM Studio         — LOCAL, 100% free, no API key, runs on your machine
 *   5. Ollama            — LOCAL, 100% free, no API key, runs on your machine
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchSettings,
  updateSettings,
  pingAIProvider,
  resetSettings,
  type AppSettings,
} from "../../api/client";

// ── provider metadata ─────────────────────────────────────────────────────────

interface ProviderInfo {
  id: string;
  name: string;
  icon: string;
  desc: string;
  badge: "free" | "key" | "local";
  badgeLabel: string;
  setupNote?: string;
  showUrlField?: boolean;
  showModelField?: boolean;
  urlField?: keyof AppSettings;
  modelField?: keyof AppSettings;
}

const PROVIDERS: ProviderInfo[] = [
  {
    id: "anthropic",
    name: "Anthropic",
    icon: "🤖",
    desc: "Cloud model provider for reasoning and writing",
    badge: "key",
    badgeLabel: "API Key",
    showModelField: true,
    modelField: "ai_model",
  },
  {
    id: "openai",
    name: "OpenAI",
    icon: "⚡",
    desc: "ChatGPT / GPT-4o — widely compatible",
    badge: "key",
    badgeLabel: "API Key",
    showModelField: true,
    modelField: "ai_model",
  },
  {
    id: "gemini",
    name: "Gemini",
    icon: "✨",
    desc: "Google — free tier available",
    badge: "free",
    badgeLabel: "Free Tier",
    showModelField: true,
    modelField: "ai_model",
  },
  {
    id: "lmstudio",
    name: "LM Studio",
    icon: "💻",
    desc: "Local — 100% free, no API key, fully private",
    badge: "local",
    badgeLabel: "Local",
    setupNote: "Open LM Studio → Local Server → load a model → Start Server",
    showUrlField: true,
    showModelField: true,
    urlField: "lmstudio_base_url",
    modelField: "lmstudio_model",
  },
];

// ── subcomponents ──────────────────────────────────────────────────────────────

function ProviderCard({
  info,
  selected,
  hasKey,
  onSelect,
}: {
  info: ProviderInfo;
  selected: boolean;
  hasKey: boolean;
  onSelect: () => void;
}) {
  const badgeClass =
    info.badge === "free" ? "badge-free" : info.badge === "local" ? "badge-local" : "badge-key";

  return (
    <div
      className={`provider-card${selected ? " selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
    >
      <span className="provider-icon">{info.icon}</span>
      <span className="provider-name">{info.name}</span>
      <span className="provider-desc">{info.desc}</span>
      <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
        <span className={`provider-badge ${badgeClass}`}>{info.badgeLabel}</span>
        {info.badge === "key" && (
          <span className={`provider-badge ${hasKey ? "badge-free" : "badge-key"}`}>
            {hasKey ? "✓ Key set" : "No key"}
          </span>
        )}
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export function SettingsPage() {
  const qc = useQueryClient();

  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
    staleTime: 30_000,
  });

  const saveMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setSaveMsg("✓ Saved");
      setTimeout(() => setSaveMsg(""), 2000);
    },
    onError: () => setSaveMsg("✗ Save failed"),
  });

  const resetMutation = useMutation({
    mutationFn: resetSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setSaveMsg("✓ Settings reset to defaults");
      setTimeout(() => setSaveMsg(""), 2500);
    },
  });

  const [pingState, setPingState] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [pingMsg, setPingMsg]     = useState("");
  const [saveMsg, setSaveMsg]     = useState("");

  // Local form state (initialised from server)
  const [provider,    setProvider]    = useState<string>("");
  const [model,       setModel]       = useState<string>("");
  const [scoreModel,  setScoreModel]  = useState<string>("");
  const [lmUrl,       setLmUrl]       = useState<string>("");
  const [lmModel,     setLmModel]     = useState<string>("");
  const [applyThresh, setApplyThresh] = useState<number>(75);
  const [rejectThresh,setRejectThresh]= useState<number>(60);
  const [hydrated,    setHydrated]    = useState(false);

  // Hydrate form from server data once
  if (settings && !hydrated) {
    setProvider(settings.ai_provider);
    setModel(settings.ai_model);
    setScoreModel(settings.ai_score_model ?? "");
    setLmUrl(settings.lmstudio_base_url);
    setLmModel(settings.lmstudio_model);
    setApplyThresh(settings.auto_apply_threshold);
    setRejectThresh(settings.match_reject_threshold);
    setHydrated(true);
  }

  const selectedProviderInfo = PROVIDERS.find((p) => p.id === provider);

  const handleSave = () => {
    saveMutation.mutate({
      ai_provider:            provider,
      ai_model:               model,
      ai_score_model:         scoreModel,
      lmstudio_base_url:      lmUrl,
      lmstudio_model:         lmModel,
      auto_apply_threshold:   applyThresh,
      match_reject_threshold: rejectThresh,
    });
  };

  const handlePing = async () => {
    setPingState("testing");
    setPingMsg("");
    try {
      const res = await pingAIProvider(provider);
      if (res.ok) {
        setPingState("ok");
        setPingMsg(`✓ Connected — model: ${res.model}`);
      } else {
        setPingState("fail");
        setPingMsg(`✗ ${res.error ?? "No response"}`);
      }
    } catch (e: any) {
      setPingState("fail");
      setPingMsg(`✗ ${e?.message ?? "Connection failed"}`);
    }
  };

  if (isLoading) {
    return (
      <div className="page">
        <div className="page-header">
          <h2>Settings</h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, color: "var(--muted)" }}>
          <div className="spinner" /> Loading settings…
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <h2>Settings</h2>
        <p className="muted">Configure AI provider, models, and application thresholds.</p>
      </div>

      {/* ── AI Provider ─────────────────────────────────────────────────── */}
      <div className="settings-section">
        <div className="settings-section-title">AI Provider</div>

        <div className="provider-grid">
          {PROVIDERS.map((p) => (
            <ProviderCard
              key={p.id}
              info={p}
              selected={provider === p.id}
              hasKey={
                p.id === "anthropic" ? (settings?.has_anthropic ?? false) :
                p.id === "openai"    ? (settings?.has_openai    ?? false) :
                p.id === "gemini"    ? (settings?.has_gemini    ?? false) : true
              }
              onSelect={() => {
                setProvider(p.id);
                setPingState("idle");
                setPingMsg("");
              }}
            />
          ))}
        </div>

        {/* Provider-specific setup note */}
        {selectedProviderInfo?.setupNote && (
          <div style={{
            padding: "10px 14px",
            borderRadius: "var(--radius)",
            background: "var(--tag-blue-bg)",
            border: "1px solid rgba(96,165,250,0.2)",
            fontSize: "0.84rem",
            color: "var(--blue)",
            marginBottom: 14,
          }}>
            <strong>Setup:</strong> {selectedProviderInfo.setupNote}
          </div>
        )}

        {/* Model / URL fields depending on selected provider */}
        <div className="form" style={{ maxWidth: 520 }}>
          {/* URL field (LM Studio / Ollama) */}
          {selectedProviderInfo?.showUrlField && (
            <label>
              {provider === "lmstudio" ? "LM Studio Server URL" : "Ollama Base URL"}
              <input
                type="text"
                value={lmUrl}
                onChange={(e) => setLmUrl(e.target.value)}
                placeholder={provider === "lmstudio" ? "http://localhost:1234/v1" : "http://localhost:11434"}
                style={{ marginTop: 6 }}
              />
            </label>
          )}

          {/* Model name */}
          {selectedProviderInfo?.showModelField && (
            <label>
              Model Name
              <input
                type="text"
                value={provider === "lmstudio" ? lmModel : model}
                onChange={(e) => provider === "lmstudio" ? setLmModel(e.target.value) : setModel(e.target.value)}
                placeholder={
                  provider === "lmstudio"  ? "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF" :
                  provider === "ollama"    ? "llama3.2" :
                  provider === "anthropic" ? "claude-sonnet-4-20250514" :
                  provider === "openai"    ? "gpt-4o" :
                  "gemini-2.5-flash"
                }
                style={{ marginTop: 6 }}
              />
              {provider === "lmstudio" && (
                <span className="muted" style={{ marginTop: 4 }}>
                  Must match the model ID shown in the LM Studio server panel.
                </span>
              )}
            </label>
          )}

          {/* Optional fast score model */}
          {!["lmstudio", "ollama"].includes(provider) && (
            <label>
              Score Model (optional)
              <input
                type="text"
                value={scoreModel}
                onChange={(e) => setScoreModel(e.target.value)}
                placeholder="Leave empty to use the same model for all tasks"
                style={{ marginTop: 6 }}
              />
              <span className="muted" style={{ marginTop: 4 }}>
                A faster/cheaper model used only for job scoring (e.g. gemini-2.0-flash, gpt-4o-mini).
              </span>
            </label>
          )}
        </div>

        {/* Connection test */}
        <div className="connection-test" style={{ marginTop: 16 }}>
          <button
            className="btn"
            onClick={handlePing}
            disabled={pingState === "testing"}
            style={{ minWidth: 140 }}
          >
            {pingState === "testing" ? (
              <><div className="spinner" style={{ width: 14, height: 14 }} /> Testing…</>
            ) : "Test Connection"}
          </button>
          {pingMsg && (
            <span style={{
              fontSize: "0.86rem",
              color: pingState === "ok" ? "var(--green)" : "var(--red)",
              fontWeight: 600,
            }}>
              {pingMsg}
            </span>
          )}
          {pingState === "idle" && !pingMsg && (
            <span className="muted" style={{ fontSize: "0.82rem" }}>
              Verify the AI provider is reachable before saving.
            </span>
          )}
        </div>
      </div>

      {/* ── Application Thresholds ───────────────────────────────────────── */}
      <div className="settings-section">
        <div className="settings-section-title">Application Thresholds</div>
        <div className="form" style={{ maxWidth: 400 }}>
          <label>
            Auto-Apply Threshold (0–100)
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 6 }}>
              <input
                type="range" min={50} max={95} step={5}
                value={applyThresh}
                onChange={(e) => setApplyThresh(Number(e.target.value))}
                style={{ flex: 1, accentColor: "var(--accent)" }}
              />
              <span style={{ fontWeight: 700, minWidth: 32, fontSize: "1rem" }}>{applyThresh}</span>
            </div>
            <span className="muted" style={{ marginTop: 4 }}>
              Jobs scoring at or above this are shown for your approval before applying.
            </span>
          </label>

          <label>
            Reject Threshold (0–100)
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 6 }}>
              <input
                type="range" min={30} max={70} step={5}
                value={rejectThresh}
                onChange={(e) => setRejectThresh(Number(e.target.value))}
                style={{ flex: 1, accentColor: "var(--accent)" }}
              />
              <span style={{ fontWeight: 700, minWidth: 32, fontSize: "1rem" }}>{rejectThresh}</span>
            </div>
            <span className="muted" style={{ marginTop: 4 }}>
              Jobs scoring below this are automatically skipped (never shown).
            </span>
          </label>
        </div>
      </div>

      {/* ── API Key Status ───────────────────────────────────────────────── */}
      <div className="settings-section">
        <div className="settings-section-title">API Key Status</div>
        <div className="panel" style={{ maxWidth: 420 }}>
          {[
            { label: "Anthropic",          ok: settings?.has_anthropic },
            { label: "OpenAI (ChatGPT)",   ok: settings?.has_openai },
            { label: "Google Gemini",      ok: settings?.has_gemini },
          ].map((item) => (
            <div className="status-row" key={item.label}>
              <span>{item.label}</span>
              <span style={{
                fontWeight: 700,
                fontSize: "0.82rem",
                color: item.ok ? "var(--green)" : "var(--dim)",
              }}>
                {item.ok ? "✓ Configured" : "Not set"}
              </span>
            </div>
          ))}
          <p className="muted" style={{ marginTop: 10, fontSize: "0.8rem" }}>
            API keys are set in your <code>.env</code> file and are never shown here.
          </p>
        </div>
      </div>

      {/* ── LM Studio guide ──────────────────────────────────────────────── */}
      <div className="settings-section">
        <div className="settings-section-title">Using LM Studio (Local AI)</div>
        <div className="panel" style={{ maxWidth: 620 }}>
          <p style={{ fontSize: "0.9rem", lineHeight: 1.7, marginBottom: 12 }}>
            Run AI <strong>100% locally</strong> for free — no API key, no data leaves your machine.
          </p>
          <ol style={{ paddingLeft: 20, fontSize: "0.88rem", lineHeight: 2, color: "var(--muted)" }}>
            <li>Download <strong style={{ color: "var(--ink)" }}>LM Studio</strong> from lmstudio.ai</li>
            <li>Search for and download a model (e.g. <code>Llama 3.2 3B</code>, <code>Phi-4</code>, <code>Qwen 2.5</code>)</li>
            <li>Open the <strong style={{ color: "var(--ink)" }}>Local Server</strong> tab → select your model → click <strong style={{ color: "var(--ink)" }}>Start Server</strong></li>
            <li>Copy the model identifier shown at the top of the server panel</li>
            <li>Select <strong style={{ color: "var(--ink)" }}>LM Studio</strong> above, paste the model name, and click Save</li>
          </ol>
          <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: "var(--radius)", background: "var(--tag-yellow-bg)", border: "1px solid rgba(251,191,36,0.2)", fontSize: "0.82rem", color: "var(--yellow)" }}>
            <strong>Tip:</strong> Larger models (7B+) give better results but are slower. 3–4B models are a good balance for job matching on a laptop.
          </div>
        </div>
      </div>

      {/* ── Save / Reset ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <button
          className="btn btn-accent"
          onClick={handleSave}
          disabled={saveMutation.isPending}
          style={{ minWidth: 120 }}
        >
          {saveMutation.isPending ? "Saving…" : "Save Settings"}
        </button>

        <button
          className="btn btn-secondary"
          onClick={() => resetMutation.mutate()}
          disabled={resetMutation.isPending}
          style={{ color: "var(--muted)" }}
        >
          Reset to defaults
        </button>

        {saveMsg && (
          <span style={{
            fontSize: "0.88rem",
            fontWeight: 700,
            color: saveMsg.startsWith("✓") ? "var(--green)" : "var(--red)",
          }}>
            {saveMsg}
          </span>
        )}
      </div>
    </div>
  );
}
