"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import GanttChart from "@/components/GanttChart";
import { authFetch } from "@/lib/authFetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Proyecto {
  id: string;
  nombre: string;
  cliente: string | null;
  estado: string;
  monto_total: number;
  fecha_inicio: string | null;
  descripcion: string | null;
  created_at: string;
}

interface CotizacionItem {
  id: string;
  proveedor_nombre: string;
  precio_unitario: number;
  precio_total: number;
  plazo_entrega_dias: number | null;
  fuente: string;
  url: string | null;
}

interface ItemProyecto {
  id: string;
  item: string;
  descripcion: string | null;
  cantidad: number;
  unidad: string;
  categoria: string | null;
  orden: number;
  precio_unitario: number | null;
  precio_total: number | null;
  plazo_entrega_dias: number | null;
  proveedor_nombre: string | null;
  estado: string;
  cotizaciones: CotizacionItem[];
}

interface GanttItem {
  id: string;
  item: string;
  categoria: string | null;
  fecha_inicio: string;
  fecha_fin: string;
  plazo_dias: number;
  estado: string;
  offset_dias: number;
  total_dias: number;
}

interface LiquidezSemana {
  semana: string;
  fecha_inicio: string;
  fecha_fin: string;
  monto: number;
  items: string[];
  nivel: string;
}

const ESTADO_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  borrador:     { label: "Borrador",     color: "var(--n-600)", bg: "var(--n-600)22" },
  cotizando:    { label: "Cotizando...", color: "var(--warning)", bg: "var(--warning)22" },
  en_ejecucion: { label: "En ejecución", color: "var(--brand)", bg: "var(--brand)22" },
  completado:   { label: "Completado",   color: "var(--success)", bg: "var(--success)22" },
};

const NIVEL_COLOR: Record<string, string> = {
  verde:    "var(--success)",
  amarillo: "var(--warning)",
  rojo:     "var(--danger)",
};

const PIE_COLORS = ["var(--brand)", "var(--success)", "var(--warning)", "var(--danger)", "var(--brand-400)", "var(--brand-300)"];

export default function ProyectoDetallePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [userId, setUserId] = useState<string | null>(null);
  const [tab, setTab] = useState<"items" | "gantt" | "liquidez" | "resumen">("items");

  const [proyecto, setProyecto] = useState<Proyecto | null>(null);
  const [items, setItems] = useState<ItemProyecto[]>([]);
  const [gantt, setGantt] = useState<GanttItem[]>([]);
  const [liquidez, setLiquidez] = useState<LiquidezSemana[]>([]);
  const [loading, setLoading] = useState(true);
  const [emitiendo, setEmitiendo] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) setUserId(data.user.id);
    });
  }, []);

  useEffect(() => {
    if (!id || !userId) return;
    cargarProyecto();
  }, [id, userId]);

  const cargarProyecto = async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const [pRes, iRes] = await Promise.all([
        authFetch(`${API_URL}/api/proyectos/${id}`),
        authFetch(`${API_URL}/api/proyectos/${id}/items`),
      ]);
      if (pRes.ok) {
        const data = await pRes.json();
        setProyecto(data);
      }
      if (iRes.ok) setItems(await iRes.json());
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  };

  const cargarGantt = async () => {
    if (!userId) return;
    const res = await authFetch(`${API_URL}/api/proyectos/${id}/gantt`);
    if (res.ok) setGantt(await res.json());
  };

  const cargarLiquidez = async () => {
    if (!userId) return;
    const res = await authFetch(`${API_URL}/api/proyectos/${id}/liquidez`);
    if (res.ok) setLiquidez(await res.json());
  };

  useEffect(() => {
    if (!userId) return;
    if (tab === "gantt" && gantt.length === 0) cargarGantt();
    if (tab === "liquidez" && liquidez.length === 0) cargarLiquidez();
  }, [tab, userId]);

  const handleSelectProveedor = async (itemId: string, cotizacionId: string) => {
    await authFetch(`${API_URL}/api/proyectos/${id}/items/${itemId}/seleccionar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cotizacion_id: cotizacionId }),
    });
    cargarProyecto();
  };

  const handleEmitirOCs = async () => {
    if (!userId) return;
    setEmitiendo(true);
    setError("");
    try {
      const res = await authFetch(`${API_URL}/api/proyectos/${id}/emitir-ocs`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      router.push("/oc");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error emitiendo OCs");
    } finally {
      setEmitiendo(false);
    }
  };

  const montoTotal = items.reduce((s, it) => s + (it.precio_total || 0), 0);
  const itemsCotizados = items.filter(it => it.precio_total != null).length;

  const tabStyle = (t: string) => ({
    padding: "8px 18px",
    fontSize: 11,
    fontWeight: tab === t ? 700 : 400,
    background: tab === t ? "var(--brand)" : "none",
    color: tab === t ? "#fff" : "var(--n-600)",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontFamily: "inherit",
  });

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 12, color: "var(--n-600)" }}>Cargando proyecto...</div>
      </div>
    );
  }

  if (!proyecto) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 12, color: "var(--danger)" }}>Proyecto no encontrado</div>
      </div>
    );
  }

  const cfg = ESTADO_CONFIG[proyecto.estado] ?? ESTADO_CONFIG.borrador;

  // Category breakdown for pie chart
  const categorias: Record<string, number> = {};
  for (const it of items) {
    if (it.precio_total) {
      const cat = it.categoria || "Sin categoría";
      categorias[cat] = (categorias[cat] || 0) + it.precio_total;
    }
  }
  const pieData = Object.entries(categorias).map(([name, value]) => ({ name, value: Math.round(value) }));

  // Unique providers
  const proveedores = Array.from(new Set(items.map(it => it.proveedor_nombre).filter((n): n is string => !!n)));

  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)", padding: "24px 20px" }}>
      <div style={{ maxWidth: 960, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <Link href="/proyectos" style={{ fontSize: 10, color: "var(--n-600)", textDecoration: "none" }}>← Proyectos</Link>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginTop: 8 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                <h1 style={{ fontSize: 20, fontWeight: 800, color: "var(--n-900)", margin: 0 }}>{proyecto.nombre}</h1>
                <span style={{ fontSize: 10, fontWeight: 700, color: cfg.color, background: cfg.bg, padding: "3px 8px", borderRadius: 20 }}>{cfg.label}</span>
              </div>
              {proyecto.cliente && <div style={{ fontSize: 11, color: "var(--n-600)" }}>{proyecto.cliente}</div>}
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: montoTotal > 0 ? "var(--brand)" : "var(--n-700)" }}>
                {montoTotal > 0 ? `$${Math.round(montoTotal).toLocaleString("es-CL")}` : "Sin cotizar"}
              </div>
              <div style={{ fontSize: 10, color: "var(--n-600)" }}>{itemsCotizados}/{items.length} ítems cotizados</div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, marginBottom: 20, background: "var(--surface)", padding: 4, borderRadius: 8, width: "fit-content" }}>
          {(["items", "gantt", "liquidez", "resumen"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={tabStyle(t)}>
              {t === "items" ? "Ítems" : t === "gantt" ? "Carta Gantt" : t === "liquidez" ? "Liquidez" : "Resumen"}
            </button>
          ))}
        </div>

        {error && (
          <div style={{ background: "var(--st-rechazada-bg)", border: "1px solid var(--danger)33", borderRadius: 8, padding: "10px 14px", fontSize: 11, color: "var(--danger)", marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* ── TAB ÍTEMS ──────────────────────────────────────────────────────── */}
        {tab === "items" && (
          <div>
            <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 10, overflow: "hidden" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    {["#", "Ítem", "Cantidad", "Proveedor seleccionado", "P. Unit.", "P. Total", "Plazo"].map(h => (
                      <th key={h} style={{ padding: "10px 12px", borderBottom: "1px solid var(--n-200)", textAlign: "left", color: "var(--n-600)", fontSize: 9 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, i) => (
                    <tr key={it.id} style={{ borderBottom: i < items.length - 1 ? "1px solid var(--surface-2)" : "none" }}>
                      <td style={{ padding: "10px 12px", color: "var(--n-700)", fontWeight: 700 }}>{i + 1}</td>
                      <td style={{ padding: "10px 12px" }}>
                        <div style={{ fontWeight: 600, color: "var(--n-900)" }}>{it.item}</div>
                        {it.descripcion && <div style={{ fontSize: 10, color: "var(--n-600)", marginTop: 2 }}>{it.descripcion}</div>}
                        {it.categoria && <span style={{ fontSize: 9, color: "var(--brand)", background: "var(--brand)11", padding: "1px 6px", borderRadius: 10, marginTop: 3, display: "inline-block" }}>{it.categoria}</span>}
                      </td>
                      <td style={{ padding: "10px 12px", color: "var(--n-500)" }}>{it.cantidad} {it.unidad}</td>
                      <td style={{ padding: "10px 12px", minWidth: 200 }}>
                        {it.cotizaciones.length > 0 ? (
                          <select
                            value={it.cotizaciones.find(c => c.proveedor_nombre === it.proveedor_nombre)?.id || ""}
                            onChange={e => e.target.value && handleSelectProveedor(it.id, e.target.value)}
                            style={{ background: "var(--canvas)", border: "1px solid var(--n-200)", borderRadius: 4, color: "var(--n-900)", fontSize: 11, padding: "4px 8px", width: "100%", fontFamily: "inherit", cursor: "pointer" }}
                          >
                            <option value="">— Sin seleccionar,</option>
                            {it.cotizaciones.map(c => (
                              <option key={c.id} value={c.id}>
                                {c.proveedor_nombre}, ${Math.round(c.precio_unitario).toLocaleString("es-CL")} ({c.plazo_entrega_dias || "?"} días)
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span style={{ color: "var(--n-700)" }}>Sin cotizaciones</span>
                        )}
                      </td>
                      <td style={{ padding: "10px 12px", color: it.precio_unitario ? "var(--n-900)" : "var(--n-700)", fontWeight: 600 }}>
                        {it.precio_unitario ? `$${Math.round(it.precio_unitario).toLocaleString("es-CL")}` : "—"}
                      </td>
                      <td style={{ padding: "10px 12px", color: it.precio_total ? "var(--brand)" : "var(--n-700)", fontWeight: 700 }}>
                        {it.precio_total ? `$${Math.round(it.precio_total).toLocaleString("es-CL")}` : "—"}
                      </td>
                      <td style={{ padding: "10px 12px", color: "var(--n-500)" }}>
                        {it.plazo_entrega_dias ? `${it.plazo_entrega_dias}d` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Footer */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16, padding: "12px 16px", background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 8 }}>
              <div>
                <span style={{ fontSize: 11, color: "var(--n-600)" }}>Total: </span>
                <span style={{ fontSize: 18, fontWeight: 800, color: "var(--brand)" }}>${Math.round(montoTotal).toLocaleString("es-CL")}</span>
                <span style={{ fontSize: 10, color: "var(--n-600)", marginLeft: 8 }}>CLP</span>
              </div>
              <button
                onClick={handleEmitirOCs}
                disabled={emitiendo || itemsCotizados === 0}
                style={{ padding: "10px 24px", fontWeight: 700, fontSize: 11, background: emitiendo || itemsCotizados === 0 ? "var(--n-200)" : "var(--brand)", color: emitiendo || itemsCotizados === 0 ? "var(--n-600)" : "#fff", border: "none", borderRadius: 6, cursor: emitiendo || itemsCotizados === 0 ? "not-allowed" : "pointer", fontFamily: "inherit" }}
              >
                {emitiendo ? "Emitiendo..." : `Emitir ${itemsCotizados} OCs →`}
              </button>
            </div>
          </div>
        )}

        {/* ── TAB GANTT (dinámico, 3 escenarios) ─────────────────────────────── */}
        {tab === "gantt" && userId && (
          <GanttChart proyectoId={id} userId={userId} />
        )}

        {/* ── TAB LIQUIDEZ ───────────────────────────────────────────────────── */}
        {tab === "liquidez" && (
          <div>
            {liquidez.length === 0 ? (
              <div style={{ textAlign: "center", padding: "48px 20px", color: "var(--n-600)", fontSize: 12 }}>
                Sin datos de liquidez, cotiza primero los ítems del proyecto.
              </div>
            ) : (
              <div>
                {liquidez.some(s => s.nivel === "rojo") && (
                  <div style={{ background: "var(--st-rechazada-bg)", border: "1px solid var(--danger)33", borderRadius: 8, padding: "10px 14px", fontSize: 11, color: "var(--danger)", marginBottom: 16 }}>
                    Alerta: hay semanas con compromisos superiores al 40% del presupuesto total.
                  </div>
                )}

                <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 10, padding: "20px 16px", marginBottom: 16 }}>
                  <div style={{ fontSize: 11, color: "var(--n-600)", marginBottom: 12 }}>Flujo de pagos semanal (CLP)</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={liquidez} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                      <XAxis dataKey="semana" tick={{ fontSize: 9, fill: "var(--n-600)" }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 9, fill: "var(--n-600)" }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v / 1000000).toFixed(1)}M`} />
                      <Tooltip
                        contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--n-200)", borderRadius: 6, fontSize: 11 }}
                        formatter={(v: number) => [`$${Math.round(v).toLocaleString("es-CL")}`, "Monto"]}
                      />
                      <Bar dataKey="monto" radius={[4, 4, 0, 0]}>
                        {liquidez.map((s, i) => (
                          <Cell key={i} fill={NIVEL_COLOR[s.nivel] || "var(--brand)"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 10, overflow: "hidden" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr style={{ background: "var(--surface-2)" }}>
                        {["Semana", "Período", "Monto", "Nivel", "Ítems"].map(h => (
                          <th key={h} style={{ padding: "8px 12px", borderBottom: "1px solid var(--n-200)", textAlign: "left", color: "var(--n-600)", fontSize: 9 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {liquidez.map((s, i) => (
                        <tr key={i} style={{ borderBottom: i < liquidez.length - 1 ? "1px solid var(--surface-2)" : "none" }}>
                          <td style={{ padding: "8px 12px", color: "var(--n-500)", fontWeight: 700 }}>{s.semana}</td>
                          <td style={{ padding: "8px 12px", color: "var(--n-600)", fontSize: 10 }}>
                            {new Date(s.fecha_inicio + "T12:00:00").toLocaleDateString("es-CL", { day: "2-digit", month: "short" })},{" "}
                            {new Date(s.fecha_fin + "T12:00:00").toLocaleDateString("es-CL", { day: "2-digit", month: "short" })}
                          </td>
                          <td style={{ padding: "8px 12px", color: NIVEL_COLOR[s.nivel] || "var(--n-900)", fontWeight: 700 }}>
                            ${Math.round(s.monto).toLocaleString("es-CL")}
                          </td>
                          <td style={{ padding: "8px 12px" }}>
                            <span style={{ fontSize: 9, fontWeight: 700, color: NIVEL_COLOR[s.nivel], background: `${NIVEL_COLOR[s.nivel]}22`, padding: "2px 8px", borderRadius: 10 }}>
                              {s.nivel}
                            </span>
                          </td>
                          <td style={{ padding: "8px 12px", color: "var(--n-600)", fontSize: 10 }}>
                            {s.items.slice(0, 2).join(", ")}{s.items.length > 2 ? ` +${s.items.length - 2}` : ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── TAB RESUMEN ────────────────────────────────────────────────────── */}
        {tab === "resumen" && (
          <div>
            {/* KPIs */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
              {[
                { label: "Monto Total", value: `$${Math.round(montoTotal).toLocaleString("es-CL")}`, color: "var(--brand)" },
                { label: "Ítems", value: `${itemsCotizados}/${items.length}`, color: "var(--success)" },
                { label: "Plazo máximo", value: `${Math.max(...items.map(it => it.plazo_entrega_dias || 0), 0)}d`, color: "var(--warning)" },
                { label: "Proveedores", value: `${proveedores.length}`, color: "var(--brand-400)" },
              ].map(k => (
                <div key={k.label} style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 8, padding: "14px 16px" }}>
                  <div style={{ fontSize: 9, color: "var(--n-600)", letterSpacing: "0.1em", marginBottom: 6 }}>{k.label}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: k.color }}>{k.value}</div>
                </div>
              ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
              {/* Pie by category */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 10, padding: "16px" }}>
                <div style={{ fontSize: 11, color: "var(--n-600)", marginBottom: 12 }}>Por categoría</div>
                {pieData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false} style={{ fontSize: 9 }}>
                        {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Tooltip contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--n-200)", borderRadius: 6, fontSize: 11 }} formatter={(v: number) => [`$${Math.round(v).toLocaleString("es-CL")}`, ""]} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ fontSize: 11, color: "var(--n-700)", textAlign: "center", paddingTop: 40 }}>Sin datos</div>
                )}
              </div>

              {/* Providers breakdown */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 10, padding: "16px" }}>
                <div style={{ fontSize: 11, color: "var(--n-600)", marginBottom: 12 }}>Proveedores seleccionados</div>
                <div style={{ maxHeight: 180, overflowY: "auto" }}>
                  {proveedores.map(prov => {
                    const provItems = items.filter(it => it.proveedor_nombre === prov);
                    const subtotal = provItems.reduce((s, it) => s + (it.precio_total || 0), 0);
                    return (
                      <div key={prov} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--surface-2)" }}>
                        <div>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--n-900)" }}>{prov}</div>
                          <div style={{ fontSize: 9, color: "var(--n-600)" }}>{provItems.length} ítem{provItems.length !== 1 ? "s" : ""}</div>
                        </div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--brand)" }}>${Math.round(subtotal).toLocaleString("es-CL")}</div>
                      </div>
                    );
                  })}
                  {proveedores.length === 0 && (
                    <div style={{ fontSize: 11, color: "var(--n-700)" }}>Sin proveedores seleccionados</div>
                  )}
                </div>
              </div>
            </div>

            {/* Project info */}
            <div style={{ background: "var(--surface)", border: "1px solid var(--n-200)", borderRadius: 10, padding: "16px", marginBottom: 16 }}>
              <div style={{ fontSize: 11, color: "var(--n-600)", marginBottom: 10 }}>Información del proyecto</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 9, color: "var(--n-600)", marginBottom: 4 }}>Creado</div>
                  <div style={{ fontSize: 11, color: "var(--n-500)" }}>{new Date(proyecto.created_at).toLocaleDateString("es-CL")}</div>
                </div>
                {proyecto.fecha_inicio && (
                  <div>
                    <div style={{ fontSize: 9, color: "var(--n-600)", marginBottom: 4 }}>Inicio estimado</div>
                    <div style={{ fontSize: 11, color: "var(--n-500)" }}>{new Date(proyecto.fecha_inicio + "T12:00:00").toLocaleDateString("es-CL")}</div>
                  </div>
                )}
                {proyecto.cliente && (
                  <div>
                    <div style={{ fontSize: 9, color: "var(--n-600)", marginBottom: 4 }}>Cliente</div>
                    <div style={{ fontSize: 11, color: "var(--n-500)" }}>{proyecto.cliente}</div>
                  </div>
                )}
              </div>
              {proyecto.descripcion && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--n-200)" }}>
                  <div style={{ fontSize: 9, color: "var(--n-600)", marginBottom: 4 }}>Descripción</div>
                  <div style={{ fontSize: 11, color: "var(--n-500)" }}>{proyecto.descripcion}</div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => {
                  authFetch(`${API_URL}/api/reportes/exportar-excel`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ proyecto_id: id, titulo: proyecto.nombre }),
                  }).then(r => r.blob()).then(blob => {
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `reporte_${proyecto.nombre.replace(/\s+/g, "_")}.xlsx`;
                    a.click();
                    URL.revokeObjectURL(url);
                  });
                }}
                style={{ padding: "10px 20px", fontSize: 11, fontWeight: 700, background: "var(--success)11", border: "1px solid var(--success)33", color: "var(--success)", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" }}
              >
                Exportar Excel
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
