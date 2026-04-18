import type { CSSProperties } from "react";

declare const __API_BASE_URL__: string;
declare const __WS_BASE_URL__: string;

const cardStyle = {
  maxWidth: "720px",
  margin: "4rem auto",
  padding: "2rem",
  borderRadius: "24px",
  background:
    "linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(243,247,252,0.96) 100%)",
  boxShadow: "0 24px 70px rgba(15, 23, 42, 0.12)",
  border: "1px solid rgba(148, 163, 184, 0.25)",
} satisfies CSSProperties;

const codeStyle = {
  display: "block",
  marginTop: "0.5rem",
  padding: "0.75rem 1rem",
  borderRadius: "14px",
  background: "#0f172a",
  color: "#e2e8f0",
  overflowX: "auto",
} satisfies CSSProperties;

export default function App() {
  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "1.5rem",
        background:
          "radial-gradient(circle at top, rgba(14,165,233,0.22), transparent 35%), linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)",
        color: "#0f172a",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
      }}
    >
      <section style={cardStyle}>
        <p style={{ letterSpacing: "0.18em", textTransform: "uppercase", color: "#0369a1" }}>
          Milestone M1
        </p>
        <h1 style={{ marginTop: 0, fontSize: "clamp(2rem, 5vw, 3.75rem)", lineHeight: 1.05 }}>
          Online Chat Server foundation is wired for local execution.
        </h1>
        <p style={{ fontSize: "1.05rem", lineHeight: 1.7, color: "#334155" }}>
          This frontend is intentionally minimal. It confirms the monorepo layout, Docker
          separation, and environment-driven API/WebSocket configuration while backend contract
          endpoints are implemented in later milestones.
        </p>
        <div style={{ display: "grid", gap: "1rem", marginTop: "1.5rem" }}>
          <div>
            <strong>REST base URL</strong>
            <code style={codeStyle}>{__API_BASE_URL__}</code>
          </div>
          <div>
            <strong>WebSocket base URL</strong>
            <code style={codeStyle}>{__WS_BASE_URL__}</code>
          </div>
        </div>
      </section>
    </main>
  );
}
