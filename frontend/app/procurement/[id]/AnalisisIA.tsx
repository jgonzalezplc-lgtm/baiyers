"use client";
import { useState } from "react";
import { API_URL, fmtPrecio } from "../constants";

interface Opcion {
  proveedor_nombre: string;
  fuente: string | null;
  precio: number | null;
  moneda: string;
  precio_cotizado: number | null;
  plazo_entrega_estimado: string | null;
  plazo_entrega_dias: number | null;
  condiciones: string | null;
  url: string | null;
}

interface FilaMatriz {
  proveedor: string;
  precio_total_estimado_clp: number | null;
  desglose_costos: { producto: number | null; transporte_estimado: number | null; aranceles_estimados: number | null; margen_riesgo: number | null };
  score_precio: number;
  score_disponibilidad: number;
  score_plazo: number;
  score_confianza: number;
  score_total: number;
  riesgos: string[];
  es_local: boolean;
}

interface Analisis {
  matriz_comparativa: FilaMatriz[];
  recomendacion_ganadora: { proveedor: string; por_que: string };
  razonamientos_por_opcion: { opcion: string; por_que_no: string }[];
}

function scoreColor(s: number): string {
  if (s >= 75) return "#1a6e45";
  if (s >= 50) return "#92400e";
  return "#c0392b";
}

export default function AnalisisIA({ userId, itemNombre, cantidad, opciones }: {
  userId: string;
  itemNombre: string;
  cantidad: number;
  opciones: Opcion[];
}) {
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [abierto, setAbierto] = useState(false);

  const analizar = async () => {
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${API_URL}/api/analizar-cotizaciones`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, item_nombre: itemNombre, cantidad, opciones }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? "Error en el análisis");
      setAnalisis(d);
      setAbierto(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ borderTop: "1px solid var(--border-subtle)", padding: "8px 14px", background: "var(--bg-surface)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button className="btn-swiss-secondary" style={{ fontSize: 10, padding: "4px 10px" }}
          disabled={loading || opciones.length < 2} onClick={() => analisis ? setAbierto(v => !v) : analizar()}>
          {loading ? "Analizando con IA…" : analisis ? (abierto ? "Ocultar análisis IA" : "Ver análisis IA") : "⚡ Análisis comparativo IA"}
        </button>
        {opciones.length < 2 && <span className="label" style={{ color: "var(--text-muted)" }}>Se requieren al menos 2 proveedores</span>}
        {error && <span className="label" style={{ color: "var(--text-error)" }}>{error}</span>}
      </div>

      {analisis && abierto && (
        <div style={{ marginTop: 10 }}>
          {/* Recomendación ganadora */}
          <div style={{ borderLeft: "3px solid #c0392b", background: "var(--bg-base)", padding: "10px 12px", marginBottom: 10 }}>
            <div className="label" style={{ color: "var(--text-accent)", fontWeight: 800, marginBottom: 3 }}>
              RECOMENDACIÓN: {analisis.recomendacion_ganadora.proveedor}
            </div>
            <div style={{ fontSize: 12, lineHeight: 1.5 }}>{analisis.recomendacion_ganadora.por_que}</div>
          </div>

          {/* Matriz comparativa */}
          <div style={{ overflowX: "auto" }}>
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 110px 70px 70px 70px 70px 80px",
              gap: 6, padding: "5px 0", borderBottom: "1px solid var(--border-default)", minWidth: 620,
            }}>
              {["PROVEEDOR", "TOTAL EST.", "PRECIO", "DISPON.", "PLAZO", "CONF.", "SCORE"].map(h => (
                <span key={h} className="label" style={{ fontWeight: 700 }}>{h}</span>
              ))}
            </div>
            {analisis.matriz_comparativa.map((f) => (
              <div key={f.proveedor} style={{
                display: "grid", gridTemplateColumns: "1fr 110px 70px 70px 70px 70px 80px",
                gap: 6, padding: "7px 0", borderBottom: "1px solid var(--border-subtle)", minWidth: 620, alignItems: "center",
              }}>
                <div>
                  <span style={{ fontSize: 11, fontWeight: 700 }}>{f.proveedor}</span>
                  {f.es_local && <span className="label" style={{ marginLeft: 6, color: "#1a6e45" }}>CL</span>}
                  {f.riesgos.length > 0 && (
                    <div className="label" style={{ color: "#92400e", marginTop: 2 }}>⚠ {f.riesgos.join(" · ")}</div>
                  )}
                </div>
                <span className="label" style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{fmtPrecio(f.precio_total_estimado_clp)}</span>
                {[f.score_precio, f.score_disponibilidad, f.score_plazo, f.score_confianza].map((s, i) => (
                  <span key={i} className="label" style={{ color: scoreColor(s), fontFamily: "var(--font-mono)" }}>{s}</span>
                ))}
                <span className="label" style={{
                  fontFamily: "var(--font-mono)", fontWeight: 800, color: "#fff",
                  background: scoreColor(f.score_total), padding: "2px 8px", justifySelf: "start",
                }}>{f.score_total}</span>
              </div>
            ))}
          </div>

          {/* Por qué no las otras */}
          {analisis.razonamientos_por_opcion.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {analisis.razonamientos_por_opcion.map((r) => (
                <div key={r.opcion} className="label" style={{ color: "var(--text-muted)", padding: "2px 0", lineHeight: 1.5 }}>
                  <span style={{ fontWeight: 700 }}>{r.opcion}:</span> {r.por_que_no}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
