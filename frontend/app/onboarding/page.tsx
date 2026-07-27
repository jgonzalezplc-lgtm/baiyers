"use client";
import OnboardingChat from "@/components/OnboardingChat";

export default function OnboardingPage() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", flexDirection: "column" }}>
      {/* Header con marca */}
      <div style={{
        borderBottom: "1px solid var(--n-200)",
        padding: "14px 24px",
        background: "var(--surface)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <span style={{
          width: 28, height: 28, borderRadius: 8,
          background: "var(--brand)", color: "#fff",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 15, fontWeight: 700,
        }}>B</span>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--n-900)", letterSpacing: "-0.015em" }}>Baiyer</div>
          <div style={{ fontSize: 12, color: "var(--n-500)" }}>Configuración de tu cuenta</div>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <OnboardingChat />
      </div>
    </div>
  );
}
