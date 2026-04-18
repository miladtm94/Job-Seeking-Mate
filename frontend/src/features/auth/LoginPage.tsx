import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginUser } from "../../api/client";
import { useAuth } from "../../contexts/AuthContext";

export function LoginPage() {
  const { login }  = useAuth();
  const navigate   = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { access_token } = await loginUser(username, password);
      login(access_token);
      navigate("/");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (msg === "Unauthorized" || msg.includes("401")) {
        setError("Invalid username or password");
      } else if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
        setError("Cannot reach server — is the backend running?");
      } else {
        setError("Login failed — check the browser console for details");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "#0d0f18",
      backgroundImage: "radial-gradient(ellipse at 30% 20%, rgba(108,99,255,0.12) 0%, transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(96,165,250,0.08) 0%, transparent 50%)",
    }}>
      <div style={{ width: "100%", maxWidth: 400, padding: "0 20px" }}>

        {/* Brand */}
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <h1 style={{
            margin: 0,
            fontSize: "1.6rem",
            fontWeight: 900,
            letterSpacing: "-0.04em",
            background: "linear-gradient(135deg, #a78bfa, #60a5fa)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}>
            Job‑Seeking Mate
          </h1>
          <p style={{ margin: "8px 0 0", color: "#7b88a8", fontSize: "0.88rem" }}>
            Your AI-powered job hunting agent
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          style={{
            background: "rgba(255,255,255,0.04)",
            padding: "32px 28px",
            borderRadius: 18,
            border: "1px solid rgba(255,255,255,0.08)",
            boxShadow: "0 24px 64px rgba(0,0,0,0.5)",
            display: "flex",
            flexDirection: "column",
            gap: 18,
            backdropFilter: "blur(12px)",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ color: "#7b88a8", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Username
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
              required
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.1)",
                background: "rgba(255,255,255,0.05)",
                color: "#e8eaf6",
                fontSize: "0.92rem",
                outline: "none",
                transition: "border-color 150ms",
                fontFamily: "inherit",
              }}
              onFocus={(e) => (e.target.style.borderColor = "#6c63ff")}
              onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ color: "#7b88a8", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.1)",
                background: "rgba(255,255,255,0.05)",
                color: "#e8eaf6",
                fontSize: "0.92rem",
                outline: "none",
                transition: "border-color 150ms",
                fontFamily: "inherit",
              }}
              onFocus={(e) => (e.target.style.borderColor = "#6c63ff")}
              onBlur={(e) => (e.target.style.borderColor = "rgba(255,255,255,0.1)")}
            />
          </div>

          {error && (
            <p style={{ margin: 0, color: "#f87171", fontSize: "0.84rem", textAlign: "center", padding: "8px 12px", background: "rgba(248,113,113,0.1)", borderRadius: 8, border: "1px solid rgba(248,113,113,0.2)" }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              padding: "11px",
              borderRadius: 10,
              background: loading
                ? "rgba(108,99,255,0.4)"
                : "linear-gradient(135deg, #6c63ff, #8b5cf6)",
              color: "#fff",
              border: "none",
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: 700,
              fontSize: "0.95rem",
              transition: "all 150ms",
              boxShadow: loading ? "none" : "0 8px 24px rgba(108,99,255,0.35)",
              fontFamily: "inherit",
              letterSpacing: "-0.01em",
            }}
          >
            {loading ? "Signing in…" : "Sign In →"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 20, color: "#4a5568", fontSize: "0.76rem" }}>
          Credentials are set in the backend <code style={{ background: "rgba(255,255,255,0.05)", padding: "2px 6px", borderRadius: 4, color: "#a78bfa" }}>backend/.env</code> file
        </p>
      </div>
    </div>
  );
}
