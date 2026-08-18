"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { prefersReducedMotion } from "./canvasTypes";

export function CollapsibleNodeSummary({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const transition = prefersReducedMotion() ? "none" : "transform 180ms ease";

  return (
    <div style={{ borderTop: "1px solid var(--n-200)", paddingTop: 12 }}>
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%",
          border: 0, background: "none", cursor: "pointer", padding: 0,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--n-700)" }}>Resumen de la tarjeta</span>
        <ChevronDown size={15} style={{ color: "var(--n-500)", transition, transform: open ? "rotate(180deg)" : "rotate(0deg)" }} />
      </button>
      {open && <div style={{ marginTop: 8 }}>{children}</div>}
    </div>
  );
}
