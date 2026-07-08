"use client";
import { useState, useEffect } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface HistorialEntry {
  fecha: string;
  precio_clp: number;
  proveedor: string;
  moneda: string;
}

interface HistorialData {
  sin_historial: boolean;
  precio_min?: number;
  precio_max?: number;
  precio_promedio?: number;
  total_compras?: number;
  ultima_compra?: string;
  tendencia?: string;
  historial?: HistorialEntry[];
  mejor_proveedor?: string;
}

interface Props {
  itemNombre: string;
  precioActual?: number;
  userId: string;
  onClose: () => void;
}

const TENDENCIA_CONFIG = {
  subiendo: { label: "Subiendo", color: "var(--text-error)" },
  bajando:  { label: "Bajando",  color: "var(--text-success)" },
  estable:  { label: "Estable",  color: "var(--text-secondary)" },
};

export default function HistorialPrecioModal({ itemNombre, precioActual, userId, onClose }: Props) {
  const [data, setData] = useState<HistorialData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/api/historico/item?item_nombre=${encodeURIComponent(itemNombre)}&user_id=${userId}`)
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => setData({ sin_historial: true }))
      .finally(() => setLoading(false));
  }, [itemNombre, userId]);

  const chartData = (data?.historial || []).map((h, i) => ({
    name: h.fecha ? new Date(h.fecha + "T12:00:00").toLocaleDateString("es-CL", { day: "2-digit", month: "short" }) : `#${i + 1}`,
    precio: Math.round(h.precio_clp),
    proveedor: h.proveedor,
  }));

  const tend = data?.tendencia ? TENDENCIA_CONFIG[data.tendencia as keyof typeof TENDENCIA_CONFIG] : null;

  const tooltipStyle = {
    background: "var(--bg-inverse)",
    border: "none",
    fontSize: 10,
    color: "var(--text-inverse)",
    fontFamily: "var(--font-mono)",
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.6)",
        zIndex: 200,
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        width: "100%", maxWidth: 680,
        maxHeight: "85vh",
        overflow: "auto",
      }}>
        {/* Header */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-default)", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <span className="label" style={{ color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Historial de precios</span>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>{itemNombre}</div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", fontSize: 18, cursor: "pointer", padding: 4 }}>×</button>
        </div>

        <div style={{ padding: "20px" }}>
          {loading && (
            <div style={{ textAlign: "center", padding: "32px 0", color: "var(--text-muted)", fontSize: 12 }}>
              Cargando historial...
            </div>
          )}

          {!loading && data?.sin_historial && (
            <div style={{ textAlign: "center", padding: "32px 0" }}>
              <div className="section-rule" style={{ margin: "0 auto 16px" }} />
              <div style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 700, marginBottom: 6 }}>
                Primera cotizacion de este item
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>No hay historial de precios previo para comparar.</div>
            </div>
          )}

          {!loading && data && !data.sin_historial && (
            <>
              {/* KPIs */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 1, marginBottom: 20, border: "1px solid var(--border-default)" }}>
                {[
                  { label: "Promedio", value: `$${(data.precio_promedio || 0).toLocaleString("es-CL")}`, color: "var(--accent)" },
                  { label: "Minimo", value: `$${(data.precio_min || 0).toLocaleString("es-CL")}`, color: "var(--text-success)" },
                  { label: "Maximo", value: `$${(data.precio_max || 0).toLocaleString("es-CL")}`, color: "var(--text-error)" },
                  { label: "N compras", value: String(data.total_compras || 0), color: "var(--text-secondary)" },
                ].map((k, i) => (
                  <div key={k.label} style={{
                    background: "var(--bg-surface)",
                    borderRight: i < 3 ? "1px solid var(--border-default)" : "none",
                    padding: "10px 12px",
                  }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: k.color, letterSpacing: "-0.01em" }}>{k.value}</div>
                    <div className="label" style={{ color: "var(--text-muted)", marginTop: 2 }}>{k.label}</div>
                  </div>
                ))}
              </div>

              {/* Meta info */}
              <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
                {tend && (
                  <span className="label" style={{ color: tend.color }}>
                    {tend.label.toUpperCase()}
                  </span>
                )}
                {data.mejor_proveedor && (
                  <span className="label" style={{ color: "var(--text-muted)" }}>
                    Mejor proveedor: <strong style={{ color: "var(--text-primary)" }}>{data.mejor_proveedor}</strong>
                  </span>
                )}
                {data.ultima_compra && (
                  <span className="label" style={{ color: "var(--text-muted)" }}>
                    Ultima compra: <strong style={{ color: "var(--text-primary)" }}>{new Date(data.ultima_compra + "T12:00:00").toLocaleDateString("es-CL")}</strong>
                  </span>
                )}
              </div>

              {/* Line chart */}
              {chartData.length > 1 && (
                <div style={{ background: "var(--bg-base)", border: "1px solid var(--border-default)", padding: "16px 8px", marginBottom: 16 }}>
                  <div className="label" style={{ color: "var(--text-muted)", marginBottom: 10, paddingLeft: 8 }}>
                    Evolucion de precios (CLP)
                  </div>
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={chartData}>
                      <XAxis dataKey="name" tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 9, fill: "var(--text-muted)" as string }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                      <Tooltip
                        contentStyle={tooltipStyle}
                        formatter={(v: number, _: string, props) => [`$${v.toLocaleString("es-CL")}`, props.payload?.proveedor || ""]}
                      />
                      {data.precio_promedio && (
                        <ReferenceLine y={data.precio_promedio} stroke="var(--accent)" strokeDasharray="4 4" label={{ value: "Promedio", fontSize: 9, fill: "var(--accent)" }} />
                      )}
                      {precioActual && (
                        <ReferenceLine y={precioActual} stroke="var(--text-warning)" strokeDasharray="4 4" label={{ value: "Actual", fontSize: 9, fill: "var(--text-warning)" }} />
                      )}
                      <Line type="monotone" dataKey="precio" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3, fill: "var(--accent)" }} activeDot={{ r: 5 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Detail table */}
              {data.historial && data.historial.length > 0 && (
                <div style={{ border: "1px solid var(--border-default)", overflow: "hidden" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr style={{ background: "var(--bg-surface)" }}>
                        {["Fecha", "Proveedor", "Precio CLP"].map(h => (
                          <th key={h} className="label" style={{ padding: "7px 12px", borderBottom: "1px solid var(--border-default)", textAlign: "left", color: "var(--text-muted)" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.historial.map((h, i) => (
                        <tr key={i} style={{ background: "var(--bg-surface)", borderBottom: i < data.historial!.length - 1 ? "1px solid var(--border-default)" : "none" }}>
                          <td style={{ padding: "6px 12px", color: "var(--text-secondary)" }}>
                            {h.fecha ? new Date(h.fecha + "T12:00:00").toLocaleDateString("es-CL") : "—"}
                          </td>
                          <td style={{ padding: "6px 12px", color: "var(--text-secondary)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {h.proveedor || "—"}
                          </td>
                          <td style={{ padding: "6px 12px", color: "var(--text-primary)", fontWeight: 700 }}>
                            ${Math.round(h.precio_clp).toLocaleString("es-CL")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
