"use client";
import type { ReactNode } from "react";
import { Bot } from "lucide-react";

export interface Mensaje {
  rol: "bot" | "user";
  texto?: string;
  /** Contenido extra dentro de la misma burbuja (ej: la tarjeta de empresa
   * del onboarding) — se arma en cada render a partir de estado en vivo, no
   * se guarda congelado en el mensaje, para que siga reaccionando a cambios
   * (ej: elegir otro logo) después de haberse mostrado. */
  extra?: ReactNode;
}

/** Burbujas de chat reusadas por todos los chats de Baiyer (onboarding,
 * configuración de autorizaciones, correcciones del canvas) — mismo look &
 * feel en todos los lugares donde Baiyer conversa con el usuario. */
export function ChatBubbles({ mensajes }: { mensajes: Mensaje[] }) {
  return (
    <>
      {mensajes.map((m, i) => (
        <div key={i} style={{ display: "flex", justifyContent: m.rol === "user" ? "flex-end" : "flex-start", gap: 8, alignItems: "flex-start" }}>
          {m.rol === "bot" && (
            <span style={{ width: 28, height: 28, borderRadius: 8, flexShrink: 0, background: "var(--brand-50)", color: "var(--brand)", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
              <Bot size={16} strokeWidth={1.75} />
            </span>
          )}
          <div style={{
            maxWidth: "80%", padding: m.extra ? 16 : "10px 14px", fontSize: 14, lineHeight: 1.5,
            background: m.rol === "user" ? "var(--brand)" : "var(--surface)",
            color: m.rol === "user" ? "#fff" : "var(--n-900)",
            border: m.rol === "user" ? "none" : "1px solid var(--n-200)",
            borderRadius: m.rol === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
            boxShadow: m.rol === "bot" ? "var(--shadow-card)" : "none",
          }}>
            {m.texto}
            {m.extra}
          </div>
        </div>
      ))}
    </>
  );
}
