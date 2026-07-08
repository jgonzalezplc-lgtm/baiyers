"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type EstadoFiltro = "todas" | "pendiente" | "pagada" | "vencida";

interface Factura {
  id: string;
  proveedor_nombre: string;
  numero_factura: string | null;
  fecha_factura: string | null;
  fecha_vencimiento: string | null;
  monto_total: number;
  moneda: string;
  estado: string;
  fecha_pago: string | null;
  oc_id: string | null;
}

const ESTADO_CONFIG: Record<string, { label: string; color: string }> = {
  pendiente: { label: "Pendiente", color: "var(--text-secondary)" },
  pagada:    { label: "Pagada",    color: "var(--text-success)" },
  vencida:   { label: "Vencida",   color: "var(--text-error)" },
};

function diasParaVencer(fecha: string | null): number | null {
  if (!fecha) return null;
  const hoy = new Date();
  hoy.setHours(0,0,0,0);
  const venc = new Date(fecha + "T00:00:00");
  return Math.ceil((venc.getTime() - hoy.getTime()) / (1000*60*60*24));
}

export default function FacturasPage() {
  const [facturas, setFacturas] = useState<Factura[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);
  const [filtroEstado, setFiltroEstado] = useState<EstadoFiltro>("todas");
  const [pagandoId, setPagandoId] = useState<string | null>(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [resumen, setResumen] = useState({ total_pendiente: 0, total_pagado_mes: 0, total_vencido: 0 });

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) {
        setUserId(data.user.id);
        cargar(data.user.id);
        cargarResumen(data.user.id);
      }
    });
  }, []);

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(""), 3000); };

  const cargar = async (uid: string, estado?: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ user_id: uid });
      if (estado && estado !== "todas") params.append("estado", estado);
      const res = await fetch(`${API_URL}/api/facturas?${params}`);
      if (res.ok) setFacturas(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  };

  const cargarResumen = async (uid: string) => {
    try {
      const res = await fetch(`${API_URL}/api/facturas/resumen?user_id=${uid}`);
      if (res.ok) setResumen(await res.json());
    } catch { /* silent */ }
  };

  const handleFiltro = (estado: EstadoFiltro) => {
    setFiltroEstado(estado);
    if (userId) cargar(userId, estado);
  };

  const handlePagar = async (f: Factura) => {
    if (!userId) return;
    setPagandoId(f.id);
    try {
      const res = await fetch(`${API_URL}/api/facturas/${f.id}/pagar?user_id=${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fecha_pago: new Date().toISOString().slice(0,10) }),
      });
      if (res.ok) {
        showToast("Factura marcada como pagada");
        cargar(userId, filtroEstado);
        cargarResumen(userId);
      }
    } catch { showToast("Error actualizando"); }
    finally { setPagandoId(null); }
  };

  const handleScan = async () => {
    if (!userId) return;
    setScanLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/facturas/scan-inbox?user_id=${userId}`, { method: "POST" });
      if (res.ok) {
        const { facturas_encontradas } = await res.json();
        showToast(facturas_encontradas > 0 ? `${facturas_encontradas} factura(s) encontrada(s)` : "Sin facturas nuevas en inbox");
        cargar(userId, filtroEstado);
        cargarResumen(userId);
      }
    } catch { showToast("Error escaneando inbox"); }
    finally { setScanLoading(false); }
  };

  const hayVencidas = facturas.some(f => f.estado === "vencida");
  const fmt = (n: number) => `$${Math.round(n).toLocaleString("es-CL")}`;

  return (
    <>
      {toast && (
        <div style={{
          position: "fixed", top: 20, right: 20,
          background: "var(--bg-inverse)",
          padding: "12px 18px",
          fontSize: 11,
          color: "var(--text-inverse)",
          fontWeight: 700,
          zIndex: 100,
          fontFamily: "var(--font-mono)",
        }}>{toast}</div>
      )}

      {/* Page header */}
      <div style={{ marginBottom: 20 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
              DOCUMENTOS
            </span>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              Facturas
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Gestión de facturas y pagos.</p>
          </div>
          <button
            onClick={handleScan}
            disabled={scanLoading}
            className={scanLoading ? "btn-swiss-secondary" : "btn-swiss-primary"}
          >
            {scanLoading ? "Escaneando..." : "Escanear inbox Gmail"}
          </button>
        </div>
      </div>

      {/* Alerta vencidas */}
      {hayVencidas && (
        <div style={{
          background: "var(--fill-error)",
          border: "1px solid var(--border-accent)",
          padding: "12px 16px",
          marginBottom: 16,
          fontSize: 11,
          color: "var(--text-error)",
          fontWeight: 600,
        }}>
          Tienes facturas vencidas sin pagar. Revisa la tabla abajo.
        </div>
      )}

      {/* KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", border: "1px solid var(--border-default)", marginBottom: 20 }}>
        {[
          { label: "Pendiente de pago", val: fmt(resumen.total_pendiente), color: resumen.total_vencido > 0 ? "var(--text-error)" : "var(--text-secondary)" },
          { label: "Pagado este mes", val: fmt(resumen.total_pagado_mes), color: "var(--text-success)" },
          { label: "Vencido sin pagar", val: fmt(resumen.total_vencido), color: resumen.total_vencido > 0 ? "var(--text-error)" : "var(--text-muted)" },
        ].map((k, i) => (
          <div key={k.label} style={{
            background: "var(--bg-surface)",
            borderRight: i < 2 ? "1px solid var(--border-default)" : "none",
            padding: "14px 16px",
          }}>
            <div className="label" style={{ color: "var(--text-muted)", marginBottom: 4 }}>{k.label}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: k.color, letterSpacing: "-0.02em" }}>{k.val}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{ display: "flex", gap: 1, marginBottom: 16, border: "1px solid var(--border-default)", width: "fit-content" }}>
        {(["todas","pendiente","pagada","vencida"] as EstadoFiltro[]).map(e => (
          <button
            key={e}
            onClick={() => handleFiltro(e)}
            className="label"
            style={{
              padding: "6px 14px",
              border: "none",
              borderRight: e !== "vencida" ? "1px solid var(--border-default)" : "none",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              background: filtroEstado === e ? "var(--bg-inverse)" : "var(--bg-surface)",
              color: filtroEstado === e ? "var(--text-inverse)" : "var(--text-muted)",
            }}
          >
            {e === "todas" ? "TODAS" : (ESTADO_CONFIG[e]?.label || e).toUpperCase()}
          </button>
        ))}
      </div>

      {/* Tabla */}
      {loading ? (
        <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", padding: 40 }}>Cargando...</div>
      ) : facturas.length === 0 ? (
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-default)",
          padding: "40px 20px",
          textAlign: "center",
        }}>
          <div className="section-rule" style={{ margin: "0 auto 16px" }} />
          <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 700, marginBottom: 8 }}>Sin facturas</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
            Usa "Escanear inbox Gmail" para detectar facturas automaticamente.
          </div>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border-default)" }}>
          {/* Header tabla */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "2fr 1fr 1fr 1fr 1.2fr 1fr",
            padding: "10px 16px",
            borderBottom: "1px solid var(--border-default)",
            gap: 8,
            background: "var(--bg-surface)",
          }}>
            {["Proveedor", "N Factura", "Fecha", "Vencimiento", "Monto", "Estado"].map(h => (
              <div key={h} className="label" style={{ color: "var(--text-muted)" }}>{h}</div>
            ))}
          </div>

          {facturas.map((f, i) => {
            const dias = f.fecha_vencimiento ? diasParaVencer(f.fecha_vencimiento) : null;
            const config = ESTADO_CONFIG[f.estado] ?? ESTADO_CONFIG.pendiente;
            const porVencer = f.estado !== "pagada" && dias !== null && dias >= 0 && dias <= 7;

            return (
              <div key={f.id} style={{
                display: "grid",
                gridTemplateColumns: "2fr 1fr 1fr 1fr 1.2fr 1fr",
                padding: "12px 16px",
                borderBottom: i < facturas.length-1 ? "1px solid var(--border-default)" : "none",
                gap: 8,
                alignItems: "center",
                background: f.estado === "vencida" ? "var(--fill-error)" : "var(--bg-surface)",
              }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>{f.proveedor_nombre}</div>
                  {f.oc_id && <div className="label" style={{ color: "var(--accent)" }}>Ver OC</div>}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{f.numero_factura || "—"}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  {f.fecha_factura ? new Date(f.fecha_factura + "T12:00:00").toLocaleDateString("es-CL", { day:"2-digit", month:"2-digit" }) : "—"}
                </div>
                <div>
                  <div style={{ fontSize: 11, color: porVencer ? "var(--text-warning)" : f.estado === "vencida" ? "var(--text-error)" : "var(--text-secondary)" }}>
                    {f.fecha_vencimiento ? new Date(f.fecha_vencimiento + "T12:00:00").toLocaleDateString("es-CL", { day:"2-digit", month:"2-digit" }) : "—"}
                  </div>
                  {porVencer && <div className="label" style={{ color: "var(--text-warning)" }}>Vence en {dias}d</div>}
                  {f.estado === "vencida" && dias !== null && dias < 0 && <div className="label" style={{ color: "var(--text-error)" }}>Hace {Math.abs(dias)}d</div>}
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>
                  {f.moneda} {Math.round(f.monto_total).toLocaleString("es-CL")}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="label" style={{ color: config.color }}>{config.label.toUpperCase()}</span>
                  {f.estado !== "pagada" && (
                    <button
                      onClick={() => handlePagar(f)}
                      disabled={pagandoId === f.id}
                      style={{
                        fontSize: 9,
                        color: "var(--text-success)",
                        background: "var(--fill-success)",
                        border: "1px solid var(--palette-green-500)",
                        padding: "2px 6px",
                        cursor: "pointer",
                        fontFamily: "var(--font-mono)",
                        whiteSpace: "nowrap",
                        letterSpacing: "0.05em",
                      }}
                    >
                      {pagandoId === f.id ? "..." : "PAGAR"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
