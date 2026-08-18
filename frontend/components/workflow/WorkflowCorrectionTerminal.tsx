"use client";

import { type KeyboardEvent } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { BtnPrimary, TypingBubble } from "@/components/ui";
import { ChatBubbles } from "@/components/chat/ChatBubbles";
import { prefersReducedMotion } from "./canvasTypes";

export function WorkflowCorrectionTerminal({
  mensajes, entrada, onEntradaChange, onEnviar, enviando, expanded, onToggleExpanded,
}: {
  mensajes: { rol: "bot" | "user"; texto: string }[];
  entrada: string;
  onEntradaChange: (v: string) => void;
  onEnviar: () => void;
  enviando: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
}) {
  const ultimo = mensajes[mensajes.length - 1];
  const transition = prefersReducedMotion() ? "none" : "height 240ms ease";

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onEnviar(); }
  };

  return (
    <div
      style={{
        position: "relative", flexShrink: 0, background: "var(--surface)", border: "1px solid var(--n-200)",
        borderRadius: "var(--r-md)", marginTop: 10, display: "flex", flexDirection: "column",
        height: expanded ? "min(320px, 46vh)" : 58, transition, overflow: "hidden", zIndex: 15,
      }}
    >
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px",
        borderBottom: expanded ? "1px solid var(--n-200)" : "none", flexShrink: 0, gap: 8,
      }}>
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--n-700)", textTransform: "uppercase", letterSpacing: 0.3 }}>
            Corregir por chat
          </span>
          {!expanded && ultimo && (
            <span style={{ fontSize: 11.5, color: "var(--n-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {ultimo.texto}
            </span>
          )}
        </div>
        <button
          aria-label={expanded ? "Contraer terminal" : "Expandir terminal"}
          aria-expanded={expanded}
          onClick={onToggleExpanded}
          style={{ border: 0, background: "none", cursor: "pointer", color: "var(--n-600)", display: "inline-flex", flexShrink: 0 }}
        >
          {expanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </div>

      {expanded && (
        <div style={{ flex: 1, overflowY: "auto", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 10 }}>
          <ChatBubbles mensajes={mensajes} />
          {enviando && <TypingBubble />}
        </div>
      )}

      <div style={{ display: "flex", gap: 6, padding: 8, flexShrink: 0 }}>
        <textarea
          value={entrada}
          onChange={e => onEntradaChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Escribe una corrección…"
          rows={expanded ? 2 : 1}
          disabled={enviando}
          style={{
            flex: 1, resize: "none", background: "var(--surface-2)", color: "var(--n-900)",
            border: "1px solid var(--n-300)", borderRadius: "var(--r-md)", padding: 8,
            fontFamily: "inherit", fontSize: 12.5, lineHeight: 1.4, outline: "none",
          }}
        />
        <BtnPrimary onClick={onEnviar} disabled={!entrada.trim() || enviando} style={{ alignSelf: "flex-end" }} size="sm">
          Enviar
        </BtnPrimary>
      </div>
    </div>
  );
}
