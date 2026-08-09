"use client";
import { Bot } from "lucide-react";

export interface Mensaje {
  rol: "bot" | "user";
  texto: string;
}

/** Burbujas de chat reusadas por el onboarding y el chat de autorizaciones —
 * mismo look & feel en los dos lugares donde Baiyer conversa con el usuario. */
export function ChatBubbles({ mensajes }: { mensajes: Mensaje[] }) {
  return (
    <>
      {mensajes.map((m, i) => (
        <div key={i} style={{ display: "flex", justifyContent: m.rol === "user" ? "flex-end" : "flex-start", gap: 8 }}>
          {m.rol === "bot" && (
            <span style={{ width: 28, height: 28, borderRadius: 8, flexShrink: 0, background: "var(--brand-50)", color: "var(--brand)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
              <Bot size={16} strokeWidth={1.75} />
            </span>
          )}
          <div style={{
            maxWidth: "80%", padding: "10px 14px", fontSize: 14, lineHeight: 1.5,
            background: m.rol === "user" ? "var(--brand)" : "var(--surface)",
            color: m.rol === "user" ? "#fff" : "var(--n-900)",
            border: m.rol === "user" ? "none" : "1px solid var(--n-200)",
            borderRadius: m.rol === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
            boxShadow: m.rol === "bot" ? "var(--shadow-card)" : "none",
          }}>
            {m.texto}
          </div>
        </div>
      ))}
    </>
  );
}
