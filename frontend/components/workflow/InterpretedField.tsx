"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { BtnGhost, BtnPrimary } from "@/components/ui";

// Muestra un campo ya interpretado (por el backend, al construir el grafo)
// o un fallback determinístico legible cuando el workflow es viejo y no lo
// trae — nunca un input vacío que el usuario deba llenar desde cero. La
// corrección manual se guarda en el mismo campo (`entrada`/`proceso`).
export function InterpretedField({ label, value, fallback, placeholder, onSave }: {
  label: string;
  value: string;
  fallback: string;
  placeholder?: string;
  onSave: (v: string) => void;
}) {
  const [editando, setEditando] = useState(false);
  const tieneValorPropio = !!value?.trim();
  const mostrado = tieneValorPropio ? value : fallback;
  const [borrador, setBorrador] = useState(mostrado);

  if (editando) {
    return (
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)", marginBottom: 6 }}>{label}</div>
        <textarea
          value={borrador}
          onChange={e => setBorrador(e.target.value)}
          placeholder={placeholder}
          rows={3}
          autoFocus
          style={{
            width: "100%", resize: "vertical", padding: 8, fontFamily: "inherit", fontSize: 12.5,
            lineHeight: 1.45, border: "1px solid var(--n-300)", background: "var(--surface)",
            color: "var(--n-900)", borderRadius: "var(--r-sm)",
          }}
        />
        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          <BtnGhost size="sm" onClick={() => { setBorrador(mostrado); setEditando(false); }}>Cancelar</BtnGhost>
          <BtnPrimary size="sm" onClick={() => { onSave(borrador.trim()); setEditando(false); }}>Guardar corrección</BtnPrimary>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, marginBottom: 4 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--n-600)" }}>{label}</div>
        <span style={{
          fontSize: 9.5, color: "var(--n-500)", background: "var(--surface-2)",
          padding: "1px 6px", borderRadius: "var(--r-sm)", flexShrink: 0,
        }}>
          {tieneValorPropio ? "Interpretado" : "Generado desde el grafo"}
        </span>
      </div>
      <div style={{
        fontSize: 12, color: "var(--n-800)", lineHeight: 1.45, padding: 8,
        background: "var(--canvas)", border: "1px solid var(--n-200)", borderRadius: "var(--r-sm)",
      }}>
        {mostrado || "—"}
      </div>
      <button
        onClick={() => { setBorrador(mostrado); setEditando(true); }}
        style={{ display: "inline-flex", alignItems: "center", gap: 4, border: 0, background: "none", color: "var(--brand)", fontSize: 11, cursor: "pointer", padding: "4px 0 0" }}
      >
        <Pencil size={11} /> Corregir manualmente
      </button>
    </div>
  );
}
