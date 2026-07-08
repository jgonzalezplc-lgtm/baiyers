"use client";
import { useState } from "react";

interface Props {
  proveedorNombre: string;
  proveedorId: string;
  userId: string;
  ocId?: string;
  onGuardado: (score: number) => void;
  onCerrar: () => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function RatingModal({ proveedorNombre, proveedorId, userId, ocId, onGuardado, onCerrar }: Props) {
  const [estrellas, setEstrellas] = useState(0);
  const [hoverEstrella, setHoverEstrella] = useState(0);
  const [precioCumplido, setPrecioCumplido] = useState<boolean | null>(null);
  const [plazoCumplido, setPlazoCumplido] = useState<boolean | null>(null);
  const [comentario, setComentario] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  const handleGuardar = async () => {
    if (estrellas === 0) { setError("Selecciona una calificacion"); return; }
    setGuardando(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/suppliers/rating`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proveedor_id: proveedorId,
          user_id: userId,
          estrellas,
          precio_cumplido: precioCumplido,
          plazo_cumplido: plazoCumplido,
          comentario: comentario || null,
        }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      onGuardado(data.nuevo_score);
    } catch {
      setError("Error guardando el rating. Intenta de nuevo.");
    } finally {
      setGuardando(false);
    }
  };

  const LABELS = ["", "Muy malo", "Malo", "Regular", "Bueno", "Excelente"];

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 16,
    }}>
      <div style={{
        width: "100%", maxWidth: 440,
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        overflow: "hidden",
      }}>

        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-default)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span className="label" style={{ color: "var(--accent)", display: "block", marginBottom: 2 }}>Supplier Intelligence</span>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.01em" }}>Califica tu experiencia</h2>
          </div>
          <button onClick={onCerrar} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18 }}>✕</button>
        </div>

        <div style={{ padding: "20px" }}>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 20 }}>
            Como fue tu experiencia con <strong style={{ color: "var(--text-primary)" }}>{proveedorNombre}</strong>?
          </div>

          {/* Estrellas */}
          <div style={{ marginBottom: 20 }}>
            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 10 }}>
              Calificacion general
            </label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {[1, 2, 3, 4, 5].map(n => (
                <button
                  key={n}
                  onClick={() => setEstrellas(n)}
                  onMouseEnter={() => setHoverEstrella(n)}
                  onMouseLeave={() => setHoverEstrella(0)}
                  style={{
                    background: "none", border: "none", cursor: "pointer",
                    fontSize: 28, lineHeight: 1, padding: 2,
                    transform: (hoverEstrella || estrellas) >= n ? "scale(1.1)" : "scale(1)",
                  }}
                >
                  <span style={{ color: (hoverEstrella || estrellas) >= n ? "#b45309" : "var(--border-default)" }}>★</span>
                </button>
              ))}
              {estrellas > 0 && (
                <span className="label" style={{ color: "#b45309", marginLeft: 4 }}>
                  {LABELS[estrellas]}
                </span>
              )}
            </div>
          </div>

          {/* Toggles */}
          <div style={{ display: "flex", flexDirection: "column", gap: 1, marginBottom: 20, border: "1px solid var(--border-default)" }}>
            {[
              { label: "El precio final fue el cotizado?", val: precioCumplido, set: setPrecioCumplido },
              { label: "Cumplio el plazo de entrega?", val: plazoCumplido, set: setPlazoCumplido },
            ].map(({ label, val, set }, idx) => (
              <div key={label} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                background: "var(--bg-surface)",
                borderBottom: idx === 0 ? "1px solid var(--border-default)" : "none",
                padding: "10px 14px",
              }}>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{label}</span>
                <div style={{ display: "flex", gap: 6 }}>
                  {[true, false].map(v => (
                    <button
                      key={String(v)}
                      onClick={() => set(v)}
                      className="label"
                      style={{
                        padding: "4px 12px",
                        cursor: "pointer",
                        fontFamily: "var(--font-mono)",
                        border: "1px solid var(--border-default)",
                        background: val === v ? (v ? "var(--fill-success)" : "var(--fill-error)") : "var(--bg-base)",
                        color: val === v ? (v ? "var(--text-success)" : "var(--text-error)") : "var(--text-muted)",
                      }}
                    >
                      {v ? "SI" : "NO"}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Comentario */}
          <div style={{ marginBottom: 20 }}>
            <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Comentario — opcional
            </label>
            <textarea
              value={comentario}
              onChange={e => setComentario(e.target.value.slice(0, 200))}
              rows={3}
              placeholder="Algo que destacar o mejorar?"
              style={{
                width: "100%", padding: "10px 12px",
                background: "var(--bg-base)",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
                fontSize: 11, outline: "none", resize: "none",
                fontFamily: "var(--font-mono)",
                boxSizing: "border-box",
              }}
            />
            <div className="label" style={{ color: "var(--text-muted)", textAlign: "right", marginTop: 2 }}>
              {comentario.length}/200
            </div>
          </div>

          {error && (
            <div style={{
              fontSize: 11, color: "var(--text-error)",
              background: "var(--fill-error)",
              border: "1px solid var(--border-accent)",
              padding: "8px 12px", marginBottom: 12,
            }}>{error}</div>
          )}

          <button
            onClick={handleGuardar}
            disabled={guardando || estrellas === 0}
            className={guardando || estrellas === 0 ? "btn-swiss-secondary" : "btn-swiss-primary"}
            style={{ width: "100%", padding: "11px" }}
          >
            {guardando ? "Guardando..." : "Guardar rating"}
          </button>
        </div>
      </div>
    </div>
  );
}
