"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer
} from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const COLORES_PIE = ["#c0392b","#e67e22","#27ae60","#2980b9","#8e44ad","#16a085","#f39c12","#d35400","#1abc9c","#2c3e50"];

interface Resumen {
  total_ocs_mes: number;
  cant_ocs_mes: number;
  total_pendiente_pago: number;
  total_pagado_mes: number;
  proyeccion_proximo_mes: number;
  variacion_vs_anterior_pct: number;
}

interface GastoMensual {
  mes: string;
  label: string;
  total: number;
  cantidad: number;
}

interface Categoria {
  categoria: string;
  total: number;
}

interface TopProveedor {
  proveedor: string;
  total: number;
}

interface Liquidez {
  semana: string;
  total: number;
  facturas: string[];
  nivel: "verde" | "amarillo" | "rojo";
}

interface ProveedorHistorico {
  nombre: string;
  score: number;
  total_solicitudes: number;
  total_oc_enviadas: number;
  total_oc_confirmadas: number;
  pct_precio_cumplido: number;
  pct_plazo_cumplido: number;
  tasa_respuesta: number;
}

const NIVEL_COLORS = { verde: "#16a085", amarillo: "#f39c12", rojo: "#c0392b" };

const fmt = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;

function KpiCard({ label, value, sub, color = "var(--text-primary)" }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "16px 18px" }}>
      <div className="label" style={{ color: "var(--text-muted)", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color, letterSpacing: "-0.02em" }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

const tooltipStyle = {
  background: "var(--bg-inverse)",
  border: "none",
  fontSize: 11,
  color: "var(--text-inverse)",
  fontFamily: "var(--font-mono)",
};

export default function EstadisticasPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [resumen, setResumen] = useState<Resumen | null>(null);
  const [gastos, setGastos] = useState<GastoMensual[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [topProvs, setTopProvs] = useState<TopProveedor[]>([]);
  const [liquidez, setLiquidez] = useState<Liquidez[]>([]);
  const [historico, setHistorico] = useState<ProveedorHistorico[]>([]);
  const [loading, setLoading] = useState(true);
  const [exportando, setExportando] = useState(false);
  const [ordenHistorico, setOrdenHistorico] = useState<keyof ProveedorHistorico>("score");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) {
        setUserId(data.user.id);
        cargarTodo(data.user.id);
      }
    });
  }, []);

  const cargarTodo = async (uid: string) => {
    setLoading(true);
    const base = `${API_URL}/api/estadisticas`;
    try {
      const [r1, r2, r3, r4, r5, r6] = await Promise.all([
        fetch(`${base}/resumen?user_id=${uid}`).then(r => r.json()),
        fetch(`${base}/gastos-mensuales?user_id=${uid}`).then(r => r.json()),
        fetch(`${base}/por-categoria?user_id=${uid}`).then(r => r.json()),
        fetch(`${base}/top-proveedores?user_id=${uid}`).then(r => r.json()),
        fetch(`${base}/liquidez?user_id=${uid}`).then(r => r.json()),
        fetch(`${base}/proveedores-historico?user_id=${uid}`).then(r => r.json()),
      ]);
      setResumen(r1); setGastos(r2); setCategorias(r3); setTopProvs(r4); setLiquidez(r5); setHistorico(r6);
    } catch (e) {
      console.error("Error cargando estadisticas:", e);
    } finally { setLoading(false); }
  };

  const handleExportar = async () => {
    if (!userId) return;
    setExportando(true);
    try {
      const res = await fetch(`${API_URL}/api/estadisticas/exportar-excel?user_id=${userId}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "estadisticas_claria.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* silent */ }
    finally { setExportando(false); }
  };

  const historicoOrdenado = [...historico].sort((a, b) => {
    const va = a[ordenHistorico] as number;
    const vb = b[ordenHistorico] as number;
    return (vb || 0) - (va || 0);
  });

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "60px 20px" }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Cargando estadisticas...</div>
      </div>
    );
  }

  return (
    <>
      {/* Page header */}
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
              ANÁLISIS
            </span>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              Estadísticas
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Análisis de gasto, ahorro y rendimiento.</p>
          </div>
          <button
            onClick={handleExportar}
            disabled={exportando}
            className={exportando ? "btn-swiss-secondary" : "btn-swiss-primary"}
          >
            {exportando ? "Generando..." : "Descargar Excel"}
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 1, marginBottom: 28 }}>
        <KpiCard
          label="OCs emitidas este mes"
          value={String(resumen?.cant_ocs_mes ?? 0)}
          sub={`Total: ${fmt(resumen?.total_ocs_mes ?? 0)}`}
          color="var(--accent)"
        />
        <KpiCard
          label="Facturas pendientes de pago"
          value={fmt(resumen?.total_pendiente_pago ?? 0)}
          color={(resumen?.total_pendiente_pago ?? 0) > 0 ? "var(--text-error)" : "var(--text-success)"}
        />
        <KpiCard
          label="Pagado este mes"
          value={fmt(resumen?.total_pagado_mes ?? 0)}
          color="var(--text-success)"
        />
        <KpiCard
          label="Proyeccion proximo mes"
          value={fmt(resumen?.proyeccion_proximo_mes ?? 0)}
          sub="Basado en recurrencias activas"
          color="var(--text-warning)"
        />
        <KpiCard
          label="Variacion vs mes anterior"
          value={`${(resumen?.variacion_vs_anterior_pct ?? 0) > 0 ? "+" : ""}${resumen?.variacion_vs_anterior_pct ?? 0}%`}
          color={(resumen?.variacion_vs_anterior_pct ?? 0) > 0 ? "var(--text-error)" : "var(--text-success)"}
        />
      </div>

      {/* Graficos */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, marginBottom: 28 }}>
        {/* Gasto mensual */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "16px 20px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 12 }}>
            Gasto mensual — ultimos 12 meses
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={gastos}>
              <defs>
                <linearGradient id="colorGasto" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#c0392b" stopOpacity={0.2}/>
                  <stop offset="95%" stopColor="#c0392b" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <XAxis dataKey="label" tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000000).toFixed(1)}M`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [fmt(v), "Gasto"]} />
              <Area type="monotone" dataKey="total" stroke="#c0392b" strokeWidth={2} fill="url(#colorGasto)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Top 5 proveedores */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "16px 20px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 12 }}>
            Top 5 proveedores por volumen
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={topProvs} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000000).toFixed(1)}M`} />
              <YAxis type="category" dataKey="proveedor" tick={{ fontSize: 9, fill: "var(--text-secondary)" as string }} axisLine={false} tickLine={false} width={80} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [fmt(v), "Total"]} />
              <Bar dataKey="total" fill="#c0392b" radius={[0,2,2,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Por categoria */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "16px 20px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 12 }}>
            Gasto por categoria de item
          </div>
          {categorias.length === 0 ? (
            <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", padding: "40px 0" }}>Sin datos suficientes</div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={categorias} dataKey="total" nameKey="categoria" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }) => `${name.slice(0,10)} ${(percent*100).toFixed(0)}%`} labelLine={false} fontSize={9}>
                  {categorias.map((_, i) => <Cell key={i} fill={COLORES_PIE[i % COLORES_PIE.length]} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [fmt(v), "Total"]} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* OCs por mes */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "16px 20px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 12 }}>OCs emitidas por mes</div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={gastos}>
              <XAxis dataKey="label" tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="cantidad" stroke="#16a085" strokeWidth={2} dot={{ fill: "#16a085", r: 3 }} name="OCs" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Liquidez 90 dias */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", padding: "20px", marginBottom: 28 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 4 }}>Liquidez — proximos 90 dias</div>
        <div className="label" style={{ color: "var(--text-muted)", marginBottom: 16 }}>Facturas pendientes agrupadas por semana</div>

        {liquidez.length === 0 ? (
          <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", padding: "24px 0" }}>
            Sin facturas pendientes en los proximos 90 dias
          </div>
        ) : (
          <div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {liquidez.map(s => (
                <div key={s.semana} title={s.facturas.join(", ")} style={{
                  flex: "0 0 auto",
                  minWidth: 70,
                  background: NIVEL_COLORS[s.nivel] + "18",
                  border: `1px solid ${NIVEL_COLORS[s.nivel]}`,
                  padding: "8px 10px",
                  cursor: "default",
                }}>
                  <div className="label" style={{ color: "var(--text-muted)", marginBottom: 4 }}>
                    {new Date(s.semana + "T12:00:00").toLocaleDateString("es-CL", { day:"2-digit", month:"2-digit" })}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: NIVEL_COLORS[s.nivel] }}>
                    ${Math.round(s.total/1000)}K
                  </div>
                  <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>{s.facturas.length} fac.</div>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
              {[{ nivel: "verde", label: "Normal" }, { nivel: "amarillo", label: "Alto" }, { nivel: "rojo", label: "Muy alto" }].map(l => (
                <span key={l.nivel} className="label" style={{ color: NIVEL_COLORS[l.nivel as keyof typeof NIVEL_COLORS] }}>
                  — {l.label}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Historial proveedores */}
      <div style={{ border: "1px solid var(--border-default)" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-default)", background: "var(--bg-surface)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)" }}>Historial de proveedores</div>
        </div>

        {historico.length === 0 ? (
          <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", padding: "32px 0", background: "var(--bg-surface)" }}>
            Sin proveedores aun.
          </div>
        ) : (
          <>
            <div style={{
              display: "grid",
              gridTemplateColumns: "2fr 0.7fr 0.8fr 0.8fr 0.9fr 0.9fr 0.8fr",
              padding: "10px 16px",
              borderBottom: "1px solid var(--border-default)",
              gap: 8,
              background: "var(--bg-surface)",
            }}>
              {[
                { key: "nombre", label: "Proveedor" },
                { key: "score", label: "Score" },
                { key: "total_solicitudes", label: "Solicitudes" },
                { key: "total_oc_enviadas", label: "OCs" },
                { key: "tasa_respuesta", label: "% Resp." },
                { key: "pct_precio_cumplido", label: "% Precio" },
                { key: "pct_plazo_cumplido", label: "% Plazo" },
              ].map(col => (
                <button
                  key={col.key}
                  onClick={() => setOrdenHistorico(col.key as keyof ProveedorHistorico)}
                  className="label"
                  style={{
                    color: ordenHistorico === col.key ? "var(--accent)" : "var(--text-muted)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    fontFamily: "var(--font-mono)",
                    padding: 0,
                  }}
                >
                  {col.label} {ordenHistorico === col.key ? "↓" : ""}
                </button>
              ))}
            </div>

            {historicoOrdenado.map((p, i) => (
              <div key={i} style={{
                display: "grid",
                gridTemplateColumns: "2fr 0.7fr 0.8fr 0.8fr 0.9fr 0.9fr 0.8fr",
                padding: "11px 16px",
                borderBottom: i < historico.length-1 ? "1px solid var(--border-default)" : "none",
                gap: 8,
                alignItems: "center",
                background: "var(--bg-surface)",
              }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>{p.nombre}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: p.score >= 80 ? "#b45309" : p.score >= 60 ? "var(--text-success)" : "var(--text-error)" }}>{p.score}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{p.total_solicitudes}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{p.total_oc_enviadas}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{p.tasa_respuesta}%</div>
                <div style={{ fontSize: 11, color: p.pct_precio_cumplido >= 80 ? "var(--text-success)" : "var(--text-error)" }}>{p.pct_precio_cumplido}%</div>
                <div style={{ fontSize: 11, color: p.pct_plazo_cumplido >= 80 ? "var(--text-success)" : "var(--text-error)" }}>{p.pct_plazo_cumplido}%</div>
              </div>
            ))}
          </>
        )}
      </div>
    </>
  );
}
