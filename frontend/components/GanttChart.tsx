"use client";
/**
 * Gantt dinámico (Fase 5, Smart Procurement).
 * - 3 escenarios: mínimo costo / entrega rápida / equilibrio
 * - Timeline editable: cambiar proveedor de un ítem recalcula el cronograma al vuelo
 * - Código de colores: ítem en ruta crítica (rojo #c0392b), con buffer (verde)
 * - Zoom in/out
 */
import { useEffect, useMemo, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Opcion {
  cotizacion_id: string | null;
  proveedor: string | null;
  precio_unitario: number;
  plazo_dias: number;
  plazo_total_dias: number;
}

interface ItemGantt {
  item_id: string;
  item: string;
  cantidad: number;
  opciones: Opcion[];
  seleccion_por_escenario: Record<string, Opcion & { precio_total: number }>;
}

interface DataEscenarios {
  proyecto: string;
  fecha_inicio: string;
  dias_cotizacion: number;
  dias_aprobacion: number;
  escenarios: Record<string, { costo_total: number; duracion_dias: number; fecha_fin_estimada: string }>;
  items: ItemGantt[];
}

type Escenario = "equilibrio" | "minimo_costo" | "entrega_rapida";

const ESC_LABEL: Record<Escenario, string> = {
  equilibrio: "Equilibrio",
  minimo_costo: "Mínimo costo",
  entrega_rapida: "Entrega rápida",
};

const fmtCLP = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;

export default function GanttChart({ proyectoId, userId }: { proyectoId: string; userId: string }) {
  const [data, setData] = useState<DataEscenarios | null>(null);
  const [error, setError] = useState("");
  const [escenario, setEscenario] = useState<Escenario>("equilibrio");
  // overrides: item_id -> cotizacion_id elegida manualmente (edición interactiva)
  const [overrides, setOverrides] = useState<Record<string, string | null>>({});
  const [zoom, setZoom] = useState(1); // px por día base 14

  useEffect(() => {
    fetch(`${API_URL}/api/proyectos/${proyectoId}/gantt/escenarios?user_id=${userId}`)
      .then(async (r) => { if (!r.ok) throw new Error("No se pudo cargar el Gantt"); return r.json(); })
      .then(setData)
      .catch((e) => setError(e.message));
  }, [proyectoId, userId]);

  // Selección efectiva por ítem = override manual o la del escenario
  const seleccion = useMemo(() => {
    if (!data) return [];
    return data.items.map((it) => {
      const overrideId = overrides[it.item_id];
      const opcion = overrideId !== undefined
        ? it.opciones.find((o) => o.cotizacion_id === overrideId) ?? it.seleccion_por_escenario[escenario]
        : it.seleccion_por_escenario[escenario];
      return { ...it, elegida: opcion, precio_total: opcion.precio_unitario * it.cantidad };
    });
  }, [data, escenario, overrides]);

  const duracionTotal = useMemo(
    () => Math.max(...seleccion.map((s) => s.elegida.plazo_total_dias), 1),
    [seleccion]
  );
  const costoTotal = useMemo(() => seleccion.reduce((a, s) => a + s.precio_total, 0), [seleccion]);

  if (error) return <div className="label" style={{ color: "var(--text-error)" }}>{error}</div>;
  if (!data) return <div className="label" style={{ color: "var(--text-muted)" }}>Cargando Gantt…</div>;

  const pxDia = 14 * zoom;
  const anchoTimeline = Math.max(duracionTotal + 3, 10) * pxDia;
  const fases = data.dias_cotizacion + data.dias_aprobacion;

  return (
    <div style={{ border: "1px solid var(--border-strong)" }}>
      {/* Header: escenarios + zoom */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, padding: "10px 14px", background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)" }}>
        <div style={{ display: "flex", gap: 0 }}>
          {(Object.keys(ESC_LABEL) as Escenario[]).map((e) => {
            const info = data.escenarios[e];
            const activo = escenario === e && Object.keys(overrides).length === 0;
            return (
              <button key={e} onClick={() => { setEscenario(e); setOverrides({}); }}
                style={{
                  border: "1px solid var(--border-default)", borderRight: "none", cursor: "pointer",
                  background: activo ? "var(--bg-inverse)" : "var(--bg-base)",
                  color: activo ? "var(--text-inverse)" : "var(--text-primary)",
                  padding: "6px 12px", textAlign: "left",
                }}>
                <div className="label" style={{ fontWeight: 800, color: "inherit" }}>{ESC_LABEL[e]}</div>
                <div className="label" style={{ color: "inherit", opacity: 0.75 }}>
                  {fmtCLP(info.costo_total)} · {info.duracion_dias}d
                </div>
              </button>
            );
          })}
          <span style={{ borderLeft: "1px solid var(--border-default)" }} />
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {Object.keys(overrides).length > 0 && (
            <span className="label" style={{ color: "var(--text-accent)", fontWeight: 700 }}>
              Personalizado: {fmtCLP(costoTotal)} · {duracionTotal}d
            </span>
          )}
          <button className="btn-swiss-secondary" style={{ fontSize: 11, padding: "3px 9px" }} onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}>−</button>
          <button className="btn-swiss-secondary" style={{ fontSize: 11, padding: "3px 9px" }} onClick={() => setZoom(z => Math.min(3, z + 0.25))}>+</button>
        </div>
      </div>

      {/* Filas del Gantt */}
      <div style={{ overflowX: "auto" }}>
        {/* Regla de días */}
        <div style={{ display: "flex", marginLeft: 280, borderBottom: "1px solid var(--border-subtle)" }}>
          {Array.from({ length: Math.ceil(anchoTimeline / pxDia / 7) + 1 }, (_, i) => (
            <div key={i} className="label" style={{ width: pxDia * 7, flexShrink: 0, color: "var(--text-muted)", borderLeft: "1px solid var(--border-subtle)", paddingLeft: 3 }}>
              S{i + 1}
            </div>
          ))}
        </div>

        {seleccion.map((s) => {
          const esCritico = s.elegida.plazo_total_dias === duracionTotal;
          const buffer = duracionTotal - s.elegida.plazo_total_dias;
          return (
            <div key={s.item_id} style={{ display: "flex", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", minHeight: 44 }}>
              {/* Columna fija: ítem + selector de proveedor */}
              <div style={{ width: 280, flexShrink: 0, padding: "6px 10px", borderRight: "1px solid var(--border-default)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.item}</div>
                <select
                  className="label"
                  value={s.elegida.cotizacion_id ?? ""}
                  onChange={(e) => setOverrides((prev) => ({ ...prev, [s.item_id]: e.target.value || null }))}
                  style={{ marginTop: 2, width: "100%", border: "1px solid var(--border-default)", background: "var(--bg-base)", fontSize: 10, padding: "1px 2px", cursor: "pointer" }}>
                  {s.opciones.map((o, i) => (
                    <option key={o.cotizacion_id ?? i} value={o.cotizacion_id ?? ""}>
                      {(o.proveedor ?? "Sin proveedor")} — {fmtCLP(o.precio_unitario)} · {o.plazo_dias}d
                    </option>
                  ))}
                </select>
              </div>

              {/* Barra */}
              <div style={{ position: "relative", height: 22, width: anchoTimeline, flexShrink: 0 }}>
                {/* fase cotización+aprobación */}
                <div style={{
                  position: "absolute", left: 0, width: fases * pxDia, top: 3, bottom: 3,
                  background: "var(--bg-surface)", border: "1px dashed var(--border-default)",
                }} title={`Cotización + aprobación: ${fases}d`} />
                {/* fase entrega */}
                <div style={{
                  position: "absolute", left: fases * pxDia, width: s.elegida.plazo_dias * pxDia, top: 3, bottom: 3,
                  background: esCritico ? "#c0392b" : "#1a6e45",
                  display: "flex", alignItems: "center", paddingLeft: 5, overflow: "hidden",
                }} title={`Entrega: ${s.elegida.plazo_dias}d${esCritico ? " (ruta crítica)" : ` (buffer ${buffer}d)`}`}>
                  <span className="label" style={{ color: "#fff", whiteSpace: "nowrap", fontWeight: 700 }}>
                    {s.elegida.proveedor ?? ""} {esCritico ? "· CRÍTICO" : buffer > 0 ? `· +${buffer}d buffer` : ""}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer resumen */}
      <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 14px", background: "var(--bg-surface)", borderTop: "1px solid var(--border-default)" }}>
        <span className="label">Inicio: {data.fecha_inicio} · {seleccion.length} ítems</span>
        <span className="label" style={{ fontWeight: 800 }}>
          Total: {fmtCLP(costoTotal)} · Fin estimado: {duracionTotal} días
        </span>
      </div>
    </div>
  );
}
