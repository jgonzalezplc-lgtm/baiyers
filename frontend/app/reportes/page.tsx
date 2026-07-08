"use client";
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import dynamic from "next/dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ReporteTemplate = dynamic(() => import("@/components/ReporteTemplate"), { ssr: false, loading: () => <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Cargando previsualizacion...</div> });

interface ReporteDatos {
  titulo: string;
  fecha: string;
  proyecto: Record<string, unknown> | null;
  items: ReporteItem[];
  proveedores_detalle: Record<string, unknown>;
  resumen: {
    total_items: number;
    items_cotizados: number;
    monto_total: number;
    proveedores_evaluados: number;
    max_plazo_dias: number;
  };
  secciones: string[];
}

interface ReporteItem {
  item: string;
  descripcion: string | null;
  cantidad: number;
  unidad: string;
  proveedor_seleccionado: string | null;
  precio_unitario: number | null;
  precio_total: number | null;
  plazo_entrega_dias: number | null;
  cotizaciones: Array<{ proveedor_nombre: string; precio_unitario: number; fuente: string }>;
}

const SECCIONES_CONFIG = [
  { id: "resumen", label: "Resumen ejecutivo", desc: "KPIs y totales del proyecto" },
  { id: "items", label: "Detalle de items", desc: "Tabla completa con precios y proveedores" },
  { id: "comparativa", label: "Comparativa proveedores", desc: "Precios por item de cada proveedor" },
  { id: "proveedores", label: "Ficha de proveedores", desc: "Score, historial y rating de cada proveedor" },
  { id: "plazos", label: "Cronograma de entrega", desc: "Vista Gantt simplificada de plazos" },
];

function ReportesPageInner() {
  const searchParams = useSearchParams();
  const proyectoId = searchParams.get("proyecto_id");

  const [userId, setUserId] = useState<string | null>(null);
  const [titulo, setTitulo] = useState("Reporte de Cotizacion");
  const [secciones, setSecciones] = useState(["resumen", "items", "comparativa", "proveedores", "plazos"]);
  const [datos, setDatos] = useState<ReporteDatos | null>(null);
  const [generando, setGenerando] = useState(false);
  const [exportandoExcel, setExportandoExcel] = useState(false);
  const [error, setError] = useState("");
  const [paso, setPaso] = useState<"config" | "preview">("config");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) setUserId(data.user.id);
    });
  }, []);

  const toggleSeccion = (id: string) => {
    setSecciones(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  const handleGenerar = async () => {
    if (!userId) return;
    setGenerando(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/reportes/datos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, proyecto_id: proyectoId || null, titulo, secciones }),
      });
      if (!res.ok) throw new Error(await res.text());
      setDatos(await res.json());
      setPaso("preview");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error generando reporte");
    } finally {
      setGenerando(false);
    }
  };

  const handleExportarExcel = async () => {
    if (!userId) return;
    setExportandoExcel(true);
    try {
      const res = await fetch(`${API_URL}/api/reportes/exportar-excel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, proyecto_id: proyectoId || null, titulo }),
      });
      if (!res.ok) throw new Error("Error exportando Excel");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${titulo.replace(/\s+/g, "_")}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error exportando Excel");
    } finally {
      setExportandoExcel(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    background: "var(--bg-base)",
    border: "1px solid var(--border-default)",
    color: "var(--text-primary)",
    fontSize: 11,
    outline: "none",
    fontFamily: "var(--font-mono)",
    boxSizing: "border-box",
  };

  return (
    <>
      {/* Page header */}
      <div style={{ marginBottom: 24 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
              REPORTES
            </span>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              Reportes
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Genera reportes de cotizaciones y OCs.</p>
          </div>
          {paso === "preview" && (
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => { setPaso("config"); setDatos(null); }} className="btn-swiss-secondary">
                ← Editar configuracion
              </button>
              <button onClick={handleExportarExcel} disabled={exportandoExcel} className="btn-swiss-primary">
                {exportandoExcel ? "Exportando..." : "Descargar Excel"}
              </button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div style={{
          background: "var(--fill-error)",
          border: "1px solid var(--border-accent)",
          padding: "10px 14px",
          fontSize: 11,
          color: "var(--text-error)",
          marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {/* Configuracion */}
      {paso === "config" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>Configuracion del reporte</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 6 }}>Titulo del reporte</label>
                <input value={titulo} onChange={e => setTitulo(e.target.value)} style={inputStyle} placeholder="Ej: Reporte Proyecto Edificio Providencia" />
              </div>
              {proyectoId && (
                <div style={{
                  fontSize: 11,
                  color: "var(--text-success)",
                  background: "var(--fill-success)",
                  border: "1px solid var(--palette-green-500)",
                  padding: "8px 12px",
                }}>
                  Proyecto seleccionado: ID {proyectoId}
                </div>
              )}
            </div>
          </div>

          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>Secciones a incluir</div>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 14 }}>
              Selecciona que informacion aparecera en el reporte
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1, border: "1px solid var(--border-default)" }}>
              {SECCIONES_CONFIG.map((s, idx) => (
                <label key={s.id} style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  cursor: "pointer",
                  padding: "12px 14px",
                  background: secciones.includes(s.id) ? "var(--fill-error)" : "var(--bg-surface)",
                  borderBottom: idx < SECCIONES_CONFIG.length - 1 ? "1px solid var(--border-default)" : "none",
                  borderLeft: secciones.includes(s.id) ? "3px solid var(--accent)" : "3px solid transparent",
                }}>
                  <input
                    type="checkbox"
                    checked={secciones.includes(s.id)}
                    onChange={() => toggleSeccion(s.id)}
                    style={{ accentColor: "var(--accent)", width: 14, height: 14 }}
                  />
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: secciones.includes(s.id) ? "var(--text-primary)" : "var(--text-secondary)" }}>
                      {s.label}
                    </div>
                    <div className="label" style={{ color: "var(--text-muted)" }}>{s.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <button
            onClick={handleGenerar}
            disabled={generando || secciones.length === 0}
            className={generando || secciones.length === 0 ? "btn-swiss-secondary" : "btn-swiss-primary"}
            style={{ padding: 14, fontSize: 12, width: "100%" }}
          >
            {generando ? "Generando reporte..." : "Generar reporte →"}
          </button>
        </div>
      )}

      {/* Preview */}
      {paso === "preview" && datos && (
        <div>
          <Suspense fallback={<div style={{ fontSize: 11, color: "var(--text-muted)" }}>Cargando previsualizacion...</div>}>
            <ReporteTemplate datos={datos} />
          </Suspense>
        </div>
      )}
    </>
  );
}

export default function ReportesPage() {
  return (
    <Suspense fallback={
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "60px 20px" }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Cargando...</div>
      </div>
    }>
      <ReportesPageInner />
    </Suspense>
  );
}
