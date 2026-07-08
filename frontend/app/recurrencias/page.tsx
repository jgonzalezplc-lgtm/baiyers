"use client";
import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import dynamic from "next/dynamic";

const RecurrenciaModal = dynamic(() => import("@/components/RecurrenciaModal"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const FRECUENCIA_LABELS: Record<string, string> = {
  diaria: "Diaria",
  semanal: "Semanal",
  mensual: "Mensual",
  bimestral: "Bimestral",
  trimestral: "Trimestral",
  anual: "Anual",
};

interface Recurrencia {
  id: string;
  nombre: string;
  items: string;
  frecuencia: string;
  dia_ejecucion: number | null;
  proveedor_id: string | null;
  cotizar_antes: boolean;
  monto_maximo: number | null;
  dias_aviso: number;
  proxima_ejecucion: string | null;
  activa: boolean;
  proveedores?: { nombre: string } | null;
}

export default function RecurrenciasPage() {
  const [recurrencias, setRecurrencias] = useState<Recurrencia[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);
  const [modalAbierto, setModalAbierto] = useState(false);
  const [editando, setEditando] = useState<Recurrencia | null>(null);
  const [ejecutando, setEjecutando] = useState<string | null>(null);
  const [toast, setToast] = useState("");

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (data.user) {
        setUserId(data.user.id);
        cargar(data.user.id);
      }
    });
  }, []);

  const cargar = async (uid: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/recurrencias?user_id=${uid}`);
      if (res.ok) setRecurrencias(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  };

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(""), 3000); };

  const handleToggle = async (r: Recurrencia) => {
    if (!userId) return;
    try {
      const res = await fetch(`${API_URL}/api/recurrencias/${r.id}/toggle?user_id=${userId}`, { method: "PATCH" });
      if (res.ok) {
        const { activa } = await res.json();
        setRecurrencias(prev => prev.map(x => x.id === r.id ? { ...x, activa } : x));
        showToast(activa ? "Recurrencia activada" : "Recurrencia pausada");
      }
    } catch { showToast("Error actualizando"); }
  };

  const handleEliminar = async (r: Recurrencia) => {
    if (!userId || !confirm(`Eliminar "${r.nombre}"?`)) return;
    try {
      await fetch(`${API_URL}/api/recurrencias/${r.id}?user_id=${userId}`, { method: "DELETE" });
      setRecurrencias(prev => prev.filter(x => x.id !== r.id));
      showToast("Recurrencia eliminada");
    } catch { showToast("Error eliminando"); }
  };

  const handleEjecutar = async (r: Recurrencia) => {
    if (!userId) return;
    setEjecutando(r.id);
    try {
      const res = await fetch(`${API_URL}/api/recurrencias/${r.id}/ejecutar?user_id=${userId}`, { method: "POST" });
      const data = await res.json();
      showToast(data.resultado || "Ejecutada");
      cargar(userId);
    } catch { showToast("Error ejecutando"); }
    finally { setEjecutando(null); }
  };

  const handleGuardado = () => {
    setModalAbierto(false);
    setEditando(null);
    if (userId) cargar(userId);
    showToast("Recurrencia guardada");
  };

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
      <div style={{ marginBottom: 28 }}>
        <div className="section-rule" style={{ marginBottom: 16 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>
              AUTOMATIZACIÓN
            </span>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
              Recurrencias
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0 }}>Compras automáticas programadas.</p>
          </div>
          <button
            onClick={() => { setEditando(null); setModalAbierto(true); }}
            className="btn-swiss-primary"
          >
            + Nueva recurrencia
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {[1,2,3].map(i => (
            <div key={i} style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-default)",
              height: 100,
              opacity: 0.5,
            }} />
          ))}
        </div>
      ) : recurrencias.length === 0 ? (
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-default)",
          padding: "48px 20px",
          textAlign: "center",
        }}>
          <div className="section-rule" style={{ margin: "0 auto 16px" }} />
          <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 700, marginBottom: 8 }}>
            Sin compras recurrentes
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 20 }}>
            Automatiza tus compras periodicas — papel, insumos, materiales.
          </div>
          <button onClick={() => setModalAbierto(true)} className="btn-swiss-primary">
            Crear primera recurrencia
          </button>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border-default)" }}>
          {recurrencias.map((r, idx) => (
            <div key={r.id} style={{
              background: "var(--bg-surface)",
              borderBottom: idx < recurrencias.length - 1 ? "1px solid var(--border-default)" : "none",
              padding: "16px 20px",
              opacity: r.activa ? 1 : 0.6,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{r.nombre}</span>
                    <span className="label" style={{
                      color: "var(--text-muted)",
                      border: "1px solid var(--border-default)",
                      padding: "1px 6px",
                    }}>
                      {FRECUENCIA_LABELS[r.frecuencia] || r.frecuencia}
                    </span>
                    {!r.activa && (
                      <span className="label" style={{ color: "var(--text-muted)" }}>Pausada</span>
                    )}
                  </div>

                  <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 8 }}>
                    {r.items.split("\n").slice(0,2).join(" · ")}{r.items.split("\n").length > 2 ? " ···" : ""}
                  </div>

                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                    {r.proveedores?.nombre && (
                      <span className="label" style={{ color: "var(--accent)" }}>Proveedor: {r.proveedores.nombre}</span>
                    )}
                    {r.proxima_ejecucion && (
                      <span className="label" style={{ color: "var(--text-muted)" }}>
                        Proxima: {new Date(r.proxima_ejecucion).toLocaleDateString("es-CL")}
                      </span>
                    )}
                    {r.monto_maximo && (
                      <span className="label" style={{ color: "var(--text-muted)" }}>
                        Max: ${r.monto_maximo.toLocaleString("es-CL")}
                      </span>
                    )}
                    <span className="label" style={{ color: r.cotizar_antes ? "var(--text-success)" : "var(--accent)" }}>
                      {r.cotizar_antes ? "Cotiza antes" : "OC directa"}
                    </span>
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 6, flexShrink: 0 }}>
                  {/* Toggle */}
                  <button
                    onClick={() => handleToggle(r)}
                    style={{
                      width: 40, height: 22,
                      border: "none",
                      cursor: "pointer",
                      background: r.activa ? "var(--accent)" : "var(--border-default)",
                      position: "relative",
                      flexShrink: 0,
                    }}
                  >
                    <span style={{
                      position: "absolute",
                      top: 3,
                      left: r.activa ? 21 : 3,
                      width: 16,
                      height: 16,
                      background: "#fff",
                      transition: "left 0.15s",
                    }} />
                  </button>
                  <button
                    onClick={() => handleEjecutar(r)}
                    disabled={ejecutando === r.id}
                    className="btn-swiss-secondary"
                    style={{ fontSize: 10, padding: "4px 8px", whiteSpace: "nowrap" }}
                  >
                    {ejecutando === r.id ? "..." : "Ejecutar"}
                  </button>
                  <button
                    onClick={() => { setEditando(r); setModalAbierto(true); }}
                    className="btn-swiss-secondary"
                    style={{ fontSize: 10, padding: "4px 8px" }}
                  >
                    Editar
                  </button>
                  <button
                    onClick={() => handleEliminar(r)}
                    style={{
                      fontSize: 10,
                      color: "var(--text-error)",
                      background: "none",
                      border: "1px solid var(--border-accent)",
                      padding: "4px 8px",
                      cursor: "pointer",
                      fontFamily: "var(--font-mono)",
                      letterSpacing: "0.05em",
                    }}
                  >
                    Eliminar
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {(modalAbierto || editando) && userId && (
        <RecurrenciaModal
          userId={userId}
          recurrencia={editando}
          onGuardado={handleGuardado}
          onCerrar={() => { setModalAbierto(false); setEditando(null); }}
        />
      )}
    </>
  );
}
