"use client";

import { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";

export function WorkflowNodePalette({ tipos, onAdd }: {
  tipos: { valor: string; label: string }[];
  onAdd: (tipo: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        aria-label="Agregar nodo"
        aria-expanded={open}
        title="Agregar nodo"
        onClick={() => setOpen(v => !v)}
        style={{
          width: 34, height: 34, borderRadius: "50%", border: "1px solid var(--n-200)",
          background: "var(--surface)", color: "var(--brand)", display: "inline-flex",
          alignItems: "center", justifyContent: "center", cursor: "pointer",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <Plus size={17} />
      </button>
      {open && (
        <div
          style={{
            position: "absolute", top: 40, right: 0, width: 212, maxHeight: 320, overflowY: "auto",
            background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: "var(--r-md)",
            boxShadow: "var(--shadow-pop)", padding: 8, display: "flex", flexDirection: "column", gap: 6,
            zIndex: 30,
          }}
        >
          {tipos.map(t => (
            <button
              key={t.valor}
              onClick={() => { onAdd(t.valor); setOpen(false); }}
              style={{
                display: "flex", alignItems: "center", gap: 6, textAlign: "left",
                background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: "var(--r-sm)",
                padding: "7px 9px", fontSize: 12.5, color: "var(--n-800)", cursor: "pointer",
              }}
            >
              <Plus size={13} /> {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
